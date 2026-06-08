"""Tests for the grok config-store cache integration (US-005)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from deep_research import profile_config
from deep_research.grok import cookies as grok_cookies


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    legacy = tmp_path / "cookies.json"
    monkeypatch.setenv("PERPLEXITY_CONFIG_FILE", str(cfg))
    monkeypatch.setenv("PERPLEXITY_COOKIES_FILE", str(legacy))
    monkeypatch.delenv("CHROME_PROFILE_USED_GROK", raising=False)
    monkeypatch.delenv("CHROME_PROFILE", raising=False)
    return cfg


class TestGrokCookiesCacheHit:
    def test_returns_cached_entry_without_scan(self, isolate_config):
        cookies = {"sso": "tok", "cf_clearance": "cf"}
        profile_config.save_profile_entry("grok", "Default", cookies)

        with (
            patch(
                "deep_research.grok.cookies.extract_grok_cookies_all_profiles"
            ) as mock_all,
            patch(
                "deep_research.grok.cookies.get_grok_cookies"
            ) as mock_get,
        ):
            result = grok_cookies.get_grok_cookies_cached()

            assert result == cookies
            mock_all.assert_not_called()
            mock_get.assert_not_called()


class TestGrokCookiesCacheMiss:
    def test_miss_resolves_single_profile(self, isolate_config):
        fresh = {"sso": "tok"}
        with (
            patch(
                "deep_research.grok.cookies._resolve_grok_profile",
                return_value=("Default", fresh),
            ) as mock_resolve,
            patch(
                "deep_research.grok.cookies.extract_grok_cookies_all_profiles"
            ) as mock_all,
        ):
            result = grok_cookies.get_grok_cookies_cached()

            assert result == fresh
            mock_resolve.assert_called_once()
            mock_all.assert_not_called()  # scan-all path removed
            assert profile_config.get_profile_entry("grok", "Default")["cookies"] == fresh

    def test_uses_configured_profile(self, isolate_config):
        profile_config.set_chosen_profile("grok", "Profile 1")
        fresh = {"sso": "p1"}
        captured = {}

        def _fake_resolve(chosen):
            captured["chosen"] = chosen
            return "Profile 1", fresh

        with patch("deep_research.grok.cookies._resolve_grok_profile", _fake_resolve):
            result = grok_cookies.get_grok_cookies_cached()

        assert result == fresh
        assert captured["chosen"] == "Profile 1"

    def test_expired_entry_triggers_resolve(self, isolate_config):
        profile_config.save_profile_entry("grok", "Default", {"sso": "old"})
        profile_config.invalidate_profile("grok", "Default")

        fresh = {"sso": "fresh"}
        with patch(
            "deep_research.grok.cookies._resolve_grok_profile",
            return_value=("Default", fresh),
        ):
            result = grok_cookies.get_grok_cookies_cached()

            assert result == fresh
            stored = profile_config.get_profile_entry("grok", "Default")
            assert stored["cookies"] == fresh
            assert not profile_config.is_expired(stored)

    def test_chosen_profile_ignores_other_cached(self, isolate_config):
        """Pinned grok profile must NOT fall back to a different profile's cache."""
        profile_config.save_profile_entry("grok", "Default", {"sso": "default"})
        profile_config.set_chosen_profile("grok", "Profile 5")

        fresh = {"sso": "p5"}
        with patch(
            "deep_research.grok.cookies._resolve_grok_profile",
            return_value=("Profile 5", fresh),
        ) as mock_resolve:
            result = grok_cookies.get_grok_cookies_cached()

        assert result == fresh
        mock_resolve.assert_called_once()


class TestResolveGrokProfile:
    @staticmethod
    def _d(tmp_path, name):
        p = tmp_path / name
        p.mkdir()
        return p

    def test_single_profile_remembered(self, isolate_config, tmp_path, monkeypatch):
        only = self._d(tmp_path, "Default")
        fresh = {"sso": "tok"}
        monkeypatch.setattr(grok_cookies.sys, "platform", "darwin")
        monkeypatch.setattr(grok_cookies, "list_chrome_profile_dirs", lambda: [only])
        monkeypatch.setattr(grok_cookies, "list_chrome_profiles_ordered", lambda: [only])
        monkeypatch.setattr(grok_cookies, "_harvest_grok_profile", lambda p: fresh)

        name, cookies = grok_cookies._resolve_grok_profile(None)

        assert (name, cookies) == ("Default", fresh)
        assert profile_config.get_chosen_profile("grok") == "Default"

    def test_multiple_profiles_warn_not_remembered(self, isolate_config, tmp_path, monkeypatch):
        d0 = self._d(tmp_path, "Default")
        d1 = self._d(tmp_path, "Profile 1")
        fresh = {"sso": "tok"}
        monkeypatch.setattr(grok_cookies.sys, "platform", "darwin")
        monkeypatch.setattr(grok_cookies, "list_chrome_profile_dirs", lambda: [d0, d1])
        monkeypatch.setattr(grok_cookies, "list_chrome_profiles_ordered", lambda: [d0, d1])
        monkeypatch.setattr(
            grok_cookies,
            "_harvest_grok_profile",
            lambda p: fresh if p.name == "Profile 1" else None,
        )

        name, _ = grok_cookies._resolve_grok_profile(None)

        assert name == "Profile 1"
        assert profile_config.get_chosen_profile("grok") is None

    def test_configured_profile_not_signed_in_raises(self, isolate_config, tmp_path, monkeypatch):
        d0 = self._d(tmp_path, "Default")
        monkeypatch.setattr(grok_cookies.sys, "platform", "darwin")
        monkeypatch.setattr(grok_cookies, "list_chrome_profile_dirs", lambda: [d0])
        monkeypatch.setattr(grok_cookies, "_harvest_grok_profile", lambda p: None)

        with pytest.raises(RuntimeError, match="not signed in"):
            grok_cookies._resolve_grok_profile("Default")


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
