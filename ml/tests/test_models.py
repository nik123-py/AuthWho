"""One-class model interface, hand-computed cases and JSON round trips."""

import json

import numpy as np
import pytest
from sklearn.ensemble import IsolationForest
from sklearn.mixture import GaussianMixture
from sklearn.svm import OneClassSVM

from ml.models import (
    MODEL_CLASSES,
    GaussianMixtureModel,
    IsolationForestModel,
    OneClassSVMModel,
    ScaledManhattan,
    from_params,
)


@pytest.fixture
def data():
    rng = np.random.default_rng(42)
    train = rng.normal(loc=1.0, scale=0.2, size=(120, 5))
    genuine = rng.normal(loc=1.0, scale=0.2, size=(40, 5))
    impostor = rng.normal(loc=2.0, scale=0.2, size=(40, 5))
    return train, genuine, impostor


ALL_KINDS = sorted(MODEL_CLASSES)


def test_registry_lists_the_four_detectors():
    assert set(ALL_KINDS) == {"scaled_manhattan", "ocsvm", "gmm", "isolation_forest"}


@pytest.mark.parametrize("kind", ALL_KINDS)
class TestSharedInterface:
    def test_scores_one_value_per_row_and_ranks_genuine_higher(self, kind, data):
        train, genuine, impostor = data
        model = MODEL_CLASSES[kind]().fit(train)
        g, i = model.score(genuine), model.score(impostor)
        assert g.shape == (40,) and i.shape == (40,)
        assert np.all(np.isfinite(g)) and np.all(np.isfinite(i))
        assert g.mean() > i.mean()

    def test_json_round_trip_gives_identical_scores(self, kind, data):
        train, genuine, impostor = data
        model = MODEL_CLASSES[kind]().fit(train)
        text = json.dumps(model.to_params())
        restored = from_params(json.loads(text))
        assert type(restored) is type(model)
        X = np.vstack([genuine, impostor])
        assert np.array_equal(model.score(X), restored.score(X))

    def test_params_name_their_kind(self, kind, data):
        params = MODEL_CLASSES[kind]().fit(data[0]).to_params()
        assert params["model_kind"] == kind

    def test_score_before_fit_raises(self, kind, data):
        with pytest.raises(RuntimeError):
            MODEL_CLASSES[kind]().score(data[1])

    def test_wrong_feature_count_raises(self, kind, data):
        model = MODEL_CLASSES[kind]().fit(data[0])
        with pytest.raises(ValueError):
            model.score(data[1][:, :3])


def test_from_params_rejects_unknown_kind():
    with pytest.raises(ValueError):
        from_params({"model_kind": "pickle"})


def test_class_from_params_rejects_other_kind(data):
    params = ScaledManhattan().fit(data[0]).to_params()
    with pytest.raises(ValueError):
        GaussianMixtureModel.from_params(params)


class TestScaledManhattan:
    def test_hand_computed_scores(self):
        # mean = [1, 2]; mean absolute deviation = [1, 2]
        model = ScaledManhattan().fit(np.array([[0.0, 0.0], [2.0, 4.0]]))
        scores = model.score(np.array([[1.0, 2.0], [3.0, 2.0], [0.0, 0.0], [1.0, 8.0]]))
        assert scores == pytest.approx([0.0, -2.0, -2.0, -3.0])

    def test_constant_feature_uses_floor_instead_of_dividing_by_zero(self):
        model = ScaledManhattan(min_scale=0.5).fit(np.array([[1.0, 0.0], [1.0, 2.0]]))
        # feature 0: mean 1, scale floored to .5; feature 1: mean 1, scale 1
        assert model.score(np.array([[2.0, 1.0]])) == pytest.approx([-2.0])


class TestAgreementWithScikitLearn:
    def test_ocsvm_numpy_decision_matches_sklearn(self, data):
        train, genuine, impostor = data
        model = OneClassSVMModel(nu=0.1).fit(train)
        X = np.vstack([genuine, impostor])
        ref = OneClassSVM(kernel="rbf", nu=0.1, gamma="scale").fit(model._standardise(train))
        assert np.allclose(model.score(X), ref.decision_function(model._standardise(X)), atol=1e-10)

    def test_gmm_numpy_loglik_matches_sklearn(self, data):
        train, genuine, impostor = data
        model = GaussianMixtureModel(n_components=2, seed=3).fit(train)
        X = np.vstack([genuine, impostor])
        ref = GaussianMixture(
            n_components=2, covariance_type="full", reg_covar=model.reg_covar, random_state=3
        ).fit(model._standardise(train))
        assert np.allclose(model.score(X), ref.score_samples(model._standardise(X)), atol=1e-8)

    def test_isolation_forest_tree_export_matches_sklearn(self, data):
        train, genuine, impostor = data
        model = IsolationForestModel(n_estimators=50, seed=5).fit(train)
        X = np.vstack([genuine, impostor, train[:5]])
        ref = IsolationForest(n_estimators=50, random_state=5).fit(train)
        assert np.allclose(model.score(X), ref.score_samples(X), atol=1e-12)


@pytest.mark.parametrize("cls", [GaussianMixtureModel, IsolationForestModel])
def test_seeded_fit_is_deterministic(cls, data):
    a = cls(seed=11).fit(data[0]).score(data[2])
    b = cls(seed=11).fit(data[0]).score(data[2])
    assert np.array_equal(a, b)
