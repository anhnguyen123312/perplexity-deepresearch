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


class BlockedError(PerplexityError):
    """Raised when Perplexity returns ``status=BLOCKED`` (permanent).

    Typical causes: ``locked_reason=insufficient_credits`` for tier-locked
    models (e.g. ``pplx_asi`` powering deep research / Advanced Research).
    Retrying does not help — the account must regain quota or the caller
    must pick a different mode.
    """

    pass
