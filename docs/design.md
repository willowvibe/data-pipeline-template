# data-pipeline-template — design

Date: 2026-11-19 · Status: approved in conversation, awaiting written-spec review
Repo (to create): `willowvibe/data-pipeline-template` · License: MIT

## Purpose

Pitch: **"Start a client data project in a day: ingestion, dbt, tests, CI and Docker wired up — with or
without Airflow."**

Audience (decision C): a polished shop window for prospects in v1, built so it can become the real
kickoff tool for client work. v1 stays small and fully tested; more warehouses and orchestrators slot in
later without a rewrite.

Supersedes the roadmap entry (`docs/plans/2026-11-16-freelance-repo-roadmap.md` §7), which assumed the
ETL-airflow rebuild. ETL-airflow is dropped (not a willowvibe repo); this template is now the portfolio's
Airflow showcase. Terraform and BigQuery move to v2.

## Scope

In v1:
- A **Copier** template (single `template/` tree with conditional files — approach 1).
- Options: `warehouse` ∈ {duckdb, postgres} × `orchestrator` ∈ {none, airflow} — four combinations, all
  tested in CI.
- Example load: **Open-Meteo** hourly weather (no key), extract → raw JSON → warehouse → dbt.
- dbt with tests and source freshness; pre-commit; generated-project CI; Docker Compose where needed.
- Airflow via **astronomer-cosmos** (each dbt model is its own task).

Out of v1 (documented extension points only): BigQuery, Snowflake, Terraform, Dagster/Prefect, a BI layer,
secrets managers, multi-environment deploys.

## Copier questions

| Key | Type / choices | Default | Notes |
|---|---|---|---|
| `project_name` | str | `weather-pipeline` | validated: lowercase letters, digits, hyphens |
| `package_name` | str (computed default) | `project_name` with `-`→`_` | Python package and dbt project name |
| `warehouse` | `duckdb` \| `postgres` | `duckdb` | |
| `orchestrator` | `none` \| `airflow` | `none` | |
| `cities` | yaml list of `{name, latitude, longitude}` | Bengaluru, London, New York | drives extract and dbt seeds |
| `python_version` | `3.12` | `3.12` | single choice in v1; a choice so 3.13 can be added |
| `author_name` | str | `WillowVibe` | README/pyproject |

Copier settings: `_subdirectory: template`, `_min_copier_version: "9.19"`, `_answers_file:
.copier-answers.yml` (enables `copier update`). No `_tasks` (no code runs at generation time, so no
`--trust` needed).

## Generated project layout

Bracketed items exist only for that option.

```
<project_name>/
├── README.md                 # quickstart rendered for the chosen options
├── Makefile                  # up, load, backfill, build, test, ci, down, clean
├── pyproject.toml            # deps per warehouse; [airflow] adds cosmos
├── .copier-answers.yml
├── .env.example              # [postgres] connection vars; [airflow] AIRFLOW_UID
├── .pre-commit-config.yaml   # ruff, ruff-format, sqlfluff (dialect per warehouse), check-yaml
├── .sqlfluff
├── .github/workflows/ci.yml  # generated project's own CI
├── docker-compose.yml        # [postgres] postgres; [airflow] airflow services + metadata db
├── airflow/                  # [airflow]
│   ├── Dockerfile            # apache/airflow + project deps
│   └── dags/weather_pipeline.py
├── src/<package_name>/
│   ├── config.py             # cities, paths, warehouse settings from env
│   ├── extract.py            # Open-Meteo → data/raw/<city>/<date>.json
│   ├── load.py               # raw JSON → raw.hourly_weather (idempotent)
│   ├── warehouse.py          # thin DuckDB / Postgres connection + SQL helpers
│   └── cli.py                # `python -m <pkg> extract|load|backfill [--offline]`
├── dbt/
│   ├── dbt_project.yml
│   ├── profiles.yml          # generated for the chosen warehouse, reads env vars
│   ├── seeds/cities.csv
│   ├── models/sources.yml    # raw.hourly_weather + freshness
│   ├── models/staging/stg_hourly_weather.sql (+ .yml tests)
│   ├── models/marts/daily_city_weather.sql (+ .yml)
│   ├── models/marts/city_extremes.sql (+ .yml)
│   └── tests/                # singular tests
├── tests/
│   ├── fixtures/open_meteo_sample.json
│   ├── test_extract.py
│   ├── test_load.py
│   └── test_dag.py           # [airflow] DAG import + structure
├── data/.gitkeep             # raw JSON and the DuckDB file land here (git-ignored)
└── docs/ARCHITECTURE.md      # diagram, design choices, "swap in your own source", "add BigQuery"
```

