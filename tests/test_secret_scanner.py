from pathlib import Path

from scripts import check_secrets


def test_secret_scanner_detects_openai_style_key_without_echoing_full_value():
    secret = "sk-" + ("A" * 32)

    findings = check_secrets.scan_text("example.env", f"OPENAI_API_KEY={secret}\n")

    assert len(findings) == 1
    assert findings[0].kind == "openai_api_key"
    formatted = findings[0].format()
    assert secret not in formatted
    assert "..." in formatted


def test_secret_scanner_allows_documented_placeholders():
    text = "\n".join(
        [
            "OPENAI_API_KEY=sk-REPLACE_WITH_YOUR_KEY",
            "OPENAI_API_KEY=your_key_here",
            "WEBHOOK_URL=https://api.pumble.com/workspaces/<workspace-id>/incomingWebhooks/postMessage/<webhook-token>",
        ]
    )

    assert check_secrets.scan_text("README.md", text) == []


def test_secret_scanner_detects_pumble_webhook():
    token = "A" * 24
    webhook = (
        "https://api.pumble.com/workspaces/workspace/incomingWebhooks/"
        f"postMessage/{token}"
    )

    findings = check_secrets.scan_text("notes.md", f"WEBHOOK_URL={webhook}\n")

    assert len(findings) == 1
    assert findings[0].kind == "pumble_webhook"
    assert webhook not in findings[0].format()


def test_secret_scanner_reports_clean_repository():
    root = Path(__file__).resolve().parents[1]

    assert check_secrets.scan_repository(root) == []
