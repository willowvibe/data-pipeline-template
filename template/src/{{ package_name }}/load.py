"""Load raw weather JSON files into the warehouse."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import DATA_DIR
from .warehouse import PARAM, begin, connect, ensure_schema, execute_many

LOGGER = logging.getLogger(__name__)

DELETE_SQL = (
    f"DELETE FROM raw.hourly_weather WHERE city = {PARAM} AND CAST(observed_at AS DATE) = {PARAM}"
)

INSERT_SQL = (
    "INSERT INTO raw.hourly_weather "
    "(city, observed_at, temperature_c, humidity_pct, precipitation_mm, wind_kmh, loaded_at) "
    f"VALUES ({PARAM}, {PARAM}, {PARAM}, {PARAM}, {PARAM}, {PARAM}, {PARAM})"
)


def _read_payload(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(  # noqa: TRY004 - keep ValueError for callers
            f"raw file {path} does not contain a JSON object"
        )
    return payload


def _rows(payload: dict[str, Any]) -> list[tuple[Any, ...]]:
    city = payload["city"]
    hourly = payload["hourly"]
    loaded_at = datetime.now(UTC).replace(tzinfo=None)
    return [
        (
            city,
            datetime.fromisoformat(str(hourly["time"][index])),
            hourly["temperature_2m"][index],
            hourly["relative_humidity_2m"][index],
            hourly["precipitation"][index],
            hourly["wind_speed_10m"][index],
            loaded_at,
        )
        for index in range(len(hourly["time"]))
    ]


def load_file(conn, path: Path) -> int:
    """Replace one raw file's rows in a single transaction and return the count."""
    payload = _read_payload(Path(path))
    rows = _rows(payload)
    ensure_schema(conn)
    if not rows:
        LOGGER.warning("raw file %s has no hourly rows", path)
        return 0

    city = rows[0][0]
    day = rows[0][1].date()
    begin(conn)
    try:
        conn.execute(DELETE_SQL, (city, day))
        execute_many(conn, INSERT_SQL, rows)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    LOGGER.info("loaded %d rows for %s on %s", len(rows), city, day)
    return len(rows)


def load_all(data_dir: Path | None = None) -> int:
    """Load every raw JSON file under data_dir and return the total row count."""
    root = Path(data_dir) if data_dir is not None else DATA_DIR
    paths = sorted((root / "raw").glob("*/*.json"))
    total = 0
    with connect() as conn:
        ensure_schema(conn)
        for path in paths:
            total += load_file(conn, path)
    LOGGER.info("loaded %d rows from %d raw files", total, len(paths))
    return total
