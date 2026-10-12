import io
import zipfile

import pytest

from ml.datasets.aalto import (
    AaltoPress,
    RangeFile,
    category_of,
    parse_keystroke_file,
    select_participants,
)

HEADER = "PARTICIPANT_ID\tTEST_SECTION_ID\tSENTENCE\tUSER_INPUT\tKEYSTROKE_ID\tPRESS_TIME\tRELEASE_TIME\tLETTER\tKEYCODE\n"


def _row(section, sentence, typed, ks_id, press, release, letter, keycode):
    return f"7\t{section}\t{sentence}\t{typed}\t{ks_id}\t{press}\t{release}\t{letter}\t{keycode}\n"


@pytest.mark.parametrize(
    ("letter", "keycode", "expected"),
    [
        ("a", 65, 1),
        ("Z", 90, 1),
        ("é", 0, 1),
        ("7", 55, 2),
        (" ", 32, 3),
        ("BKSP", 8, 4),
        ("DELETE", 46, 4),
        ("SHIFT", 16, 5),
        ("CTRL", 17, 5),
        ("CAPS_LOCK", 20, 5),
        ("ARROW_LEFT", 37, 6),
        ("TAB", 9, 6),
        ("ENTER", 13, 7),
        (".", 190, 7),
        ("", 65, 1),
        ("", 8, 4),
        ("", 16, 5),
        ("", 39, 6),
        ("", 32, 3),
        ("", 50, 2),
        ("", 112, 7),
    ],
)
def test_category_of(letter, keycode, expected):
    assert category_of(letter, keycode) == expected


def test_parse_keeps_only_categories_codes_and_times(tmp_path):
    secret_sentence = "The quick brown fox"
    text = HEADER
    text += _row(1, secret_sentence, "Th", 1, 1000, 1080, "SHIFT", 16)
    text += _row(1, secret_sentence, "Th", 2, 1050, 1120, "T", 84)
    text += _row(1, secret_sentence, "Th", 3, 1200, 1270, "h", 72)
    text += _row(2, "Second one", "S", 4, 5000, 5090, " ", 32)
    text += "garbage line without enough fields\n"
    text += _row(2, "Second one", "S", 5, "notanumber", 5190, "x", 88)
    path = tmp_path / "7_keystrokes.txt"
    path.write_text(text, encoding="utf-8")

    sections = parse_keystroke_file(path)

    assert [len(s) for s in sections] == [3, 1]
    first = sections[0]
    assert first[0] == AaltoPress(category=5, key_id=16, down_t=1000.0, up_t=1080.0)
    assert first[1] == AaltoPress(category=1, key_id=84, down_t=1050.0, up_t=1120.0)
    assert sections[1][0].category == 3
    for section in sections:
        for p in section:
            assert set(vars(p)) == {"category", "key_id", "down_t", "up_t"}
            assert all(isinstance(v, (int, float)) for v in vars(p).values())


def test_parse_drops_presses_with_release_before_press(tmp_path):
    text = HEADER + _row(1, "s", "a", 1, 2000, 1990, "a", 65) + _row(1, "s", "a", 2, 2100, 2180, "b", 66)
    path = tmp_path / "8_keystrokes.txt"
    path.write_text(text, encoding="utf-8")
    sections = parse_keystroke_file(path)
    assert [p.key_id for p in sections[0]] == [66]


def test_select_participants_is_seeded_and_sorted():
    names = [f"Keystrokes/files/{i}_keystrokes.txt" for i in range(100, 200)] + [
        "Keystrokes/files/metadata_participants.txt",
        "Keystrokes/readme.txt",
    ]
    a = select_participants(names, n=10, seed=3)
    b = select_participants(names, n=10, seed=3)
    c = select_participants(names, n=10, seed=4)
    assert a == b
    assert a != c
    assert len(a) == 10 and a == sorted(a)
    assert all(n.endswith("_keystrokes.txt") for n in a)


def test_range_file_reads_zip_members_through_ranges():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("Keystrokes/files/1_keystrokes.txt", "hello " * 1000)
        zf.writestr("Keystrokes/readme.txt", "readme")
    blob = buf.getvalue()
    calls = []

    def fetch(start, end):
        calls.append((start, end))
        return blob[start : end + 1]

    rf = RangeFile(fetch, size=len(blob), block_size=4096)
    with zipfile.ZipFile(rf) as zf:
        assert zf.read("Keystrokes/readme.txt") == b"readme"
        assert zf.read("Keystrokes/files/1_keystrokes.txt") == b"hello " * 1000
    assert calls, "reads must go through the range fetcher"
    assert all(e - s + 1 <= 4096 for s, e in calls)
