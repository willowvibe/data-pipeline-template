import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from packaging.version import InvalidVersion, Version

TEMPLATE_ROOT = Path(__file__).resolve().parents[1]
GIT_IDENTITY = [
    "-c",
    "user.name=Copier Update Test",
    "-c",
    "user.email=copier-update@example.com",
]


def _run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def _git(*args: str, cwd: Path = TEMPLATE_ROOT) -> subprocess.CompletedProcess[str]:
    return _run(["git", *args], cwd=cwd)


def _pep440_tags() -> list[tuple[Version, str]]:
    tags: list[tuple[Version, str]] = []
    for tag in _git("tag", "--list").stdout.splitlines():
        try:
            version = Version(tag)
        except InvalidVersion:
            continue
        if version.is_prerelease or version.is_devrelease:
            continue
        tags.append((version, tag))
    return sorted(tags, key=lambda item: item[0], reverse=True)


def _describe_head() -> str:
    return _git("describe", "--tags", "--always").stdout.strip()


def _is_pep440_describe(description: str) -> bool:
    match = re.match(r"^(?P<tag>.+)-(?P<n>\d+)-g(?P<sha>[0-9a-f]+)$", description)
    candidate = match.group("tag") if match else description
    try:
        Version(candidate)
    except InvalidVersion:
        return False
    return True


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("v1.0.0", True),
        ("v1.0.0-3-gb2401ce", True),
        ("b2401ce", False),
        ("not-a-version-2-gabc123", False),
    ],
)
def test_is_pep440_describe(description: str, expected: bool) -> None:
    assert _is_pep440_describe(description) is expected


def test_copier_update_from_newest_tag(tmp_path: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git is not installed")

    if _git("rev-parse", "--git-dir").returncode != 0:
        pytest.skip("template repo is not a git checkout")

    tags = _pep440_tags()
    if not tags:
        pytest.skip(
            "no PEP 440 git tag yet; copier update needs versioned refs on both sides"
        )

    _, tag = tags[0]
    project = tmp_path / "weather-pipeline"

    copy_result = _run(
        [
            sys.executable,
            "-m",
            "copier",
            "copy",
            "--defaults",
            "--vcs-ref",
            tag,
            "--data",
            "warehouse=duckdb",
            "--data",
            "orchestrator=none",
            str(TEMPLATE_ROOT),
            str(project),
        ]
    )
    assert copy_result.returncode == 0, copy_result.stderr

    assert _git("init", "--quiet", cwd=project).returncode == 0
    assert _git("add", ".", cwd=project).returncode == 0
    commit_result = _run(
        ["git", *GIT_IDENTITY, "commit", "--quiet", "-m", "Initial template copy"],
        cwd=project,
    )
    assert commit_result.returncode == 0, commit_result.stderr

    head_commit = _git("rev-parse", "HEAD").stdout.strip()
    head_description = _describe_head()
    if not _is_pep440_describe(head_description):
        pytest.skip(
            "HEAD has no PEP 440-describable tag ancestry; "
            "copier update needs a version on both refs"
        )

    update_result = _run(
        [
            sys.executable,
            "-m",
            "copier",
            "update",
            "--defaults",
            "--vcs-ref",
            head_commit,
        ],
        cwd=project,
    )
    assert update_result.returncode == 0, update_result.stderr

    rejected = list(project.rglob("*.rej"))
    assert not rejected, f"copier update left conflict files: {rejected}"

    answers = yaml.safe_load((project / ".copier-answers.yml").read_text(encoding="utf-8"))
    assert answers["_commit"] == head_description
