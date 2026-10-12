"""Metric tests against small cases computed by hand.

Convention: higher score means more genuine; a sample is accepted when its
score is greater than or equal to the threshold.
"""

import numpy as np
import pytest

from ml.metrics import bootstrap_ci, eer, far_frr, roc_auc


class TestFarFrr:
    def test_threshold_between_classes_gives_zero_errors(self):
        far, frr = far_frr(genuine=[3.0, 4.0], impostor=[1.0, 2.0], threshold=2.5)
        assert far == 0.0
        assert frr == 0.0

    def test_score_equal_to_threshold_is_accepted(self):
        # Impostor 2.0 >= 2.0 is accepted (1 of 2); genuine 1.0 < 2.0 is rejected (1 of 4).
        far, frr = far_frr(genuine=[1.0, 2.0, 3.0, 4.0], impostor=[2.0, 0.0], threshold=2.0)
        assert far == pytest.approx(0.5)
        assert frr == pytest.approx(0.25)

    def test_empty_input_raises(self):
        with pytest.raises(ValueError):
            far_frr(genuine=[], impostor=[1.0], threshold=0.0)


class TestEer:
    def test_perfect_separation_gives_zero(self):
        assert eer(genuine=[3.0, 4.0], impostor=[1.0, 2.0]) == pytest.approx(0.0)

    def test_crossing_exactly_at_an_operating_point(self):
        # t=1: FAR 1, FRR 0; t=2: FAR 1, FRR .5; t=3: FAR .5, FRR .5 -> EER .5
        assert eer(genuine=[1.0, 3.0], impostor=[2.0, 4.0]) == pytest.approx(0.5)

    def test_interpolates_between_adjacent_operating_points(self):
        # t=1: (FAR 1, FRR 0); t=2: (.5, 0); t=2.5: (.5, 1/3); t=3: (0, 1/3).
        # FAR-FRR goes 1/6 -> -1/3, so lambda = 1/3 and EER = .5 - .5/3 = 1/3.
        assert eer(genuine=[2.0, 3.0, 4.0], impostor=[1.0, 2.5]) == pytest.approx(1 / 3)

    def test_interpolates_when_both_rates_change(self):
        # t=0: (1, 0); t=1: (.5, 0); t=2: (0, .5). Midpoint of last segment: .25.
        assert eer(genuine=[1.0, 2.0], impostor=[1.0, 0.0]) == pytest.approx(0.25)

    def test_fully_inverted_scores_give_one(self):
        assert eer(genuine=[1.0, 2.0], impostor=[3.0, 4.0]) == pytest.approx(1.0)


class TestRocAuc:
    def test_hand_computed_with_tie(self):
        # Pairs (g, i): (1,0)=1, (1,1)=.5, (2,0)=1, (2,1)=1 -> 3.5 / 4
        assert roc_auc(genuine=[1.0, 2.0], impostor=[0.0, 1.0]) == pytest.approx(0.875)

    def test_perfect_separation(self):
        assert roc_auc(genuine=[3.0, 4.0], impostor=[1.0, 2.0]) == pytest.approx(1.0)


class TestBootstrapCi:
    def test_constant_values_give_degenerate_interval(self):
        low, high = bootstrap_ci([0.1, 0.1, 0.1], n_resamples=200, seed=0)
        assert low == pytest.approx(0.1)
        assert high == pytest.approx(0.1)

    def test_two_users_mean_interval_covers_extremes(self):
        # Resampled means of [0, 1] are 0 (p=.25), .5 (p=.5), 1 (p=.25),
        # so the 2.5th percentile is 0 and the 97.5th is 1.
        low, high = bootstrap_ci([0.0, 1.0], n_resamples=4000, confidence=0.95, seed=1)
        assert low == pytest.approx(0.0)
        assert high == pytest.approx(1.0)

    def test_narrow_confidence_lands_on_the_middle_mass(self):
        # 30th and 70th percentiles both fall inside the .5 mass (cumulative .25 to .75).
        low, high = bootstrap_ci([0.0, 1.0], n_resamples=4000, confidence=0.4, seed=1)
        assert low == pytest.approx(0.5)
        assert high == pytest.approx(0.5)

    def test_same_seed_is_reproducible_and_seed_matters(self):
        values = np.linspace(0, 1, 11)
        a = bootstrap_ci(values, n_resamples=300, seed=7)
        b = bootstrap_ci(values, n_resamples=300, seed=7)
        c = bootstrap_ci(values, n_resamples=300, seed=8)
        assert a == b
        assert a != c

    def test_custom_statistic(self):
        low, high = bootstrap_ci([2.0, 2.0], statistic=np.median, n_resamples=50, seed=0)
        assert (low, high) == (2.0, 2.0)
