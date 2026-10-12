import numpy as np
import pytest

from server.features.interaction import InteractionWindower, extract_interaction
from server.features.schemas import IF1, IF1_NAMES
from server.features.types import InteractionEvent

WHEEL, SCROLL, FOCUS, BLUR, VIS, CLIP, PAGE, ACTION = 6, 7, 8, 9, 10, 11, 12, 13


def ev(code, t, *values):
    return InteractionEvent(code=code, t=float(t), values=tuple(float(v) for v in values))


def sample_window():
    return [
        ev(PAGE, 0, 3),
        ev(FOCUS, 1000, 0, 1),
        ev(BLUR, 3000, 0),
        ev(FOCUS, 3500, 2, 3),
        ev(BLUR, 4500, 2),
        ev(FOCUS, 5000, 1, 1),  # went back to an earlier field: one inversion
        ev(BLUR, 6000, 1),
        ev(CLIP, 6500, 3),
        ev(WHEEL, 7000, 0, 100, 0),
        ev(WHEEL, 7100, 0, 120, 0),
        ev(WHEEL, 7200, 0, -80, 0),  # direction change
        ev(ACTION, 9200, 1),  # 2000 ms after the previous event
    ]


def test_interaction_features_on_hand_built_window():
    fv = extract_interaction(sample_window())
    assert fv.schema == IF1 and fv.names == IF1_NAMES and fv.channel == "interaction"
    v = dict(zip(fv.names, fv.values))
    assert v["span_s"] == pytest.approx(9.2)
    assert v["event_rate"] == pytest.approx(12 / 9.2)
    assert v["focus_frac"] == pytest.approx(3 / 12)
    assert v["wheel_frac"] == pytest.approx(3 / 12)
    assert v["wheel_dy_abs_mean"] == pytest.approx(100.0)
    assert v["scroll_direction_changes"] == pytest.approx(1 / 2)
    assert v["field_order_inversions"] == pytest.approx(1 / 2)
    assert v["focus_dwell_mean"] == pytest.approx((2000 + 1000 + 1000) / 3)
    assert v["hesitation_mean"] == pytest.approx(2000.0)
    assert v["paste_rate"] == pytest.approx(1 / 9.2)
    assert np.all(np.isfinite(fv.values))
    assert fv.quality == pytest.approx(1.0)


def test_missing_parts_are_filled_and_lower_quality():
    fv = extract_interaction([ev(SCROLL, 0, 0, 10), ev(SCROLL, 500, 0, 20), ev(SCROLL, 900, 0, 30)])
    v = dict(zip(fv.names, fv.values))
    assert v["hesitation_mean"] == 0.0 and v["focus_dwell_mean"] == 0.0 and v["wheel_dy_abs_mean"] == 0.0
    assert fv.quality < 1.0
    assert np.all(np.isfinite(fv.values))


def test_extract_needs_two_events():
    with pytest.raises(ValueError):
        extract_interaction([ev(PAGE, 0, 1)])


def test_windower_20_events_stride_10_and_ignores_other_channels():
    w = InteractionWindower(size=20, stride=10)
    events = []
    for i in range(45):
        events.append([1, i * 100.0, 1, i])  # keystroke, ignored
        events.append([7, i * 100.0 + 1, 0.0, float(i)])  # scroll
    windows = w.add(events[:50]) + w.add(events[50:])
    assert [len(x) for x in windows] == [20, 20, 20]
    assert windows[1][0].t == pytest.approx(1001.0)
    assert all(e.code == 7 for x in windows for e in x)
