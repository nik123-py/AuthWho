"""Pairing key events into presses and cutting overlapping windows."""

from server.features.types import KeyPress
from server.features.windowing import KeystrokeWindower

KD, KU = 1, 2


def _press(pid, down, up, cat=1):
    return [[KD, down, cat, pid], [KU, up, cat, pid]]


def _presses(n, start=0):
    events = []
    for k in range(start, start + n):
        events += _press(k, k * 100.0, k * 100.0 + 60.0)
    return events


def test_pairs_down_and_up_by_press_id_across_batches():
    w = KeystrokeWindower(size=2, stride=2)
    assert w.add([[KD, 0.0, 1, 0], [KD, 50.0, 3, 1]]) == []
    windows = w.add([[KU, 80.0, 1, 0], [KU, 90.0, 3, 1]])
    assert windows == [[KeyPress(1, 0.0, 80.0), KeyPress(3, 50.0, 90.0)]]


def test_window_size_and_stride():
    w = KeystrokeWindower(size=50, stride=25)
    windows = w.add(_presses(100))
    assert len(windows) == 3
    assert [len(x) for x in windows] == [50, 50, 50]
    assert windows[0][0].down_t == 0.0 and windows[1][0].down_t == 2500.0
    assert windows[2][-1].down_t == 9900.0


def test_defaults_match_interfaces():
    w = KeystrokeWindower()
    assert (w.size, w.stride) == (50, 25)


def test_keeps_key_down_order_when_releases_overlap():
    w = KeystrokeWindower(size=2, stride=2)
    # Second key goes down first-released: rollover.
    out = w.add([[KD, 0.0, 1, 0], [KD, 40.0, 1, 1], [KU, 70.0, 1, 1]])
    assert out == []  # head press not complete yet
    out = w.add([[KU, 90.0, 1, 0]])
    assert out == [[KeyPress(1, 0.0, 90.0), KeyPress(1, 40.0, 70.0)]]


def test_orphan_key_down_is_dropped_after_timeout():
    w = KeystrokeWindower(size=2, stride=2, orphan_ms=5000)
    events = [[KD, 0.0, 1, 0]] + _press(1, 6000.0, 6050.0) + _press(2, 6100.0, 6150.0)
    out = w.add(events)
    assert out == [[KeyPress(1, 6000.0, 6050.0), KeyPress(1, 6100.0, 6150.0)]]


def test_ignores_other_events_duplicates_and_bad_pairs():
    w = KeystrokeWindower(size=2, stride=2)
    events = [
        [3, 10.0, 100, 200],  # pointer move
        [KD, 0.0, 1, 0],
        [KD, 5.0, 1, 0],  # duplicate press id
        [KU, 50.0, 1, 7],  # unknown press id
        [KU, 60.0, 1, 0],
        [KD, 100.0, 1, 1],
        [KU, 90.0, 1, 1],  # up before down: dropped
        *_press(2, 200.0, 250.0),
    ]
    assert w.add(events) == [[KeyPress(1, 0.0, 60.0), KeyPress(1, 200.0, 250.0)]]


def test_buffer_is_bounded():
    w = KeystrokeWindower(size=50, stride=25)
    w.add(_presses(1000))
    assert w.buffered() < 50
