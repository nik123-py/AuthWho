"""Continuous trust: channel fusion with a penalty-and-reward rule (proposal Section 8, step 6).

One ``TrustEngine`` per session. Each scored window moves the running trust
value T in [0, 100], in the spirit of Mondal and Bours (2017): a window that
matches the profile earns a small reward, one that does not costs a larger
penalty, so a single odd window cannot end a session but sustained deviation
quickly lowers trust.

For a window with calibrated match score s in (0, 1) and confidence c, on a
channel with weight w:

    delta = w * c * REWARD  * (s - TAU) / (1 - TAU)   if s >= TAU
    delta = -w * c * PENALTY * (TAU - s) / TAU        otherwise

with TAU = 0.25, REWARD = 5 and PENALTY = 10. Because genuine scores are
roughly uniform (``ml/profile.py``), a genuine user drifts upwards on average
(about +0.4 per full-confidence window) while a window less like the user than
any enrollment window costs up to 10 points. These values were chosen by a
sweep on chimeric users (``experiments/fusion_chimeric.py``, ruling R13). T starts at 100: the user has just
passed login and MFA.

Channel weights: keystroke 1, pointer 1, interaction 0.5 (the interaction
channel has no public benchmark yet). Overall confidence is
1 - prod(1 - w_c * c_c) over fresh scored channels.

A channel is fresh while its latest scored window is at most ``FRESH_S`` (120)
seconds old. With no fresh scored channel the state is
``insufficient_signal`` and ``trust`` and ``confidence`` are null, so nothing
downstream can act on a stale or guessed number; the engine keeps T and
resumes from it when evidence returns.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

CHANNELS = ("keystroke", "pointer", "interaction")
CHANNEL_WEIGHTS = {"keystroke": 1.0, "pointer": 1.0, "interaction": 0.5}
TAU = 0.25
REWARD = 5.0
PENALTY = 10.0
FRESH_S = 120.0
START_TRUST = 100.0
TRUST_MODEL_VERSION = "trust-pr-1"


def _iso(ts: float | None) -> str:
    return datetime.fromtimestamp(ts if ts is not None else 0.0, tz=UTC).isoformat().replace("+00:00", "Z")


def _empty(status: str = "no_profile") -> dict[str, Any]:
    return {"status": status, "score": None, "confidence": None, "window_id": None,
            "top_features": [], "scored_at": None, "model_version": None}


class TrustEngine:
    def __init__(self, session_id: str, user_id: str, now: float, trust: float = START_TRUST) -> None:
        self.session_id = session_id
        self.user_id = user_id
        self.trust = float(trust)
        self.seq = 0
        self.created = float(now)
        self.channels: dict[str, dict[str, Any]] = {c: _empty() for c in CHANNELS}

    def set_status(self, channel: str, status: str) -> None:
        """Mark a channel as opted out, without a profile, and so on."""
        self.channels[channel] = {**_empty(status), "model_version": self.channels[channel].get("model_version")}

    def update(self, channel: str, result: dict[str, Any], now: float) -> dict[str, Any]:
        entry = self.channels[channel]
        entry["status"] = result["status"]
        entry["window_id"] = result.get("window_id")
        entry["model_version"] = result.get("model_version") or entry.get("model_version")
        if "pointer_device" in result:
            entry["pointer_device"] = result["pointer_device"]
        if result["status"] == "scored":
            s, c = float(result["score"]), float(result["confidence"])
            w = CHANNEL_WEIGHTS[channel]
            if s >= TAU:
                delta = w * c * REWARD * (s - TAU) / (1 - TAU)
            else:
                delta = -w * c * PENALTY * (TAU - s) / TAU
            self.trust = min(100.0, max(0.0, self.trust + delta))
            entry.update(score=s, confidence=c, top_features=list(result.get("top_features", [])), scored_at=float(now))
        else:
            entry.update(score=None, confidence=None, top_features=[])
        return self.snapshot(now)

    def _fresh(self, entry: dict[str, Any], now: float) -> bool:
        return entry["status"] == "scored" and entry["scored_at"] is not None and now - entry["scored_at"] <= FRESH_S

    def snapshot(self, now: float) -> dict[str, Any]:
        self.seq += 1
        channels, fresh_conf, versions = {}, [], {}
        for c in CHANNELS:
            e = self.channels[c]
            fresh = self._fresh(e, now)
            out = {"status": e["status"], "score": e["score"], "confidence": e["confidence"],
                   "window_id": e["window_id"], "fresh": fresh, "top_features": e["top_features"]}
            if c == "pointer":
                out["pointer_device"] = e.get("pointer_device", "unknown")
            channels[c] = out
            if fresh:
                fresh_conf.append(CHANNEL_WEIGHTS[c] * e["confidence"])
            if e.get("model_version"):
                versions[c] = e["model_version"]
        versions["trust"] = TRUST_MODEL_VERSION
        scored = bool(fresh_conf)
        confidence = None
        if scored:
            miss = 1.0
            for fc in fresh_conf:
                miss *= 1.0 - fc
            confidence = 1.0 - miss
        return {
            "v": 1,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "at": _iso(now),
            "seq": self.seq,
            "state": "scored" if scored else "insufficient_signal",
            "trust": round(self.trust, 2) if scored else None,
            "confidence": round(confidence, 4) if scored else None,
            "channels": channels,
            "bot_flags": [],
            "model_versions": versions,
        }

    def to_dict(self) -> dict[str, Any]:
        return {"session_id": self.session_id, "user_id": self.user_id, "trust": self.trust,
                "seq": self.seq, "created": self.created, "channels": self.channels}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TrustEngine":
        e = cls(d["session_id"], d["user_id"], now=d["created"], trust=d["trust"])
        e.seq = int(d["seq"])
        e.channels = {c: dict(d["channels"][c]) for c in CHANNELS}
        return e
