#!/usr/bin/env bash
# Run full NYCHA audit and push results to Grafana.
#
# Building list is discovered automatically from nycha_info.csv — no manual
# CSV maintenance required. New buildings appear on the next run.
#
# Prerequisites:
#   - SSH access to grafana_prometheus
#   - nycha_info.csv present (via JAKE_NYCHA_INFO_CSV or jake/data/nycha_info.csv)
#
# Cron job (runs nightly at 3am):
#   0 3 * * * /Users/jono/projects/LynxNetStack/jake2/audits/run_nycha_refresh.sh >> /Users/jono/projects/LynxNetStack/jake2/logs/nycha_refresh.log 2>&1
#
set -euo pipefail

# Resolve the repo from this script's own location so the job survives moves.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$REPO/.venv/bin/python"
LOG_DIR="$REPO/logs"
mkdir -p "$LOG_DIR"

echo "=== NYCHA refresh started at $(date) ==="

cd "$REPO"

# Push inline dashboards to Grafana — discovers all buildings from nycha_info.csv,
# runs live audit via JakeOps for every building, computes readiness aggregates,
# and overwrites both Grafana dashboards with fresh data.
echo "--- Running live audit and pushing dashboards to Grafana ---"
"$PYTHON" audits/push_nycha_grafana.py

echo "=== NYCHA refresh completed at $(date) ==="
