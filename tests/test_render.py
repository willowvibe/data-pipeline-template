from pathlib import Path

import pytest

COMBINATIONS = [
    ("duckdb", "none"),
    ("duckdb", "airflow"),
    ("postgres", "none"),
    ("postgres", "airflow"),
]

TEXT_SUFFIXES = {".md", ".py", ".toml", ".yml", ".yaml", ".txt", ".ini", ".cfg", ".sh"}


def _text_files(root: Path) -> list[Path]:
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in TEXT_SUFFIXES and path.name != ".gitignore":
            continue
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        files.append(path)
    return files


@pytest.mark.parametrize(("warehouse", "orchestrator"), COMBINATIONS)
def test_render_shape(copie, warehouse, orchestrator):
    result = copie.copy(
        extra_answers={
            "project_name": "weather-pipeline",
            "warehouse": warehouse,
            "orchestrator": orchestrator,
        }
    )

    assert result.exit_code == 0
    assert result.exception is None

    project = result.project_dir
    assert (project / ".copier-answers.yml").is_file()
    assert (project / "src" / "weather_pipeline" / "__init__.py").is_file()
    assert (project / "pyproject.toml").is_file()
    assert (project / "README.md").is_file()

    for path in _text_files(project):
        if "dbt" in path.relative_to(project).parts:
            continue  # dbt models, macros and profiles legitimately contain Jinja
        text = path.read_text(encoding="utf-8")
        assert "{{" not in text, f"unrendered '{{{{' left in {path}"
        assert "{%" not in text, f"unrendered '{{%' left in {path}"
