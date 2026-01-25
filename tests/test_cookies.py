"""
Tests for cookie extraction and management module.

Tests cover:
- Cookie extraction from Chrome
- Cookie normalization with variant matching
- HTTP cookie reconstruction
- Cookie persistence and expiry
- Database lock detection
- TRY-FIRST flow with Chrome handling
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from sqlite3 import OperationalError
from unittest.mock import MagicMock, patch

import pytest

from perplexity_deep_research.cookies import (
    extract_cookies_raw,
    extract_cookies_with_relaunch,
    get_chrome_cookie_path,
    get_cookies,
    load_cookies,
    normalize_cookies,
    save_cookies,
    to_http_cookies,
)
from perplexity_deep_research.exceptions import CookieExtractionError


@pytest.fixture(autouse=True)
def isolate_cookies_file(tmp_path, monkeypatch):
    """Redirect PERPLEXITY_COOKIES_FILE to tmp_path for all tests."""
    test_cookies_file = tmp_path / "cookies.json"
    monkeypatch.setenv("PERPLEXITY_COOKIES_FILE", str(test_cookies_file))
    return test_cookies_file


class TestExtractCookiesRaw:
    """Tests for extract_cookies_raw() function."""

    def test_extract_cookies_success(self):
        """Test successful cookie extraction from Chrome."""
        raw_cookies = {
            "__Secure-next-auth.session-token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
            "__Secure-next-auth.csrf-token": "abc123def456",
        }

        with patch("perplexity_deep_research.cookies.chrome_cookies") as mock_chrome:
            mock_chrome.return_value = raw_cookies
            result = extract_cookies_raw()

        assert result == raw_cookies
        assert "session_token" not in result  # Raw, not normalized


class TestNormalizeCookies:
    """Tests for normalize_cookies() function."""

    def test_normalize_cookies_secure_prefix(self):
        """Test normalization with __Secure- variant."""
        raw_cookies = {
            "__Secure-next-auth.session-token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
            "__Secure-next-auth.csrf-token": "abc123def456",
        }

        result = normalize_cookies(raw_cookies)

        assert result["session_token"] == "eyJ0eXAiOiJKV1QiLCJhbGc..."
        assert result["session_token_name"] == "__Secure-next-auth.session-token"
        assert result["csrf_token"] == "abc123def456"
        assert result["csrf_token_name"] == "__Secure-next-auth.csrf-token"

    def test_normalize_cookies_plain(self):
        """Test normalization with plain next-auth. variant."""
        raw_cookies = {
            "next-auth.session-token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
            "next-auth.csrf-token": "xyz789",
        }

        result = normalize_cookies(raw_cookies)

        assert result["session_token"] == "eyJ0eXAiOiJKV1QiLCJhbGc..."
        assert result["session_token_name"] == "next-auth.session-token"
        assert result["csrf_token"] == "xyz789"
        assert result["csrf_token_name"] == "next-auth.csrf-token"

    def test_normalize_cookies_mixed_variants(self):
        """Test normalization with mixed variants (prefers __Secure-)."""
        raw_cookies = {
            "__Secure-next-auth.session-token": "secure_token",
            "next-auth.session-token": "plain_token",  # Should be ignored
            "next-auth.csrf-token": "csrf_value",
        }

        result = normalize_cookies(raw_cookies)

        # Should prefer __Secure- variant
        assert result["session_token"] == "secure_token"
        assert result["session_token_name"] == "__Secure-next-auth.session-token"
        assert result["csrf_token"] == "csrf_value"

    def test_normalize_cookies_missing_session(self):
        """Test that missing session token raises error."""
        raw_cookies = {
            "__Secure-next-auth.csrf-token": "abc123",
        }

        with pytest.raises(CookieExtractionError, match="No session token found"):
            normalize_cookies(raw_cookies)

    def test_normalize_cookies_optional_csrf(self):
        """Test that CSRF token is optional."""
        raw_cookies = {
            "__Secure-next-auth.session-token": "session_value",
        }

        result = normalize_cookies(raw_cookies)

        assert result["session_token"] == "session_value"
        assert "csrf_token" not in result
        assert "csrf_token_name" not in result


class TestToHttpCookies:
    """Tests for to_http_cookies() function."""

    def test_to_http_cookies_with_csrf(self):
        """Test HTTP reconstruction with both session and CSRF tokens."""
        normalized = {
            "session_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
            "session_token_name": "__Secure-next-auth.session-token",
            "csrf_token": "abc123def456",
            "csrf_token_name": "__Secure-next-auth.csrf-token",
        }

        result = to_http_cookies(normalized)

        assert result == {
            "__Secure-next-auth.session-token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
            "__Secure-next-auth.csrf-token": "abc123def456",
        }

    def test_to_http_cookies_without_csrf(self):
        """Test HTTP reconstruction with only session token."""
        normalized = {
            "session_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
            "session_token_name": "__Secure-next-auth.session-token",
        }

        result = to_http_cookies(normalized)

        assert result == {
            "__Secure-next-auth.session-token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
        }

    def test_to_http_cookies_preserves_original_names(self):
        """Test that original cookie names are preserved in HTTP format."""
        normalized = {
            "session_token": "token_value",
            "session_token_name": "next-auth.session-token",  # Plain variant
            "csrf_token": "csrf_value",
            "csrf_token_name": "next-auth.csrf-token",
        }

        result = to_http_cookies(normalized)

        # Should use original names, not canonical keys
        assert "next-auth.session-token" in result
        assert "next-auth.csrf-token" in result
        assert "session_token" not in result
        assert "csrf_token" not in result


class TestSaveCookies:
    """Tests for save_cookies() function."""

    def test_save_cookies(self, isolate_cookies_file):
        """Test saving cookies to JSON file."""
        cookies = {
            "session_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
            "session_token_name": "__Secure-next-auth.session-token",
        }

        save_cookies(cookies, isolate_cookies_file)

        assert isolate_cookies_file.exists()
        data = json.loads(isolate_cookies_file.read_text())
        assert data["cookies"] == cookies
        assert "extracted_at" in data

    def test_save_cookies_creates_parent_dir(self, tmp_path, monkeypatch):
        """Test that save_cookies creates parent directory if missing."""
        cookies_file = tmp_path / "subdir" / "nested" / "cookies.json"
        monkeypatch.setenv("PERPLEXITY_COOKIES_FILE", str(cookies_file))

        cookies = {
            "session_token": "token_value",
            "session_token_name": "__Secure-next-auth.session-token",
        }

        save_cookies(cookies, cookies_file)

        assert cookies_file.exists()
        assert cookies_file.parent.exists()

    def test_save_cookies_with_default_path(self, isolate_cookies_file):
        """Test save_cookies uses get_cookies_file_path() by default."""
        cookies = {
            "session_token": "token_value",
            "session_token_name": "__Secure-next-auth.session-token",
        }

        save_cookies(cookies)  # No path argument

        assert isolate_cookies_file.exists()


class TestLoadCookies:
    """Tests for load_cookies() function."""

    def test_load_cookies_valid(self, isolate_cookies_file):
        """Test loading valid cookies (age < 24h)."""
        cookies = {
            "session_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
            "session_token_name": "__Secure-next-auth.session-token",
        }
        save_cookies(cookies, isolate_cookies_file)

        result = load_cookies(isolate_cookies_file)

        assert result == cookies

    def test_load_cookies_expired(self, isolate_cookies_file):
        """Test that expired cookies return None."""
        cookies = {
            "session_token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
            "session_token_name": "__Secure-next-auth.session-token",
        }

        # Save with old timestamp
        old_time = (datetime.now() - timedelta(hours=25)).isoformat()
        data = {"cookies": cookies, "extracted_at": old_time}
        isolate_cookies_file.write_text(json.dumps(data))

        result = load_cookies(isolate_cookies_file)

        assert result is None

    def test_load_cookies_missing_file(self, isolate_cookies_file):
        """Test that missing file returns None."""
        result = load_cookies(isolate_cookies_file)

        assert result is None

    def test_load_cookies_with_default_path(self, isolate_cookies_file):
        """Test load_cookies uses get_cookies_file_path() by default."""
        cookies = {
            "session_token": "token_value",
            "session_token_name": "__Secure-next-auth.session-token",
        }
        save_cookies(cookies, isolate_cookies_file)

        result = load_cookies()  # No path argument

        assert result == cookies


class TestExtractCookiesWithRelaunch:
    """Tests for extract_cookies_with_relaunch() function."""

    def test_extract_succeeds_without_prompt_if_not_locked(self):
        """Test TRY-FIRST: extraction succeeds → no Chrome prompt called."""
        raw_cookies = {
            "__Secure-next-auth.session-token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
        }

        with (
            patch(
                "perplexity_deep_research.cookies.check_full_disk_access"
            ) as mock_fda,
            patch(
                "perplexity_deep_research.cookies.extract_cookies_raw"
            ) as mock_extract,
            patch(
                "perplexity_deep_research.cookies.ensure_chrome_accessible"
            ) as mock_ensure,
        ):
            mock_fda.return_value = True
            mock_extract.return_value = raw_cookies

            result = extract_cookies_with_relaunch()

            assert result["session_token"] == "eyJ0eXAiOiJKV1QiLCJhbGc..."
            mock_ensure.assert_not_called()

    def test_extract_prompts_only_when_locked(self):
        """Test that Chrome prompt is only called when DB is locked."""
        raw_cookies = {
            "__Secure-next-auth.session-token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
        }

        lock_error = OperationalError("database is locked")

        with (
            patch(
                "perplexity_deep_research.cookies.check_full_disk_access"
            ) as mock_fda,
            patch(
                "perplexity_deep_research.cookies.extract_cookies_raw"
            ) as mock_extract,
            patch(
                "perplexity_deep_research.cookies.ensure_chrome_accessible"
            ) as mock_ensure,
            patch("perplexity_deep_research.cookies.relaunch_chrome") as mock_relaunch,
        ):
            mock_fda.return_value = True
            mock_extract.side_effect = [lock_error, raw_cookies]
            mock_ensure.return_value = MagicMock(
                accessible=True, was_quit=True, was_running=True
            )

            result = extract_cookies_with_relaunch()

            mock_ensure.assert_called_once()
            mock_relaunch.assert_called_once()
            assert result["session_token"] == "eyJ0eXAiOiJKV1QiLCJhbGc..."

    def test_extract_raises_if_chrome_not_accessible(self):
        """Test that error is raised if Chrome can't be accessed."""
        lock_error = OperationalError("database is locked")

        with (
            patch(
                "perplexity_deep_research.cookies.check_full_disk_access"
            ) as mock_fda,
            patch(
                "perplexity_deep_research.cookies.extract_cookies_raw"
            ) as mock_extract,
            patch(
                "perplexity_deep_research.cookies.ensure_chrome_accessible"
            ) as mock_ensure,
        ):
            mock_fda.return_value = True
            mock_extract.side_effect = lock_error
            mock_ensure.return_value = MagicMock(accessible=False)

            with pytest.raises(CookieExtractionError, match="could not be closed"):
                extract_cookies_with_relaunch()

    def test_extract_propagates_non_lock_errors(self):
        """Test that non-lock errors are propagated."""
        other_error = ValueError("Some other error")

        with (
            patch(
                "perplexity_deep_research.cookies.check_full_disk_access"
            ) as mock_fda,
            patch(
                "perplexity_deep_research.cookies.extract_cookies_raw"
            ) as mock_extract,
            patch(
                "perplexity_deep_research.cookies.ensure_chrome_accessible"
            ) as mock_ensure,
        ):
            mock_fda.return_value = True
            mock_extract.side_effect = other_error

            with pytest.raises(ValueError, match="Some other error"):
                extract_cookies_with_relaunch()

            mock_ensure.assert_not_called()

    def test_extract_raises_if_full_disk_access_missing(self):
        """Test that error is raised if Full Disk Access is missing."""
        with (
            patch(
                "perplexity_deep_research.cookies.check_full_disk_access"
            ) as mock_fda,
            patch(
                "perplexity_deep_research.cookies.show_full_disk_access_dialog"
            ) as mock_dialog,
        ):
            mock_fda.return_value = False

            with pytest.raises(
                CookieExtractionError, match="Full Disk Access required"
            ):
                extract_cookies_with_relaunch()

            mock_dialog.assert_called_once()

    def test_extract_prompts_for_keychain_password(self):
        """Test that keychain password is prompted when needed."""
        raw_cookies = {
            "__Secure-next-auth.session-token": "eyJ0eXAiOiJKV1QiLCJhbGc...",
        }
        keychain_error = Exception("keychain access denied")

        with (
            patch(
                "perplexity_deep_research.cookies.check_full_disk_access"
            ) as mock_fda,
            patch(
                "perplexity_deep_research.cookies.extract_cookies_raw"
            ) as mock_extract,
            patch(
                "perplexity_deep_research.cookies.prompt_keychain_password"
            ) as mock_prompt,
        ):
            mock_fda.return_value = True
            mock_extract.side_effect = [keychain_error, raw_cookies]
            mock_prompt.return_value = "test_password"

            result = extract_cookies_with_relaunch()

            mock_prompt.assert_called_once()
            assert result["session_token"] == "eyJ0eXAiOiJKV1QiLCJhbGc..."

    def test_extract_raises_if_keychain_cancelled(self):
        """Test that error is raised if keychain password prompt is cancelled."""
        keychain_error = Exception("keychain access denied")

        with (
            patch(
                "perplexity_deep_research.cookies.check_full_disk_access"
            ) as mock_fda,
            patch(
                "perplexity_deep_research.cookies.extract_cookies_raw"
            ) as mock_extract,
            patch(
                "perplexity_deep_research.cookies.prompt_keychain_password"
            ) as mock_prompt,
        ):
            mock_fda.return_value = True
            mock_extract.side_effect = keychain_error
            mock_prompt.return_value = None

            with pytest.raises(
                CookieExtractionError, match="Keychain access cancelled"
            ):
                extract_cookies_with_relaunch()


