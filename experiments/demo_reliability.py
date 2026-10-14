"""P5 success criterion: the live takeover demo works reliably.

Usage (Docker Compose up, Playwright and Chromium installed):
    .venv/Scripts/python -m experiments.demo_reliability --runs 10

Runs the end-to-end takeover scenario (enrol, another typist takes over, trust
falls below 75, adding a payee asks for a step-up, the genuine password passes)
``--runs`` times, each in a fresh pytest process with a fresh stack, and writes
every outcome and duration to experiments/results/demo_reliability.md and .json.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

OUT = Path("experiments/results")
TEST = "tests/e2e/test_authwho_e2e.py::test_takeover_step_up_passed_by_the_genuine_user"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=10)
    args = ap.parse_args()
    runs = []
    for i in range(1, args.runs + 1):
        start = time.perf_counter()
        proc = subprocess.run([sys.executable, "-m", "pytest", TEST, "-m", "e2e", "-q", "-p", "no:cacheprovider"],
                              capture_output=True, text=True)
        seconds = round(time.perf_counter() - start, 1)
        passed = proc.returncode == 0
        runs.append({"run": i, "passed": passed, "seconds": seconds})
        print(f"run {i}: {'passed' if passed else 'FAILED'} in {seconds} s", flush=True)
    ok = sum(r["passed"] for r in runs)
    result = {"experiment": "demo_reliability", "test": TEST, "runs": runs, "passed": ok, "total": len(runs),
               "finished_at": datetime.now(timezone.utc).isoformat()}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "demo_reliability.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    lines = ["# Live takeover demo reliability (P5)", "",
             f"Command: `python -m experiments.demo_reliability --runs {len(runs)}`. Each run starts the whole stack "
             f"and runs `{TEST}` in Chromium.", "",
             f"**{ok} of {len(runs)} runs passed.**", "", "| Run | Result | Seconds |", "|---|---|---|"]
    lines += [f"| {r['run']} | {'passed' if r['passed'] else 'failed'} | {r['seconds']} |" for r in runs]
    (OUT / "demo_reliability.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
