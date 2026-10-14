import numpy as np

from ml.synthetic import PRIORS, SyntheticUser, generate_cohort, generate_session, make_users
from server.features.interaction import InteractionWindower
from server.features.pointer import PointerWindower
from server.features.windowing import KeystrokeWindower


def test_cohort_shape_devices_and_days_are_deterministic():
    a = make_users(25, seed=7)
    b = make_users(25, seed=7)
    assert [u.user_id for u in a] == [u.user_id for u in b]
    assert len(a) == 25 and len({u.user_id for u in a}) == 25
    assert sum(u.device == "touchpad" for u in a) == 10
    for u in a:
        assert len(u.session_days) == 6 and len(set(u.session_days)) >= 3
        assert u.session_days == sorted(u.session_days) and max(u.session_days) <= 13


def test_users_differ_and_follow_the_priors():
    users = make_users(200, seed=1, touchpad_share=0.4)
    dwell = np.array([u.ks["dwell_median"] for u in users])
    lo, med, hi = PRIORS["keystroke"]["dwell_median"]
    assert lo * 0.8 < np.median(dwell) < hi * 1.2
    assert abs(np.median(dwell) - med) / med < 0.15
    assert np.std(dwell) > 5


def test_session_events_are_numbers_only_and_time_ordered():
    u = make_users(1, seed=3)[0]
    events = generate_session(u, session_index=0, seed=3)
    assert len(events) > 2000
    assert all(isinstance(v, (int, float)) and np.isfinite(v) for e in events for v in e)
    t = [e[1] for e in events]
    assert t == sorted(t)
    assert {e[0] for e in events} >= {1, 2, 3, 4, 5, 6, 8, 9, 12}


def test_live_windowers_turn_a_session_into_windows_on_every_channel():
    u = make_users(1, seed=4)[0]
    events = generate_session(u, session_index=0, seed=4)
    ks = KeystrokeWindower().add(events)
    pt = PointerWindower().add(events)
    it = InteractionWindower().add(events)
    assert len(ks) >= 20 and len(pt) >= 6 and len(it) >= 5


def test_typing_timing_matches_the_users_parameters():
    u = SyntheticUser.from_params("x", "mouse", [0, 1, 2, 3, 4, 5], ks={**{k: v[1] for k, v in PRIORS["keystroke"].items()},
                                  "dwell_median": 120.0}, pt={k: v[1] for k, v in PRIORS["pointer"].items()}, seed=0)
    events = generate_session(u, session_index=0, seed=0)
    downs = {e[3]: e[1] for e in events if e[0] == 1}
    dwell = [e[1] - downs[e[3]] for e in events if e[0] == 2 and e[3] in downs]
    assert 105 < np.median(dwell) < 140


def test_generate_cohort_writes_a_manifest_and_sessions(tmp_path):
    manifest = generate_cohort(tmp_path, n_users=3, seed=5)
    assert len(manifest["users"]) == 3 and manifest["synthetic"] is True
    files = list(tmp_path.glob("*/*.json.gz"))
    assert len(files) == 18
