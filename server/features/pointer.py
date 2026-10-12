"""Pointer strokes and ``pf-1`` features (docs/interfaces.md section 8).

A stroke is a run of pointer samples. It ends when the button is released
after a press (a click or a drag ends the stroke), or when more than
``pause_ms`` (300 ms) passes between two samples while no button is held.
Only strokes with at least two movement samples are kept, because the
kinematic measures need a path.

Per-stroke measures, from movement samples only (samples with no time step are
skipped; units are px and ms):
- duration: time from the first to the last movement sample;
- path_length: sum of distances between consecutive samples;
- efficiency: straight-line distance from first to last sample divided by
  path length (1 for a straight line; 1 when the path length is zero);
- v_mean, v_max: mean and peak of segment speed (distance over time step);
- acc_mean, jerk_mean: mean absolute change of speed per ms, and of
  acceleration per ms, between consecutive segment midpoints;
- curvature_mean: mean absolute heading change between consecutive
  non-zero segments divided by the length of the later segment (radians per
  px); angle_change_mean: the same heading change without the division;
- pauses: number of time steps longer than 100 ms;
- pre_click_pause: time from the last movement sample to the button press;
- click_hold: time from press to release.
A measure with no data is 0, except the click measures, which are NaN for
strokes without a click.

Window features (``pf-1``): the mean and standard deviation over the window's
strokes of the nine kinematic measures, the mean number of pauses, the share
of strokes ending in a click, and the mean pre-click pause and click hold over
clicking strokes. Fill rule: with no clicking stroke in the window the two
click means are 0 and count as filled; quality is the share of features not
filled.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np

from server.features.schemas import PF1, PF1_NAMES, PF1_STROKE_MEASURES
from server.features.types import FeatureVector, PointerSample

MOVE, DOWN, UP = 3, 4, 5
PAUSE_MS = 300.0
INNER_PAUSE_MS = 100.0
_STROKE_KEYS = {
    "duration": "duration",
    "path_length": "path_length",
    "efficiency": "efficiency",
    "velocity": "v_mean",
    "velocity_peak": "v_max",
    "acceleration": "acc_mean",
    "jerk": "jerk_mean",
    "curvature": "curvature_mean",
    "angle_change": "angle_change_mean",
}


def _mean_abs_rate(values: np.ndarray, times: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Rates of change of ``values`` at the midpoints of ``times``."""
    if values.size < 2:
        return np.array([]), np.array([])
    dt = np.diff(times)
    ok = dt > 0
    rate = np.diff(values)[ok] / dt[ok]
    mid = ((times[1:] + times[:-1]) / 2.0)[ok]
    return rate, mid


def stroke_features(samples: Sequence[PointerSample]) -> dict[str, float]:
    moves = [s for s in samples if s.kind == MOVE]
    pts = []
    for s in moves:
        if pts and s.t <= pts[-1][0]:
            continue
        pts.append((s.t, float(s.x), float(s.y)))
    f = {"duration": 0.0, "path_length": 0.0, "efficiency": 1.0, "v_mean": 0.0, "v_max": 0.0,
         "acc_mean": 0.0, "jerk_mean": 0.0, "curvature_mean": 0.0, "angle_change_mean": 0.0, "pauses": 0.0}
    if len(pts) >= 2:
        arr = np.array(pts)
        t, xy = arr[:, 0], arr[:, 1:]
        seg = np.diff(xy, axis=0)
        dist = np.hypot(seg[:, 0], seg[:, 1])
        dt = np.diff(t)
        path = float(dist.sum())
        straight = float(np.hypot(*(xy[-1] - xy[0])))
        speed = dist / dt
        mid = (t[1:] + t[:-1]) / 2.0
        acc, acc_t = _mean_abs_rate(speed, mid)
        jerk, _ = _mean_abs_rate(acc, acc_t)
        heading = np.arctan2(seg[:, 1], seg[:, 0])
        nonzero = dist > 0
        h, d = heading[nonzero], dist[nonzero]
        turn = np.abs((np.diff(h) + math.pi) % (2 * math.pi) - math.pi)
        f.update(
            duration=float(t[-1] - t[0]),
            path_length=path,
            efficiency=straight / path if path > 0 else 1.0,
            v_mean=float(speed.mean()),
            v_max=float(speed.max()),
            acc_mean=float(np.abs(acc).mean()) if acc.size else 0.0,
            jerk_mean=float(np.abs(jerk).mean()) if jerk.size else 0.0,
            curvature_mean=float((turn / d[1:]).mean()) if turn.size else 0.0,
            angle_change_mean=float(turn.mean()) if turn.size else 0.0,
            pauses=float(np.sum(dt > INNER_PAUSE_MS)),
        )
    down = next((s for s in samples if s.kind == DOWN), None)
    up = next((s for s in samples if s.kind == UP), None)
    if down is not None:
        before = [s.t for s in moves if s.t <= down.t]
        f["pre_click_pause"] = float(down.t - before[-1]) if before else 0.0
        f["click_hold"] = float(up.t - down.t) if up is not None and up.t >= down.t else math.nan
    else:
        f["pre_click_pause"] = math.nan
        f["click_hold"] = math.nan
    return f


