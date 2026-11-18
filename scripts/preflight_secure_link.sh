#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

MAIN_COMPOSE_FILE="docker-compose.app.yml"
SECURE_OVERLAY_FILE="docker-compose.cloudflare.yml"

echo "[1/5] checking docker cli"
if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker not found"
  exit 1
fi

echo "[2/5] checking docker compose"
if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: docker compose not available"
  exit 1
fi

echo "[3/5] checking .env tunnel token"
if [[ ! -f .env ]]; then
  echo "ERROR: .env not found. Copy .env.example to .env first."
  exit 1
fi

if ! grep -E '^CLOUDFLARE_TUNNEL_TOKEN=' .env >/dev/null 2>&1; then
  echo "ERROR: CLOUDFLARE_TUNNEL_TOKEN missing in .env"
  exit 1
fi

if grep -E '^CLOUDFLARE_TUNNEL_TOKEN=replace_with_real_tunnel_token$' .env >/dev/null 2>&1; then
  echo "ERROR: CLOUDFLARE_TUNNEL_TOKEN still placeholder"
  exit 1
fi

echo "[4/5] checking app secrets file"
if [[ ! -f config/api-keys.env ]]; then
  echo "ERROR: config/api-keys.env missing"
  exit 1
fi

echo "[5/5] validating compose config merge"
merged_config="$(docker compose -f "$MAIN_COMPOSE_FILE" -f "$SECURE_OVERLAY_FILE" config)"
if grep -q 'published: "5001"' <<<"$merged_config"; then
  echo "ERROR: secure overlay still publishes host port 5001"
  exit 1
fi

echo "OK: preflight passed"
echo "Next: docker compose -f $MAIN_COMPOSE_FILE -f $SECURE_OVERLAY_FILE up -d"
