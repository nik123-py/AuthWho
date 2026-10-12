"""A key press as used offline by the dataset loaders.

``category`` is the seven-way key category from docs/interfaces.md section 5.
``key_id`` identifies the physical key and exists only for offline research
on public datasets (the key-pair comparison in P1-3). It never enters the live
system, which sees categories only. Times are milliseconds.
"""

from __future__ import annotations

from dataclasses import dataclass

from server.features.types import KeyPress


@dataclass(frozen=True)
class Press:
    category: int
    key_id: int
    down_t: float
    up_t: float

    def as_keypress(self) -> KeyPress:
        """The category-only view the live extractor accepts."""
        return KeyPress(category=self.category, down_t=self.down_t, up_t=self.up_t)
