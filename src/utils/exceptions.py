"""
自定义异常类 - 用于更精确的错误处理
Custom exception classes for more precise error handling
"""


class PaperToolsError(Exception):
    """PaperTools 基础异常类"""
    pass


class ConfigurationError(PaperToolsError):
    """配置相关错误"""
    pass


class APIError(PaperToolsError):
    """API 调用相关错误"""

    def __init__(self, message: str, status_code: int = None, response: str = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class RateLimitError(APIError):
    """API 速率限制错误"""

    def __init__(self, message: str = "API 速率限制", retry_after: int = None):
        super().__init__(message)
        self.retry_after = retry_after


class TimeoutError(APIError):
    """API 超时错误"""
    pass


class CrawlError(PaperToolsError):
    """爬取相关错误"""
    pass


class FilterError(PaperToolsError):
    """筛选相关错误"""
    pass


class SummaryError(PaperToolsError):
    """总结生成相关错误"""
    pass


class CacheError(PaperToolsError):
    """缓存相关错误"""
    pass


class FileError(PaperToolsError):
    """文件操作相关错误"""
    pass


class ValidationError(PaperToolsError):
    """数据验证错误"""
    pass


class PipelineError(PaperToolsError):
    """流水线执行错误"""

    def __init__(self, message: str, stage: str = None, details: str = None):
        super().__init__(message)
        self.stage = stage
        self.details = details
