# End-to-end tests

This folder will hold the Playwright for Python end-to-end tests for AuthWho. They arrive in phase P4; until then it contains only this file.

## Scenarios planned

1. The SDK captures events in a real browser, and no captured event or batch contains a typed character.
2. The collector accepts a correctly signed batch and rejects a replayed, reordered or tampered one.
3. A simulated takeover drives the trust score down and triggers the TOTP step-up; a failed step-up ends the session.
4. An idle or scroll-only session reports insufficient signal, not a low score.
5. The dashboard shows each decision with its plain-language explanation.

All behaviour in these tests is synthetic or scripted. No volunteer data and no real credentials are ever committed or used.

## How they will be run

Tests are plain pytest tests using the `pytest-playwright` plugin and carry the `e2e` marker. Services start through Docker Compose and pytest fixtures; there is no separate server helper script.

From the repository root on Windows:

```bash
.venv/Scripts/python -m pip install -e ".[dev,e2e]"
.venv/Scripts/python -m playwright install chromium firefox
docker compose up -d --wait
.venv/Scripts/python -m pytest tests/e2e -m e2e --browser chromium --browser firefox
docker compose down -v
```

`tests/e2e` is not in the default pytest `testpaths`, so the path must be given explicitly. Only desktop browsers are targeted: Chromium and Firefox, plus Edge (`--browser-channel msedge`) where it is installed.

In CI the GitHub Actions workflow `.github/workflows/ci.yml` gains an `e2e` job in P4; a commented placeholder for it is already in the workflow.
