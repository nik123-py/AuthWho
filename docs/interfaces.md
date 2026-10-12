# AuthWho shared interfaces

Version 1. Owned by the orchestrator. Every agent builds against this file. A change to it is made only by the orchestrator, recorded in the change log at the bottom, and announced to the agents it affects.

Section references (for example "proposal Section 9") point to `AuthWho_Project_Proposal.tex`.

## 1. Repository layout and ownership

| Path | Owner | Contents |
|---|---|---|
| `sdk/` | sdk-engineer | TypeScript browser SDK |
| `server/collector/`, `server/features/`, `server/db/`, `server/worker/`, `server/api/`, `server/research/`, `server/common/` | backend-engineer | Collector, windowing and features, migrations and retention, pipeline worker, admin and query API with WebSocket, volunteer research export, shared config and crypto |
| `docker-compose.yml`, `.env.example` | backend-engineer | Local infrastructure |
| `server/policy/`, `server/session/` | policy-engineer | Policy engine, decisions, bot and replay heuristics, session state, exemptions |
| `demo_app/backend/` | policy-engineer | Demo web application API (login, TOTP, pages, high-risk actions) |
| `ml/`, `experiments/`, `data/` | ml-engineer | Dataset loaders, models, templates, scorers, trust engine, evaluation |
| `dashboard/`, `demo_app/frontend/` | frontend-engineer | Admin dashboard and demo web application UI |
| `tests/e2e/`, `.github/workflows/` | qa-engineer | Playwright end-to-end suite and CI |
| Root files, `docs/`, `PLAN.md`, `PROGRESS.md`, `README.md` | orchestrator | Root `pyproject.toml`, root `package.json` (npm workspaces), contracts, plans |

Python code is one importable tree: packages `server`, `ml` and `demo_app.backend`, configured by the root `pyproject.toml`. Python tests live next to the code they test (`server/**/tests/`, `ml/tests/`, `demo_app/backend/tests/`) and run with `.venv/Scripts/python -m pytest` from the repository root.

## 2. Services and ports (local)

| Service | Port | Notes |
|---|---|---|
| PostgreSQL 16 | 5432 | Docker Compose, named volume |
| Redis 7 | 6379 | Docker Compose, no persistence to disk (`--save "" --appendonly no`) so raw events never reach disk |
| AuthWho API (collector, admin API, WebSocket) | 8000 | `server.api.app:app` mounts the collector router and the admin router |
| AuthWho worker | none | `python -m server.worker` consumes Redis Streams |
| Demo app backend | 8100 | `demo_app.backend.app:app` |
| Demo app frontend | 5173 | Vite dev server |
| Admin dashboard | 5174 | Vite dev server |

Local development uses plain HTTP on `localhost`, which browsers treat as a secure context, so WebCrypto works. TLS is only needed for the stretch public deployment. All batch transport in the MVP is HTTPS-ready HTTP POST; WebSocket is used only for dashboard push.

## 3. Configuration and secrets

All secrets come from `.env` (gitignored). `.env.example` lists every variable with dummy values.

| Variable | Used by | Meaning |
|---|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | docker compose | Database container credentials |
| `AUTHWHO_DATABASE_URL` | server, worker | PostgreSQL connection string. Use `127.0.0.1`, not `localhost`: on Windows `localhost` tries IPv6 first and each connection waits about 5 s |
| `AUTHWHO_REDIS_URL` | server, worker | Redis connection string |
| `AUTHWHO_DATA_KEY` | server, worker | 32-byte key, base64, for AES-256-GCM encryption of window vectors and templates |
| `AUTHWHO_APP_API_KEY` | collector, demo backend | Server-to-server key the demo backend uses to create sessions and streams |
| `AUTHWHO_ADMIN_TOKEN` | admin API, dashboard | Bearer token for the admin API in the MVP |
| `AUTHWHO_CORS_ORIGINS` | collector | Comma-separated allowed browser origins |
| `AUTHWHO_COLLECTOR_URL` | demo backend | AuthWho API base URL, default `http://localhost:8000` |
| `DEMO_DB_PATH` | demo backend | SQLite file for demo users, default `data/demo/demo.sqlite` |
| `AUTHWHO_ENROLL_WINDOWS` | worker | Windows needed before a channel's profile is trained, default 20, minimum 5 |
| `DEMO_WITHDRAWAL_RETRY_SECONDS` | demo backend | Interval for retrying unconfirmed consent withdrawals, default 300, must be greater than zero |
| `DEMO_SECRET_KEY` | demo backend | Reserved for signing demo app values; login sessions use opaque server-side tokens |
| `DEMO_TOTP_KEY` | demo backend | 32-byte key, base64, encrypting stored TOTP secrets |
| `RESEARCH_EXPORT_KEY` | research export | 32-byte key, base64, encrypting volunteer research files |

