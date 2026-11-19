#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 <warehouse: duckdb|postgres> <orchestrator: none|airflow>" >&2
  exit 2
}

if [ "$#" -ne 2 ]; then
  usage
fi

warehouse=$1
orchestrator=$2

template_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workdir=$(mktemp -d "${TMPDIR:-/tmp}/data-pipeline-template.XXXXXX")
project="$workdir/project"

cleanup() {
  rm -rf "$workdir"
}
trap cleanup EXIT

bash "$template_root/scripts/render.sh" "$warehouse" "$orchestrator" "$project"

cd "$project"

python3.12 -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -e '.[dev]'

export PIPELINE_OFFLINE=1

if [ -f Makefile ]; then
  make ci
else
  .venv/bin/python -m pytest -q
fi
