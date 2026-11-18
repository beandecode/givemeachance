#!/usr/bin/env bash
# Full local gate; CI runs the same script. Needs the mise.toml toolchain (`mise install`) and
# .venv with requirements-dev.txt.
set -euo pipefail
cd "$(dirname "$0")/.."
# Use the Python/Node pinned in mise.toml even when the calling shell has not activated mise.
if command -v mise >/dev/null 2>&1; then
  eval "$(mise env -s bash)"
fi
PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
"$PYTHON_BIN" -m ruff check .
"$PYTHON_BIN" -m ruff format --check .
"$PYTHON_BIN" -m mypy
"$PYTHON_BIN" -m pytest -q -W error
"$PYTHON_BIN" scripts/export_route_inventory.py --check
"$PYTHON_BIN" scripts/export_openapi.py --check
"$PYTHON_BIN" scripts/check_docs.py
# React app (web/): generated API types current, types, lint, format, unit tests, production build.
if [ ! -d web/node_modules ]; then
  echo "web/node_modules is missing: run (cd web && npm ci)" >&2
  exit 1
fi
(cd web && npm run --silent check)
# Browser tests of the built app against a throwaway mock-provider server (Chromium inside web/node_modules).
if [ ! -d web/node_modules/playwright-core/.local-browsers ]; then
  echo "test browser missing: run (cd web && npx playwright install --only-shell chromium)" >&2
  exit 1
fi
(cd web && npm run --silent e2e)
