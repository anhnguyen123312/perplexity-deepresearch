"""
Custom exception classes for Perplexity Deep Research MCP Server.

Exception hierarchy:
- PerplexityError (base)
  - CookieExtractionError
  - BrowserControlError
  - AuthenticationError
  - RateLimitError
"""


class PerplexityError(Exception):
    """Base exception for all Perplexity-related errors."""

    pass


class CookieExtractionError(PerplexityError):
    """Raised when cookie extraction from Chrome fails."""

    pass


class BrowserControlError(PerplexityError):
    """Raised when browser control operations (AppleScript) fail."""

    pass


class AuthenticationError(PerplexityError):
    """Raised when authentication with Perplexity API fails."""

    pass


class RateLimitError(PerplexityError):
    """Raised when Perplexity API rate limit is exceeded."""

    pass
