from __future__ import annotations

import io
import json
import http.server

import pytest

from src.core import serve_webpages


def _handler(request_headers: dict | None = None):
    handler = object.__new__(serve_webpages.CustomHTTPRequestHandler)
    handler.status = None
    handler.headers = request_headers or {}
    handler.sent_headers = []
    handler.wfile = io.BytesIO()
    handler.rfile = io.BytesIO()
    handler.send_response = lambda status: setattr(handler, "status", status)
    handler.send_header = lambda name, value: handler.sent_headers.append((name, value))
    handler.end_headers = lambda: None
    return handler


def _sent_headers(handler) -> dict:
    return dict(handler.sent_headers)


def _response_payload(handler) -> dict:
    return json.loads(handler.wfile.getvalue().decode("utf-8"))


def test_user_state_path_rejects_traversal(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    handler = _handler()

    with pytest.raises(ValueError):
        handler._state_file_for_date("../outside")

    assert not (tmp_path.parent / "outside" / ".user_state.json").exists()


def test_toggle_read_rejects_invalid_date_without_writing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    handler = _handler()

    handler._handle_toggle_read(
        {"date": "../outside", "arxiv_id": "2605.00001", "read": True}
    )

    assert handler.status == 400
    assert _response_payload(handler) == {"error": "invalid date or missing arxiv_id"}
    assert not (tmp_path.parent / "outside" / ".user_state.json").exists()


def test_toggle_read_persists_state_with_atomic_helper(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    handler = _handler()

    handler._handle_toggle_read(
        {"date": "2026-05-12", "arxiv_id": "2605.00001", "read": True}
    )

    assert handler.status == 200
    assert _response_payload(handler) == {"ok": True}
    state_file = tmp_path / "2026-05-12" / ".user_state.json"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state == {"deleted_ids": [], "read_ids": ["2605.00001"]}


def test_toggle_read_reports_state_write_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(serve_webpages, "save_json", lambda *_args, **_kwargs: False)
    handler = _handler()

    handler._handle_toggle_read(
        {"date": "2026-05-12", "arxiv_id": "2605.00001", "read": True}
    )

    assert handler.status == 500
    assert _response_payload(handler) == {"error": "failed to persist user state"}


def test_delete_refuses_sibling_prefix_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    safe_dir = tmp_path / "2026-05-12"
    sibling_target = tmp_path / "2026-05-12-other" / "paper"
    safe_dir.mkdir()
    sibling_target.mkdir(parents=True)
    handler = _handler()

    handler._handle_delete(
        {
            "date": "2026-05-12",
            "arxiv_id": "2605.00001",
            "paper_dir": "2026-05-12-other/paper",
        }
    )

    assert handler.status == 200
    assert _response_payload(handler) == {"ok": True, "deleted_dir": False}
    assert sibling_target.exists()


def test_delete_refuses_date_directory_itself(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    safe_dir = tmp_path / "2026-05-12"
    safe_dir.mkdir()
    handler = _handler()

    handler._handle_delete(
        {
            "date": "2026-05-12",
            "arxiv_id": "2605.00001",
            "paper_dir": "2026-05-12",
        }
    )

    assert handler.status == 200
    assert _response_payload(handler) == {"ok": True, "deleted_dir": False}
    assert safe_dir.exists()


def test_cors_rejects_non_loopback_origin(monkeypatch):
    handler = _handler({"Origin": "https://evil.example"})
    monkeypatch.setattr(
        http.server.SimpleHTTPRequestHandler, "end_headers", lambda _self: None
    )

    serve_webpages.CustomHTTPRequestHandler.end_headers(handler)

    headers = _sent_headers(handler)
    assert "Access-Control-Allow-Origin" not in headers
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "SAMEORIGIN"
    assert headers["Referrer-Policy"] == "no-referrer"


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://[::1]:8080",
    ],
)
def test_cors_allows_loopback_origins(origin, monkeypatch):
    handler = _handler({"Origin": origin})
    monkeypatch.setattr(
        http.server.SimpleHTTPRequestHandler, "end_headers", lambda _self: None
    )

    serve_webpages.CustomHTTPRequestHandler.end_headers(handler)

    headers = _sent_headers(handler)
    assert headers["Access-Control-Allow-Origin"] == origin
    assert headers["Access-Control-Allow-Methods"] == "GET, POST, OPTIONS"
    assert headers["Access-Control-Allow-Headers"] == "Content-Type"
    assert headers["Vary"] == "Origin"


@pytest.mark.parametrize(
    "origin",
    [
        "",
        "null",
        "file://local/index.html",
        "http://localhost.evil.example",
        "https://127.0.0.1.evil.example",
    ],
)
def test_cors_origin_validator_rejects_non_loopback(origin):
    assert not serve_webpages._is_allowed_cors_origin(origin)


def test_default_bind_host_is_loopback():
    assert serve_webpages.DEFAULT_BIND_HOST == "127.0.0.1"


def test_post_rejects_oversized_json_body():
    handler = _handler({"Content-Length": str(serve_webpages.MAX_API_BODY_BYTES + 1)})
    handler.path = "/api/toggle-read"

    handler.do_POST()

    assert handler.status == 413
    assert _response_payload(handler) == {"error": "request body too large"}


@pytest.mark.parametrize("content_length", ["not-a-number", "-1"])
def test_post_rejects_invalid_content_length(content_length):
    handler = _handler({"Content-Length": content_length})
    handler.path = "/api/toggle-read"

    handler.do_POST()

    assert handler.status == 400
    assert _response_payload(handler) == {"error": "invalid content length"}


def test_post_rejects_invalid_json_body():
    body = b"{bad json"
    handler = _handler({"Content-Length": str(len(body))})
    handler.rfile = io.BytesIO(body)
    handler.path = "/api/toggle-read"

    handler.do_POST()

    assert handler.status == 400
    assert _response_payload(handler) == {"error": "invalid json body"}


def test_post_rejects_non_object_json_body():
    body = b"[]"
    handler = _handler({"Content-Length": str(len(body))})
    handler.rfile = io.BytesIO(body)
    handler.path = "/api/toggle-read"

    handler.do_POST()

    assert handler.status == 400
    assert _response_payload(handler) == {"error": "json body must be an object"}


def test_post_accepts_valid_json_object(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    payload = {
        "date": "2026-05-12",
        "arxiv_id": "2605.00001",
        "read": True,
    }
    body = json.dumps(payload).encode("utf-8")
    handler = _handler({"Content-Length": str(len(body))})
    handler.rfile = io.BytesIO(body)
    handler.path = "/api/toggle-read"

    handler.do_POST()

    assert handler.status == 200
    assert _response_payload(handler) == {"ok": True}