## 4. Users, sessions and stream handshake

0. When a user gives, changes or withdraws consent, the demo backend calls the collector (header `X-AuthWho-App-Key`):
   - `PUT /v1/users/{user_id}` with body `{"app_id": "demo", "role": "analyst", "consent_version": "1", "consent_at": "<ISO 8601>", "research_consent": false, "opt_outs": ["interaction"], "pointer_device": "touchpad"}`. Response `200 {"user_id": "<uuid>"}`. Creates or updates the `users` row (section 12). Turning research consent off deletes the volunteer research folder first and returns `503 {"error": "deletion_incomplete"}` with `Retry-After` if that deletion could not be verified.
   - `DELETE /v1/users/{user_id}`. Response `204`. Withdrawal: deletes the user's row, profiles, windows, trust points and volunteer research folder, and ends their active streams. If any of that data could not be removed (for example a locked file), the response is `503 {"error": "deletion_incomplete"}` and the caller must retry; `204` is never returned while data remains. The demo backend keeps a durable `withdrawal_pending` flag and retries until it gets `204` or `404`.
   `POST /v1/sessions` for a user without a consent row returns `409 {"error": "no_consent"}`.
1. The user logs in to the demo app. The demo backend calls the collector:
   `POST /v1/sessions` with header `X-AuthWho-App-Key`, body
   `{"user_id": "<uuid>", "app_id": "demo", "role": "analyst"}`.
   Response `201 {"session_id": "<uuid>"}`.
   `user_id` is a pseudonymous UUID. AuthWho never receives usernames, emails or passwords.
2. On every page load the demo frontend asks its own backend for a stream, and the demo backend calls
   `POST /v1/sessions/{session_id}/streams` with `X-AuthWho-App-Key`.
   Response `201 {"stream_id": "<uuid>", "stream_key": "<base64url, 32 bytes>", "expires_at": "<ISO 8601>", "channels": {"keystroke": true, "pointer": true, "interaction": true}, "pointer_device": "mouse" | "touchpad" | "unknown"}`.
   `channels` already reflects the user's opt-outs and exemptions; the SDK must not capture a disabled channel.
3. The stream key lives only in page memory and in Redis hot state (`aw:stream:{stream_id}`, TTL 24 h). It is never written to PostgreSQL, logs or browser storage.

Pointing device type: browsers report both mice and touchpads as `pointerType: "mouse"`, so the device cannot be detected reliably. The user declares it in the consent and enrollment flow (mouse or touchpad), it is stored with the user, and it can be changed per session. This is a ruling, see `PLAN.md`.

## 5. Event schema (SDK to collector)

Every event is a JSON array of finite numbers only. No event ever contains a string, boolean, object or null. This makes the "no characters" rule mechanically testable: the test asserts that every element of every event is a finite number, and that no typed text appears anywhere in the serialised batch.

Times `t` are milliseconds since the stream started, taken from the browser's `event.timeStamp` (same clock as `performance.now()`) minus the stream start, rounded to 0.1 ms. An event stamped just before the stream started may have a small negative `t`; the collector accepts any finite value. Coordinates are viewport CSS pixels, rounded to integers.

| Type | Code | Layout | Channel |
|---|---|---|---|
| KEY_DOWN | 1 | `[1, t, category, press_id]` | keystroke |
| KEY_UP | 2 | `[2, t, category, press_id]` | keystroke |
| POINTER_MOVE | 3 | `[3, t, x, y]` | pointer |
| POINTER_DOWN | 4 | `[4, t, x, y, button]` | pointer |
| POINTER_UP | 5 | `[5, t, x, y, button]` | pointer |
| WHEEL | 6 | `[6, t, delta_x, delta_y, delta_mode]` | interaction |
| SCROLL | 7 | `[7, t, scroll_x, scroll_y]` (throttled to one per 100 ms) | interaction |
| FIELD_FOCUS | 8 | `[8, t, field_index, field_kind]` | interaction |
| FIELD_BLUR | 9 | `[9, t, field_index]` | interaction |
| VISIBILITY | 10 | `[10, t, state]` (1 visible and focused, 0 hidden or blurred) | interaction |
| CLIPBOARD | 11 | `[11, t, action]` (1 copy, 2 cut, 3 paste; occurrence only, never content) | interaction |
| PAGE | 12 | `[12, t, page_code]` | interaction |
| ACTION_MARK | 13 | `[13, t, action_code]` (the app marks the start of a sensitive action) | interaction |

