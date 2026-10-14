"""Scoring stage: enrollment, per-window scoring, trust updates, freshness."""

import numpy as np
import pytest

from ml.trust import FRESH_S
from server.features.schemas import KF1_NAMES, PF1_NAMES
from server.worker.scoring import TrustScorer, device_key
from server.worker.store import UserContext, WindowRecord


class FakeStore:
    def __init__(self):
        self.windows = {}  # (user, channel, device_key) -> list of (values, quality)
        self.profiles = {}
        self.points = []
        self.saves = 0

    def add_window(self, user, channel, device, values, quality=1.0):
        self.windows.setdefault((user, channel, device_key(channel, device)), []).append((list(values), quality))

    def active_profile(self, user_id, channel, dkey):
        return self.profiles.get((user_id, channel, dkey))

    def enrollment_windows(self, user_id, channel, dkey, limit):
        return self.windows.get((user_id, channel, dkey), [])[:limit]

    def save_profile(self, user_id, channel, dkey, template):
        self.saves += 1
        self.profiles[(user_id, channel, dkey)] = template
        return True

    def insert_trust_point(self, update):
        self.points.append(update)


class FakePublisher:
    def __init__(self):
        self.sent = []

    def publish(self, update):
        self.sent.append(update)


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


def rec(user, session, channel="keystroke", device="mouse", wid="00000000-0000-0000-0000-000000000001"):
    schema = {"keystroke": "kf-1", "pointer": "pf-1", "interaction": "if-1"}[channel]
    return WindowRecord(window_id=wid, session_id=session, stream_id="st", user_id=user, channel=channel,
                        pointer_device=device, schema=schema, start_t=0.0, end_t=1.0, n_actions=50,
                        quality=1.0, features_enc=b"", extractor_version="x")


def genuine(n, width, seed=0):
    rng = np.random.default_rng(seed)
    return rng.normal(loc=np.arange(1, width + 1) * 10.0, scale=np.arange(1, width + 1), size=(n, width))


@pytest.fixture
def parts():
    store, pub, clock = FakeStore(), FakePublisher(), Clock()
    return store, pub, clock, TrustScorer(store, pub, enroll_windows=8, clock=clock)


CTX = UserContext("u1", (), False)


def test_before_enrollment_the_channel_has_no_profile(parts):
    store, pub, clock, scorer = parts
    x = genuine(1, len(KF1_NAMES))[0]
    store.add_window("u1", "keystroke", "mouse", x)
    u = scorer.on_window(CTX, rec("u1", "s1"), x.tolist())
    assert u["state"] == "insufficient_signal" and u["trust"] is None
    assert u["channels"]["keystroke"]["status"] == "no_profile"
    assert store.points == [u] and pub.sent == [u]
    assert store.saves == 0


def test_enrollment_trains_once_then_windows_are_scored(parts):
    store, pub, clock, scorer = parts
    X = genuine(12, len(KF1_NAMES))
    for i in range(8):
        store.add_window("u1", "keystroke", "mouse", X[i])
        scorer.on_window(CTX, rec("u1", "s1"), X[i].tolist())
    assert store.saves == 1
    t = store.profiles[("u1", "keystroke", "any")]
    assert t["n_windows"] == 8 and t["channel"] == "keystroke"
    clock.t += 5
    u = scorer.on_window(CTX, rec("u1", "s1"), X[9].tolist())
    assert store.saves == 1
    assert u["state"] == "scored" and u["channels"]["keystroke"]["status"] == "scored"
    assert 0 < u["channels"]["keystroke"]["score"] < 1
    assert u["trust"] is not None and u["model_versions"]["keystroke"] == "keystroke-scaled_manhattan-1"


def test_impostor_windows_lower_trust(parts):
    store, pub, clock, scorer = parts
    X = genuine(8, len(KF1_NAMES))
    for x in X:
        store.add_window("u1", "keystroke", "mouse", x)
        scorer.on_window(CTX, rec("u1", "s1"), x.tolist())
    for k in range(6):
        clock.t += 10
        u = scorer.on_window(CTX, rec("u1", "s1"), (genuine(1, len(KF1_NAMES), seed=50 + k)[0] * 3).tolist())
    assert u["trust"] < 50


def test_pointer_profiles_are_per_device(parts):
    store, pub, clock, scorer = parts
    X = genuine(8, len(PF1_NAMES))
    for x in X:
        store.add_window("u1", "pointer", "touchpad", x)
        scorer.on_window(CTX, rec("u1", "s1", "pointer", "touchpad"), x.tolist())
    assert ("u1", "pointer", "touchpad") in store.profiles
    u = scorer.on_window(CTX, rec("u1", "s1", "pointer", "mouse"), X[0].tolist())
    assert u["channels"]["pointer"]["status"] == "no_profile"
    assert u["channels"]["pointer"]["pointer_device"] == "mouse"


