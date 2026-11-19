#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 <warehouse: duckdb|postgres> <orchestrator: none|airflow> <destination>" >&2
  exit 2
}

if [ "$#" -ne 3 ]; then
  usage
fi

warehouse=$1
orchestrator=$2
destination=$3

case "$warehouse" in
  duckdb | postgres) ;;
  *)
    echo "error: unknown warehouse '$warehouse' (choose duckdb or postgres)" >&2
    exit 2
    ;;
esac

case "$orchestrator" in
  none | airflow) ;;
  *)
    echo "error: unknown orchestrator '$orchestrator' (choose none or airflow)" >&2
    exit 2
    ;;
esac

template_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)

default_copier="$template_root/.venv/bin/copier"
COPIER=${COPIER:-"$default_copier"}
if [ ! -x "$COPIER" ]; then
  if command -v copier >/dev/null 2>&1; then
    COPIER=$(command -v copier)
  else
    echo "error: copier not found (set COPIER or install copier~=9.19)" >&2
    exit 1
  fi
fi

"$COPIER" copy "$template_root" "$destination" \
  --defaults \
  --overwrite \
  --data "warehouse=$warehouse" \
  --data "orchestrator=$orchestrator"
