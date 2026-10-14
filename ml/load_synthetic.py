"""Load the synthetic cohort into a running AuthWho, through the real API path.

For a demonstration before volunteers are recorded: each synthetic person gives
consent (``PUT /v1/users``), each of their sessions is opened (``POST
/v1/sessions`` and a stream), and its events are sent as signed,
sequence-numbered batches exactly as the browser SDK would. The worker then
windows, enrolls, scores and records trust and decisions, so the dashboard shows
real timelines. Every account it creates is a synthetic person.

The user and session routes are not public in production, so run it inside the
deployment, for example:
    docker compose --env-file .env.production -f docker-compose.prod.yml exec api \\
        python -m ml.load_synthetic --api http://127.0.0.1:8000 --data /app/data/synthetic
Development:
    .venv/Scripts/python -m ml.load_synthetic --env-file .env
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import httpx

from ml.synthetic import load_session

MAX_EVENTS = 200


def batches_of(events: list) -> list[list]:
    return [events[i : i + MAX_EVENTS] for i in range(0, len(events), MAX_EVENTS)]


def _sign(key_b64url: str, body: bytes) -> str:
    key = base64.urlsafe_b64decode(key_b64url + "=" * (-len(key_b64url) % 4))
    return base64.urlsafe_b64encode(hmac.new(key, body, hashlib.sha256).digest()).rstrip(b"=").decode()


def _send_session(client: httpx.Client, app_key: str, user: dict, events: list, pace_s: float) -> int:
    h = {"X-AuthWho-App-Key": app_key}
    sid = client.post("/v1/sessions", headers=h, json={"user_id": user["user_id"], "app_id": "demo",
                                                         "role": "analyst"}).json()["session_id"]
    stream = client.post(f"/v1/sessions/{sid}/streams", headers=h).json()
    sent = 0
    for seq, chunk in enumerate(batches_of(events)):
        body = json.dumps({"v": 1, "session_id": sid, "stream_id": stream["stream_id"], "seq": seq,
                           "nonce": base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode(),
                           "sent_at": chunk[-1][1], "pointer_device": user["device"], "events": chunk}).encode()
        for _attempt in range(20):
            r = client.post("/v1/batches", content=body, headers={"Content-Type": "application/json",
                                                                  "X-AuthWho-Signature": _sign(stream["stream_key"], body)})
            if r.status_code != 429:
                break
            time.sleep(float(r.json().get("retry_after", 1)))
        r.raise_for_status()
        sent += 1
        if pace_s:
            time.sleep(pace_s)
    client.post(f"/v1/sessions/{sid}/end", headers=h, json={"reason": "logout"})
    return sent


def load_cohort_into(client: httpx.Client, data: Path, app_key: str, sessions_per_user: int = 6,
                     pace_s: float = 0.25, threads: int = 8) -> dict:
    data = Path(data)
    manifest = json.loads((data / "manifest.json").read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc).isoformat()
    for u in manifest["users"]:
        client.put(f"/v1/users/{u['user_id']}", headers={"X-AuthWho-App-Key": app_key}, json={
            "app_id": "demo", "role": "analyst", "consent_version": "1", "consent_at": now,
            "research_consent": False, "opt_outs": [], "pointer_device": u["device"]}).raise_for_status()

    def run(u: dict) -> tuple[int, int]:
        batches = 0
        for s in u["sessions"][:sessions_per_user]:
            batches += _send_session(client, app_key, u, load_session(data / u["user_id"] / s["file"]), pace_s)
        return len(u["sessions"][:sessions_per_user]), batches

    with ThreadPoolExecutor(max_workers=threads) as pool:
        results = list(pool.map(run, manifest["users"]))
    return {"users": len(manifest["users"]), "sessions": sum(r[0] for r in results),
            "batches": sum(r[1] for r in results)}


def main() -> None:
    from server.common.config import load_env_file

    ap = argparse.ArgumentParser(description="Load the synthetic cohort into a running AuthWho.")
    ap.add_argument("--api", default="http://127.0.0.1:8000")
    ap.add_argument("--data", default="data/synthetic")
    ap.add_argument("--sessions", type=int, default=6)
    ap.add_argument("--env-file")
    args = ap.parse_args()
    if args.env_file:
        load_env_file(args.env_file)
    with httpx.Client(base_url=args.api, timeout=30) as client:
        print(load_cohort_into(client, Path(args.data), os.environ["AUTHWHO_APP_API_KEY"], args.sessions))


if __name__ == "__main__":
    main()
