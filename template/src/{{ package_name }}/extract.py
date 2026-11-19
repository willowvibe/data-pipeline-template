"""Extract hourly weather from Open-Meteo and store raw JSON files."""

from __future__ import annotations

import copy
import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from .config import ARCHIVE_URL, CITIES, DATA_DIR, FORECAST_URL, HOURLY_VARS, OFFLINE, City

LOGGER = logging.getLogger(__name__)
TIMEOUT_SECONDS = 20.0
FIXTURE_PATH = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "open_meteo_sample.json"


class PayloadError(ValueError):
    """Raised when an Open-Meteo response does not have the expected shape."""


@dataclass
class ExtractResult:
    """Outcome of extracting all cities."""

    written: list[Path] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


def _client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_SECONDS)


def _should_retry(error: BaseException) -> bool:
    if isinstance(error, httpx.TimeoutException):
        return True
    if isinstance(error, httpx.HTTPStatusError):
        status = error.response.status_code
        return status == 429 or status >= 500
    return False


@retry(
    retry=retry_if_exception(_should_retry),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.1, min=0.1, max=2),
    reraise=True,
)
def _get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    with _client() as client:
        response = client.get(url, params=params)
        response.raise_for_status()
        payload = response.json()
    if not isinstance(payload, dict):
        raise PayloadError("Open-Meteo response is not a JSON object")
    return payload


def _request_params(
    city: City,
    start: date | None,
    end: date | None,
) -> tuple[str, dict[str, Any]]:
    params: dict[str, Any] = {
        "latitude": city.latitude,
        "longitude": city.longitude,
        "hourly": ",".join(HOURLY_VARS),
        "timezone": "UTC",
    }
    if start is None and end is None:
        params["past_days"] = 2
        params["forecast_days"] = 1
        return FORECAST_URL, params

    start_date = start or end
    end_date = end or start
    params["start_date"] = start_date.isoformat()
    params["end_date"] = end_date.isoformat()
    return ARCHIVE_URL, params


def fetch_city(
    city: City,
    *,
    start: date | None = None,
    end: date | None = None,
) -> dict[str, Any]:
    """Fetch hourly weather for one city from Open-Meteo."""
    url, params = _request_params(city, start, end)
    return _get_json(url, params)


def validate_payload(payload: dict[str, Any]) -> None:
    """Validate that a payload contains all hourly arrays with equal lengths."""
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict):
        raise PayloadError("payload is missing the 'hourly' object")

    required = ["time", *HOURLY_VARS]
    missing = [name for name in required if name not in hourly]
    if missing:
        raise PayloadError(f"payload is missing hourly keys: {', '.join(missing)}")

    lengths = {name: len(hourly[name]) for name in required}
    if len(set(lengths.values())) != 1:
        raise PayloadError(f"hourly arrays have different lengths: {lengths}")
    if lengths["time"] == 0:
        raise PayloadError("payload contains no hourly rows")


def _city_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "city"


def _split_by_date(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    hourly = payload["hourly"]
    rows_by_date: dict[str, list[int]] = defaultdict(list)
    for index, timestamp in enumerate(hourly["time"]):
        rows_by_date[str(timestamp)[:10]].append(index)

    split: dict[str, dict[str, Any]] = {}
    for day, indexes in sorted(rows_by_date.items()):
        day_hourly = {"time": [hourly["time"][index] for index in indexes]}
        for name in HOURLY_VARS:
            day_hourly[name] = [hourly[name][index] for index in indexes]
        split[day] = {
            "city": payload.get("city"),
            "latitude": payload.get("latitude"),
            "longitude": payload.get("longitude"),
            "timezone": payload.get("timezone", "UTC"),
            "hourly_units": payload.get("hourly_units", {}),
            "hourly": day_hourly,
        }
    return split


def write_raw(city: City, payload: dict[str, Any], data_dir: Path) -> list[Path]:
    """Write one raw JSON file per UTC date, returning the paths written."""
    validate_payload(payload)
    enriched = copy.deepcopy(payload)
    enriched["city"] = city.name
    enriched["latitude"] = city.latitude
    enriched["longitude"] = city.longitude

    directory = Path(data_dir) / "raw" / _city_slug(city.name)
    directory.mkdir(parents=True, exist_ok=True)

    written = []
    for day, day_payload in _split_by_date(enriched).items():
        path = directory / f"{day}.json"
        path.write_text(json.dumps(day_payload, indent=2), encoding="utf-8")
        written.append(path)
    return written


def _shift_to_today(payload: dict[str, Any]) -> dict[str, Any]:
    shifted = copy.deepcopy(payload)
    times = shifted["hourly"]["time"]
    if not times:
        return shifted

    last_day = date.fromisoformat(str(times[-1])[:10])
    delta = datetime.now(UTC).date() - last_day
    if not delta:
        return shifted

    shifted["hourly"]["time"] = [
        (datetime.fromisoformat(str(timestamp)) + delta).isoformat(timespec="minutes")
        for timestamp in times
    ]
    return shifted


def _offline_payload(
    city: City,
    start: date | None,
    end: date | None,
) -> dict[str, Any]:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    if city.name not in data:
        raise KeyError(f"offline fixture has no sample for {city.name}")
    payload = _shift_to_today(data[city.name])

    if start is None and end is None:
        return payload

    first = (start or end).isoformat()
    last = (end or start).isoformat()
    hourly = payload["hourly"]
    indexes = [
        index
        for index, timestamp in enumerate(hourly["time"])
        if first <= str(timestamp)[:10] <= last
    ]
    filtered = copy.deepcopy(payload)
    filtered["hourly"] = {"time": [hourly["time"][i] for i in indexes]}
    for name in HOURLY_VARS:
        filtered["hourly"][name] = [hourly[name][i] for i in indexes]
    return filtered


def extract_all(
    cities: list[City],
    *,
    start: date | None = None,
    end: date | None = None,
    offline: bool = OFFLINE,
) -> ExtractResult:
    """Extract every city, keeping going when one city fails."""
    result = ExtractResult()
    for city in cities:
        try:
            if offline:
                payload = _offline_payload(city, start, end)
            else:
                payload = fetch_city(city, start=start, end=end)
            result.written.extend(write_raw(city, payload, DATA_DIR))
        except Exception as error:  # noqa: BLE001 - one bad city must not stop the rest
            LOGGER.warning("extract failed for %s: %s", city.name, error)
            result.failed.append(city.name)
    return result


def default_cities() -> list[City]:
    """Return the configured cities."""
    return list(CITIES)