def test_opted_out_channels_are_reported(parts):
    store, pub, clock, scorer = parts
    ctx = UserContext("u1", ("pointer", "interaction"), False)
    x = genuine(1, len(KF1_NAMES))[0]
    u = scorer.on_window(ctx, rec("u1", "s1"), x.tolist())
    assert u["channels"]["pointer"]["status"] == "opted_out"
    assert u["channels"]["interaction"]["status"] == "opted_out"


def test_tick_reports_insufficient_signal_once_evidence_is_stale(parts):
    store, pub, clock, scorer = parts
    X = genuine(9, len(KF1_NAMES))
    for x in X[:8]:
        store.add_window("u1", "keystroke", "mouse", x)
        scorer.on_window(CTX, rec("u1", "s1"), x.tolist())
    assert scorer.on_window(CTX, rec("u1", "s1"), X[8].tolist())["state"] == "scored"
    assert scorer.tick() == []
    clock.t += FRESH_S + 1
    out = scorer.tick()
    assert len(out) == 1 and out[0]["state"] == "insufficient_signal" and out[0]["trust"] is None
    assert scorer.tick() == []  # reported once
    assert store.points[-1] == out[0] and pub.sent[-1] == out[0]


def test_sessions_are_independent(parts):
    store, pub, clock, scorer = parts
    X = genuine(8, len(KF1_NAMES))
    for x in X:
        store.add_window("u1", "keystroke", "mouse", x)
        scorer.on_window(CTX, rec("u1", "s1"), x.tolist())
    a = scorer.on_window(CTX, rec("u1", "s2"), X[0].tolist())
    assert a["session_id"] == "s2" and a["seq"] == 1


class FakeMonitor:
    def __init__(self):
        self.updates = []

    def on_update(self, u):
        self.updates.append(u)


class FakeControl:
    def __init__(self):
        self.verified = {}

    def verified_at(self, sid):
        return self.verified.get(sid)


def _scripted_window():
    from server.features.keystroke import extract_keystroke
    from server.features.types import KeyPress
    presses = [KeyPress(1, 150.0 * k, 150.0 * k + 80.0) for k in range(50)]
    return extract_keystroke(presses).values


def test_bot_flags_reach_the_update_and_the_monitor():
    store, pub, clock = FakeStore(), FakePublisher(), Clock()
    mon = FakeMonitor()
    scorer = TrustScorer(store, pub, enroll_windows=8, clock=clock, monitor=mon)
    u = scorer.on_window(CTX, rec("u1", "s1"), _scripted_window())
    assert u["bot_flags"][0]["kind"] == "timing_regularity"
    assert mon.updates == [u]


def test_replayed_window_is_flagged():
    store, pub, clock = FakeStore(), FakePublisher(), Clock()
    store.recent = [genuine(1, len(KF1_NAMES), seed=3)[0].tolist()]
    store.recent_windows = lambda user, channel, dkey, exclude, limit: store.recent
    scorer = TrustScorer(store, pub, enroll_windows=8, clock=clock)
    u = scorer.on_window(CTX, rec("u1", "s1"), store.recent[0])
    assert any(f["kind"] == "replay_match" for f in u["bot_flags"])


def test_passed_step_up_restores_full_trust():
    store, pub, clock = FakeStore(), FakePublisher(), Clock()
    ctl = FakeControl()
    scorer = TrustScorer(store, pub, enroll_windows=8, clock=clock, control=ctl)
    X = genuine(8, len(KF1_NAMES))
    for x in X:
        store.add_window("u1", "keystroke", "mouse", x)
        scorer.on_window(CTX, rec("u1", "s1"), x.tolist())
    for k in range(5):
        clock.t += 10
        low = scorer.on_window(CTX, rec("u1", "s1"), (genuine(1, len(KF1_NAMES), seed=70 + k)[0] * 3).tolist())
    assert low["trust"] < 60
    ctl.verified["s1"] = clock.t + 1
    clock.t += 5
    after = scorer.on_window(CTX, rec("u1", "s1"), genuine(1, len(KF1_NAMES), seed=99)[0].tolist())
    assert after["trust"] >= 90


def test_recent_windows_are_loaded_once_then_cached():
    store, pub, clock = FakeStore(), FakePublisher(), Clock()
    calls = []
    store.recent_windows = lambda user, channel, dkey, exclude, limit: calls.append(1) or []
    scorer = TrustScorer(store, pub, enroll_windows=50, clock=clock)
    X = genuine(5, len(KF1_NAMES))
    for i, x in enumerate(X):
        u = scorer.on_window(CTX, rec("u1", "s1", wid=f"00000000-0000-0000-0000-00000000000{i}"), x.tolist())
    assert len(calls) == 1
    replayed = scorer.on_window(CTX, rec("u1", "s1", wid="00000000-0000-0000-0000-000000000099"), X[2].tolist())
    assert any(f["kind"] == "replay_match" for f in replayed["bot_flags"])
