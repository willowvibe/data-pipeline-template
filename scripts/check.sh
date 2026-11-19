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
started_compose=0
compose_cmd=""

detect_compose() {
  if docker compose version >/dev/null 2>&1; then
    echo "docker compose"
  else
    echo "docker-compose"
  fi
}

cleanup() {
  if [ "$started_compose" -eq 1 ]; then
    (cd "$project" && $compose_cmd down --volumes --remove-orphans) >/dev/null 2>&1 || true
  fi
  rm -rf "$workdir"
}
trap cleanup EXIT

bash "$template_root/scripts/render.sh" "$warehouse" "$orchestrator" "$project"

cd "$project"

export PIPELINE_HOME="$project"
if [ "$orchestrator" = "airflow" ]; then
  export AIRFLOW_HOME="$workdir/airflow-home"
  export AIRFLOW__CORE__DAGS_FOLDER="$project/airflow/dags"
  export AIRFLOW__CORE__LOAD_EXAMPLES=false
  export AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION=true
  mkdir -p "$AIRFLOW_HOME"
fi

if [ "$warehouse" = "postgres" ]; then
  export WAREHOUSE_DB=${WAREHOUSE_DB:-warehouse}
  export WAREHOUSE_USER=${WAREHOUSE_USER:-warehouse}
  export WAREHOUSE_PASSWORD=${WAREHOUSE_PASSWORD:-warehouse}

  if [ -n "${WAREHOUSE_HOST:-}" ]; then
    export WAREHOUSE_HOST
    export WAREHOUSE_PORT=${WAREHOUSE_PORT:-5432}
    echo "Using existing Postgres at ${WAREHOUSE_HOST}:${WAREHOUSE_PORT}"
  else
    export WAREHOUSE_HOST=localhost
    export WAREHOUSE_PORT=${WAREHOUSE_PORT:-5436}
    export COMPOSE_PROJECT_NAME="dpt-${warehouse}-${orchestrator}-$$"
    compose_cmd=$(detect_compose)
    echo "Starting Postgres via ${compose_cmd} on port ${WAREHOUSE_PORT}..."
    if [ "$orchestrator" = "airflow" ]; then
      $compose_cmd up -d warehouse-db
    else
      $compose_cmd up -d
    fi
    started_compose=1
    echo "Waiting for warehouse-db to become healthy..."
    until $compose_cmd exec -T warehouse-db pg_isready \
      -U "$WAREHOUSE_USER" -d "$WAREHOUSE_DB" >/dev/null 2>&1; do
      sleep 1
    done
  fi
fi

python3.12 -m venv .venv
.venv/bin/python -m pip install --quiet --upgrade pip

export PIPELINE_OFFLINE=1
export PATH="$project/.venv/bin:$PATH"

if [ "$orchestrator" = "airflow" ]; then
  .venv/bin/python -m pip install --quiet -e '.[dev,airflow]'
  airflow db migrate
else
  .venv/bin/python -m pip install --quiet -e '.[dev]'
fi

if [ -f Makefile ]; then
  make ci
else
  .venv/bin/python -m pytest -q
fi

if [ "$orchestrator" = "airflow" ]; then
  PIPELINE_OFFLINE=1 airflow dags test weather_pipeline "$(date -u +%F)"
fi