def extract_pointer(strokes: Sequence[Sequence[PointerSample]]) -> FeatureVector:
    if not strokes:
        raise ValueError("a pointer window needs at least one stroke")
    per = [stroke_features(s) for s in strokes]
    feats: dict[str, float] = {}
    for m in PF1_STROKE_MEASURES:
        vals = np.array([p[_STROKE_KEYS[m]] for p in per], dtype=float)
        feats[f"{m}_mean"] = float(vals.mean())
        feats[f"{m}_std"] = float(vals.std())
    feats["pauses_mean"] = float(np.mean([p["pauses"] for p in per]))
    holds = [p["click_hold"] for p in per if not math.isnan(p["click_hold"])]
    pre = [p["pre_click_pause"] for p in per if not math.isnan(p["pre_click_pause"])]
    feats["click_rate"] = float(np.mean([not math.isnan(p["pre_click_pause"]) for p in per]))
    filled = 0
    feats["pre_click_pause_mean"] = float(np.mean(pre)) if pre else 0.0
    feats["click_hold_mean"] = float(np.mean(holds)) if holds else 0.0
    filled += (not pre) + (not holds)
    values = [feats[n] for n in PF1_NAMES]
    if not all(np.isfinite(values)):
        raise ValueError("non-finite pointer feature")
    return FeatureVector(
        schema=PF1,
        channel="pointer",
        names=list(PF1_NAMES),
        values=values,
        n_actions=len(strokes),
        quality=1.0 - filled / len(PF1_NAMES),
    )


class _Segmenter:
    def __init__(self, pause_ms: float = PAUSE_MS) -> None:
        self.pause_ms = pause_ms
        self.current: list[PointerSample] = []
        self.pressed = False
        self.last_t: float | None = None

    def _close(self, out: list[list[PointerSample]]) -> None:
        if sum(1 for s in self.current if s.kind == MOVE) >= 2:
            out.append(self.current)
        self.current = []
        self.pressed = False

    def feed(self, s: PointerSample, out: list[list[PointerSample]]) -> None:
        if self.current and not self.pressed and self.last_t is not None and s.t - self.last_t > self.pause_ms:
            self._close(out)
        self.last_t = s.t
        if s.kind == MOVE:
            self.current.append(s)
        elif s.kind == DOWN:
            if self.pressed:
                self._close(out)
            self.current.append(s)
            self.pressed = True
        elif s.kind == UP and self.pressed:
            self.current.append(s)
            self._close(out)

    def flush(self, out: list[list[PointerSample]]) -> None:
        if self.current:
            self._close(out)


def _sample(ev: Sequence[float]) -> PointerSample | None:
    code = int(ev[0])
    if code == MOVE:
        return PointerSample(float(ev[1]), float(ev[2]), float(ev[3]), MOVE, None)
    if code in (DOWN, UP):
        button = int(ev[4])
        if button not in (0, 1, 2):
            return None
        return PointerSample(float(ev[1]), float(ev[2]), float(ev[3]), code, button)
    return None


def segment_strokes(samples: Sequence[PointerSample], pause_ms: float = PAUSE_MS) -> list[list[PointerSample]]:
    """Split a complete sample sequence into strokes (the last one is closed too)."""
    seg, out = _Segmenter(pause_ms), []
    for s in samples:
        seg.feed(s, out)
    seg.flush(out)
    return out


class PointerWindower:
    """Incremental strokes and windows of ``size`` strokes every ``stride``.

    The last stroke stays open until a later sample shows it has ended, so a
    window can span batches. Events of other channels are ignored.
    """

    def __init__(self, size: int = 30, stride: int = 15, pause_ms: float = PAUSE_MS) -> None:
        if not 0 < stride <= size:
            raise ValueError("need 0 < stride <= size")
        self.size = size
        self.stride = stride
        self._seg = _Segmenter(pause_ms)
        self._strokes: list[list[PointerSample]] = []

    def add(self, events: Sequence[Sequence[float]]) -> list[list[list[PointerSample]]]:
        for ev in events:
            s = _sample(ev)
            if s is not None:
                self._seg.feed(s, self._strokes)
        windows = []
        while len(self._strokes) >= self.size:
            windows.append(self._strokes[: self.size])
            del self._strokes[: self.stride]
        return windows
