from __future__ import annotations

import textwrap

from scripts.check_dependency_metadata import check_dependency_metadata


def _write_project_files(tmp_path, requirements: str) -> None:
    (tmp_path / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [project]
            dependencies = [
                "requests>=2.28.0",
                "beautifulsoup4>=4.11.0",
            ]
            """
        ).strip(),
        encoding="utf-8",
    )
    (tmp_path / "requirements.txt").write_text(requirements, encoding="utf-8")


def test_dependency_metadata_accepts_matching_requirements(tmp_path):
    _write_project_files(
        tmp_path,
        """
        # Runtime dependencies mirror pyproject.toml.
        requests>=2.28.0
        beautifulsoup4>=4.11.0
        """,
    )

    assert check_dependency_metadata(tmp_path) == []


def test_dependency_metadata_rejects_extra_legacy_requirements(tmp_path):
    _write_project_files(
        tmp_path,
        """
        requests>=2.28.0
        beautifulsoup4>=4.11.0
        pydantic>=2.0.0
        """,
    )

    errors = check_dependency_metadata(tmp_path)

    assert errors
    assert "requirements.txt must mirror pyproject.toml" in errors[0]