Key categories (`category`):

| Code | Category | Keys |
|---|---|---|
| 1 | letter | Any single produced character that is a Unicode letter |
| 2 | digit | Any single produced character that is a Unicode digit |
| 3 | space | Space bar |
| 4 | backspace | Backspace and Delete (corrections) |
| 5 | modifier | Shift, Control, Alt, AltGraph, Meta, CapsLock |
| 6 | navigation | Arrow keys, Home, End, PageUp, PageDown, Tab |
| 7 | other | Everything else: Enter, Escape, punctuation, symbols, function keys, IME composition, unidentified keys |

Rules for the SDK:
- The key identifier is read only inside one pure function that returns the category code. It is never stored, logged or sent.
- `press_id` is a per-stream counter that increases by one on every non-repeat key-down; the matching key-up carries the same `press_id`. It lets the server pair presses and detect rollover without knowing which key it was.
- Auto-repeat key-downs (`event.repeat === true`) are dropped.
- Keystrokes inside `input[type=password]` and inside any element with `data-authwho="ignore"` are not captured at all, because the category sequence of a password reveals its composition. Pointer events there are still captured.
- `field_index` is the element's position among the page's form controls in document order; `field_kind` is 1 text, 2 password, 3 email, 4 number, 5 textarea, 6 select, 7 checkbox or radio, 8 button, 9 other. No field names, ids or values are ever read into events.
- `button` is 0 primary, 1 middle, 2 secondary. `delta_mode` is the DOM `WheelEvent.deltaMode`.
- `page_code` and `action_code` are integers the host application passes to `setPage()` and `markAction()`; their meaning is kept in the demo app's registry, not in the SDK.

## 6. Batch format and signing

`POST /v1/batches`, `Content-Type: application/json`, header `X-AuthWho-Signature: <base64url HMAC-SHA256(stream_key, raw_body_bytes)>`.

```json
{
  "v": 1,
  "session_id": "<uuid>",
  "stream_id": "<uuid>",
  "seq": 0,
  "nonce": "<base64url, 16 random bytes>",
  "sent_at": 2034.5,
  "pointer_device": "mouse",
  "events": [[1, 1201.3, 1, 0], [2, 1288.9, 1, 0]]
}
```

- The SDK serialises the body once, signs those exact bytes with WebCrypto, and sends those exact bytes. The server verifies the HMAC over the raw request body before parsing.
- `seq` starts at 0 for each stream and must equal the last accepted `seq + 1`. The SDK flushes every 2 s or at 200 events, whichever comes first, and on `visibilitychange` to hidden using `fetch` with `keepalive`. Limits: at most 500 events and 64 KiB per batch.
- Unknown top-level fields, unknown event codes, wrong arity or non-numeric event elements are rejected.
- SDK delivery rules: `seq` advances only when a batch is accepted (202, or 409 `duplicate`). A batch rejected with 400, 413 or another 409 reason is dropped and the next batch reuses its `seq`. A 401 ends delivery for the stream. Network errors, 408 and 5xx are retried with the identical body, backing off from 1 s to 30 s. After `stop()` each batch gets at most three attempts. `pagehide` and `visibilitychange` to hidden both trigger a keepalive flush.

Responses:

| Status | Body | Meaning |
|---|---|---|
| 202 | `{"accepted": true, "seq": n}` | Stored in the Redis stream |
| 400 | `{"error": "schema", "detail": "..."}` | Schema violation (detail never echoes event values) |
| 401 | `{"error": "signature"}` or `{"error": "unknown_stream"}` | Bad signature, unknown or expired stream |
| 409 | `{"error": "replay", "reason": "duplicate" \| "out_of_order" \| "nonce_reused"}` | Rejected replayed, reordered or reused batch. A client retrying its own last batch treats `duplicate` as success |
| 413 | `{"error": "too_large"}` | Batch over limits |
| 429 | `{"error": "rate_limited", "retry_after": s}` | Per-stream rate limit (default 5 batches per second, burst 20) |

