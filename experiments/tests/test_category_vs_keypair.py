import numpy as np

from experiments.category_vs_keypair import aalto_splits


def test_aalto_splits_halves_and_one_impostor_window_per_other_user():
    per_user = {
        "a": np.arange(9 * 2, dtype=float).reshape(9, 2),
        "b": 100 + np.arange(8 * 2, dtype=float).reshape(8, 2),
        "c": 200 + np.arange(10 * 2, dtype=float).reshape(10, 2),
    }
    splits = {s.subject: s for s in aalto_splits(per_user)}
    a = splits["a"]
    assert a.train.shape == (4, 2) and a.genuine.shape == (5, 2)
    assert np.array_equal(a.impostor, np.vstack([per_user["b"][:1], per_user["c"][:1]]))
    # training and genuine windows never overlap
    assert not set(map(tuple, a.train)) & set(map(tuple, a.genuine))
