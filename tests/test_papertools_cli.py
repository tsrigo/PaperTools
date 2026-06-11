from __future__ import annotations

import sys
from types import SimpleNamespace
import builtins

import pytest

import papertools


def test_serve_webpages_rejects_existing_unvalidated_site(tmp_path, monkeypatch):
    webpages = tmp_path / "webpages"
    webpages.mkdir()
    (webpages / "index.html").write_text("<html></html>", encoding="utf-8")
    started = []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        papertools, "validate_webpages_for_publication", lambda _webpages_dir: False
    )
    monkeypatch.setattr(papertools, "start_web_server", lambda: started.append(True))

    assert papertools.serve_webpages() == 1
    assert started == []


def test_serve_webpages_starts_only_after_validation(tmp_path, monkeypatch):
    webpages = tmp_path / "webpages"
    webpages.mkdir()
    (webpages / "index.html").write_text("<html></html>", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        papertools, "validate_webpages_for_publication", lambda _webpages_dir: True
    )
    monkeypatch.setattr(papertools, "start_web_server", lambda: 17)

    assert papertools.serve_webpages() == 17


def test_serve_webpages_propagates_unified_generation_failure(tmp_path, monkeypatch):
    summary = tmp_path / "summary"
    summary.mkdir()
    (summary / "papers.json").write_text("[]", encoding="utf-8")
    calls = []

    def fake_run(cmd, check=False):
        calls.append((cmd, check))
        return SimpleNamespace(returncode=7)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(papertools.subprocess, "run", fake_run)

    assert papertools.serve_webpages() == 7
    assert calls == [
        (
            [
                sys.executable,
                "src/core/pipeline.py",
                "--start-from",
                "unified",
                "--skip-serve",
            ],
            False,
        )
    ]


def test_validate_webpages_for_publication_runs_release_validator(
    tmp_path, monkeypatch
):
    validator = tmp_path / "scripts" / "validate_published_payloads.py"
    validator.parent.mkdir()
    validator.write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    calls = []

    def fake_run(cmd, check=False):
        calls.append((cmd, check))
        return SimpleNamespace(returncode=0)

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(papertools.subprocess, "run", fake_run)

    assert papertools.validate_webpages_for_publication("webpages") is True
    assert calls == [
        (
            [
                sys.executable,
                "scripts/validate_published_payloads.py",
                "--webpages-dir",
                "webpages",
            ],
            False,
        )
    ]


def test_main_returns_serve_exit_code(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["papertools.py", "serve"])
    monkeypatch.setattr(papertools, "check_python_version", lambda: None)
    monkeypatch.setattr(papertools, "serve_webpages", lambda: 5)

    assert papertools.main() == 5


def test_missing_dependencies_do_not_auto_install_by_default(monkeypatch):
    real_import = builtins.__import__
    install_calls = []

    def fake_import(name, *args, **kwargs):
        if name == "openai":
            raise ImportError("missing openai")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(
        papertools.subprocess,
        "check_call",
        lambda cmd: install_calls.append(cmd),
    )

    assert papertools.check_and_install_dependencies() is False
    assert install_calls == []


def test_missing_dependencies_install_only_when_explicitly_requested(monkeypatch):
    real_import = builtins.__import__
    install_calls = []

    def fake_import(name, *args, **kwargs):
        if name == "openai":
            raise ImportError("missing openai")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(
        papertools.subprocess,
        "check_call",
        lambda cmd: install_calls.append(cmd),
    )

    assert papertools.check_and_install_dependencies(install_missing=True) is True
    assert install_calls == [[sys.executable, "-m", "pip", "install", "openai>=1.0.0"]]


def test_check_command_plumbs_install_missing_flag(monkeypatch):
    calls = []

    monkeypatch.setattr(sys, "argv", ["papertools.py", "check", "--install-missing"])
    monkeypatch.setattr(papertools, "check_python_version", lambda: None)
    monkeypatch.setattr(
        papertools,
        "check_and_install_dependencies",
        lambda install_missing=False: calls.append(install_missing) or True,
    )
    monkeypatch.setattr(papertools, "check_config", lambda: True)
    monkeypatch.setattr(papertools, "report_document_extractor_statuses", lambda: True)

    assert papertools.main() == 0
    assert calls == [True]


def test_check_python_version_rejects_runtime_below_declared_floor(monkeypatch, capsys):
    monkeypatch.setattr(papertools.sys, "version_info", (3, 9, 18))

    with pytest.raises(SystemExit) as exc:
        papertools.check_python_version()

    assert exc.value.code == 1
    assert "Python 3.10" in capsys.readouterr().out


def test_check_python_version_accepts_declared_floor(monkeypatch):
    monkeypatch.setattr(papertools.sys, "version_info", (3, 10, 0))

    papertools.check_python_version()