Other collector errors: `401 {"error": "unauthorized"}` (missing or wrong app key), `404 {"error": "unknown_session"}`, `409 {"error": "session_ended"}`, `400 {"error": "schema"}` for invalid bodies on the user and session endpoints. Event values outside the enumerations above (for example `button` 3) are rejected. Events from opted-out or exempt channels are dropped by the server as a second line of defence, and changing opt-outs updates live streams.

## 7. Redis keys and streams

| Key | Type | Contents | Retention |
|---|---|---|---|
| `aw:events` | Stream | One entry per accepted batch: `session_id`, `stream_id`, `seq`, `received_at`, `pointer_device`, `events` (the JSON event array) | Every `XADD` uses exact `MINID <now minus 24 h>` (the approximate `~` form was shown to leave old entries), and the retention job also runs `XTRIM` so the limit holds when no batches arrive. Consumer groups `features` and `research` |
| `aw:stream:{stream_id}` | Hash | Stream key, session id, user id, last seq, channels, pointer device, expiry | TTL 24 h |
| `aw:nonce:{stream_id}` | Set | Seen nonces | TTL 24 h |
| `aw:rate:{stream_id}` | String | Rate-limit counter | TTL a few seconds |
| `aw:session:{session_id}` | Hash | Hot session state: status (`active`, `step_up_required`, `terminated`), last trust update | TTL 24 h after last activity |
| `aw:trust` | Pub/Sub channel | Trust updates and decisions for the dashboard WebSocket (section 10) | Not stored |

Raw event batches exist only in `aw:events`. They are never copied to PostgreSQL, application logs or files, with one exception: the volunteer research export (section 12).

## 8. Windows and feature vectors

The worker (`server/worker/`) reads `aw:events`, rebuilds per-session, per-channel action sequences, and cuts overlapping windows by action count:

| Channel | Unit | Window size | Stride |
|---|---|---|---|
| keystroke | completed key press (paired KEY_DOWN and KEY_UP) | 50 presses | 25 |
| pointer | stroke: pointer movement ending in a click or a pause over 300 ms | 30 strokes | 15 |
| interaction | interaction event (codes 6 to 13) | 20 events | 10 |

Feature extraction is pure Python in `server/features/` with no I/O, so that `ml/` calls the same functions on public datasets. The normalised inputs are:

```python
KeyPress(category: int, down_t: float, up_t: float)            # one per press_id
PointerSample(t: float, x: float, y: float, kind: int, button: int | None)  # kind: 3 move, 4 down, 5 up
InteractionEvent(code: int, t: float, values: tuple[float, ...])
```

Each extractor returns a `FeatureVector`:

```json
{
  "schema": "kf-1",
  "channel": "keystroke",
  "names": ["dwell_mean", "dwell_std", "..."],
  "values": [92.1, 18.4],
  "n_actions": 50,
  "quality": 1.0
}
```

- Schemas are versioned: `kf-1` (keystroke), `pf-1` (pointer), `if-1` (interaction). The ordered name list for each schema is a constant in `server/features/schemas.py`. Changing names or order requires a new schema version.
- Values are always finite. A sub-feature with no data in the window (for example no backspaces) is filled by the rule documented next to its name, and `quality` drops below 1.0 in proportion to the share of filled features.
- Keystroke features (`kf-1`, 35 values, defined with their fill rules in `server/features/keystroke.py`) cover dwell, flight (key-up to next key-down, clipped to [-500, 2000] ms), down-down latency, rollover rate and overlap, correction rate and correction rhythm, category-level digraph latencies (for example letter to space, letter to backspace), typing rate and pause rate.
- Pointer features (`pf-1`) cover per-stroke duration, path length, efficiency (straight distance over path length), velocity, acceleration, jerk, curvature and angle change, pauses, pre-click pause and click hold time, aggregated over the window.
- Interaction features (`if-1`) cover scroll rate and direction changes, field focus order and focus duration, hesitation before marked sensitive actions, clipboard use rate, visibility changes and navigation rate.

Window store (PostgreSQL table `windows`):

