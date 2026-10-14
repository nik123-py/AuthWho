import base64
import hashlib
import hmac
import json

import httpx

from ml.load_synthetic import batches_of, load_cohort_into
from ml.synthetic import generate_cohort

KEY = base64.urlsafe_b64encode(b"s" * 32).rstrip(b"=").decode()


def test_batches_respect_size_limits():
    events = [[3, float(i), i, i] for i in range(1050)]
    batches = batches_of(events)
    assert [len(b) for b in batches] == [200] * 5 + [50]
    assert all(len(json.dumps(b)) < 64 * 1024 for b in batches)


def test_loader_consents_opens_sessions_and_sends_signed_ordered_batches(tmp_path):
    generate_cohort(tmp_path, n_users=2, seed=1)
    seen = {"put": [], "sessions": 0, "streams": 0, "batches": []}

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("X-AuthWho-App-Key") == "app-key" or request.url.path == "/v1/batches"
        path = request.url.path
        if request.method == "PUT" and path.startswith("/v1/users/"):
            seen["put"].append(json.loads(request.content))
            return httpx.Response(200, json={"user_id": path.rsplit("/", 1)[1]})
        if path == "/v1/sessions":
            seen["sessions"] += 1
            return httpx.Response(201, json={"session_id": f"00000000-0000-4000-8000-{seen['sessions']:012d}"})
        if path.endswith("/streams"):
            seen["streams"] += 1
            return httpx.Response(201, json={"stream_id": f"10000000-0000-4000-8000-{seen['streams']:012d}",
                                             "stream_key": KEY, "channels": {}, "pointer_device": "mouse"})
        if path.endswith("/end"):
            return httpx.Response(200, json={"status": "terminated"})
        if path == "/v1/batches":
            body = request.content
            key = base64.urlsafe_b64decode(KEY + "=")
            sig = base64.urlsafe_b64encode(hmac.new(key, body, hashlib.sha256).digest()).rstrip(b"=").decode()
            assert request.headers["X-AuthWho-Signature"] == sig
            seen["batches"].append(json.loads(body))
            return httpx.Response(202, json={"accepted": True})
        return httpx.Response(404)

    client = httpx.Client(transport=httpx.MockTransport(handle), base_url="http://api.test")
    summary = load_cohort_into(client, tmp_path, app_key="app-key", sessions_per_user=2, pace_s=0.0)
    assert summary == {"users": 2, "sessions": 4, "batches": len(seen["batches"])}
    assert all(p["consent_version"] == "1" and p["opt_outs"] == [] and p["research_consent"] is False for p in seen["put"])
    assert {p["pointer_device"] for p in seen["put"]} <= {"mouse", "touchpad"}
    by_stream = {}
    for b in seen["batches"]:
        by_stream.setdefault(b["stream_id"], []).append(b["seq"])
        assert all(isinstance(v, (int, float)) for e in b["events"] for v in e)
    assert len(by_stream) == 4 and all(seqs == list(range(len(seqs))) for seqs in by_stream.values())
