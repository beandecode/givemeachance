#!/usr/bin/env bash
# Check the public demo: it answers /health, and today's AI and job-board budget is not nearly spent.
# Read-only: one HTTP GET and one SELECT inside the demo container; nothing is started, stopped or changed.
# On a problem it shows a macOS notification (once per change of state) and always appends one line to
# logs/demo-check.log. Run it by hand, or every 15 minutes with scripts/com.givemeachance.demo-check.plist
# (docs/operations.md#demo-monitoring).
#
#   DEMO_URL        address to check (default https://jobs.givemeachance.qzz.io)
#   DEMO_CONTAINER  container name (default gmc-demo-app)
#   WARN_AT         percent of a daily limit that counts as nearly spent (default 90)
set -u
cd "$(dirname "$0")/.."

URL="${DEMO_URL:-https://jobs.givemeachance.qzz.io}"
CONTAINER="${DEMO_CONTAINER:-gmc-demo-app}"
WARN_AT="${WARN_AT:-90}"
SETTINGS="config/settings.demo-live.yaml"
LOG="logs/demo-check.log"
STATE="logs/demo-check.state"
mkdir -p logs

problems=()

body="$(curl -fsS --max-time 15 "$URL/health" 2>&1)" || problems+=("health: no answer from $URL")
if [ "${#problems[@]}" -eq 0 ] && ! printf '%s' "$body" | grep -q '"status": *"ok"'; then
  problems+=("health: unexpected answer")
fi

# Global daily limits for the whole demo, from the live settings (the lines "gemini_global_daily_limit: 100").
limit_of() { awk -v key="$1" '$1 == key ":" { print $2 }' "$SETTINGS"; }
usage="$(docker exec "$CONTAINER" python -c '
import sqlite3, datetime
c = sqlite3.connect("file:output_demo/demo.db?mode=ro", uri=True)
today = datetime.datetime.now(datetime.timezone.utc).date().isoformat()
try:
    rows = c.execute("SELECT provider, used_count FROM api_usage_daily WHERE usage_date = ?", (today,)).fetchall()
except sqlite3.OperationalError:
    rows = []  # the table appears with the first call of the day
for provider, used in rows:
    print(provider, used)
' 2>&1)" || problems+=("budget: cannot read usage from container $CONTAINER")

summary="ok"
if [ "${#problems[@]}" -eq 0 ]; then
  summary=""
  for provider in gemini adzuna; do
    limit="$(limit_of "${provider}_global_daily_limit")"
    used="$(printf '%s\n' "$usage" | awk -v p="$provider" '$1 == p { print $2 }')"
    used="${used:-0}"
    summary="$summary $provider $used/${limit:-?}"
    if [ -n "$limit" ] && [ "$limit" -gt 0 ] && [ $((used * 100 / limit)) -ge "$WARN_AT" ]; then
      problems+=("budget: $provider $used of $limit used today")
    fi
  done
fi

stamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if [ "${#problems[@]}" -eq 0 ]; then
  echo "$stamp OK$summary" >> "$LOG"
  echo ok > "$STATE"
  exit 0
fi

message="$(printf '%s; ' "${problems[@]}")"; message="${message%; }"
echo "$stamp PROBLEM $message" >> "$LOG"
echo "$message"
if [ "$(cat "$STATE" 2>/dev/null)" != "$message" ]; then  # tell once, not every 15 minutes
  osascript -e "display notification \"$message\" with title \"GivemeaChance demo\"" >/dev/null 2>&1 || true
fi
echo "$message" > "$STATE"
exit 1
