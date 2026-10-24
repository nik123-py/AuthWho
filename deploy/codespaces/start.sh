#!/usr/bin/env bash
# Starts the AuthWho production stack inside a GitHub Codespace.
#
# Runs automatically when the codespace starts (.devcontainer/devcontainer.json).
# Run it again by hand at any time: bash deploy/codespaces/start.sh
#   LOAD_SYNTHETIC=1 bash deploy/codespaces/start.sh   also loads the 25-person synthetic cohort
set -euo pipefail
cd "$(dirname "$0")/../.."

PORT=8088
if [ -n "${CODESPACE_NAME:-}" ]; then
  PUBLIC_URL="https://${CODESPACE_NAME}-${PORT}.${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
else
  PUBLIC_URL="http://localhost:${PORT}"
fi
HOST="${PUBLIC_URL#*://}"

# 1. Secrets: generated once per codespace, never committed (.env.* is gitignored).
if [ ! -f .env.production ]; then
  python3 -m server.common.production --domain "$HOST" > .env.production
  sed -i "s#^DEMO_PUBLIC_COLLECTOR_URL=.*#DEMO_PUBLIC_COLLECTOR_URL=${PUBLIC_URL}#" .env.production
  sed -i "s#^AUTHWHO_CORS_ORIGINS=.*#AUTHWHO_CORS_ORIGINS=${PUBLIC_URL}#" .env.production
  echo "HTTP_PORT=${PORT}" >> .env.production
  echo "Generated .env.production for ${PUBLIC_URL}"
fi

# 2. Wait for Docker, then build and start everything.
for _ in $(seq 1 90); do docker info >/dev/null 2>&1 && break; sleep 2; done
if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running. In a codespace, rebuild the container; on a laptop, start Docker Desktop." >&2
  exit 1
fi
COMPOSE=(docker compose -p authwho --env-file .env.production -f docker-compose.prod.yml)
"${COMPOSE[@]}" up -d --build

# 3. Make the port public so others can open the demo (needs the gh CLI that Codespaces provides).
if [ -n "${CODESPACE_NAME:-}" ] && command -v gh >/dev/null 2>&1; then
  gh codespace ports visibility "${PORT}:public" -c "$CODESPACE_NAME" >/dev/null 2>&1 \
    || echo "Could not make port ${PORT} public automatically: open the Ports tab, right-click ${PORT}, Port Visibility, Public."
fi

# 4. Optional demo data: 25 synthetic people sent through the real API path (about 5 minutes).
if [ "${LOAD_SYNTHETIC:-0}" = "1" ]; then
  "${COMPOSE[@]}" exec -T api python -m ml.synthetic --out /app/data/synthetic
  "${COMPOSE[@]}" exec -T api python -m ml.load_synthetic --data /app/data/synthetic
fi

TOKEN="$(grep '^AUTHWHO_ADMIN_TOKEN=' .env.production | cut -d= -f2-)"
cat <<MSG

AuthWho is running.
  Demo app:         ${PUBLIC_URL}/
  Admin dashboard:  ${PUBLIC_URL}/admin/
  Admin token:      ${TOKEN}
Keep the token private. Stop with: ${COMPOSE[*]} down
MSG
