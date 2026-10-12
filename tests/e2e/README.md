# End-to-end tests

Playwright for Python tests that drive the demo app in a real Chromium browser against the whole AuthWho stack. All behaviour is scripted; no volunteer data and no real credentials are used.

## Scenarios

1. The SDK captures events in a real browser, and no captured event contains a typed character or the password.
2. The collector accepts a correctly signed batch and rejects a replayed (409) or tampered (401) one.
3. A simulated takeover: the user enrolls by typing in one rhythm, then a much slower typist continues. Trust falls below 75, adding a payee asks "Confirm it is you", and
   - the genuine password passes the check and the action succeeds;
   - three wrong answers end the session and record a critical decision.
4. A session with scrolling only is judged "insufficient signal": the action is allowed and no trust value is recorded.

## Running them

From the repository root on Windows, with Docker Desktop running:

```bash
docker compose up -d --wait
.venv/Scripts/python -m pip install -e ".[dev,e2e]"
.venv/Scripts/python -m playwright install chromium
npm run build -w sdk
.venv/Scripts/python -m pytest tests/e2e -m e2e
```

`tests/e2e/conftest.py` starts the AuthWho API (port 18000), the worker (enrollment after 5 windows), the demo backend (18100, temporary SQLite file) and the demo frontend (15173), and stops exactly those processes afterwards. The suite takes about three minutes. CI runs it in the `e2e` job.
