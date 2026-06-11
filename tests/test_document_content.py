"""Tests for shared extracted-document content validation."""

from src.utils.document_content import get_document_content_issue, normalize_whitespace


def test_shared_document_content_rules_detect_error_pages_without_length_gate():
    content = "503 Service Unavailable\nGateway Timeout\n" + ("retry " * 500)

    assert (
        get_document_content_issue(content, enforce_paper_length=False)
        == "命中错误页特征: 503 service unavailable"
    )


def test_shared_document_content_rules_detect_long_antibot_pages():
    content = (
        "Just a moment... Please enable JavaScript and cookies. "
        + ("challenge " * 12000)
        + "Cloudflare Ray ID: abc123"
    )

    assert (
        get_document_content_issue(content, enforce_paper_length=True)
        == "命中访问拦截页特征: just a moment"
    )


def test_shared_document_content_rules_allow_long_papers_discussing_captcha():
    content = (
        ("Introduction Methods Results " * 500)
        + "The experiment studies captcha resistance in web automation. "
        + ("Conclusion " * 500)
    )

    assert get_document_content_issue(content, enforce_paper_length=True) is None


def test_shared_document_content_rules_keep_cache_and_paper_length_gates_separate():
    short_real_content = "paper text"

    assert (
        get_document_content_issue(short_real_content, enforce_paper_length=False)
        is None
    )
    assert (
        get_document_content_issue(short_real_content, enforce_paper_length=True)
        == "内容过短 (10 chars)"
    )


def test_shared_document_content_rules_allow_long_paper_discussing_server_errors():
    content = (
        ("Introduction Methods Results " * 500)
        + "The benchmark has a server error label for failed tool calls. "
        + ("Conclusion " * 500)
    )

    assert get_document_content_issue(content, enforce_paper_length=True) is None


def test_normalize_whitespace_accepts_non_string_values():
    assert normalize_whitespace(None) == ""
    assert normalize_whitespace(" a\n\tb ") == "a b"
    assert normalize_whitespace(123) == "123"
