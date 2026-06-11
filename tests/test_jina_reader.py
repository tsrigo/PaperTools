import unittest

from src.utils.jina_reader import (
    build_jina_reader_url,
    ensure_valid_paper_content,
    get_paper_content_issue,
    normalize_arxiv_pdf_url,
)


class JinaReaderTests(unittest.TestCase):
    def test_normalize_relative_arxiv_path(self):
        self.assertEqual(
            normalize_arxiv_pdf_url("/arxiv/2501.01234"),
            "https://arxiv.org/pdf/2501.01234.pdf",
        )

    def test_normalize_abs_url(self):
        self.assertEqual(
            normalize_arxiv_pdf_url("https://arxiv.org/abs/2501.01234v2"),
            "https://arxiv.org/pdf/2501.01234v2.pdf",
        )

    def test_normalize_raw_id(self):
        self.assertEqual(
            normalize_arxiv_pdf_url("2501.01234"),
            "https://arxiv.org/pdf/2501.01234.pdf",
        )

    def test_build_jina_reader_url(self):
        self.assertEqual(
            build_jina_reader_url("2501.01234"),
            "https://r.jina.ai/https://arxiv.org/pdf/2501.01234.pdf",
        )

    def test_invalid_content_detects_error_page(self):
        issue = get_paper_content_issue("Error code: 429 Too Many Requests")
        self.assertIsNotNone(issue)
        self.assertIn("错误页特征", issue)

    def test_valid_long_paper_text_can_mention_server_error(self):
        valid_text = (
            ("Introduction Methods Results " * 500)
            + "The benchmark contains a server error category for failed tool calls. "
            + ("Conclusion " * 500)
        )

        self.assertIsNone(get_paper_content_issue(valid_text))

    def test_ensure_valid_content_accepts_reasonable_text(self):
        valid_text = ("Introduction " * 300) + ("Method " * 300)
        self.assertTrue(
            ensure_valid_paper_content(valid_text, "test").startswith("Introduction")
        )


if __name__ == "__main__":
    unittest.main()
