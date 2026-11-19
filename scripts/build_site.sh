#!/usr/bin/env bash
set -euo pipefail

template_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
site_dir="$template_root/_site"
workdir=$(mktemp -d "${TMPDIR:-/tmp}/data-pipeline-template-site.XXXXXX")
project="$workdir/project"

cleanup() {
  rm -rf "$workdir"
}
trap cleanup EXIT

echo "Rendering duckdb + none into $project"
bash "$template_root/scripts/render.sh" duckdb none "$project"

cd "$project"

echo "Creating the generated project virtualenv"
python3.12 -m venv .venv
make install

echo "Running the pipeline offline"
PIPELINE_OFFLINE=1 make run
make build

echo "Generating dbt docs"
.venv/bin/python -m dbt.cli.main docs generate --project-dir dbt --profiles-dir dbt

rm -rf "$site_dir"
mkdir -p "$site_dir/dbt"
cp -R dbt/target/. "$site_dir/dbt/"
cp "$template_root/site/index.html" "$site_dir/index.html"

echo "Writing the sample daily_city_weather table"
.venv/bin/python - "$project" "$site_dir/sample.html" <<'PY'
from __future__ import annotations

import html
import sys
from datetime import UTC, datetime
from pathlib import Path

import duckdb

project = Path(sys.argv[1])
output = Path(sys.argv[2])

connection = duckdb.connect(str(project / "data" / "warehouse.duckdb"), read_only=True)
result = connection.execute(
    """
    select
        city,
        observation_date,
        round(min_temperature_c, 1) as min_temperature_c,
        round(max_temperature_c, 1) as max_temperature_c,
        round(avg_temperature_c, 1) as avg_temperature_c,
        round(total_precipitation_mm, 2) as total_precipitation_mm,
        round(max_wind_kmh, 1) as max_wind_kmh,
        hours_observed
    from main.daily_city_weather
    order by observation_date desc, city
    """
)
columns = [column[0] for column in result.description]
rows = result.fetchall()
connection.close()


def cell(value: object) -> str:
    if value is None:
        return "<td>—</td>"
    if isinstance(value, float):
        value = f"{value:g}"
    return f"<td>{html.escape(str(value))}</td>"


table_rows = "\n".join(
    "        <tr>" + "".join(cell(value) for value in row) + "</tr>" for row in rows
)
header = "".join(f"<th>{html.escape(name)}</th>" for name in columns)
generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>daily_city_weather sample — data-pipeline-template</title>
  <style>
    :root {{
      color-scheme: light dark;
      --bg: #f5f7fb;
      --surface: #ffffff;
      --text: #162033;
      --muted: #52607a;
      --border: #d9e0ec;
      --accent: #1668dc;
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --bg: #0b1020;
        --surface: #121a2d;
        --text: #e8eefb;
        --muted: #9fb0cc;
        --border: #24314c;
        --accent: #6ea8ff;
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 16px/1.6 system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }}
    .wrap {{ width: min(1100px, calc(100% - 40px)); margin: 0 auto; padding: 48px 0; }}
    a {{ color: var(--accent); text-underline-offset: 3px; }}
    h1 {{ margin: 0 0 8px; font-size: clamp(1.7rem, 4vw, 2.4rem); letter-spacing: -0.02em; }}
    p {{ margin: 0 0 20px; color: var(--muted); }}
    .table-wrap {{
      overflow: auto;
      border: 1px solid var(--border);
      border-radius: 14px;
      background: var(--surface);
      box-shadow: 0 16px 48px rgba(22, 32, 51, 0.10);
    }}
    table {{ width: 100%; border-collapse: collapse; font-size: 0.92rem; }}
    th, td {{ padding: 11px 14px; border-bottom: 1px solid var(--border); white-space: nowrap; }}
    th {{
      position: sticky;
      top: 0;
      background: var(--surface);
      text-align: left;
      font-size: 0.82rem;
      letter-spacing: 0.03em;
      text-transform: uppercase;
    }}
    tbody tr:last-child td {{ border-bottom: 0; }}
    tbody tr:hover {{ background: color-mix(in srgb, var(--accent) 7%, transparent); }}
    footer {{ margin-top: 18px; color: var(--muted); font-size: 0.88rem; }}
  </style>
</head>
<body>
  <main class="wrap">
    <h1>daily_city_weather</h1>
    <p>
      The daily city mart built from the recorded Open-Meteo fixture, one row per city per
      UTC date. Generated {generated_at} by <code>scripts/build_site.sh</code>.
    </p>
    <div class="table-wrap">
      <table>
        <thead><tr>{header}</tr></thead>
        <tbody>
{table_rows}
        </tbody>
      </table>
    </div>
    <footer>
      <a href="index.html">Back to the template landing page</a> ·
      <a href="dbt/index.html">dbt docs</a>
    </footer>
  </main>
</body>
</html>
"""

output.write_text(page, encoding="utf-8")
PY

echo "Site written to $site_dir"
