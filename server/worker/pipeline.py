"""Raw batches to encrypted feature windows (docs/interfaces.md section 8).

One windower per stream, because event times are stream-relative. For each
batch the user's consent context is looked up; batches of unknown sessions
(for example after a withdrawal), exempt users and opted-out channels are not
buffered at all. The store checks the same rules again inside the insert
transaction. P1 windows the keystroke channel; pointer and interaction
windowing is added in P2.

Window state lives in memory. A stream idle for ``idle_s`` seconds is
dropped, and a worker restart loses partly filled windows; both only delay
the next window, they never mix data from different streams. Nothing here
logs event contents.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from server.features.keystroke import extract_keystroke
from server.features.schemas import KF1, KF1_EXTRACTOR_VERSION
from server.features.windowing import KeystrokeWindower
from server.worker.store import UserContext, WindowRecord, WindowStore, encrypt_features

log = logging.getLogger("authwho.worker")

POINTER_DEVICES = ("mouse", "touchpad", "unknown")


@dataclass
class _StreamState:
    session_id: str
    keystroke: KeystrokeWindower = field(default_factory=KeystrokeWindower)
    last_seen: float = 0.0


class FeaturePipeline:
    def __init__(self, store: WindowStore, key: bytes, idle_s: float = 1800.0,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.store = store
        self.key = key
        self.idle_s = idle_s
        self.clock = clock
        self._streams: dict[str, _StreamState] = {}

    def open_streams(self) -> int:
        return len(self._streams)

    def process(self, entries: list[tuple[str, dict]]) -> int:
        now = self.clock()
        contexts: dict[str, UserContext | None] = {}
        written = 0
        for _entry_id, fields in entries:
            try:
                session_id = str(uuid.UUID(fields["session_id"]))
                stream_id = str(uuid.UUID(fields["stream_id"]))
                events = json.loads(fields["events"])
            except (KeyError, ValueError, TypeError):
                log.warning("skipped a malformed stream entry")
                continue
            if session_id not in contexts:
                contexts[session_id] = self.store.user_context(session_id)
            ctx = contexts[session_id]
            if ctx is None or not ctx.allows("keystroke"):
                continue
            device = fields.get("pointer_device")
            device = device if device in POINTER_DEVICES else "unknown"
            state = self._streams.setdefault(stream_id, _StreamState(session_id))
            state.last_seen = now
            try:
                windows = state.keystroke.add(events)
            except (IndexError, ValueError, TypeError):
                log.warning("skipped a batch with malformed events")
                continue
            for window in windows:
                if self._write_keystroke(ctx, session_id, stream_id, device, window):
                    written += 1
        self._evict(now)
        return written

    def _write_keystroke(self, ctx, session_id, stream_id, device, presses) -> bool:
        fv = extract_keystroke(presses)
        window_id = str(uuid.uuid4())
        rec = WindowRecord(
            window_id=window_id,
            session_id=session_id,
            stream_id=stream_id,
            user_id=ctx.user_id,
            channel="keystroke",
            pointer_device=device,
            schema=KF1,
            start_t=min(p.down_t for p in presses),
            end_t=max(p.up_t for p in presses),
            n_actions=fv.n_actions,
            quality=fv.quality,
            features_enc=encrypt_features(fv.values, self.key, window_id),
            extractor_version=KF1_EXTRACTOR_VERSION,
        )
        return self.store.insert_window(rec)

    def _evict(self, now: float) -> None:
        for stream_id in [s for s, st in self._streams.items() if now - st.last_seen > self.idle_s]:
            del self._streams[stream_id]