| Column | Type | Notes |
|---|---|---|
| `window_id` | uuid | Primary key |
| `session_id`, `stream_id`, `user_id` | uuid | `stream_id` is needed because `start_t` and `end_t` are relative to the stream |
| `channel` | text | `keystroke`, `pointer`, `interaction` |
| `pointer_device` | text | `mouse`, `touchpad`, `unknown` |
| `schema` | text | For example `kf-1` |
| `start_t`, `end_t` | double precision | Stream-relative ms |
| `n_actions` | int | |
| `quality` | real | |
| `features_enc` | bytea | AES-256-GCM over the JSON `values` array with `AUTHWHO_DATA_KEY`; the 16 bytes of `window_id` are the associated data |
| `extractor_version` | text | |
| `created_at` | timestamptz | Rows older than 30 days are deleted by the retention job |

## 9. Profiles, scoring and trust

Profile template (table `profiles`, migration `0005`): one active template per user, channel and device key, where the device key is the pointer device type for the pointer channel and `any` for keystroke and interaction. The template is the JSON document built by `ml/profile.py` (model parameters, per-feature mean and deviation, and a per-user calibration set), encrypted with the `profile_id` bytes as associated data.

| Column | Type | Notes |
|---|---|---|
| `profile_id` | uuid | |
| `user_id` | uuid | |
| `channel`, `pointer_device` | text | |
| `version` | int | Increases on re-enrollment; activating a new version deletes the old one |
| `model_kind` | text | `scaled_manhattan`, `ocsvm`, `gmm` |
| `template_enc` | bytea | AES-256-GCM over a JSON document of model parameters and window-feature summary statistics. Never pickle |
| `n_windows` | int | Enrollment windows used |
| `created_at` | timestamptz | Kept until re-enrollment or account deletion |

Enrollment: a channel is enrolled once the user has at least 20 windows on that channel (and device type) from consented sessions (`AUTHWHO_ENROLL_WINDOWS`, minimum 5, may lower this for demos). Until then the channel's status is `no_profile`. Scores are calibrated per user: `score` is the share of the user's own cross-validated enrollment scores at or below the window's raw score, so genuine windows score roughly uniformly in (0, 1) (ruling R14).

Channel score (output of `ml` scorers, one per window):

```json
{
  "session_id": "<uuid>", "window_id": "<uuid>", "channel": "keystroke",
  "status": "scored",
  "score": 0.82,
  "confidence": 0.7,
  "model_kind": "scaled_manhattan", "model_version": "ks-sm-1",
  "top_features": [{"name": "flight_mean", "z": 2.4}]
}
```

- `status` is one of `scored`, `no_profile`, `opted_out`, `low_quality`. Only `scored` carries `score` and `confidence`; the others carry `null`.
- `score` is in [0, 1], where 1 means "matches the enrolled profile". `confidence` is in [0, 1] and grows with evidence (actions, quality).
- `top_features` lists up to three features with their deviation in profile standard deviations, for explanations.

Trust update (output of the `ml` trust engine, one per session after each scored window or freshness timeout):

```json
{
  "v": 1,
  "session_id": "<uuid>", "user_id": "<uuid>",
  "at": "<ISO 8601>", "seq": 17,
  "state": "scored",
  "trust": 64.0,
  "confidence": 0.81,
  "channels": {
    "keystroke": {"status": "scored", "score": 0.31, "confidence": 0.8, "window_id": "<uuid>", "fresh": true, "top_features": []},
    "pointer": {"status": "scored", "score": 0.44, "confidence": 0.6, "window_id": "<uuid>", "fresh": true, "pointer_device": "mouse", "top_features": []},
    "interaction": {"status": "no_profile", "score": null, "confidence": null, "window_id": null, "fresh": false, "top_features": []}
  },
  "bot_flags": [],
  "model_versions": {"keystroke": "ks-sm-1", "pointer": "pt-sm-1", "trust": "trust-pr-1"}
}
```

- `trust` is in [0, 100], higher means more likely the enrolled user. It starts at 100 when the session starts (the user has just passed login and MFA) and moves with the penalty-and-reward rule (Mondal and Bours) applied to evidence-weighted channel scores.
- `state` is `scored` or `insufficient_signal`. It is `insufficient_signal` when no channel has a fresh `scored` window (fresh means the window ended within the last 120 s). In that state `trust` and `confidence` are `null` in the message, so no consumer can act on a stale or guessed number. The engine keeps its internal running value for when evidence returns.
- Trust updates are stored in table `trust_points` (`session_id`, `user_id`, `seq`, `at`, `state`, `trust`, `confidence`, and the whole update as `payload`) for the dashboard timeline and incident reports, and deleted after 30 days, the same as the windows they derive from. Each update is also published on `aw:trust` as `{"type": "trust", "data": <update>}` and kept as `last_trust` in `aw:session:{session_id}`.
- Trust update constants: TAU 0.25, REWARD 5, PENALTY 10; channel weights keystroke 1, pointer 1, interaction 0.5 (`ml/trust.py`, ruling R13). A channel whose user opted out reports status `opted_out`.

