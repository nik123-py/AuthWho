# server/db

Migration runner, shared schema and retention jobs. Owner: backend-engineer.

## Running

```
docker compose up -d --wait
.venv/Scripts/python -m server.db.migrate --env-file .env
.venv/Scripts/python -m server.db.retention --env-file .env
```

`--env-file` only fills variables that are not already set in the environment.

## Migration convention

- Migrations are plain SQL files at `server/<folder>/migrations/NNNN_<name>.sql`, where `NNNN` is four digits and `<name>` uses lower-case letters, digits and underscores.
- The runner collects the files from every `server/*/migrations/` folder and applies them in global filename order, so the number alone decides the order.
- Number ranges per folder:

| Range | Folder |
|---|---|
| 0001 to 0099 | `server/db` (users, sessions, windows, profiles, trust points) |
| 0100 to 0199 | `server/policy` and `server/session` |
| 0200 onward | later folders, in blocks of 100 agreed with the orchestrator |

- Filenames must be unique across all folders; the runner refuses duplicates.
- Each file runs in one transaction and is recorded in `schema_migrations` with its SHA-256 checksum. Running the runner again applies nothing.
- Never edit a migration that has been applied. The runner refuses a changed file; add a new migration instead.
- Each folder owner writes only their own migrations; the runner applies them all.

## Retention

`python -m server.db.retention` runs one function per rule (proposal Section 9, interfaces sections 7 to 12). Run it at least hourly. Each rule runs in its own transaction with the session setting `authwho.retention = on`, which the append-only decision log requires before it allows deletes.

| Rule | Data | Limit |
|---|---|---|
| `trim_raw_events` | `aw:events` stream entries (Redis) | 24 hours (also trimmed on every `XADD`) |
| `delete_expired_sessions` | `sessions` rows | 90 days |
| `delete_expired_windows` | `windows` rows | 30 days |
| later: trust points | `trust_points` rows | 30 days |
| later: decisions | `decisions` rows | 90 days |
