"""Raw batches to encrypted feature windows (docs/interfaces.md section 8).

One windower per stream, because event times are stream-relative. For each
batch the user's consent context is looked up; batches of unknown sessions
(for example after a withdrawal), exempt users and opted-out channels are not
buffered at all, and each channel is windowed only if the user has not opted
out of it. The store checks the same rules again inside the insert
transaction. Every stream has one windower per channel: keystroke (``kf-1``),
pointer (``pf-1``) and interaction (``if-1``).

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

from server.features.interaction import InteractionWindower, extract_interaction
from server.features.keystroke import extract_keystroke
from server.features.pointer import PointerWindower, extract_pointer
from server.features.schemas import (
    IF1, IF1_EXTRACTOR_VERSION, KF1, KF1_EXTRACTOR_VERSION, PF1, PF1_EXTRACTOR_VERSION,
)
from server.features.windowing import KeystrokeWindower
from server.worker.store import UserContext, WindowRecord, WindowStore, encrypt_features

log = logging.getLogger("authwho.worker")

POINTER_DEVICES = ("mouse", "touchpad", "unknown")
CHANNELS = ("keystroke", "pointer", "interaction")


@dataclass
class _StreamState:
    session_id: str
    keystroke: KeystrokeWindower = field(default_factory=KeystrokeWindower)
    pointer: PointerWindower = field(default_factory=PointerWindower)
    interaction: InteractionWindower = field(default_factory=InteractionWindower)
    last_seen: float = 0.0


class FeaturePipeline:
    def __init__(self, store: WindowStore, key: bytes, idle_s: float = 1800.0,
                 clock: Callable[[], float] = time.monotonic,
                 on_window: Callable[[UserContext, WindowRecord, list[float]], object] | None = None) -> None:
        self.store = store
        self.on_window = on_window
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
            if ctx is None:
                continue
            channels = [c for c in CHANNELS if ctx.allows(c)]
            if not channels:
                continue
            device = fields.get("pointer_device")
            device = device if device in POINTER_DEVICES else "unknown"
            state = self._streams.setdefault(stream_id, _StreamState(session_id))
            state.last_seen = now
            for channel in channels:
                try:
                    windows = getattr(state, channel).add(events)
                except (IndexError, ValueError, TypeError):
                    log.warning("skipped a batch with malformed events")
                    continue
                for window in windows:
                    if self._write(channel, ctx, session_id, stream_id, device, window):
                        written += 1
        self._evict(now)
        return written

    def _write(self, channel, ctx, session_id, stream_id, device, window) -> bool:
        try:
            if channel == "keystroke":
                fv = extract_keystroke(window)
                schema, version = KF1, KF1_EXTRACTOR_VERSION
                start_t, end_t = min(p.down_t for p in window), max(p.up_t for p in window)
            elif channel == "pointer":
                fv = extract_pointer(window)
                schema, version = PF1, PF1_EXTRACTOR_VERSION
                start_t, end_t = window[0][0].t, max(s.t for stroke in window for s in stroke)
            else:
                fv = extract_interaction(window)
                schema, version = IF1, IF1_EXTRACTOR_VERSION
                start_t, end_t = min(e.t for e in window), max(e.t for e in window)
        except ValueError:
            log.warning("skipped a %s window that could not be featurised", channel)
            return False
        window_id = str(uuid.uuid4())
        rec = WindowRecord(
            window_id=window_id,
            session_id=session_id,
            stream_id=stream_id,
            user_id=ctx.user_id,
            channel=channel,
            pointer_device=device,
            schema=schema,
            start_t=start_t,
            end_t=end_t,
            n_actions=fv.n_actions,
            quality=fv.quality,
            features_enc=encrypt_features(fv.values, self.key, window_id),
            extractor_version=version,
        )
        if not self.store.insert_window(rec):
            return False
        if self.on_window is not None:
            try:
                self.on_window(ctx, rec, fv.values)
            except Exception:  # scoring must never stop windowing; values are not logged
                log.exception("scoring failed for a %s window", channel)
        return True

    def _evict(self, now: float) -> None:
        for stream_id in [s for s, st in self._streams.items() if now - st.last_seen > self.idle_s]:
            del self._streams[stream_id]
