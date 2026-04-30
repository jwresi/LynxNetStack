#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$PROJECT_ROOT/.venv/bin/activate"
[ -f "$PROJECT_ROOT/.env" ] && set -a && source "$PROJECT_ROOT/.env" && set +a

queries=(
  "dhcp leak mikrotik"
  "vilo onboarding failure"
  "000007 topology"
  "rogue dhcp BR-CGNAT"
  "splynx blocked customer behavior"
)

for q in "${queries[@]}"; do
  echo
  echo "==== $q ===="
  python "$PROJECT_ROOT/rag/query.py" <<< "$q"
done
