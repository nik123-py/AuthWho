"""CMU keystroke benchmark loader and the Killourhy and Maxion protocol split."""

import numpy as np
import pytest

from ml.datasets.cmu import load_cmu, standard_protocol

HEADER = "subject,sessionIndex,rep,H.a,DD.a.b,UD.a.b,H.b"


def _write_fixture(path, n_subjects=3, n_sessions=2, n_reps=3):
    """Each feature value encodes subject, session and rep so splits can be checked."""
    lines = [HEADER]
    for s in range(n_subjects):
        for sess in range(1, n_sessions + 1):
            for rep in range(1, n_reps + 1):
                order = (sess - 1) * n_reps + rep
                vals = [s * 1000 + order, 0.5, -0.1, 0.2]
                lines.append(f"s{s:03d},{sess},{rep}," + ",".join(str(v) for v in vals))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def test_loader_reads_subjects_features_and_order(tmp_path):
    data = load_cmu(_write_fixture(tmp_path / "cmu.csv"))
    assert data.subjects == ["s000", "s001", "s002"]
    assert data.feature_names == ["H.a", "DD.a.b", "UD.a.b", "H.b"]
    assert data.X.shape == (18, 4)
    # Rows of one subject are in typing order: session first, then rep.
    first = data.X[data.subject == "s001", 0]
    assert first.tolist() == [1001, 1002, 1003, 1004, 1005, 1006]


def test_loader_rejects_missing_columns(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("subject,rep,H.a\ns000,1,0.1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="sessionIndex"):
        load_cmu(p)


def test_standard_protocol_split(tmp_path):
    data = load_cmu(_write_fixture(tmp_path / "cmu.csv"))
    splits = list(standard_protocol(data, n_train=4, n_impostor_reps=2))
    assert [s.subject for s in splits] == data.subjects
    s1 = splits[1]
    # Train on the first 4 reps, test on the remaining 2 of the same subject.
    assert s1.train[:, 0].tolist() == [1001, 1002, 1003, 1004]
    assert s1.genuine[:, 0].tolist() == [1005, 1006]
    # Impostors: the first 2 reps of every other subject.
    assert sorted(s1.impostor[:, 0].tolist()) == [1, 2, 2001, 2002]


def test_standard_protocol_needs_enough_reps(tmp_path):
    data = load_cmu(_write_fixture(tmp_path / "cmu.csv"))
    with pytest.raises(ValueError, match="repetitions"):
        list(standard_protocol(data, n_train=6))


def test_loader_on_real_file_if_present():
    from pathlib import Path

    path = Path("data/cmu/DSL-StrongPasswordData.csv")
    if not path.exists():
        pytest.skip("CMU dataset not downloaded")
    data = load_cmu(path)
    assert len(data.subjects) == 51
    assert data.X.shape == (20400, 31)
    assert np.all(np.isfinite(data.X))


def test_presses_rebuilt_from_timing_columns():
    from ml.datasets.cmu import CMU_KEYS, presses_from_row

    names = []
    values = []
    hold = {k: 0.08 + 0.001 * i for i, k in enumerate(CMU_KEYS)}
    for i, k in enumerate(CMU_KEYS):
        names.append(f"H.{k}")
        values.append(hold[k])
        if i + 1 < len(CMU_KEYS):
            nxt = CMU_KEYS[i + 1]
            names.append(f"DD.{k}.{nxt}")
            values.append(0.2)
            names.append(f"UD.{k}.{nxt}")
            values.append(0.2 - hold[k])
    presses = presses_from_row(np.array(values), names)

    assert len(presses) == len(CMU_KEYS) == 11
    assert presses[0].down_t == 0.0
    for i, p in enumerate(presses):
        assert p.down_t == pytest.approx(200.0 * i)
        assert p.up_t - p.down_t == pytest.approx(1000.0 * hold[CMU_KEYS[i]])
    cats = [p.category for p in presses]
    # . t i e 5 R o a n l Return
    assert cats == [7, 1, 1, 1, 2, 1, 1, 1, 1, 1, 7]
    assert len({p.key_id for p in presses}) == 11


def test_presses_rebuilt_reject_inconsistent_ud():
    from ml.datasets.cmu import CMU_KEYS, presses_from_row

    names, values = [], []
    for i, k in enumerate(CMU_KEYS):
        names.append(f"H.{k}")
        values.append(0.1)
        if i + 1 < len(CMU_KEYS):
            names += [f"DD.{k}.{CMU_KEYS[i + 1]}", f"UD.{k}.{CMU_KEYS[i + 1]}"]
            values += [0.2, 0.5]  # UD must equal DD - H
    with pytest.raises(ValueError):
        presses_from_row(np.array(values), names)
