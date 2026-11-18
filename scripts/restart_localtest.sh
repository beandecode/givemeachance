#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.localtest.yml}"
BIND_ADDR="$(grep -E '^LOCALTEST_BIND_ADDR=.+' "$ROOT_DIR/.env" 2>/dev/null | tail -n1 | cut -d= -f2- || true)"
HEALTH_URL="${HEALTH_URL:-http://${BIND_ADDR:-127.0.0.1}:5011/health}"
HEALTH_RETRIES="${HEALTH_RETRIES:-20}"
HEALTH_SLEEP_SECONDS="${HEALTH_SLEEP_SECONDS:-1}"
LOCALTEST_SETTINGS_FILE="${LOCALTEST_SETTINGS_FILE:-config/settings.localtest.yaml}"
LOCALTEST_SEARCH_PARAMS_FILE="${LOCALTEST_SEARCH_PARAMS_FILE:-output_localtest/search_params.yaml}"

cd "$ROOT_DIR"

case "$COMPOSE_FILE" in
  *localtest*) ;;
  *)
    echo "ERROR: restart_localtest.sh only accepts localtest compose files. Refusing COMPOSE_FILE=$COMPOSE_FILE" >&2
    exit 1
    ;;
esac

if [[ ! -f config/api-keys.env ]]; then
  echo "ERROR: config/api-keys.env is required for localtest live-provider staging." >&2
  exit 1
fi

for key_name in GEMINI_API_KEY ADZUNA_APP_ID ADZUNA_APP_KEY; do
  if ! grep -Eq "^${key_name}=.+" config/api-keys.env; then
    echo "ERROR: ${key_name} is missing from config/api-keys.env." >&2
    exit 1
  fi
done

if ! grep -Eq "^LOCALTEST_FLASK_SECRET_KEY=.{32,}" .env 2>/dev/null; then
  echo "ERROR: set LOCALTEST_FLASK_SECRET_KEY (>=32 random chars) in .env; see .env.example." >&2
  exit 1
fi

if [[ ! -f "$LOCALTEST_SETTINGS_FILE" ]]; then
  echo "ERROR: $LOCALTEST_SETTINGS_FILE does not exist." >&2
  exit 1
fi

if grep -Eq "primary:[[:space:]]*mock_|provider:[[:space:]]*mock_" "$LOCALTEST_SETTINGS_FILE"; then
  echo "ERROR: $LOCALTEST_SETTINGS_FILE must use real providers, not mock providers." >&2
  exit 1
fi

if ! grep -Eq "primary:[[:space:]]*adzuna_api" "$LOCALTEST_SETTINGS_FILE"; then
  echo "ERROR: $LOCALTEST_SETTINGS_FILE must set data_sources.primary to adzuna_api." >&2
  exit 1
fi

if ! grep -Eq "provider:[[:space:]]*gemini_api" "$LOCALTEST_SETTINGS_FILE"; then
  echo "ERROR: $LOCALTEST_SETTINGS_FILE must set llm.provider to gemini_api." >&2
  exit 1
fi

mkdir -p output_localtest logs_localtest
if [[ ! -f "$LOCALTEST_SEARCH_PARAMS_FILE" ]]; then
  cp config/search_params.yaml "$LOCALTEST_SEARCH_PARAMS_FILE"
fi

# Make compose output deterministic and non-interactive for CI/editor terminals.
export COMPOSE_MENU=0
export BUILDKIT_PROGRESS=plain

echo "[restart_localtest] compose file: $COMPOSE_FILE"
echo "[restart_localtest] health url: $HEALTH_URL"
echo "[restart_localtest] settings file: $LOCALTEST_SETTINGS_FILE"

docker compose --ansi never -f "$COMPOSE_FILE" down --remove-orphans || true
docker compose --ansi never -f "$COMPOSE_FILE" build --progress plain
docker compose --ansi never -f "$COMPOSE_FILE" up -d --no-build --remove-orphans
docker compose --ansi never -f "$COMPOSE_FILE" ps

for ((i = 1; i <= HEALTH_RETRIES; i++)); do
  if curl -fsS "$HEALTH_URL"; then
    echo
    echo "[restart_localtest] health check passed on attempt $i/$HEALTH_RETRIES"
    exit 0
  fi
  echo "[restart_localtest] waiting for health ($i/$HEALTH_RETRIES)"
  sleep "$HEALTH_SLEEP_SECONDS"
done

echo "[restart_localtest] health check failed after $HEALTH_RETRIES attempts" >&2
exit 1
