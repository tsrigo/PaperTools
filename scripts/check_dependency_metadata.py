#!/usr/bin/env python3
"""Check that legacy dependency files stay aligned with pyproject.toml."""

from __future__ import annotations

from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
    import tomli as tomllib  # type: ignore[no-redef]


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _normalize_requirement(line: str) -> str:
    """Normalize whitespace while preserving requirement semantics."""
    return " ".join(line.strip().split())


def read_runtime_requirements(requirements_path: Path) -> list[str]:
    """Read non-comment runtime requirements from requirements.txt."""
    requirements: list[str] = []
    for raw_line in requirements_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("-r ", "--requirement ", "-c ", "--constraint ")):
            raise ValueError(
                f"{requirements_path}: nested requirement files are not supported: {line}"
            )
        requirements.append(_normalize_requirement(line))
    return requirements


def read_project_dependencies(pyproject_path: Path) -> list[str]:
    """Read core project dependencies from pyproject.toml."""
    with pyproject_path.open("rb") as handle:
        pyproject = tomllib.load(handle)
    project = pyproject.get("project")
    if not isinstance(project, dict):
        raise ValueError(f"{pyproject_path}: missing [project] table")
    dependencies = project.get("dependencies")
    if not isinstance(dependencies, list) or not all(
        isinstance(item, str) for item in dependencies
    ):
        raise ValueError(
            f"{pyproject_path}: project.dependencies must be a string list"
        )
    return [_normalize_requirement(item) for item in dependencies]


def check_dependency_metadata(project_root: Path = PROJECT_ROOT) -> list[str]:
    """Return metadata drift errors."""
    pyproject_dependencies = read_project_dependencies(project_root / "pyproject.toml")
    requirements = read_runtime_requirements(project_root / "requirements.txt")
    if requirements != pyproject_dependencies:
        return [
            "requirements.txt must mirror pyproject.toml [project.dependencies]",
            f"pyproject.toml: {pyproject_dependencies}",
            f"requirements.txt: {requirements}",
        ]
    return []


def main() -> int:
    errors = check_dependency_metadata()
    if errors:
        print("Dependency metadata check failed:")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("Dependency metadata is consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
