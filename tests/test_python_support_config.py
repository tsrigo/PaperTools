from __future__ import annotations

import re
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]


ROOT = Path(__file__).resolve().parents[1]
SUPPORTED_CPYTHON_VERSIONS = ("3.10", "3.11", "3.12", "3.13", "3.14")


def _load_pyproject() -> dict:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def _workflow_text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _ci_test_matrix_versions() -> tuple[str, ...]:
    ci = _workflow_text(".github/workflows/ci.yml")
    match = re.search(r"python-version: \[(?P<versions>[^\]]+)\]", ci)
    assert match, "CI test matrix must declare python-version explicitly"
    return tuple(re.findall(r"'([^']+)'", match.group("versions")))


def _literal_workflow_python_versions(path: str) -> set[str]:
    return set(re.findall(r"python-version:\s*'([^']+)'", _workflow_text(path)))


def test_python_metadata_tracks_supported_cpython_versions():
    pyproject = _load_pyproject()
    project = pyproject["project"]
    classifiers = set(project["classifiers"])

    assert project["requires-python"] == ">=3.10"
    assert "Programming Language :: Python :: 3.9" not in classifiers
    assert {
        f"Programming Language :: Python :: {version}"
        for version in SUPPORTED_CPYTHON_VERSIONS
    } <= classifiers

    assert pyproject["tool"]["ruff"]["target-version"] == "py310"


def test_ci_matrix_tracks_declared_python_support():
    assert _ci_test_matrix_versions() == SUPPORTED_CPYTHON_VERSIONS


def test_workflow_tooling_uses_supported_python_versions():
    ci_versions = _literal_workflow_python_versions(".github/workflows/ci.yml")
    deploy_versions = _literal_workflow_python_versions(".github/workflows/deploy.yml")

    assert ci_versions
    assert deploy_versions
    assert ci_versions <= set(SUPPORTED_CPYTHON_VERSIONS)
    assert deploy_versions <= set(SUPPORTED_CPYTHON_VERSIONS)
