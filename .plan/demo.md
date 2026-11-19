# Demo video tooling for data-pipeline-template
scripts/demo/ was seeded by copying rag-docs-chatbot's demo tooling (record_demo.py, assemble_demo.py,
cards/title.html, cards/end.html). Adapt it to this project. The recorder runs with the SYSTEM python3
(Playwright 1.60 + Chromium are installed there; Playwright is not a repo dependency), records 1920x1080
via Playwright `record_video_dir`, and holds each scene for max(base hold, narration clip + 0.5 s),
writing the timeline to /tmp/dpt-demo-tts/holds.json. The assembler cuts scenes, pads by the transition,
joins with xfade, lays the narration clips at scene starts, and writes MP4 + poster. Keep that design,
the desync guards and the CLI shape; rename rag-specific names (rag-raw.webm -> dpt-raw.webm,
/tmp/rag-demo-tts -> /tmp/dpt-demo-tts, outputs data-pipeline-template-demo.mp4 and
data-pipeline-template-demo-poster.jpg in video-work/, which is gitignored). There are 8 narration clips
00.mp3..07.mp3. No captions or subtitle streams. Card style: match site/index.html light palette
(--bg #f5f7fb, --surface #fff, --text #162033, --muted #52607a, --accent #1668dc, --code #101a2c,
--code-text #e6edf8), IBM Plex Sans / IBM Plex Mono from Google Fonts, 1920x1080 fixed body.
Nothing here may claim anything not shown by real output.

## 1 cards
files: scripts/demo/cards/
do: Rewrite cards/title.html and cards/end.html for this project and add cards/terminal.html.
  - title.html: eyebrow "WillowVibe · open-source template", title "data-pipeline-template",
    subtitle "Start a client data project in a day", a row of chips: "Copier", "dbt", "DuckDB or Postgres",
    "Airflow + Cosmos", "GitHub Actions".
  - end.html: heading "Generate your own", a dark code block with
    `copier copy gh:willowvibe/data-pipeline-template my-pipeline`, then two lines of links text:
    "github.com/willowvibe/data-pipeline-template" and "willowvibe.github.io/data-pipeline-template",
    small footer "MIT · WillowVibe".
  - terminal.html: a full-frame dark terminal window (title bar with three dots and a title slot,
    --code background, IBM Plex Mono ~22px, line-height 1.45, padding 48px). It exposes
    `window.playTerminal({title, command, lines, durationMs})`: sets the title, types `$ ` + command
    at ~28 ms/char with a caret, then appends `lines` one by one spread evenly over the rest of
    durationMs, auto-scrolling so the newest line stays visible (overflow hidden, no scrollbar).
    Colour lines: containing " PASS " or "OK " or "Done. PASS" -> green #7ee787; "ERROR" or "FAIL" -> red
    #ff7b72; starting "INFO" -> muted #9fb0cc; `create` lines -> accent-soft #8cc4ff. Escape text
    (textContent), never innerHTML for line content. It sets `window.terminalDone = true` when finished.
done-when: `test -f scripts/demo/cards/terminal.html`; `grep -q playTerminal scripts/demo/cards/terminal.html`; `grep -q terminalDone scripts/demo/cards/terminal.html`; `! grep -qi rag scripts/demo/cards/title.html scripts/demo/cards/end.html`
dont: add external JS libraries
difficulty: medium
kind: change

## 2 recorder and assembler
files: scripts/demo/record_demo.py, scripts/demo/assemble_demo.py
needs: 1
do: Adapt both scripts to the 8 scenes below (BASE_HOLDS = [4, 13, 16, 14, 9, 8, 9, 6]).
  - Before scene 0, log in to Airflow on a SEPARATE page in the same context (not the recorded page):
    goto `{airflow}/auth/login/?next=%2Fdags%2Fweather_pipeline`, `get_by_label("Username:").fill(user)`,
    `get_by_label("Password:").fill(pw)`, `get_by_role("button", name="Sign In").click()`,
    `wait_for_url("**/dags/weather_pipeline**")`, then close that page. After recording, delete every
    other page@*.webm in the out dir so only the main page's video is kept. CLI flags: --airflow-url
    (default http://localhost:8080), --airflow-user/--airflow-password (default airflow), --ci-url
    (required; a GitHub Actions run URL), --pages-url (default
    https://willowvibe.github.io/data-pipeline-template), --out, --tts.
  - scene 0 title card. scene 7 end card.
  - scenes 1 and 2: goto cards/terminal.html, then `page.evaluate("cfg => playTerminal(cfg)", cfg)` with
    durationMs = int((hold - 1.2) * 1000) so the last line lands before the cut. Scene 1: title
    "weather-pipeline — copier", command
    `copier copy --defaults --data warehouse=duckdb --data orchestrator=none gh:willowvibe/data-pipeline-template weather-pipeline`,
    lines = scripts/demo/logs/copier.log (non-empty lines). Scene 2: title "weather-pipeline — make up",
    command `make up`, lines = scripts/demo/logs/make-up.log (non-empty lines), but shorten each line that is
    longer than 118 chars to 117 chars + "…" (Open-Meteo request URLs are very long).
  - scene 3 Airflow: goto `{airflow}/dags/weather_pipeline`, wait_for_load_state("networkidle"), click
    `get_by_role("button", name="Expand all task groups")`, hold ~45% of the scene on this grid view,
    then click `get_by_role("button", name="Show Graph (Press g)")`, wait 1.5 s, collapse the details panel
    with `page.mouse.click(1357, 571)`, wait 1 s, click "Expand all task groups" again, wait 1 s, click
    `.react-flow__controls-fitview`, then move the mouse to (1900, 1000) so no tooltip covers the graph.
  - scene 4 dbt lineage: goto `{pages}/dbt/index.html#!/overview?g_v=1` (wait_until networkidle) and wait
    ~3 s for the graph to lay out.
  - scene 5 sample table: goto `{pages}/sample.html`, set `document.documentElement.style.zoom='1.35'`.
  - scene 6 CI: goto ci_url (wait_until networkidle), zoom 1.25, scroll to top.
  - The page-load waits in scenes 3-6 count toward each scene's hold (keep the existing guard that fails
    if actions exceed the hold). Set default navigation timeout 45 s.
  - Poster frame: the middle of scene 3's graph phase (store poster_at in the timeline).
  - assemble_demo.py: same pipeline as before with the renamed paths, 8 clips, 0.35 s transitions,
    1920x1080 H.264 (crf 20, yuv420p, +faststart) + AAC 160k; verify no subtitle stream and that the
    output duration is within 0.5 s of timeline total; write the poster JPEG from poster_at.
done-when: `python3 -m py_compile scripts/demo/record_demo.py scripts/demo/assemble_demo.py`; `python3 scripts/demo/record_demo.py --help`; `python3 scripts/demo/assemble_demo.py --help`; `! grep -qi 'rag' scripts/demo/record_demo.py scripts/demo/assemble_demo.py`
dont: add repository dependencies; burn in captions
difficulty: hard
kind: change
