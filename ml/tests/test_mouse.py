import pytest

from ml.datasets.mouse import parse_mouse_csv, windows_of

BALABIT = """record timestamp,client timestamp,button,state,x,y
0.0,0.0,NoButton,Move,10,20
0.2,0.1,NoButton,Move,12,22
0.3,0.2,Left,Pressed,12,22
0.4,0.3,Left,Released,12,22
0.5,0.4,Scroll,Down,12,22
0.6,0.5,Left,Drag,30,40
0.7,0.6,Right,Pressed,30,40
bad,row
"""

SAPI = """client timestamp,button,state,x,y
15585,NoButton,Move,967,706
15601,NoButton,Move,958,700
15620,Left,Pressed,958,700
15700,Left,Released,958,700
"""


def test_balabit_rows_map_to_pointer_samples_in_ms():
    s = parse_mouse_csv(BALABIT, seconds=True)
    assert [(p.kind, p.button) for p in s] == [(3, None), (3, None), (4, 0), (5, 0), (3, None), (4, 2)]
    assert s[1].t == pytest.approx(100.0)
    assert (s[4].x, s[4].y) == (30.0, 40.0)  # a drag is movement


def test_sapimouse_rows_in_ms():
    s = parse_mouse_csv(SAPI, seconds=False)
    assert [p.kind for p in s] == [3, 3, 4, 5]
    assert s[0].t == 15585.0 and s[3].t == 15700.0


def test_windows_of_non_overlapping_and_overlapping():
    items = list(range(100))
    assert [w[0] for w in windows_of(items, 30)] == [0, 30, 60]
    assert [w[0] for w in windows_of(items, 30, stride=15)] == [0, 15, 30, 45, 60]
    assert windows_of(items[:10], 30) == []