## 10. Bot and replay flags

```json
{"kind": "timing_regularity", "severity": "high", "evidence": "keystroke flight std 0.4 ms over 50 presses"}
```

`kind` is one of `timing_regularity`, `implausible_motion`, `replay_match` (near-exact match to one of the user's stored windows from the last 30 days), `population_like` (closer to the population average than to the user). `severity` is `low`, `medium` or `high`. `evidence` is a short sentence with numbers, never raw events. A `high` severity `timing_regularity` or `implausible_motion` flag counts as confirmed automation.

## 11. Policy, decisions and session control

Trust levels (proposal Section 7) and default thresholds, all editable per app, role and action in the `policies` table:

| Level | Default rule | Outcome |
|---|---|---|
| `insufficient_signal` | `state` is `insufficient_signal`, or every channel is opted out, exempt or without a profile | `continue` under normal session rules |
| `high_confidence` | trust at least 75 and no channel below 0.5 | `continue` |
| `moderate_deviation` | trust from 50 to 75, or exactly one fresh channel below 0.5 | `monitor`; actions with sensitivity `high` require `step_up` |
| `strong_deviation` | trust below 50 with two or more channels below 0.5, or a `replay_match` or `population_like` flag of medium or high severity | `step_up` before continuing |
| `critical` | confirmed automation, or a failed step-up while in strong deviation | `terminate` (block the pending action and end the session) |

Action sensitivity is `low`, `medium` or `high`. In the demo app, "add payee" and "export report" are `high`.

Decision record (table `decisions`, append-only, 90 days):

| Column | Type | Notes |
|---|---|---|
| `decision_id` | uuid | |
| `session_id`, `stream_id`, `user_id` | uuid | `stream_id` is needed because `start_t` and `end_t` are relative to the stream |
| `app_id`, `role` | text | |
| `created_at` | timestamptz | |
| `trigger` | text | `trust_update`, `action_request`, `step_up_result` |
| `action_code` | text, nullable | For example `add_payee` |
| `action_sensitivity` | text, nullable | |
| `level` | text | One of the five levels |
| `outcome` | text | `continue`, `monitor`, `step_up`, `terminate` |
| `action_allowed` | boolean, nullable | |
| `trust`, `confidence` | real, nullable | Null for insufficient signal |
| `channels` | jsonb | The per-channel block from the trust update |
| `bot_flags` | jsonb | |
| `window_ids` | uuid[] | Windows behind the decision |
| `model_versions` | jsonb | |
| `policy_version` | text | |
| `explanation` | text | One plain-language sentence, for example "Typing rhythm and mouse speed both diverged from this user's profile for 40 seconds." |
| `step_up_result` | text, nullable | `passed`, `failed` |

A database trigger rejects every `UPDATE` and rejects `DELETE` unless the session setting `authwho.retention` is `on`, which only the retention job sets.

Session control API (called by the demo backend with `X-AuthWho-App-Key`):

| Endpoint | Body | Response |
|---|---|---|
| `GET /v1/sessions/{id}/status` | | `{"status": "active" \| "step_up_required" \| "terminated", "decision_id": "<uuid>" \| null}` |
| `POST /v1/sessions/{id}/actions` | `{"action_code": "add_payee", "sensitivity": "high"}` | `{"decision_id", "outcome", "action_allowed", "explanation_for_user"}` |
| `POST /v1/sessions/{id}/step-up-result` | `{"passed": true}` | `{"decision_id", "outcome", "status"}` |
| `POST /v1/sessions/{id}/end` | `{"reason": "logout"}` | `{"status": "terminated"}`. Implemented in the collector from P0: marks the session ended and deletes its stream keys at once, so later batches get 401 `unknown_stream`. Idempotent |

`explanation_for_user` is a neutral sentence such as "Please confirm it is you." It never reveals scores, channels or features to the session operator. The demo backend runs the TOTP check itself with pyotp and reports only the result. Nothing in this API can disable, lock or delete an account.

## 12. Users, consent and volunteer research export

Table `users`: `user_id` (uuid), `app_id`, `role`, `consent_version`, `consent_at`, `research_consent` (boolean), `research_consent_at` (set when research consent is turned on, cleared when it is turned off; only batches received at or after it are exported), `opt_outs` (text array of channels), `exempt` (boolean, set per user or inherited from a role exemption), `pointer_device`, `created_at`. Deleting a user deletes their profiles, windows and trust points; decisions are pseudonymous and expire after 90 days.

The `sessions` table (`session_id`, `user_id`, `app_id`, `role`, `status`, `created_at`, `ended_at`) holds no behavioural data and is deleted after 90 days, like decisions.

Volunteer research export (`server/research/`): a separate consumer, `python -m server.research`, reads `aw:events` with its own consumer group `research`. Only for users with `research_consent = true`, it appends each raw batch to an AES-256-GCM encrypted file under `data/volunteer/<pseudonymous id>/` using `RESEARCH_EXPORT_KEY`. This is the only place raw events leave Redis, matching the "volunteer research dataset" row of proposal Section 9. A withdrawal deletes the user's folder. `data/` is gitignored.

## 13. Admin API and WebSocket (dashboard)

All admin endpoints need `Authorization: Bearer <AUTHWHO_ADMIN_TOKEN>`.

| Endpoint | Response |
|---|---|
| `GET /v1/admin/sessions` | List of sessions with user, app, status, latest level, latest trust or "Cannot determine" |
| `GET /v1/admin/sessions/{id}/timeline` | Trust points for the session |
| `GET /v1/admin/sessions/{id}/decisions` | Decision records |
| `GET /v1/admin/sessions/{id}/incident-report` | JSON report: timeline, decisions, contributing features, confidence |
| `GET /v1/admin/policies`, `PUT /v1/admin/policies/{policy_id}` | Policy thresholds, action sensitivities, exemptions |
| `WS /v1/admin/ws?token=...` | Server pushes `{"type": "trust", "data": <trust update>}` and `{"type": "decision", "data": <decision record>}` |

## 14. SDK public API

Package `@authwho/sdk` (npm workspace `sdk/`). Its `package.json` `exports` points at `./src/index.ts`, so Vite apps in the workspace import the TypeScript source directly; `npm run build -w sdk` also produces an ESM bundle in `sdk/dist/`.

```ts
export type Channel = "keystroke" | "pointer" | "interaction";
export type PointerDevice = "mouse" | "touchpad" | "unknown";

export interface AuthWhoConfig {
  endpoint: string;                 // collector base URL, for example "http://localhost:8000"
  sessionId: string;
  streamId: string;
  streamKey: string;                // base64url, 32 bytes
  channels: Record<Channel, boolean>;
  pointerDevice: PointerDevice;
  flushIntervalMs?: number;         // default 2000
  maxBatchEvents?: number;          // default 200
  root?: Document;                  // default window.document; injectable for tests
  fetchImpl?: typeof fetch;         // injectable for tests
  now?: () => number;               // injectable clock, default performance.now
}

export interface AuthWhoHandle {
  setPage(pageCode: number): void;
  markAction(actionCode: number): void;
  flush(): Promise<void>;
  stop(): Promise<void>;            // flushes, then removes every listener
}

export function start(config: AuthWhoConfig): AuthWhoHandle;
export function categoryOf(e: KeyboardEvent): number;   // exported for tests only
```

## 15. Demo app API (demo backend, port 8100)

The demo frontend calls these under the relative path `/api`; its Vite dev server proxies `/api` to `http://localhost:8100`, so the session cookie is same-origin. Demo users live in the demo app's own SQLite database (`DEMO_DB_PATH`, default `data/demo/demo.sqlite`), separate from AuthWho. Login sessions are opaque random tokens in an `HttpOnly`, `SameSite=Lax` cookie `demo_session`, stored server-side.

| Endpoint | Body | Response |
|---|---|---|
| `POST /api/register` | `{"username", "password"}` | `201 {"username"}`; `409` if taken. Passwords hashed with `hashlib.scrypt` |
| `POST /api/login` | `{"username", "password"}` | `200 {"username", "needs_consent": bool}` and sets the cookie; `401` on bad credentials |
| `POST /api/logout` | | `204`; ends the AuthWho session |
| `GET /api/me` | | `200 {"username", "consent": null \| {"version", "at", "channels": {"keystroke", "pointer", "interaction"}, "research_consent", "pointer_device"}, "withdrawal_pending": bool}`; `401` when logged out. `withdrawal_pending` is true while the AuthWho deletion after a withdrawal is still unconfirmed |
| `POST /api/consent` | `{"version": "1", "channels": {...}, "research_consent": bool, "pointer_device": "mouse" \| "touchpad"}` | `200`; forwards to `PUT /v1/users/{user_id}` |
| `DELETE /api/consent` | | `204`, or `502 authwho_unavailable` when AuthWho could not confirm the deletion; either way consent is withdrawn and capture stops at once. An unconfirmed deletion is retried on login, `GET /api/me`, `POST /api/consent` and by a background task every 5 minutes. `POST /api/consent` during a pending withdrawal finishes the deletion first or returns `502` |
| `POST /api/authwho/stream` | | `200 {"endpoint", "session_id", "stream_id", "stream_key", "channels", "pointer_device"}`; `409 {"error": "no_consent"}` |
| `GET /api/registry` | | `200 {"pages": {"home": 1, "write": 2, "form": 3, "payees": 4, "reports": 5, "collect": 6, "settings": 7}, "actions": {"add_payee": 1, "export_report": 2}}` |
| `POST /api/notes` | `{"text"}` | `204`. The text is discarded, never stored or logged; the page exists only to produce free-text typing |
| `POST /api/payees` | `{"name", "account"}` | `200 {"ok": true}`; high-risk, checked with AuthWho first (see below) |
| `POST /api/reports/export` | | `200 {"ok": true}`; high-risk, checked with AuthWho first |
| `GET /api/session` | | `200 {"status": "active" \| "step_up_required", "method": "totp" \| "password"}`; the frontend polls it to show the step-up prompt |
| `POST /api/totp/setup` | | `200 {"secret", "otpauth_uri"}` with `Cache-Control: no-store`; `409 totp_already_enabled`; `503 totp_unavailable` without `DEMO_TOTP_KEY` |
| `POST /api/totp/confirm` | `{"code"}` | `200 {"totp_enabled": true}`; `400 invalid_code` |
| `POST /api/step-up` | `{"code"}` or `{"password"}` | `200 {"status": "active"}`; `400 {"error": "step_up_failed", "attempts_left": n}`; after three wrong answers `401 session_ended`; `409 no_step_up_pending` |

Continuous authentication (P4): every request from a login with an AuthWho session checks `GET /v1/sessions/{id}/status`. A terminated session logs the user out with `401 {"error": "session_ended"}`. While a step-up is required, notes and high-risk actions answer `403 {"error": "step_up_required", "method": "totp" | "password"}`; high-risk actions also call `POST /v1/sessions/{id}/actions` and answer the same way when the policy asks for step-up. The step-up uses a TOTP code once the user has set one up (secret encrypted with `DEMO_TOTP_KEY`), and the account password otherwise; three wrong answers report a failed check to AuthWho, which ends the session. When AuthWho is unreachable, normal session rules apply. `GET /api/me` also returns `"totp_enabled": bool`.

Errors are always `{"error": "<code>"}`, never echoing submitted input: `username_taken` (409), `invalid_credentials` (401), `not_logged_in` (401, every endpoint except register, login and registry), `authwho_unavailable` (502), `invalid_request` (422, with `"fields": [...]` naming the invalid fields only). Passwords must be 8 to 1024 characters; usernames are case-insensitive. `POST /api/consent` returns the stored consent object. A consent withdrawal detaches the current AuthWho session, so consenting again creates a new one within the same login. The stream response carries `Cache-Control: no-store`.

## Change log

| Date | Version | Change |
|---|---|---|
| 2026-10-09 | 1 | First version |
| 2026-10-13 | 1.4 | Decisions and policies tables (migration 0100); session control API live in the AuthWho API; demo app TOTP, step-up and session-end endpoints (section 15) |
| 2026-10-12 | 1.3 | Pointer (`pf-1`, 22 features) and interaction (`if-1`, 17 features) windows in the worker; `profiles` and `trust_points` tables (migration 0005) with `device_key`; per-user score calibration; trust constants; `AUTHWHO_ENROLL_WINDOWS` |
| 2026-10-09 | 1.1 | Added user consent endpoints (section 4), `sessions` table and research consumer (section 12), SDK public API (section 14), demo app API (section 15) |
| 2026-10-12 | 1.2 | `windows` table gains `stream_id`; `features_enc` uses `window_id` as associated data; `kf-1` fixed at 35 features. Withdrawal deletes the `users` row before the user's data rows, and writers lock the user row before inserting |
