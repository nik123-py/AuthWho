"""Scoring stage: windows to channel scores to continuous trust (docs/interfaces.md section 9).

Called by the feature pipeline after each window is stored. For the window's
user, channel and device key (the device type for pointer, ``any`` otherwise):

- without an active profile, the user is still enrolling: once at least
  ``enroll_windows`` (default 20, ``AUTHWHO_ENROLL_WINDOWS``) stored windows
  exist, a template is trained from them (``ml.profile``) and saved, and this
  window's channel status is ``no_profile``;
- with a profile, the window is scored and the session's ``TrustEngine``
  (``ml.trust``) is updated.

Every resulting trust update is stored as a trust point and published for the
dashboard. ``tick`` reports, once, each session whose evidence has gone stale,
so the dashboard shows "Cannot determine" instead of an old number.

Enrollment trusts the first consented windows, as proposal Section 4 does with
its "consented initial period of normal use". Updating a profile later from
verified sessions is deferred (ruling R8). Nothing here logs feature values.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any, Protocol

from ml.profile import score_window, train_template
from ml.trust import CHANNELS, FRESH_S, TrustEngine
from server.features.schemas import IF1, IF1_NAMES, KF1, KF1_NAMES, PF1, PF1_NAMES
from server.worker.store import UserContext, WindowRecord

log = logging.getLogger("authwho.worker")

SCHEMAS = {"keystroke": (KF1, KF1_NAMES), "pointer": (PF1, PF1_NAMES), "interaction": (IF1, IF1_NAMES)}
ENROLL_WINDOWS = 20
IDLE_EVICT_S = 1800.0


def device_key(channel: str, pointer_device: str) -> str:
    return pointer_device if channel == "pointer" else "any"


class ScoringStore(Protocol):
    def active_profile(self, user_id: str, channel: str, dkey: str) -> dict | None: ...

    def enrollment_windows(self, user_id: str, channel: str, dkey: str, limit: int) -> list[tuple[list[float], float]]: ...

    def save_profile(self, user_id: str, channel: str, dkey: str, template: dict) -> bool: ...

    def insert_trust_point(self, update: dict) -> None: ...


class TrustPublisher(Protocol):
    def publish(self, update: dict) -> None: ...


class TrustScorer:
    def __init__(self, store: ScoringStore, publisher: TrustPublisher, enroll_windows: int = ENROLL_WINDOWS,
                 clock: Callable[[], float] = time.time) -> None:
        self.store = store
        self.publisher = publisher
        self.enroll_windows = enroll_windows
        self.clock = clock
        self._engines: dict[str, TrustEngine] = {}
        self._last_state: dict[str, str] = {}
        self._last_seen: dict[str, float] = {}

    def _engine(self, session_id: str, user_id: str, now: float) -> TrustEngine:
        if session_id not in self._engines:
            self._engines[session_id] = TrustEngine(session_id, user_id, now=now)
        return self._engines[session_id]

    def _channel_result(self, ctx: UserContext, rec: WindowRecord, values: list[float]) -> dict[str, Any]:
        dkey = device_key(rec.channel, rec.pointer_device)
        template = self.store.active_profile(ctx.user_id, rec.channel, dkey)
        if template is None:
            rows = self.store.enrollment_windows(ctx.user_id, rec.channel, dkey, limit=self.enroll_windows)
            if len(rows) >= self.enroll_windows:
                schema, names = SCHEMAS[rec.channel]
                template = train_template(rec.channel, schema, names, [r[0] for r in rows], [r[1] for r in rows])
                self.store.save_profile(ctx.user_id, rec.channel, dkey, template)
                log.info("enrolled a %s profile from %d windows", rec.channel, len(rows))
            return {"status": "no_profile", "score": None, "confidence": None, "top_features": [],
                    "model_version": None}
        return score_window(template, values, rec.quality)

    def on_window(self, ctx: UserContext, rec: WindowRecord, values: list[float]) -> dict[str, Any]:
        now = self.clock()
        engine = self._engine(rec.session_id, ctx.user_id, now)
        for c in CHANNELS:
            if not ctx.allows(c):
                engine.set_status(c, "opted_out")
        result = self._channel_result(ctx, rec, values)
        result = {**result, "window_id": rec.window_id}
        if rec.channel == "pointer":
            result["pointer_device"] = rec.pointer_device
        update = engine.update(rec.channel, result, now=now)
        self._emit(update)
        self._last_seen[rec.session_id] = now
        return update

    def _emit(self, update: dict[str, Any]) -> None:
        self._last_state[update["session_id"]] = update["state"]
        self.store.insert_trust_point(update)
        self.publisher.publish(update)

    def tick(self) -> list[dict[str, Any]]:
        """Report sessions whose evidence went stale; forget long-idle sessions."""
        now = self.clock()
        out = []
        for sid, engine in list(self._engines.items()):
            if self._last_state.get(sid) == "scored":
                fresh = any(
                    e["status"] == "scored" and e["scored_at"] is not None and now - e["scored_at"] <= FRESH_S
                    for e in engine.channels.values()
                )
                if not fresh:
                    update = engine.snapshot(now)
                    self._emit(update)
                    out.append(update)
            if now - self._last_seen.get(sid, now) > IDLE_EVICT_S:
                del self._engines[sid]
                self._last_state.pop(sid, None)
                self._last_seen.pop(sid, None)
        return out
