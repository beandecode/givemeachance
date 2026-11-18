#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

MAIN_COMPOSE_FILE="docker-compose.app.yml"
SECURE_OVERLAY_FILE="docker-compose.cloudflare.yml"

bash scripts/preflight_secure_link.sh

echo "Starting public secure-link stack (app + cloudflared)..."
docker compose -f "$MAIN_COMPOSE_FILE" -f "$SECURE_OVERLAY_FILE" up -d

echo
echo "Stack status:"
docker compose -f "$MAIN_COMPOSE_FILE" -f "$SECURE_OVERLAY_FILE" ps

echo
echo "Done."
echo "Public URL should be available after Cloudflare tunnel DNS propagates."
echo "Tip: use 'docker compose -f $MAIN_COMPOSE_FILE -f $SECURE_OVERLAY_FILE logs -f cloudflared' to watch tunnel status."
