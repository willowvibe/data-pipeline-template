#!/usr/bin/env python3
"""Record the data-pipeline-template demo walkthrough at 1920x1080.

Run this with the system python3: Playwright 1.60 and its Chromium build are
installed there, and Playwright is intentionally not a repository dependency.

The recorder signs in to Airflow on a throwaway page first, then records the
eight scenes. Each scene holds for the larger of its base duration and its
measured narration clip plus 0.5s, so the voice track and the visuals stay
aligned. The timeline is written to /tmp/dpt-demo-tts/holds.json for assembly.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "video-work"
DEFAULT_TTS = Path("/tmp/dpt-demo-tts")
DEFAULT_AIRFLOW = "http://localhost:8080"
DEFAULT_AIRFLOW_USER = "airflow"
DEFAULT_AIRFLOW_PASSWORD = "airflow"
DEFAULT_PAGES = "https://willowvibe.github.io/data-pipeline-template"
CARD_DIR = Path(__file__).resolve().parent / "cards"
LOG_DIR = Path(__file__).resolve().parent / "logs"

BASE_HOLDS = [4.0, 13.0, 16.0, 14.0, 9.0, 8.0, 9.0, 6.0]

SCENES = [
    "title card",
    "copier",
    "make up",
    "airflow grid and graph",
    "dbt lineage",
    "sample table",
    "ci run",
    "end card",
]

COPIER_COMMAND = (
    "copier copy --defaults --data warehouse=duckdb --data orchestrator=none "
    "gh:willowvibe/data-pipeline-template weather-pipeline"
)


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=nw=1:nk=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(f"ffprobe failed for {path}: {result.stderr.strip()}")
    return float(result.stdout.strip())


def segment_durations(tts: Path) -> list[float]:
    durations = []
    for index in range(len(BASE_HOLDS)):
        segment = tts / f"{index:02d}.mp3"
        if not segment.exists():
            raise SystemExit(f"missing narration segment {segment}")
        durations.append(probe_duration(segment))
    return durations


def build_timeline(tts: Path) -> dict:
    durations = segment_durations(tts)
    holds = [max(base, length + 0.5) for base, length in zip(BASE_HOLDS, durations)]
    starts = []
    cursor = 0.0
    for hold in holds:
        starts.append(round(cursor, 3))
        cursor += hold
    timeline = {
        "scenes": SCENES,
        "audio_durations": [round(length, 3) for length in durations],
        "holds": [round(hold, 3) for hold in holds],
        "scene_starts": starts,
        "total": round(cursor, 3),
    }
    write_timeline(tts, timeline)
    return timeline


def write_timeline(tts: Path, timeline: dict) -> None:
    (tts / "holds.json").write_text(json.dumps(timeline, indent=2) + "\n")


def read_log(path: Path) -> list[str]:
    if not path.exists():
        raise SystemExit(f"missing log {path}")
    return [line for line in path.read_text().splitlines() if line.strip()]


def shorten(line: str, limit: int = 118) -> str:
    if len(line) <= limit:
        return line
    return line[: limit - 1] + "\u2026"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--airflow-url",
        default=DEFAULT_AIRFLOW,
        help=f"Airflow base URL (default: {DEFAULT_AIRFLOW})",
    )
    parser.add_argument(
        "--airflow-user",
        default=DEFAULT_AIRFLOW_USER,
        help=f"Airflow username (default: {DEFAULT_AIRFLOW_USER})",
    )
    parser.add_argument(
        "--airflow-password",
        default=DEFAULT_AIRFLOW_PASSWORD,
        help=f"Airflow password (default: {DEFAULT_AIRFLOW_PASSWORD})",
    )
    parser.add_argument(
        "--ci-url",
        required=True,
        help="GitHub Actions run URL to show in the CI scene",
    )
    parser.add_argument(
        "--pages-url",
        default=DEFAULT_PAGES,
        help=f"generated docs base URL (default: {DEFAULT_PAGES})",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"directory for the raw recording (default: {DEFAULT_OUT})",
    )
    parser.add_argument(
        "--tts",
        type=Path,
        default=DEFAULT_TTS,
        help=f"directory with 00.mp3..07.mp3 (default: {DEFAULT_TTS})",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    out = args.out
    tts = args.tts
    out.mkdir(parents=True, exist_ok=True)

    cards = {}
    for name in ("title", "terminal", "end"):
        path = CARD_DIR / f"{name}.html"
        if not path.exists():
            raise SystemExit(f"missing card {path}")
        cards[name] = path.resolve().as_uri()

    copier_lines = read_log(LOG_DIR / "copier.log")
    make_lines = [shorten(line) for line in read_log(LOG_DIR / "make-up.log")]

    timeline = build_timeline(tts)
    holds = timeline["holds"]
    starts = timeline["scene_starts"]
    print(f"timeline: {timeline['total']:.2f}s", file=sys.stderr)
    for index, (start, hold) in enumerate(zip(starts, holds)):
        print(f"scene {index}: start {start:.2f}s hold {hold:.2f}s", file=sys.stderr)

    for stale in out.glob("page@*.webm"):
        stale.unlink()

    from playwright.sync_api import Error, sync_playwright

    main_video = None
    poster_at = None
    graph_offset: dict[str, float] = {}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(out),
            record_video_size={"width": 1920, "height": 1080},
        )
        try:
            login = context.new_page()
            login.set_default_timeout(90000)
            login.set_default_navigation_timeout(45000)
            login.goto(
                f"{args.airflow_url}/auth/login/?next=%2Fdags%2Fweather_pipeline",
                wait_until="load",
            )
            login.get_by_label("Username:").fill(args.airflow_user)
            login.get_by_label("Password:").fill(args.airflow_password)
            login.get_by_role("button", name="Sign In").click()
            login.wait_for_url("**/dags/weather_pipeline**")
            login.close()

            page = context.new_page()
            page.set_default_timeout(90000)
            page.set_default_navigation_timeout(45000)

            def scene(index: int, action) -> float:
                started = time.monotonic()
                action()
                elapsed = time.monotonic() - started
                hold = holds[index]
                print(
                    f"scene {index}: actions {elapsed:.2f}s / hold {hold:.2f}s",
                    file=sys.stderr,
                )
                if elapsed > hold:
                    raise SystemExit(
                        f"scene {index} took {elapsed:.2f}s, longer than its "
                        f"{hold:.2f}s hold; narration would desync"
                    )
                remaining = hold - elapsed
                if remaining > 0:
                    page.wait_for_timeout(int(remaining * 1000))
                return elapsed

            def play_terminal(
                title: str, command: str, lines: list[str], index: int
            ) -> None:
                page.goto(cards["terminal"], wait_until="load")
                duration_ms = int((holds[index] - 1.2) * 1000)
                page.evaluate(
                    "cfg => playTerminal(cfg)",
                    {
                        "title": title,
                        "command": command,
                        "lines": lines,
                        "durationMs": duration_ms,
                    },
                )

            def airflow_scene() -> None:
                action_started = time.monotonic()
                page.goto(
                    f"{args.airflow_url}/dags/weather_pipeline", wait_until="load"
                )
                page.wait_for_load_state("networkidle")

                def expand_all() -> None:
                    # Expansion state is shared by grid and graph; the button is
                    # disabled once every group is already open.
                    button = page.get_by_role("button", name="Expand all task groups")
                    if button.is_enabled():
                        button.click()

                expand_all()
                page.wait_for_timeout(int(holds[3] * 0.45 * 1000))
                page.get_by_role("button", name="Show Graph (Press g)").click()
                graph_offset["value"] = time.monotonic() - action_started
                page.wait_for_timeout(1500)
                page.mouse.click(1357, 571)
                page.wait_for_timeout(1000)
                expand_all()
                page.wait_for_timeout(1000)
                page.locator(".react-flow__controls-fitview").click()
                page.mouse.move(1900, 1000)

            def dbt_scene() -> None:
                page.goto(
                    f"{args.pages_url}/dbt/index.html#!/overview?g_v=1",
                    wait_until="networkidle",
                )
                page.wait_for_timeout(3000)

            def sample_scene() -> None:
                page.goto(f"{args.pages_url}/sample.html", wait_until="load")
                page.evaluate("document.documentElement.style.zoom = '1.35'")

            def ci_scene() -> None:
                page.goto(args.ci_url, wait_until="networkidle")
                page.evaluate("document.documentElement.style.zoom = '1.25'")
                page.evaluate("window.scrollTo(0, 0)")

            scene(0, lambda: page.goto(cards["title"], wait_until="load"))
            scene(
                1,
                lambda: play_terminal(
                    "weather-pipeline \u2014 copier",
                    COPIER_COMMAND,
                    copier_lines,
                    1,
                ),
            )
            scene(
                2,
                lambda: play_terminal(
                    "weather-pipeline \u2014 make up",
                    "make up",
                    make_lines,
                    2,
                ),
            )
            scene(3, airflow_scene)
            scene(4, dbt_scene)
            scene(5, sample_scene)
            scene(6, ci_scene)
            scene(7, lambda: page.goto(cards["end"], wait_until="load"))

            offset = graph_offset.get("value", holds[3] * 0.5)
            poster_at = starts[3] + offset + max(0.0, holds[3] - offset) / 2.0

            main_video = page.video
        finally:
            context.close()
            browser.close()

    if poster_at is None:
        raise SystemExit("recording finished without a poster timestamp")

    main_path = None
    if main_video is not None:
        try:
            main_path = Path(main_video.path())
        except Error:
            main_path = None

    candidates = sorted(out.glob("page@*.webm"), key=lambda path: path.stat().st_mtime)
    if main_path is None:
        if not candidates:
            raise SystemExit("Playwright did not produce a video")
        main_path = candidates[-1]

    for candidate in candidates:
        if candidate.resolve() != main_path.resolve():
            candidate.unlink()

    target = out / "dpt-raw.webm"
    if target.exists():
        target.unlink()
    main_path.replace(target)

    recorded = probe_duration(target)
    if abs(recorded - timeline["total"]) > 0.5:
        raise SystemExit(
            f"recording is {recorded:.2f}s but the planned timeline is "
            f"{timeline['total']:.2f}s; narration would desync"
        )

    timeline["poster_at"] = round(float(poster_at), 3)
    write_timeline(tts, timeline)

    print(f"recording: {recorded:.2f}s (timeline {timeline['total']:.2f}s)")
    print(f"poster at: {timeline['poster_at']:.2f}s")
    print(target)


if __name__ == "__main__":
    main()
