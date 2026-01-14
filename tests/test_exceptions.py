"""Tests for custom exception classes"""

import pytest
from src.utils.exceptions import (
    PaperToolsError,
    ConfigurationError,
    APIError,
    RateLimitError,
    TimeoutError,
    CrawlError,
    FilterError,
    SummaryError,
    CacheError,
    FileError,
    ValidationError,
    PipelineError,
)


class TestPaperToolsExceptions:
    """Test custom exception classes"""

    def test_base_exception(self):
        """Test PaperToolsError base class"""
        with pytest.raises(PaperToolsError):
            raise PaperToolsError("Test error")

    def test_configuration_error(self):
        """Test ConfigurationError"""
        with pytest.raises(ConfigurationError):
            raise ConfigurationError("Missing API key")

    def test_api_error_with_details(self):
        """Test APIError with status code and response"""
        error = APIError("API failed", status_code=500, response="Internal Server Error")
        assert error.status_code == 500
        assert error.response == "Internal Server Error"
        assert str(error) == "API failed"

    def test_rate_limit_error(self):
        """Test RateLimitError with retry_after"""
        error = RateLimitError("Too many requests", retry_after=60)
        assert error.retry_after == 60
        assert isinstance(error, APIError)

    def test_timeout_error(self):
        """Test TimeoutError inheritance"""
        error = TimeoutError("Request timed out")
        assert isinstance(error, APIError)
        assert isinstance(error, PaperToolsError)

    def test_pipeline_error_with_stage(self):
        """Test PipelineError with stage info"""
        error = PipelineError(
            "Pipeline failed",
            stage="filter",
            details="LLM returned invalid response"
        )
        assert error.stage == "filter"
        assert error.details == "LLM returned invalid response"

    def test_exception_hierarchy(self):
        """Test that all exceptions inherit from PaperToolsError"""
        exceptions = [
            ConfigurationError,
            APIError,
            RateLimitError,
            TimeoutError,
            CrawlError,
            FilterError,
            SummaryError,
            CacheError,
            FileError,
            ValidationError,
            PipelineError,
        ]
        for exc_class in exceptions:
            assert issubclass(exc_class, PaperToolsError)

    def test_catch_all_papertools_errors(self):
        """Test catching all PaperTools errors with base class"""
        errors_caught = []

        for exc_class in [CrawlError, FilterError, SummaryError]:
            try:
                raise exc_class("Test")
            except PaperToolsError as e:
                errors_caught.append(type(e).__name__)

        assert len(errors_caught) == 3
        assert "CrawlError" in errors_caught
        assert "FilterError" in errors_caught
        assert "SummaryError" in errors_caught
