import math

import numpy as np
import pytest

from server.features.pointer import PointerWindower, extract_pointer, segment_strokes, stroke_features
from server.features.schemas import PF1, PF1_NAMES
from server.features.types import PointerSample

MOVE, DOWN, UP = 3, 4, 5


def line(t0=0.0, n=11, dx=10.0, dt=10.0, x0=0.0, y0=0.0):
    """A straight horizontal stroke at constant speed dx/dt px per ms."""
    return [PointerSample(t0 + i * dt, x0 + i * dx, y0, MOVE, None) for i in range(n)]


def click(t_down, t_up, x, y):
    return [PointerSample(t_down, x, y, DOWN, 0), PointerSample(t_up, x, y, UP, 0)]


def test_straight_line_stroke_features():
    f = stroke_features(line())
    assert f["duration"] == pytest.approx(100.0)
    assert f["path_length"] == pytest.approx(100.0)
    assert f["efficiency"] == pytest.approx(1.0)
    assert f["v_mean"] == pytest.approx(1.0)
    assert f["v_max"] == pytest.approx(1.0)
    assert f["acc_mean"] == pytest.approx(0.0, abs=1e-9)
    assert f["curvature_mean"] == pytest.approx(0.0, abs=1e-9)
    assert math.isnan(f["click_hold"])


def test_circle_has_constant_curvature_and_low_efficiency():
    r, n = 100.0, 37
    pts = [PointerSample(10.0 * i, r * math.cos(2 * math.pi * i / (n - 1)), r * math.sin(2 * math.pi * i / (n - 1)), MOVE, None) for i in range(n)]
    f = stroke_features(pts)
    assert f["efficiency"] == pytest.approx(0.0, abs=1e-6)  # ends where it started
    assert f["path_length"] == pytest.approx(2 * math.pi * r, rel=0.01)
    # turning 10 degrees per segment of length about 17.4 px
    seg = 2 * r * math.sin(math.pi / (n - 1))
    assert f["curvature_mean"] == pytest.approx(math.radians(10) / seg, rel=0.01)


def test_click_features():
    pts = line(n=6) + click(100.0, 180.0, 50.0, 0.0)
    f = stroke_features(pts)
    assert f["pre_click_pause"] == pytest.approx(50.0)  # last move at 50 ms, down at 100 ms
    assert f["click_hold"] == pytest.approx(80.0)


def test_segmentation_splits_on_pause_and_click():
    a = line(t0=0.0)  # ends at 100 ms
    b = line(t0=500.0)  # 400 ms gap: new stroke
    c = line(t0=620.0, n=5) + click(670.0, 700.0, 40.0, 0.0)  # 20 ms gap after b, so joins b
    d = line(t0=710.0, n=5)  # after a click: new stroke
    strokes = segment_strokes(a + b + c + d)
    assert [len(s) for s in strokes] == [11, 11 + 5 + 2, 5]


def test_segmentation_drops_strokes_with_fewer_than_two_positions():
    pts = [PointerSample(0.0, 0, 0, MOVE, None)] + line(t0=1000.0)
    assert [len(s) for s in segment_strokes(pts)] == [11]


def test_extract_pointer_schema_and_finiteness():
    strokes = [line(t0=1000.0 * i) for i in range(5)] + [line(t0=6000.0, n=6) + click(6100.0, 6180.0, 50.0, 0.0)]
    fv = extract_pointer(strokes)
    assert fv.schema == PF1 and fv.channel == "pointer"
    assert fv.names == PF1_NAMES
    assert fv.n_actions == 6
    assert np.all(np.isfinite(fv.values))
    vals = dict(zip(fv.names, fv.values))
    assert vals["click_rate"] == pytest.approx(1 / 6)
    assert vals["efficiency_mean"] == pytest.approx(1.0)


def test_extract_pointer_fills_click_features_when_no_clicks():
    fv = extract_pointer([line(t0=1000.0 * i) for i in range(4)])
    vals = dict(zip(fv.names, fv.values))
    assert vals["click_hold_mean"] == 0.0 and vals["pre_click_pause_mean"] == 0.0
    assert fv.quality < 1.0


def _events(strokes):
    out = []
    for s in strokes:
        for p in s:
            out.append([p.kind, p.t, p.x, p.y] if p.kind == MOVE else [p.kind, p.t, p.x, p.y, p.button])
    return out


def test_windower_cuts_30_strokes_with_stride_15_across_batches():
    w = PointerWindower(size=30, stride=15)
    strokes = [line(t0=1000.0 * i) for i in range(61)]
    events = _events(strokes)
    windows = []
    for k in range(0, len(events), 37):  # arbitrary batch boundaries
        windows += w.add(events[k : k + 37])
    # the 61st stroke closes only when a later sample shows the pause, so 60 strokes are complete
    assert len(windows) == 3
    assert all(len(win) == 30 for win in windows)
    assert windows[1][0][0].t == pytest.approx(15000.0)


def test_windower_ignores_non_pointer_events_and_bad_buttons():
    w = PointerWindower(size=2, stride=2)
    events = _events([line(t0=0.0)]) + [[1, 50.0, 1, 0], [6, 60.0, 0.0, 3.0, 0]] + _events([line(t0=1000.0), line(t0=2000.0)])
    windows = w.add(events)
    assert len(windows) == 1 and len(windows[0]) == 2
