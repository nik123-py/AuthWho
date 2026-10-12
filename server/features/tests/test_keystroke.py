"""kf-1 keystroke features against a hand-computed window."""

import math

import numpy as np
import pytest

from server.features.keystroke import extract_keystroke
from server.features.schemas import KF1_NAMES
from server.features.types import KeyPress

LETTER, DIGIT, SPACE, BACKSPACE, MODIFIER, NAVIGATION, OTHER = 1, 2, 3, 4, 5, 6, 7

# A, B letters; C space; a 2.3 s pause; D, E backspaces; F letter pressed before E is released.
WINDOW = [
    KeyPress(LETTER, 0.0, 100.0),
    KeyPress(LETTER, 150.0, 230.0),
    KeyPress(SPACE, 300.0, 360.0),
    KeyPress(BACKSPACE, 2600.0, 2680.0),
    KeyPress(BACKSPACE, 2800.0, 2850.0),
    KeyPress(LETTER, 2840.0, 2900.0),
]


@pytest.fixture
def fv():
    return extract_keystroke(WINDOW)


def _f(fv, name):
    return fv.values[fv.names.index(name)]


def test_envelope(fv):
    assert fv.schema == "kf-1"
    assert fv.channel == "keystroke"
    assert fv.names == KF1_NAMES
    assert len(fv.values) == len(KF1_NAMES) == 35
    assert fv.n_actions == 6
    assert all(math.isfinite(v) for v in fv.values)


def test_dwell(fv):
    dwell = [100, 80, 60, 80, 50, 60]
    assert _f(fv, "dwell_mean") == pytest.approx(np.mean(dwell))
    assert _f(fv, "dwell_std") == pytest.approx(np.std(dwell))
    assert _f(fv, "dwell_median") == pytest.approx(70.0)
    assert _f(fv, "dwell_p10") == pytest.approx(np.percentile(dwell, 10))
    assert _f(fv, "dwell_p90") == pytest.approx(np.percentile(dwell, 90))


def test_flight_is_clipped(fv):
    flight = [50, 70, 2000, 120, -10]  # the 2240 ms flight is clipped to 2000
    assert _f(fv, "flight_mean") == pytest.approx(446.0)
    assert _f(fv, "flight_median") == pytest.approx(70.0)
    assert _f(fv, "flight_std") == pytest.approx(np.std(flight))


def test_down_down_latency(fv):
    dd = [150, 150, 2000, 200, 40]
    assert _f(fv, "dd_mean") == pytest.approx(np.mean(dd))
    assert _f(fv, "dd_median") == pytest.approx(150.0)


def test_rollover(fv):
    assert _f(fv, "rollover_rate") == pytest.approx(0.2)
    assert _f(fv, "overlap_mean") == pytest.approx(2.0)


def test_category_dwell_and_fill(fv):
    assert _f(fv, "dwell_letter") == pytest.approx(80.0)
    assert _f(fv, "dwell_space") == pytest.approx(60.0)
    assert _f(fv, "dwell_backspace") == pytest.approx(65.0)
    assert _f(fv, "dwell_digit") == pytest.approx(70.0)  # filled with dwell_median


def test_category_digraphs_and_fill(fv):
    assert _f(fv, "dg_letter_letter") == pytest.approx(150.0)
    assert _f(fv, "dg_letter_space") == pytest.approx(150.0)
    assert _f(fv, "dg_backspace_backspace") == pytest.approx(200.0)
    assert _f(fv, "dg_backspace_letter") == pytest.approx(40.0)
    assert _f(fv, "dg_space_letter") == pytest.approx(150.0)  # filled with dd_median


def test_corrections_and_rhythm(fv):
    assert _f(fv, "correction_rate") == pytest.approx(2 / 6)
    assert _f(fv, "correction_burst_len") == pytest.approx(2.0)
    assert _f(fv, "pause_rate") == pytest.approx(0.2)
    assert _f(fv, "hesitation_rate") == pytest.approx(0.0)
    # Four gaps under 2 s, 540 ms in total.
    assert _f(fv, "typing_rate") == pytest.approx(4 / 0.54)


def test_quality_drops_with_filled_features(fv):
    # Filled: dwell_digit, dwell_modifier and six category digraphs.
    assert fv.quality == pytest.approx(1 - 8 / 35)


def test_order_of_input_does_not_matter():
    shuffled = [WINDOW[i] for i in (3, 0, 5, 1, 4, 2)]
    assert extract_keystroke(shuffled).values == extract_keystroke(WINDOW).values


def test_no_corrections_fills_burst_length():
    fv = extract_keystroke([KeyPress(LETTER, 0, 90), KeyPress(LETTER, 120, 200)])
    assert _f(fv, "correction_rate") == 0.0
    assert _f(fv, "correction_burst_len") == 0.0
    assert fv.quality < 1.0


def test_needs_two_presses():
    with pytest.raises(ValueError):
        extract_keystroke([KeyPress(LETTER, 0, 90)])


def test_rejects_key_up_before_key_down():
    with pytest.raises(ValueError):
        extract_keystroke([KeyPress(LETTER, 100, 90), KeyPress(LETTER, 120, 200)])


def test_rejects_unknown_category():
    with pytest.raises(ValueError):
        extract_keystroke([KeyPress(9, 0, 90), KeyPress(LETTER, 120, 200)])


def test_vector_serialises_to_interface_json(fv):
    d = fv.to_dict()
    assert set(d) == {"schema", "channel", "names", "values", "n_actions", "quality"}