class TestGetCookies:
    """Tests for get_cookies() public API."""

    def test_get_cookies_returns_cached(self, isolate_cookies_file):
        """Test that cached cookies are returned if valid."""
        cookies = {
            "session_token": "cached_token",
            "session_token_name": "__Secure-next-auth.session-token",
        }
        save_cookies(cookies, isolate_cookies_file)

        with patch(
            "perplexity_deep_research.cookies.extract_cookies_with_relaunch"
        ) as mock_extract:
            result = get_cookies()

            # Should return cached without calling extract
            assert result == cookies
            mock_extract.assert_not_called()

    def test_get_cookies_extracts_fresh_if_missing(self, isolate_cookies_file):
        """Test that fresh cookies are extracted if cache missing."""
        fresh_cookies = {
            "session_token": "fresh_token",
            "session_token_name": "__Secure-next-auth.session-token",
        }

        with patch(
            "perplexity_deep_research.cookies.extract_cookies_with_relaunch"
        ) as mock_extract:
            mock_extract.return_value = fresh_cookies

            result = get_cookies()

            assert result == fresh_cookies
            # Should have saved to cache
            assert isolate_cookies_file.exists()

    def test_get_cookies_extracts_fresh_if_expired(self, isolate_cookies_file):
        """Test that fresh cookies are extracted if cache expired."""
        old_cookies = {
            "session_token": "old_token",
            "session_token_name": "__Secure-next-auth.session-token",
        }
        # Save with old timestamp
        old_time = (datetime.now() - timedelta(hours=25)).isoformat()
        data = {"cookies": old_cookies, "extracted_at": old_time}
        isolate_cookies_file.write_text(json.dumps(data))

        fresh_cookies = {
            "session_token": "fresh_token",
            "session_token_name": "__Secure-next-auth.session-token",
        }

        with patch(
            "perplexity_deep_research.cookies.extract_cookies_with_relaunch"
        ) as mock_extract:
            mock_extract.return_value = fresh_cookies

            result = get_cookies()

            assert result == fresh_cookies
            # Should have updated cache
            loaded = load_cookies(isolate_cookies_file)
            assert loaded == fresh_cookies


