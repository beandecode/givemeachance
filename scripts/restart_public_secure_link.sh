#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

MAIN_COMPOSE_FILE="docker-compose.app.yml"
SECURE_OVERLAY_FILE="docker-compose.cloudflare.yml"
APP_SERVICE_NAME="app"
CF_SERVICE_NAME="cloudflared"
HEALTH_RETRIES="${HEALTH_RETRIES:-40}"
HEALTH_SLEEP_SECONDS="${HEALTH_SLEEP_SECONDS:-1}"

# Make output deterministic for editor/CI terminals.
export COMPOSE_MENU=0
export BUILDKIT_PROGRESS=plain

compose() {
  docker compose --ansi never -f "$MAIN_COMPOSE_FILE" -f "$SECURE_OVERLAY_FILE" "$@"
}

echo "[restart_public_secure_link] preflight"
bash scripts/preflight_secure_link.sh

echo "[restart_public_secure_link] stopping current secure stack"
compose down --remove-orphans || true

echo "[restart_public_secure_link] building app image"
docker compose --ansi never --progress plain -f "$MAIN_COMPOSE_FILE" -f "$SECURE_OVERLAY_FILE" build "$APP_SERVICE_NAME"

echo "[restart_public_secure_link] starting secure stack"
compose up -d --no-build --remove-orphans

app_container_id="$(compose ps -q "$APP_SERVICE_NAME")"
if [[ -z "$app_container_id" ]]; then
  echo "ERROR: app container id not found" >&2
  exit 1
fi

echo "[restart_public_secure_link] waiting for app health"
for ((i = 1; i <= HEALTH_RETRIES; i++)); do
  app_health="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$app_container_id" 2>/dev/null || true)"
  if [[ "$app_health" == "healthy" ]]; then
    echo "[restart_public_secure_link] app healthy on attempt $i/$HEALTH_RETRIES"
    break
  fi
  if [[ "$app_health" == "unhealthy" || "$app_health" == "exited" || "$app_health" == "dead" ]]; then
    echo "ERROR: app entered bad state: $app_health" >&2
    compose ps
    compose logs --tail 120 "$APP_SERVICE_NAME" || true
    exit 1
  fi
  echo "[restart_public_secure_link] app state=$app_health ($i/$HEALTH_RETRIES)"
  sleep "$HEALTH_SLEEP_SECONDS"

done

app_health_final="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$app_container_id" 2>/dev/null || true)"
if [[ "$app_health_final" != "healthy" ]]; then
  echo "ERROR: app was not healthy after $HEALTH_RETRIES attempts (final=$app_health_final)" >&2
  compose ps
  compose logs --tail 120 "$APP_SERVICE_NAME" || true
  exit 1
fi

echo "[restart_public_secure_link] stack status"
compose ps

echo "[restart_public_secure_link] cloudflared recent logs"
cloudflared_logs="$(compose logs --tail 200 "$CF_SERVICE_NAME" || true)"
printf '%s\n' "$cloudflared_logs"

if grep -E 'Registered tunnel connection|Connected to|connection ready|Updated to new configuration' <<<"$cloudflared_logs" >/dev/null 2>&1; then
  echo "[restart_public_secure_link] cloudflared tunnel connection detected"
else
  echo "WARNING: no explicit tunnel-registration line found yet; re-check with:"
  echo "docker compose -f $MAIN_COMPOSE_FILE -f $SECURE_OVERLAY_FILE logs -f $CF_SERVICE_NAME"
fi

echo "[restart_public_secure_link] done"
