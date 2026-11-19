"""Command-line entry points for the weather pipeline."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Sequence
from datetime import date

from .config import CITIES, OFFLINE
from .extract import ExtractResult, extract_all
from .load import load_all

LOGGER = logging.getLogger(__name__)


def _parse_date(value: str) -> date:
    """Parse a YYYY-MM-DD command-line date."""
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"invalid date {value!r}; expected YYYY-MM-DD"
        ) from error


def _extract(args: argparse.Namespace) -> ExtractResult:
    return extract_all(
        CITIES,
        start=getattr(args, "start", None),
        end=getattr(args, "end", None),
        offline=args.offline or OFFLINE,
    )


def _report(result: ExtractResult) -> int:
    if result.failed:
        LOGGER.error("failed cities: %s", ", ".join(result.failed))
        return 1
    LOGGER.info("wrote %d raw files", len(result.written))
    return 0


def _cmd_extract(args: argparse.Namespace) -> int:
    return _report(_extract(args))


def _cmd_load(args: argparse.Namespace) -> int:
    LOGGER.info("loaded %d rows", load_all())
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    result = _extract(args)
    LOGGER.info("loaded %d rows", load_all())
    return _report(result)


def _cmd_backfill(args: argparse.Namespace) -> int:
    return _report(_extract(args))


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for every pipeline command."""
    parser = argparse.ArgumentParser(
        prog=__package__ or "weather-pipeline",
        description="Extract, load and backfill hourly weather data.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    extract_parser = subparsers.add_parser("extract", help="Fetch raw weather data.")
    extract_parser.add_argument(
        "--offline",
        action="store_true",
        help="Use recorded fixtures instead of the Open-Meteo API.",
    )
    extract_parser.set_defaults(handler=_cmd_extract)

    load_parser = subparsers.add_parser("load", help="Load raw files into the warehouse.")
    load_parser.set_defaults(handler=_cmd_load)

    run_parser = subparsers.add_parser("run", help="Extract and then load.")
    run_parser.add_argument(
        "--offline",
        action="store_true",
        help="Use recorded fixtures instead of the Open-Meteo API.",
    )
    run_parser.set_defaults(handler=_cmd_run)

    backfill_parser = subparsers.add_parser(
        "backfill", help="Extract a historic date range and load it."
    )
    backfill_parser.add_argument(
        "--start",
        type=_parse_date,
        required=True,
        help="First date to backfill (YYYY-MM-DD).",
    )
    backfill_parser.add_argument(
        "--end",
        type=_parse_date,
        required=True,
        help="Last date to backfill (YYYY-MM-DD).",
    )
    backfill_parser.add_argument(
        "--offline",
        action="store_true",
        help="Use recorded fixtures instead of the Open-Meteo API.",
    )
    backfill_parser.set_defaults(handler=_cmd_backfill)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run one pipeline command and return its exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "backfill" and args.start > args.end:
        parser.error("--start must be on or before --end")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    return args.handler(args)
