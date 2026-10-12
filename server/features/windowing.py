"""Action-count windows for one stream (docs/interfaces.md section 8).

``KeystrokeWindower`` pairs KEY_DOWN and KEY_UP events by ``press_id`` into
``KeyPress`` objects and cuts windows of ``size`` presses every ``stride``
presses, in key-down order. A press joins the window sequence only once it and
every earlier press are complete, so overlapping keys never reorder a window.
A key-down whose key-up never arrives (for example a lost batch) is dropped
once a later key goes down more than ``orphan_ms`` after it, so it cannot
stall the stream. Key-ups for unknown presses, repeated key-downs for the same
``press_id`` and key-ups earlier than their key-down are ignored.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Sequence

from server.features.types import KeyPress

KEY_DOWN, KEY_UP = 1, 2


class _Pending:
    __slots__ = ("category", "down_t", "up_t", "dropped")

    def __init__(self, category: int, down_t: float) -> None:
        self.category = category
        self.down_t = down_t
        self.up_t: float | None = None
        self.dropped = False


class KeystrokeWindower:
    def __init__(self, size: int = 50, stride: int = 25, orphan_ms: float = 5000.0) -> None:
        if not 0 < stride <= size:
            raise ValueError("need 0 < stride <= size")
        self.size = size
        self.stride = stride
        self.orphan_ms = orphan_ms
        self._pending: deque[_Pending] = deque()
        self._by_id: dict[int, _Pending] = {}
        self._seen: set[int] = set()
        self._ready: list[KeyPress] = []
        self._latest_down = float("-inf")

    def buffered(self) -> int:
        return len(self._pending) + len(self._ready)

    def add(self, events: Sequence[Sequence[float]]) -> list[list[KeyPress]]:
        for ev in events:
            code = int(ev[0])
            if code == KEY_DOWN:
                pid = int(ev[3])
                if pid in self._seen:
                    continue
                self._seen.add(pid)
                entry = _Pending(int(ev[2]), float(ev[1]))
                self._pending.append(entry)
                self._by_id[pid] = entry
                self._latest_down = max(self._latest_down, entry.down_t)
            elif code == KEY_UP:
                entry = self._by_id.pop(int(ev[3]), None)
                if entry is None:
                    continue
                if float(ev[1]) < entry.down_t:
                    entry.dropped = True
                else:
                    entry.up_t = float(ev[1])
        self._advance()
        return self._cut()

    def _advance(self) -> None:
        while self._pending:
            head = self._pending[0]
            if head.dropped:
                self._pending.popleft()
            elif head.up_t is not None:
                self._pending.popleft()
                self._ready.append(KeyPress(head.category, head.down_t, head.up_t))
            elif self._latest_down - head.down_t > self.orphan_ms:
                self._pending.popleft()
                for pid, e in list(self._by_id.items()):
                    if e is head:
                        del self._by_id[pid]
            else:
                break

    def _cut(self) -> list[list[KeyPress]]:
        windows = []
        while len(self._ready) >= self.size:
            windows.append(self._ready[: self.size])
            del self._ready[: self.stride]
        return windows
