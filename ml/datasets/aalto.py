"""Aalto 136M keystrokes dataset (Dhakal et al., CHI 2018), offline use only.

Official source: https://userinterfaces.aalto.fi/136Mkeystrokes/ . The archive
``Keystrokes.zip`` is about 1.57 GB with one file per participant
(``Keystrokes/files/<id>_keystrokes.txt``). Licence: free for research and
non-commercial use with attribution to the authors.

To keep the laptop and this OneDrive folder light, the whole archive is never
downloaded. ``fetch_subset`` reads the zip's central directory through HTTP
range requests, picks a seeded random subset of participants and extracts only
their files into ``data/aalto/files/`` (gitignored).

Each participant file is tab-separated with a header row and the columns
PARTICIPANT_ID, TEST_SECTION_ID, SENTENCE, USER_INPUT, KEYSTROKE_ID,
PRESS_TIME, RELEASE_TIME, LETTER, KEYCODE (times in epoch milliseconds).
SENTENCE, USER_INPUT and LETTER contain text. ``parse_keystroke_file`` reads
each row, turns LETTER and KEYCODE into a key category and a key code, and
discards every text field immediately; nothing it returns contains text.

Usage:
    .venv/Scripts/python -m ml.datasets.aalto --n 500 --seed 0
"""

from __future__ import annotations

import argparse
import io
import json
import random
import re
import zipfile
from collections.abc import Callable
from pathlib import Path

from ml.datasets.presses import Press

ARCHIVE_URL = "https://userinterfaces.aalto.fi/136Mkeystrokes/data/Keystrokes.zip"
DEFAULT_DIR = Path("data/aalto")
_MEMBER = re.compile(r"(?:^|/)files/(\d+)_keystrokes\.txt$")

AaltoPress = Press

_MODIFIERS = {"SHIFT", "CTRL", "CONTROL", "ALT", "ALTGR", "ALT_GRAPH", "META", "CAPS_LOCK", "CAPSLOCK", "WIN", "CMD", "OS"}
_BACKSPACE = {"BKSP", "BACKSPACE", "DELETE", "DEL"}
_NAVIGATION = {"TAB", "HOME", "END", "PAGE_UP", "PAGE_DOWN", "PAGEUP", "PAGEDOWN"}
_MODIFIER_CODES = {16, 17, 18, 20, 91, 92, 93, 224, 225}
_NAVIGATION_CODES = {9, 33, 34, 35, 36, 37, 38, 39, 40}


def category_of(letter: str, keycode: int) -> int:
    """Map an Aalto LETTER and KEYCODE to the seven categories of section 5.

    A single produced character decides first, as the live SDK does with
    ``event.key``. Named special keys come next, and the JavaScript key code is
    the fallback when LETTER is empty (some participants lack it).
    """
    if len(letter) == 1:
        if letter == " ":
            return 3
        if letter.isalpha():
            return 1
        if letter.isdigit():
            return 2
        return 7
    name = letter.strip().upper()
    if name:
        if name in _MODIFIERS:
            return 5
        if name in _BACKSPACE:
            return 4
        if name in _NAVIGATION or name.startswith("ARROW"):
            return 6
        if name == "SPACE":
            return 3
        return 7
    if keycode == 32:
        return 3
    if keycode in (8, 46):
        return 4
    if keycode in _MODIFIER_CODES:
        return 5
    if keycode in _NAVIGATION_CODES:
        return 6
    if 65 <= keycode <= 90:
        return 1
    if 48 <= keycode <= 57 or 96 <= keycode <= 105:
        return 2
    return 7


