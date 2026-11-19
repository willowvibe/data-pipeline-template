# data-pipeline-template — launch checklist

The build steps live in `.plan/v1.md` and go to the cheap-agent worker. Claude handles the steps below
directly, in this order, with the user approving anything public.

## Before the build
- [ ] Create `willowvibe/data-pipeline-template` on GitHub (public, MIT, no auto-init) and push `main`
      with `docs/design.md`, `docs/launch-checklist.md` and `.plan/v1.md`.
- [ ] Enable branch protection like the other repos (PRs, CI required once CI exists).

## During the build (one PR per plan group)
- [ ] PR A: steps 1–5 (template harness → extract → load → CLI → dbt; duckdb/none green end to end).
- [ ] PR B: steps 6–8 (Postgres, lint, generated CI).
- [ ] PR C: steps 9a–9b (Airflow + Cosmos DAG). Record whether Cosmos worked on Airflow 3.4 or the
      BashOperator fallback was used, and say so in the README.
- [ ] PR D: steps 10–13 (template CI, update test, docs, Pages).
- [ ] After each PR: CI green for all four combinations before merging (the user authorised merging
      milestone PRs myself, as with plm-bom-pipeline).

## Release
- [ ] Manual smoke test from a clean directory: `copier copy gh:willowvibe/data-pipeline-template demo`
      → `make up` for duckdb/none and postgres/airflow; screenshot the Airflow grid with Cosmos tasks.
- [ ] Demo media with the `portfolio-demo-media` skill: voice-only narrated MP4 (release asset), poster,
      README GIF (`docs/assets/data-pipeline-template-demo.gif`), Pages video.
- [ ] Tag `v1.0.0`, release notes from CHANGELOG, then confirm `tests/test_update.py` stops skipping.
- [ ] Claims audit: every README number and command reproduced from the quickstart.

## Listings
- [ ] Hub card on willowvibe.github.io (proof-of-work grid).
- [ ] willowvibe.com products page: card under "Open-source tools"; chatbot prompt picks it up once the
      prompt is built from `PRODUCTS` (see willowvibe-web PR #5 follow-ups).
- [ ] Org profile (`willowvibe/.github`): project section, repositories row, Airflow mention in What We Build.
- [ ] Update `docs/portfolio-status.md` and memory.