class TestDatabaseLockedDetection:
    """Tests for database lock error detection."""

    def test_database_locked_detection(self):
        """Test is_database_locked_error() detects lock patterns."""
        from perplexity_deep_research.config import is_database_locked_error

        # Test various lock error messages
        lock_errors = [
            OperationalError("database is locked"),
            OperationalError("database is busy"),
            OperationalError("unable to open database"),
            OperationalError("disk i/o error"),
        ]

        for error in lock_errors:
            assert is_database_locked_error(error) is True

    def test_database_locked_detection_non_lock_error(self):
        """Test is_database_locked_error() returns False for non-lock errors."""
        from perplexity_deep_research.config import is_database_locked_error

        non_lock_errors = [
            OperationalError("table not found"),
            ValueError("some other error"),
            RuntimeError("something else"),
        ]

        for error in non_lock_errors:
            assert is_database_locked_error(error) is False


class TestGetChromeCookiePath:
    """Tests for get_chrome_cookie_path() function."""

    def test_get_chrome_cookie_path_default_profile(self, monkeypatch):
        """Test Chrome cookie path resolution with default profile."""
        # Mock the path existence check
        with patch("perplexity_deep_research.cookies.Path.exists") as mock_exists:
            mock_exists.return_value = True
            with patch("perplexity_deep_research.cookies.Path.resolve") as mock_resolve:
                mock_resolve.return_value = Path(
                    "/Users/test/Library/Application Support/Google/Chrome/Default/Cookies"
                )

                result = get_chrome_cookie_path()

                assert isinstance(result, str)
                assert "Cookies" in result

    def test_get_chrome_cookie_path_custom_profile(self, monkeypatch):
        """Test Chrome cookie path resolution with custom profile."""
        with patch("perplexity_deep_research.cookies.Path.exists") as mock_exists:
            mock_exists.return_value = True
            with patch("perplexity_deep_research.cookies.Path.resolve") as mock_resolve:
                mock_resolve.return_value = Path(
                    "/Users/test/Library/Application Support/Google/Chrome/Profile 1/Cookies"
                )

                result = get_chrome_cookie_path(profile="Profile 1")

                assert isinstance(result, str)
                assert "Profile 1" in result

    def test_get_chrome_cookie_path_not_found(self):
        """Test that error is raised if Chrome cookie file not found."""
        with patch("perplexity_deep_research.cookies.Path.exists") as mock_exists:
            mock_exists.return_value = False

            with pytest.raises(
                CookieExtractionError, match="Chrome cookie file not found"
            ):
                get_chrome_cookie_path()