def parse_keystroke_file(path: str | Path) -> list[list[Press]]:
    """Read one participant file into presses grouped by test section.

    Rows are split from the right so that tabs inside the sentence columns
    cannot shift the numeric fields. Rows with non-numeric times or codes, or
    with a release before the press, are skipped. Sections keep file order.
    """
    sections: dict[str, list[Press]] = {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        next(fh, None)  # header
        for line in fh:
            line = line.rstrip("\r\n")
            head = line.split("\t", 2)
            tail = line.rsplit("\t", 5)
            if len(head) < 3 or len(tail) < 6:
                continue
            section = head[1]
            _, press_s, release_s, letter, keycode_s = tail[1], tail[2], tail[3], tail[4], tail[5]
            try:
                down = float(press_s)
                up = float(release_s)
                keycode = int(keycode_s)
            except ValueError:
                continue
            if up < down:
                continue
            sections.setdefault(section, []).append(
                Press(category=category_of(letter, keycode), key_id=keycode, down_t=down, up_t=up)
            )
    return list(sections.values())


def select_participants(names: list[str], n: int, seed: int) -> list[str]:
    """A seeded, sorted random choice of ``n`` participant member names."""
    members = sorted(name for name in names if _MEMBER.search(name))
    if n > len(members):
        raise ValueError(f"only {len(members)} participant files available")
    return sorted(random.Random(seed).sample(members, n))


class RangeFile(io.RawIOBase):
    """A read-only, seekable file whose bytes come from a range fetcher.

    ``fetch(start, end)`` returns the inclusive byte range. Reads are served
    from aligned blocks of ``block_size`` bytes, cached in memory, so that the
    many small reads ``zipfile`` makes become a few requests.
    """

    def __init__(self, fetch: Callable[[int, int], bytes], size: int, block_size: int = 1 << 20, max_blocks: int = 64):
        self._fetch = fetch
        self._size = size
        self._block = block_size
        self._max_blocks = max_blocks
        self._cache: dict[int, bytes] = {}
        self._pos = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self._pos, io.SEEK_END: self._size}[whence]
        self._pos = max(0, base + offset)
        return self._pos

    def _block_at(self, index: int) -> bytes:
        if index not in self._cache:
            if len(self._cache) >= self._max_blocks:
                self._cache.pop(next(iter(self._cache)))
            start = index * self._block
            end = min(self._size, start + self._block) - 1
            data = self._fetch(start, end)
            if len(data) != end - start + 1:
                raise OSError("short range response")
            self._cache[index] = data
        return self._cache[index]

    def read(self, size: int = -1) -> bytes:
        if self._pos >= self._size:
            return b""
        end = self._size if size is None or size < 0 else min(self._size, self._pos + size)
        out = bytearray()
        while self._pos < end:
            index, offset = divmod(self._pos, self._block)
            chunk = self._block_at(index)[offset : offset + (end - self._pos)]
            out += chunk
            self._pos += len(chunk)
        return bytes(out)

    def readinto(self, buffer) -> int:
        data = self.read(len(buffer))
        buffer[: len(data)] = data
        return len(data)


def _http_range_file(url: str, block_size: int = 1 << 20) -> RangeFile:
    import httpx

    client = httpx.Client(timeout=120.0, follow_redirects=True)
    size = int(client.head(url).headers["content-length"])

    def fetch(start: int, end: int) -> bytes:
        r = client.get(url, headers={"Range": f"bytes={start}-{end}"})
        if r.status_code != 206:
            raise OSError(f"range request failed with HTTP {r.status_code}")
        return r.content

    return RangeFile(fetch, size=size, block_size=block_size)


def fetch_subset(n: int, seed: int, out_dir: Path = DEFAULT_DIR, url: str = ARCHIVE_URL) -> dict:
    """Extract a seeded subset of participant files from the official archive."""
    files_dir = out_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "subset.json"
    with zipfile.ZipFile(_http_range_file(url)) as zf:
        names = zf.namelist()
        chosen = select_participants(names, n=n, seed=seed)
        for name in chosen:
            target = files_dir / Path(name).name
            if not target.exists():
                tmp = target.with_suffix(".part")
                tmp.write_bytes(zf.read(name))
                tmp.replace(target)
    manifest = {
        "source": url,
        "seed": seed,
        "n_requested": n,
        "n_participant_files_in_archive": sum(1 for x in names if _MEMBER.search(x)),
        "files": [Path(x).name for x in chosen],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def load_subset(out_dir: Path = DEFAULT_DIR) -> dict[str, list[Press]]:
    """Participant id to presses in typing order, for the fetched subset."""
    manifest = json.loads((out_dir / "subset.json").read_text(encoding="utf-8"))
    out = {}
    for name in manifest["files"]:
        sections = parse_keystroke_file(out_dir / "files" / name)
        out[name.split("_", 1)[0]] = [p for section in sections for p in section]
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch a seeded subset of the Aalto 136M keystrokes dataset.")
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    manifest = fetch_subset(args.n, args.seed)
    print(f"fetched {len(manifest['files'])} of {manifest['n_participant_files_in_archive']} participant files")


if __name__ == "__main__":
    main()
