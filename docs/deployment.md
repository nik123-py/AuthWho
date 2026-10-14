# Deploying AuthWho

AuthWho runs as one Docker Compose stack on a single host. Everything is free and open source; any small Linux VM with Docker works (2 vCPU and 2 GB of RAM are enough for a class-sized deployment).

## What runs

| Service | Role | Exposed |
|---|---|---|
| `web` | nginx: serves the demo app at `/` and the admin dashboard at `/admin/`, and proxies the APIs | Port 80 (`HTTP_PORT`) |
| `api` | AuthWho API: collector, session control, admin API and live WebSocket | Internal |
| `worker` | Windows, features, enrollment, scoring, trust, policy and bot checks | Internal |
| `demo` | Demo application backend: accounts, consent, TOTP or password step-up | Internal |
| `retention` | Applies the retention table of proposal Section 9 every hour | Internal |
| `migrate` | Applies database migrations, then exits | Internal |
| `postgres`, `redis` | Storage; Redis keeps nothing on disk | Internal |
| `research` | Volunteer research export, off unless the `research` profile is enabled | Internal |

From the internet, only these paths are reachable: the demo app and its `/api/`, the dashboard at `/admin/`, the SDK batch endpoint `/v1/batches`, the admin API `/v1/admin/` (admin token required) and `/healthz`. User, session and session-control routes answer 404 publicly; the demo backend reaches them on the internal network.

## Steps

1. **A host with Docker.** For example, a free-tier VM from any cloud provider, or a university server. Install Docker Engine and the Compose plugin, and point a DNS name at the host.

2. **Get the code.**

   ```bash
   git clone https://github.com/nik123-py/AuthWho.git
   cd AuthWho
   ```

3. **Generate secrets.** This writes every key and token freshly at random. Keep the file private and out of version control (`.env.*` is already in `.gitignore`).

   ```bash
   python3 -m venv .venv && .venv/bin/pip install -e .
   .venv/bin/python -m server.common.production --domain authwho.example.org > .env.production
   ```

   With `AUTHWHO_ENV=production`, every service refuses to start if a secret is missing, a placeholder, too short, or if login cookies would not be Secure.

4. **Start.**

   ```bash
   docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
   docker compose --env-file .env.production -f docker-compose.prod.yml ps
   ```

5. **Add HTTPS.** Login cookies are marked Secure, so the site must be served over HTTPS. Choose one:
   - Put the host behind a TLS-terminating proxy or tunnel you already use (for example a cloud load balancer or a Cloudflare tunnel) that forwards to port 80.
   - Or run nginx with TLS on the host: obtain a certificate with certbot (`certbot certonly --standalone -d authwho.example.org`), set `HTTP_PORT=8080` in `.env.production` so the stack listens on 8080, and proxy 443 to it from a host nginx using the certificate.

6. **Sign in to the dashboard.** Open `https://authwho.example.org/admin/` and enter the value of `AUTHWHO_ADMIN_TOKEN` from `.env.production`.

7. **Optional: load the synthetic cohort** so the dashboard has data before volunteers start. These are 25 generated people, clearly synthetic, sent through the real API path:

   ```bash
   docker compose --env-file .env.production -f docker-compose.prod.yml exec api python -m ml.synthetic --out /app/data/synthetic
   docker compose --env-file .env.production -f docker-compose.prod.yml exec api python -m ml.load_synthetic --data /app/data/synthetic
   ```

On Windows with Git Bash, prefix `docker compose ... exec` commands that contain container paths with `MSYS_NO_PATHCONV=1`, or Git Bash rewrites `/app/...` into a Windows path.

## Operating it

- **Logs:** `docker compose -f docker-compose.prod.yml logs -f api worker demo`. Application logs hold counts, statuses and pseudonymous ids only, never typed text or raw events; nginx logs paths without query strings.
- **Backups:** back up the `pgdata` volume (profiles, windows, decisions) and the `demodata` volume (demo accounts), for example with `docker compose exec postgres pg_dump -U authwho authwho > backup.sql`. Raw events are never in a backup: they live only in Redis for at most 24 hours.
- **Upgrades:** `git pull`, then the `up -d --build` command again. Migrations run automatically before the API starts.
- **Rotating secrets:** changing `AUTHWHO_DATA_KEY` makes stored windows and profiles unreadable, so users re-enroll; rotate the admin token and the app key freely.
- **Enrollment length:** `AUTHWHO_ENROLL_WINDOWS` (default 20 windows per channel, about 10 minutes of normal use). Lower values enroll faster but give weaker profiles.

## Before real users

- Consent forms and any approval your institution requires for collecting behavioural data, as the proposal states.
- Keep the research profile off unless volunteers have given research consent.
- The volunteer dataset is needed to confirm the headline numbers; see `docs/evaluation_report.md`.
