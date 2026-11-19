# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

## [1.0.0] - 2026-11-19

### Added

- Copier template with `warehouse` (`duckdb` or `postgres`) and `orchestrator`
  (`none` or `airflow`) options, a computed package name, configurable cities, Python
  version and author, plus `.copier-answers.yml` for `copier update`.
- Open-Meteo extraction with response validation, per-city/per-date raw JSON, retries with
  exponential backoff, a recorded offline fixture, and a CLI for extract, load, run and
  backfill.
- Idempotent delete-then-insert loading into `raw.hourly_weather` for both DuckDB and
  Postgres, with rollback on failure.
- dbt project with a cities seed, source freshness, typed staging, daily city weather and
  city extremes marts, generic range tests, grain tests, relationships and a singular test.
- Generated Makefile with `install`, `extract`, `load`, `run`, `backfill`, `build`, `test`,
  `lint`, `ci`, `up`, `down` and `clean` targets.
- Postgres 16 Docker Compose service with health checks and `.env.example`.
- Airflow 3.4 stack with LocalExecutor, a Cosmos `DbtTaskGroup`, and the `weather_pipeline`
  DAG including DAG structure tests; `make up` brings the stack up, waits for the DAG to be
  parsed, then unpauses and triggers it, with containers running as the host uid.
- Template CI job `airflow-stack` that runs the generated `make up` for both Airflow
  combinations and waits for every DAG run to succeed.
- Generated projects ship an empty, tracked `data/` directory.
- Ruff, sqlfluff and pre-commit configuration in generated projects.
- Generated GitHub Actions workflow for the chosen options, including Postgres services and
  an Airflow `dags test` job.
- Template CI that renders and runs all four option combinations, plus a weekly live-API
  job.
- `copier update` test that applies the newest tagged template over a generated project.
- Generated project README and architecture documentation.
- Repository README, changelog, static landing page, dbt docs/sample-page build script and
  GitHub Pages deployment.

[1.0.0]: https://github.com/willowvibe/data-pipeline-template/releases/tag/v1.0.0
