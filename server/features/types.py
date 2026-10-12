"""Normalised inputs and the feature vector envelope (docs/interfaces.md section 8).

Extractors are pure functions over these types with no I/O, so ``ml/`` can call
the same code on public datasets.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# Key category codes (docs/interfaces.md section 5).
LETTER, DIGIT, SPACE, BACKSPACE, MODIFIER, NAVIGATION, OTHER = 1, 2, 3, 4, 5, 6, 7
KEY_CATEGORIES = {
    LETTER: "letter",
    DIGIT: "digit",
    SPACE: "space",
    BACKSPACE: "backspace",
    MODIFIER: "modifier",
    NAVIGATION: "navigation",
    OTHER: "other",
}


@dataclass(frozen=True)
class KeyPress:
    """One completed key press: a KEY_DOWN and its matching KEY_UP."""

    category: int
    down_t: float
    up_t: float


@dataclass(frozen=True)
class PointerSample:
    t: float
    x: float
    y: float
    kind: int  # 3 move, 4 down, 5 up
    button: int | None


@dataclass(frozen=True)
class InteractionEvent:
    code: int
    t: float
    values: tuple[float, ...]


@dataclass(frozen=True)
class FeatureVector:
    schema: str
    channel: str
    names: list[str]
    values: list[float]
    n_actions: int
    quality: float

    def to_dict(self) -> dict:
        return asdict(self)
