#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

source "$PROJECT_ROOT/.venv/bin/activate"
[ -f "$PROJECT_ROOT/.env" ] && set -a && source "$PROJECT_ROOT/.env" && set +a

rm -rf "$PROJECT_ROOT/data/chroma"
rm -f "$PROJECT_ROOT/data/manifests/ingest_manifest.json"

mkdir -p "$PROJECT_ROOT/data/chroma"
mkdir -p "$PROJECT_ROOT/data/manifests"

python "$PROJECT_ROOT/rag/ingest.py"
"$PROJECT_ROOT/rag/test_queries.sh"
