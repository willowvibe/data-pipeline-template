#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "usage: $0 <warehouse: duckdb|postgres>" >&2
  exit 2
}

if [ "$#" -ne 1 ]; then
  usage
fi

warehouse=$1

template_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
workdir=$(mktemp -d "${TMPDIR:-/tmp}/data-pipeline-stack.XXXXXX")
project="$workdir/project"
started_compose=0

detect_compose() {
  if docker compose version >/dev/null 2>&1; then
    echo "docker compose"
  else
    echo "docker-compose"
  fi
}

COMPOSE=$(detect_compose)
export COMPOSE
export COMPOSE_PROJECT_NAME="dpt-stack-${warehouse}-$$"

dump_diagnostics() {
  echo "--- ${COMPOSE} ps ---" >&2
  (cd "$project" && $COMPOSE ps) >&2 || true
  echo "--- last 200 lines of ${COMPOSE} logs airflow-scheduler ---" >&2
  (cd "$project" && $COMPOSE logs --tail 200 airflow-scheduler) >&2 || true
}

cleanup() {
  if [ "$started_compose" -eq 1 ]; then
    (cd "$project" && make down VOLUMES=1) >/dev/null 2>&1 || true
  fi
  rm -rf "$workdir"
}
trap cleanup EXIT

parse_runs() {
  python3 -c '
import json
import sys

raw = sys.stdin.read()
try:
    data = json.loads(raw)
except json.JSONDecodeError:
    print("pending")
    raise SystemExit(0)

if isinstance(data, dict):
    runs = data.get("dag_runs") or data.get("runs") or []
else:
    runs = data

states = [
    str(run.get("state", "")).lower()
    for run in runs
    if isinstance(run, dict)
]

if any(state == "failed" for state in states):
    print("failed")
elif states and all(state == "success" for state in states):
    print("success")
else:
    print("pending")
'
}

bash "$template_root/scripts/render.sh" "$warehouse" airflow "$project"

cd "$project"
cp .env.example .env

started_compose=1
echo "Starting the Airflow stack for ${warehouse}..."
if ! make up; then
  echo "error: 'make up' failed" >&2
  dump_diagnostics
  exit 1
fi

echo "Waiting up to 15 minutes for every weather_pipeline run to succeed..."
deadline=$((SECONDS + 900))
while :; do
  runs_json=""
  if runs_json=$($COMPOSE exec -T airflow-scheduler \
    airflow dags list-runs weather_pipeline -o json 2>/dev/null); then
    status=$(printf '%s' "$runs_json" | parse_runs)
  else
    status=pending
  fi

  case "$status" in
    success)
      echo "All weather_pipeline DAG runs succeeded."
      exit 0
      ;;
    failed)
      echo "error: a weather_pipeline DAG run failed" >&2
      printf '%s\n' "$runs_json" >&2
      dump_diagnostics
      exit 1
      ;;
  esac

  if [ "$SECONDS" -ge "$deadline" ]; then
    echo "error: timed out waiting for weather_pipeline DAG runs to succeed" >&2
    printf '%s\n' "$runs_json" >&2 || true
    dump_diagnostics
    exit 1
  fi

  sleep 10
done