## Data flow

```
Open-Meteo ──extract──▶ data/raw/<city>/<date>.json ──load──▶ raw.hourly_weather
                                          dbt seed cities ──┐        │
                                    stg_hourly_weather (cast, units, dedupe) ◀┘
                                                │
                           daily_city_weather · city_extremes
```

- **Extract:** one request per city to `https://api.open-meteo.com/v1/forecast` with `hourly=
  temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m`, `past_days=2`, `forecast_days=1`,
  `timezone=UTC`. Responses are validated (expected keys and equal-length hourly arrays) and saved raw,
  split into one file per city per UTC date. Future hours are dropped at load time, not extract time.
- **Backfill:** `make backfill START=YYYY-MM-DD END=YYYY-MM-DD` uses
  `https://archive-api.open-meteo.com/v1/archive` with `start_date`/`end_date`. In Airflow the DAG uses
  `data_interval_start/end`, so Airflow 3's `airflow backfill create --dag-id weather_pipeline
  --from-date … --to-date …` works with the same code path.
- **Load:** per (city, date), delete then insert inside one transaction. Re-runs never duplicate. Table
  `raw.hourly_weather(city, observed_at, temperature_c, humidity_pct, precipitation_mm, wind_kmh,
  loaded_at)`; the same SQL works on DuckDB and Postgres.
- **dbt:**
  - `stg_hourly_weather`: typed columns, rows after `now()` removed, dedupe on (city, observed_at).
  - `daily_city_weather`: per city per day — min/max/avg temperature, total precipitation, max wind,
    hours observed.
  - `city_extremes`: hottest day, coldest day and wettest day per city across the loaded range.
  - Tests: `not_null` + `unique` on the grain; `accepted_range`-style tests (temperature −60..60 °C,
    humidity 0..100, precipitation ≥ 0) written as generic tests in the project (no extra package);
    `relationships` from marts to the `cities` seed; source freshness warn 6 h / error 24 h.

## Error handling

| Failure | Behaviour |
|---|---|
| API timeout / 5xx / 429 | `tenacity`: 3 attempts, exponential backoff; Airflow task `retries=2` on top |
| One city fails | Remaining cities still processed; exit code 1 with failed city names listed |
| Payload shape changed | Extract validation raises before writing anything for that city |
| Load error | Transaction rolls back that (city, date); nothing partial is committed |
| dbt test fails | `dbt build` skips dependants; in Airflow (Cosmos) only that model's test task fails |
| Freshness error | `make test` fails; in Airflow a final `dbt source freshness` task fails |

## Offline mode and fixtures

`--offline` (env `PIPELINE_OFFLINE=1`) makes extract read `tests/fixtures/open_meteo_sample.json` instead
of calling the API, re-dated so freshness passes. pytest, `make ci` and all CI runs use offline mode.
The fixture is a recorded real response, trimmed to 3 cities × 3 days.

## Airflow (orchestrator = airflow)

- Docker Compose adapted from the official Airflow compose file (Apache-2.0) and the layout of
  `cnstlungu/portable-data-stack-airflow` (MIT, credited in README): Postgres for Airflow metadata,
  `airflow-apiserver`, `airflow-scheduler`, `airflow-dag-processor`, `airflow-init`; LocalExecutor; no
  Celery, Redis, triggerer or Superset.
- For `warehouse=postgres` the same Postgres container hosts a separate `warehouse` database.
- DAG `weather_pipeline`: `@daily`, `catchup=False`, `extract` → `load` → Cosmos `DbtTaskGroup`
  (`ProfileConfig(profiles_yml_filepath=...)`, no Airflow Connection) → `source_freshness`.
- `make up` = `docker compose up -d` + wait for health + trigger the DAG; Airflow UI on
  `localhost:8080`.

## Template repo layout

```
data-pipeline-template/
├── copier.yml
├── template/                 # rendered tree (Jinja, conditional names)
├── tests/
│   ├── test_render.py        # shape checks per combination (pytest-copie)
│   └── test_update.py        # copier update from previous tag applies cleanly
├── .github/workflows/
│   ├── ci.yml                # matrix: render 4 combos → run each project's `make ci`
│   ├── live-api.yml          # weekly: one combo against the live API (never blocks PRs)
│   └── pages.yml             # build dbt docs of a generated project → GitHub Pages
├── docs/assets/              # GIF, poster
├── site/                     # Pages landing (tree, options, lineage link, sample mart table)
├── README.md
├── CHANGELOG.md
└── LICENSE
```

## Testing

- **Shape tests** (`tests/test_render.py`, pytest-copie): per combination — Airflow files exist only for
  `airflow`; `profiles.yml` targets the chosen adapter; `docker-compose.yml` absent for duckdb+none; no
  `{{`/`{%` left in any rendered file; `package_name` appears in pyproject, src and dbt project.
- **Generated-project CI** (`make ci` inside each render): ruff, sqlfluff lint, pytest (offline),
  `dbt deps` (none needed in v1), `dbt seed`, `dbt build`, `dbt source freshness`.
  - postgres combos: GitHub Actions `postgres:16` service container.
  - airflow combos: also `airflow dags test weather_pipeline <date>` in a CI venv with Airflow installed
    via the official constraints file — runs the full DAG incl. Cosmos tasks without the webserver.
- **Update test:** render from the previous git tag, then `copier update` to HEAD; assert clean apply.
  Skipped until a first tag exists.
- **Live API job:** weekly scheduled, duckdb+none, without `--offline`.

## Deliverables (portfolio standard)

- README: value line, GIF, quickstart ≤ 5 commands, generated tree, options table, "swap in your own
  source", "How we'd adapt this for your business", credits. Every claim reproducible.
- GitHub Pages: dbt docs + lineage of a generated project, sample `daily_city_weather` table, tree.
- Voice-only narrated demo video + GIF (`portfolio-demo-media` skill).
- v1.0.0 tag + release notes; hub card (willowvibe.github.io), willowvibe.com products card (Open-source
  tools), org profile section.

## Pinned versions (checked on PyPI 2026-11-19)

copier 9.19.1 · apache-airflow 3.4.0 · astronomer-cosmos 1.16.0 · dbt-core 1.12.7 · dbt-duckdb 1.11.1 ·
dbt-postgres 1.11.0 · duckdb 2.0.0 · psycopg 3.3.9 · httpx 0.28.1 · tenacity 9.2.1 · pytest-copie 0.3.1 ·
ruff 0.17.5 · sqlfluff 4.5.0 · Python 3.12. Pin with `~=` (compatible release) in generated projects.

## Risks

- **Cosmos ↔ Airflow 3.4 compatibility** — verify in the first Airflow step; fall back to a
  `BashOperator` running `dbt build` (documented trade-off) if Cosmos fails.
- **dbt-core 1.12 vs adapters 1.11** — adapters are versioned separately since dbt-adapters; confirm
  `dbt debug` on both adapters in the first dbt step.
- **duckdb 2.0 vs dbt-duckdb 1.11** — pin duckdb to what dbt-duckdb supports if the major bump breaks it.
- **Airflow in CI** is the slowest leg; cache the venv; keep the DAG test to one date.
- Open-Meteo is free for non-commercial use; README says client deployments should use their own source
  or Open-Meteo's commercial plan.
