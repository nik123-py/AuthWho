"""C1: strict batch and event schema (docs/interfaces.md sections 5 and 6)."""

import json

import pytest

from server.collector.schema import (
    CATEGORY_NAMES,
    EVENT_TYPES,
    MAX_EVENTS,
    SchemaError,
    TooLarge,
    channel_of,
    parse_json,
    validate_batch,
)

SID = "6f1c1d1e-3a3b-4c4d-8e8f-000000000001"
STID = "6f1c1d1e-3a3b-4c4d-8e8f-000000000002"
NONCE = "AAECAwQFBgcICQoLDA0ODw"  # 16 bytes, base64url without padding

VALID_EVENTS = [
    [1, 1201.3, 1, 0],
    [2, 1288.9, 1, 0],
    [3, 1300.0, 10, 20],
    [4, 1310.0, 10, 20, 0],
    [5, 1390.0, 10, 20, 0],
    [6, 1400.0, 0, -120, 0],
    [7, 1500.0, 0, 300],
    [8, 1600.0, 2, 1],
    [9, 1700.0, 2],
    [10, 1800.0, 0],
    [11, 1900.0, 3],
    [12, 2000.0, 4],
    [13, 2100.0, 1],
]


def batch(**overrides):
    body = {
        "v": 1,
        "session_id": SID,
        "stream_id": STID,
        "seq": 0,
        "nonce": NONCE,
        "sent_at": 2034.5,
        "pointer_device": "mouse",
        "events": VALID_EVENTS,
    }
    body.update(overrides)
    return body


def test_valid_batch_with_every_event_type_is_accepted():
    result = validate_batch(batch())
    assert result.seq == 0
    assert result.stream_id == STID
    assert result.events == VALID_EVENTS


def test_event_table_matches_contract():
    assert sorted(EVENT_TYPES) == list(range(1, 14))
    arity = {code: len(t.fields) for code, t in EVENT_TYPES.items()}
    assert arity == {1: 4, 2: 4, 3: 4, 4: 5, 5: 5, 6: 5, 7: 4, 8: 4, 9: 3, 10: 3, 11: 3, 12: 3, 13: 3}
    assert EVENT_TYPES[1].name == "KEY_DOWN"
    assert CATEGORY_NAMES == {1: "letter", 2: "digit", 3: "space", 4: "backspace",
                              5: "modifier", 6: "navigation", 7: "other"}
    assert [channel_of(c) for c in (1, 2, 3, 4, 5, 6, 13)] == [
        "keystroke", "keystroke", "pointer", "pointer", "pointer", "interaction", "interaction"]


def test_unknown_top_level_field_is_rejected():
    with pytest.raises(SchemaError, match="unknown field"):
        validate_batch(batch(text="hello"))


@pytest.mark.parametrize("missing", ["v", "session_id", "stream_id", "seq", "nonce", "sent_at",
                                     "pointer_device", "events"])
def test_missing_top_level_field_is_rejected(missing):
    body = batch()
    del body[missing]
    with pytest.raises(SchemaError):
        validate_batch(body)


@pytest.mark.parametrize("field,value", [
    ("v", 2), ("v", True), ("seq", -1), ("seq", 1.5), ("seq", True), ("seq", "0"),
    ("session_id", "not-a-uuid"), ("stream_id", 5), ("nonce", "short"), ("nonce", "A" * 40),
    ("sent_at", "x"), ("pointer_device", "pen"), ("events", {}), ("events", "[]"),
])
def test_bad_top_level_values_are_rejected(field, value):
    with pytest.raises(SchemaError):
        validate_batch(batch(**{field: value}))


@pytest.mark.parametrize("event", [[0, 1.0], [14, 1.0, 1], [99, 1.0, 1, 0], [-1, 1.0, 1]])
def test_unknown_event_code_is_rejected(event):
    with pytest.raises(SchemaError, match="unknown event code"):
        validate_batch(batch(events=[event]))


@pytest.mark.parametrize("event", [[1, 1.0, 1], [1, 1.0, 1, 0, 0], [3, 1.0, 1], [9, 1.0, 1, 1], []])
def test_wrong_arity_is_rejected(event):
    with pytest.raises(SchemaError):
        validate_batch(batch(events=[event]))


@pytest.mark.parametrize("bad", ["a", True, False, None, [1], {"k": 1}, float("nan"),
                                 float("inf"), float("-inf")])
def test_non_numeric_or_non_finite_elements_are_rejected(bad):
    with pytest.raises(SchemaError):
        validate_batch(batch(events=[[1, bad, 1, 0]]))


def test_event_that_is_not_a_list_is_rejected():
    with pytest.raises(SchemaError):
        validate_batch(batch(events=[{"code": 1}]))


@pytest.mark.parametrize("event", [
    [1, 1.0, 0, 0], [1, 1.0, 8, 0], [1, 1.0, 65, 0], [2, 1.0, 1.5, 0],  # category outside 1..7
    [1, 1.0, 1, -1], [1, 1.0, 1, 0.5],                                   # press_id
    [4, 1.0, 0, 0, 3],                                                   # button
    [8, 1.0, 0, 10], [10, 1.0, 2], [11, 1.0, 4], [6, 1.0, 0, 0, 3],      # enumerations
    [1.0, 1.0, 1, 0],                                                    # code must be an integer
])
def test_out_of_range_enumerations_are_rejected(event):
    with pytest.raises(SchemaError):
        validate_batch(batch(events=[event]))


def test_more_than_500_events_is_too_large():
    assert MAX_EVENTS == 500
    validate_batch(batch(events=[[10, 1.0, 1]] * 500))
    with pytest.raises(TooLarge):
        validate_batch(batch(events=[[10, 1.0, 1]] * 501))


def test_error_detail_never_echoes_event_values():
    secret = 987654.321
    for events in ([[1, secret, 99, 0]], [[1, secret, 1]], [[secret, 1.0]], [[1, 1.0, 1, 0], [42424242]]):
        with pytest.raises(SchemaError) as info:
            validate_batch(batch(events=events))
        detail = str(info.value)
        assert "987654" not in detail and "42424242" not in detail and "99" not in detail


def test_parse_json_rejects_nan_infinity_duplicates_and_bad_utf8():
    assert parse_json(b'{"a": [1, 2.5]}') == {"a": [1, 2.5]}
    for raw in (b'{"a": NaN}', b'{"a": Infinity}', b'{"a": -Infinity}', b'{"a": 1, "a": 2}',
                b"\xff\xfe", b"{not json", json.dumps([1, 2]).encode()):
        with pytest.raises(SchemaError):
            parse_json(raw)
