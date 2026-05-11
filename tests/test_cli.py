"""Tests for the perplexity-deep-research-config CLI (US-007)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from perplexity_deep_research import cli, profile_config


@pytest.fixture(autouse=True)
def isolate_config(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    legacy = tmp_path / "cookies.json"
    monkeypatch.setenv("PERPLEXITY_CONFIG_FILE", str(cfg))
    monkeypatch.setenv("PERPLEXITY_COOKIES_FILE", str(legacy))
    return cfg


class TestShow:
    def test_show_masks_cookies_by_default(self, capsys, isolate_config):
        profile_config.save_profile_entry(
            "perplexity", "Default", {"session": "supersecrettoken123"}
        )

        rc = cli.main(["show"])
        assert rc == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        cookie_val = data["providers"]["perplexity"]["profiles"]["Default"]["cookies"][
            "session"
        ]
        assert cookie_val.endswith("…")
        assert "supersecrettoken123" not in out

    def test_show_reveal_prints_full_cookies(self, capsys, isolate_config):
        profile_config.save_profile_entry(
            "perplexity", "Default", {"session": "supersecrettoken123"}
        )

        rc = cli.main(["show", "--reveal"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "supersecrettoken123" in out


class TestExportImport:
    def test_export_then_import_roundtrip(self, tmp_path, capsys, isolate_config):
        profile_config.save_profile_entry(
            "perplexity", "Default", {"session": "tok-a"}
        )
        profile_config.save_profile_entry("grok", "Profile 1", {"sso": "tok-b"})

        dest = tmp_path / "snapshot.json"
        assert cli.main(["export", str(dest)]) == 0
        assert dest.exists()
        snapshot = json.loads(dest.read_text())
        assert (
            snapshot["providers"]["perplexity"]["profiles"]["Default"]["cookies"][
                "session"
            ]
            == "tok-a"
        )

        # Wipe and re-import
        profile_config.save_config(profile_config._empty_config())
        assert profile_config.get_profile_entry("perplexity", "Default") is None

        assert cli.main(["import", str(dest)]) == 0
        assert (
            profile_config.get_profile_entry("perplexity", "Default")["cookies"][
                "session"
            ]
            == "tok-a"
        )
        assert (
            profile_config.get_profile_entry("grok", "Profile 1")["cookies"]["sso"]
            == "tok-b"
        )

    def test_import_merge_keeps_existing_profiles(self, tmp_path, isolate_config):
        profile_config.save_profile_entry(
            "perplexity", "Default", {"session": "local"}
        )
        # Build a snapshot file with a different profile (separate config path)
        profile_config.save_profile_entry(
            "perplexity",
            "Profile 1",
            {"session": "imported"},
            path=tmp_path / "snap.json",
        )
        # Hack: write snapshot at tmp_path/snap.json was just done.
        snap_path = tmp_path / "snap.json"

        assert cli.main(["import", str(snap_path)]) == 0
        # Both should now exist
        assert profile_config.get_profile_entry("perplexity", "Default") is not None
        assert profile_config.get_profile_entry("perplexity", "Profile 1") is not None

    def test_import_replace_overwrites(self, tmp_path, isolate_config):
        profile_config.save_profile_entry(
            "perplexity", "Default", {"session": "local"}
        )
        snap_path = tmp_path / "snap.json"
        profile_config.save_profile_entry(
            "perplexity",
            "Profile 1",
            {"session": "imported"},
            path=snap_path,
        )

        assert cli.main(["import", str(snap_path), "--replace"]) == 0
        # Default should be gone, Profile 1 should remain
        assert profile_config.get_profile_entry("perplexity", "Default") is None
        assert profile_config.get_profile_entry("perplexity", "Profile 1") is not None


class TestSetExpire:
    def test_set_expire_updates_provider(self, capsys, isolate_config):
        rc = cli.main(["set-expire", "perplexity", "7200"])
        assert rc == 0
        cfg = profile_config.load_config()
        assert cfg["providers"]["perplexity"]["expire_seconds"] == 7200


class TestRescan:
    def test_rescan_perplexity_persists_all_profiles(self, capsys, isolate_config):
        fresh = [
            ("Default", {"__Secure-next-auth.session-token": "a"}),
            ("Profile 1", {"__Secure-next-auth.session-token": "b"}),
        ]
        with patch(
            "perplexity_deep_research.cookies.extract_cookies_all_profiles",
            return_value=fresh,
        ):
            rc = cli.main(["rescan", "perplexity"])
            assert rc == 0

        out = capsys.readouterr().out
        assert "Default" in out and "Profile 1" in out
        assert (
            profile_config.get_profile_entry("perplexity", "Default")["cookies"][
                "__Secure-next-auth.session-token"
            ]
            == "a"
        )
        assert (
            profile_config.get_profile_entry("perplexity", "Profile 1")["cookies"][
                "__Secure-next-auth.session-token"
            ]
            == "b"
        )

    def test_rescan_grok_persists_all_profiles(self, capsys, isolate_config):
        fresh = [("Default", {"sso": "x"}), ("Profile 1", {"sso": "y"})]
        with patch(
            "perplexity_deep_research.grok.cookies.extract_grok_cookies_all_profiles",
            return_value=fresh,
        ):
            rc = cli.main(["rescan", "grok"])
            assert rc == 0

        assert profile_config.get_profile_entry("grok", "Default")["cookies"]["sso"] == "x"
        assert (
            profile_config.get_profile_entry("grok", "Profile 1")["cookies"]["sso"] == "y"
        )

    def test_rescan_returns_error_when_no_profiles_signed_in(
        self, capsys, isolate_config
    ):
        with patch(
            "perplexity_deep_research.cookies.extract_cookies_all_profiles",
            return_value=[],
        ):
            rc = cli.main(["rescan", "perplexity"])
            assert rc == 1
