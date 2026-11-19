from pathlib import Path

import pytest
import yaml

COMBINATIONS = [
    ("duckdb", "none"),
    ("duckdb", "airflow"),
    ("postgres", "none"),
    ("postgres", "airflow"),
]

PACKAGE_NAME = "weather_pipeline"

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
    assert (project / "src" / PACKAGE_NAME / "__init__.py").is_file()
    assert (project / "pyproject.toml").is_file()
    assert (project / "README.md").is_file()
    assert (project / "data" / ".gitkeep").is_file()
    assert "!data/.gitkeep" in (project / ".gitignore").read_text(encoding="utf-8")

    for path in _text_files(project):
        parts = path.relative_to(project).parts
        if "dbt" in parts:
            continue  # dbt models, macros and profiles legitimately contain Jinja
        text = path.read_text(encoding="utf-8")
        if ".github" in parts:
            text = text.replace("${{", "")  # GitHub Actions expressions are not Jinja
        assert "{{" not in text, f"unrendered '{{{{' left in {path}"
        assert "{%" not in text, f"unrendered '{{%' left in {path}"

    workflow_path = project / ".github" / "workflows" / "ci.yml"
    assert workflow_path.is_file()
    workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
    assert isinstance(workflow, dict)
    assert "jobs" in workflow

    compose_path = project / "docker-compose.yml"
    if warehouse == "duckdb" and orchestrator == "none":
        assert not compose_path.exists()
    else:
        assert compose_path.is_file()

    airflow_dir = project / "airflow"
    dag_test = project / "tests" / "test_dag.py"
    if orchestrator == "airflow":
        assert airflow_dir.is_dir()
        assert (airflow_dir / "dags" / "weather_pipeline.py").is_file()
        assert dag_test.is_file()
        assert "airflow-dag" in workflow["jobs"]
    else:
        assert not airflow_dir.exists()
        assert not dag_test.exists()
        assert "airflow-dag" not in workflow["jobs"]

    profiles = (project / "dbt" / "profiles.yml").read_text(encoding="utf-8")
    assert f"type: {warehouse}" in profiles

    assert PACKAGE_NAME in (project / "pyproject.toml").read_text(encoding="utf-8")
    assert PACKAGE_NAME in (project / "dbt" / "dbt_project.yml").read_text(encoding="utf-8")
    assert (project / "src" / PACKAGE_NAME).is_dir()
