"""Public mouse datasets: Balabit Mouse Dynamics Challenge and SapiMouse.

Official sources (archives are kept under ``data/``, gitignored, and read in
place without extracting):
- Balabit: https://github.com/balabit/Mouse-Dynamics-Challenge (no licence
  file; published by Balabit as a public research benchmark). 10 users.
  ``training_files/<user>/`` holds genuine sessions; ``test_files/<user>/``
  holds sessions labelled in ``public_labels.csv`` (``is_illegal`` 1 means an
  impostor used the account). Columns: record timestamp, client timestamp
  (seconds), button, state, x, y.
- SapiMouse: http://www.ms.sapientia.ro/~manyi/sapimouse/sapimouse.zip
  (Antal, Fejer and Buza, 2021). 120 users, a 3-minute and a 1-minute session
  each. Columns: client timestamp (ms), button, state, x, y. The authors note
  that some participants used a touchpad; this is not labelled per user.

Rows become ``PointerSample`` objects like the live system's: ``Move`` and
``Drag`` are movement, ``Pressed`` and ``Released`` are button press and
release (Left 0, Middle 1, Right 2); wheel rows and malformed rows are skipped.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Sequence
from pathlib import Path

from server.features.types import PointerSample

BALABIT_ZIP = Path("data/balabit/master.zip")
SAPIMOUSE_ZIP = Path("data/sapimouse/sapimouse.zip")
BALABIT_URL = "https://codeload.github.com/balabit/Mouse-Dynamics-Challenge/zip/refs/heads/master"
SAPIMOUSE_URL = "http://www.ms.sapientia.ro/~manyi/sapimouse/sapimouse.zip"

_BUTTONS = {"Left": 0, "Middle": 1, "Right": 2}
_MOVE_STATES = {"Move", "Drag"}


def parse_mouse_csv(text: str, seconds: bool) -> list[PointerSample]:
    """Pointer samples from one session file; ``seconds`` scales times to ms."""
    scale = 1000.0 if seconds else 1.0
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if not header:
        return []
    ti = header.index("client timestamp")
    bi, si, xi, yi = header.index("button"), header.index("state"), header.index("x"), header.index("y")
    out = []
    for row in reader:
        try:
            t = float(row[ti]) * scale
            button, state = row[bi], row[si]
            x, y = float(row[xi]), float(row[yi])
        except (IndexError, ValueError):
            continue
        if state in _MOVE_STATES:
            out.append(PointerSample(t, x, y, 3, None))
        elif state in ("Pressed", "Released") and button in _BUTTONS:
            out.append(PointerSample(t, x, y, 4 if state == "Pressed" else 5, _BUTTONS[button]))
    return out


def windows_of(items: Sequence, size: int, stride: int | None = None) -> list:
    stride = stride or size
    return [list(items[i : i + size]) for i in range(0, len(items) - size + 1, stride)]


def _read(z: zipfile.ZipFile, name: str) -> str:
    return z.read(name).decode("utf-8", errors="replace")


def load_balabit(path: Path = BALABIT_ZIP) -> dict:
    """Training sessions per user and labelled test sessions per user."""
    with zipfile.ZipFile(path) as z:
        names = [n for n in z.namelist() if not n.endswith("/")]
        root = names[0].split("/", 1)[0]
        labels = {}
        for row in csv.DictReader(io.StringIO(_read(z, f"{root}/public_labels.csv"))):
            labels[row["filename"]] = int(row["is_illegal"])
        train: dict[str, list[list[PointerSample]]] = {}
        test: dict[str, list[tuple[int, list[PointerSample]]]] = {}
        for n in names:
            parts = n.split("/")
            if len(parts) != 4 or not parts[3].startswith("session_"):
                continue
            kind, user, session = parts[1], parts[2], parts[3]
            if kind == "training_files":
                train.setdefault(user, []).append(parse_mouse_csv(_read(z, n), seconds=True))
            elif kind == "test_files" and session in labels:
                test.setdefault(user, []).append((labels[session], parse_mouse_csv(_read(z, n), seconds=True)))
    return {"train": train, "test": test}


def load_sapimouse(path: Path = SAPIMOUSE_ZIP) -> dict[str, dict[str, list[PointerSample]]]:
    """User to {"3min": samples, "1min": samples}."""
    out: dict[str, dict[str, list[PointerSample]]] = {}
    with zipfile.ZipFile(path) as z:
        for n in z.namelist():
            parts = n.split("/")
            if len(parts) != 3 or not parts[2].endswith(".csv"):
                continue
            which = "3min" if parts[2].endswith("_3min.csv") else "1min" if parts[2].endswith("_1min.csv") else None
            if which:
                out.setdefault(parts[1], {})[which] = parse_mouse_csv(_read(z, n), seconds=False)
    return out
