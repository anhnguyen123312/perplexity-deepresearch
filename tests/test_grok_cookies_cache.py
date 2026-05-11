"""Tests for the grok config-store cache integration (US-005)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from perplexity_deep_research import profile_config
from perplexity_deep_research.grok import cookies as grok_cookies


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    legacy = tmp_path / "cookies.json"
    monkeypatch.setenv("PERPLEXITY_CONFIG_FILE", str(cfg))
    monkeypatch.setenv("PERPLEXITY_COOKIES_FILE", str(legacy))
    monkeypatch.delenv("CHROME_PROFILE_USED_GROK", raising=False)
    return cfg


class TestGrokCookiesCacheHit:
    def test_returns_cached_entry_without_scan(self, isolate_config):
        cookies = {"sso": "tok", "cf_clearance": "cf"}
        profile_config.save_profile_entry("grok", "Default", cookies)

        with (
            patch(
                "perplexity_deep_research.grok.cookies.extract_grok_cookies_all_profiles"
            ) as mock_all,
            patch(
                "perplexity_deep_research.grok.cookies.get_grok_cookies"
            ) as mock_get,
        ):
            result = grok_cookies.get_grok_cookies_cached()

            assert result == cookies
            mock_all.assert_not_called()
            mock_get.assert_not_called()


class TestGrokCookiesCacheMiss:
    def test_harvest_populates_cache_and_returns_preferred(self, isolate_config):
        fresh_default = {"sso": "default-tok"}
        fresh_p1 = {"sso": "p1-tok"}
        with (
            patch(
                "perplexity_deep_research.grok.cookies.extract_grok_cookies_all_profiles",
                return_value=[("Profile 1", fresh_p1), ("Default", fresh_default)],
            ),
            patch(
                "perplexity_deep_research.grok.cookies._preferred_grok_profile_order",
                return_value=["Default", "Profile 1"],
            ),
        ):
            result = grok_cookies.get_grok_cookies_cached()

            assert result == fresh_default
            # Both saved
            assert profile_config.get_profile_entry("grok", "Default")["cookies"] == fresh_default
            assert profile_config.get_profile_entry("grok", "Profile 1")["cookies"] == fresh_p1

    def test_falls_back_to_single_profile_when_harvest_empty(self, isolate_config):
        fresh = {"sso": "diagnostic-tok"}
        with (
            patch(
                "perplexity_deep_research.grok.cookies.extract_grok_cookies_all_profiles",
                return_value=[],
            ),
            patch(
                "perplexity_deep_research.grok.cookies.get_grok_cookies",
                return_value=fresh,
            ),
        ):
            result = grok_cookies.get_grok_cookies_cached()

            assert result == fresh
            assert profile_config.get_profile_entry("grok", "Default")["cookies"] == fresh

    def test_expired_entry_triggers_rescan(self, isolate_config):
        old = {"sso": "old"}
        profile_config.save_profile_entry("grok", "Default", old)
        profile_config.invalidate_profile("grok", "Default")

        fresh = {"sso": "fresh"}
        with patch(
            "perplexity_deep_research.grok.cookies.extract_grok_cookies_all_profiles",
            return_value=[("Default", fresh)],
        ):
            result = grok_cookies.get_grok_cookies_cached()

            assert result == fresh
            stored = profile_config.get_profile_entry("grok", "Default")
            assert stored["cookies"] == fresh
            assert not profile_config.is_expired(stored)


class TestInvalidateGrokCache:
    def test_invalidate_marks_all_entries_expired(self, isolate_config):
        profile_config.save_profile_entry("grok", "Default", {"sso": "a"})
        profile_config.save_profile_entry("grok", "Profile 1", {"sso": "b"})

        grok_cookies.invalidate_grok_cache()

        for name in ("Default", "Profile 1"):
            entry = profile_config.get_profile_entry("grok", name)
            assert profile_config.is_expired(entry)

    def test_invalidate_is_safe_when_empty(self, isolate_config):
        # No grok entries yet — must not raise
        grok_cookies.invalidate_grok_cache()
        assert profile_config.list_valid_profiles("grok") == []
