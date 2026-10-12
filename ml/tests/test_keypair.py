import numpy as np
import pytest

from ml.datasets.presses import Press
from ml.keypair import KP1_NAMES, SHARED_NAMES, extract_category, extract_keypair
from server.features.schemas import KF1_NAMES

T, H, E, SPACE = 84, 72, 69, 32


def _seq():
    # "the the" with fixed timings: each press holds 100 ms, presses 200 ms apart.
    keys = [T, H, E, SPACE, T, H, E]
    cats = [1, 1, 1, 3, 1, 1, 1]
    return [Press(category=c, key_id=k, down_t=200.0 * i, up_t=200.0 * i + 100.0) for i, (k, c) in enumerate(zip(keys, cats))]


def test_shared_names_are_the_non_category_part_of_kf1():
    assert all(n in KF1_NAMES for n in SHARED_NAMES)
    assert not any(n.startswith(("dg_", "dwell_letter", "dwell_space")) for n in SHARED_NAMES)
    assert len(SHARED_NAMES) == 20


def test_category_variant_is_exactly_kf1():
    names, values = extract_category(_seq())
    assert names == KF1_NAMES
    assert len(values) == 35


def test_keypair_values_on_hand_built_sequence():
    vals = dict(zip(KP1_NAMES, extract_keypair(_seq())))
    assert len(KP1_NAMES) == 50
    assert vals["kdwell_84"] == pytest.approx(100.0)  # T
    assert vals["kdwell_32"] == pytest.approx(100.0)  # space
    assert vals["kdd_th"] == pytest.approx(200.0)
    assert vals["kdd_he"] == pytest.approx(200.0)
    # "in" never occurs: filled with the window's mean down-down latency
    assert vals["kdd_in"] == pytest.approx(vals["dd_mean"])
    # "o" never occurs: filled with the window's mean dwell
    assert vals["kdwell_79"] == pytest.approx(vals["dwell_mean"])


def test_keypair_uses_only_consecutive_presses():
    seq = _seq()
    # Make the gap between the two words long; "e" then "t" across the space is not a pair.
    vals = dict(zip(KP1_NAMES, extract_keypair(seq)))
    assert vals["kdd_te"] == pytest.approx(vals["dd_mean"])


def test_all_values_finite():
    assert np.all(np.isfinite(extract_keypair(_seq())))
