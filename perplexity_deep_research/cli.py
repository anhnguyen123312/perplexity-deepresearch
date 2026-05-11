"""CLI entrypoint for managing the unified config store.

Usage examples::

    perplexity-deep-research-config show
    perplexity-deep-research-config show --reveal
    perplexity-deep-research-config export /tmp/snapshot.json
    perplexity-deep-research-config import /tmp/snapshot.json
    perplexity-deep-research-config import /tmp/snapshot.json --replace
    perplexity-deep-research-config set-expire perplexity 43200
    perplexity-deep-research-config rescan grok

All commands accept ``-c <path>`` / ``--config <path>`` to override the active
config file (same as ``PERPLEXITY_CONFIG_FILE``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

from . import profile_config


def _mask_cookies(entry: dict) -> dict:
    """Return a copy of ``entry`` with cookie values reduced to a short prefix."""
    masked = {k: v for k, v in entry.items() if k != "cookies"}
    masked["cookies"] = {
        name: (val[:6] + "…") if isinstance(val, str) and len(val) > 8 else val
        for name, val in entry.get("cookies", {}).items()
    }
    return masked


def _mask_config(config: dict) -> dict:
    out = json.loads(json.dumps(config))  # deep copy
    for provider in out.get("providers", {}).values():
        for name, entry in provider.get("profiles", {}).items():
            provider["profiles"][name] = _mask_cookies(entry)
    return out


def _path_arg(args: argparse.Namespace) -> Path | None:
    return Path(args.config) if args.config else None


def cmd_show(args: argparse.Namespace) -> int:
    path = _path_arg(args)
    cfg = profile_config.load_config(path)
    if args.reveal:
        print(json.dumps(cfg, indent=2))
    else:
        print(json.dumps(_mask_config(cfg), indent=2))
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    path = _path_arg(args)
    dest = profile_config.export_config(Path(args.dest), path)
    print(f"Exported config to {dest}")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    path = _path_arg(args)
    profile_config.import_config(
        Path(args.src), merge=not args.replace, path=path
    )
    mode = "replaced" if args.replace else "merged"
    print(f"Imported config ({mode}) from {args.src}")
    return 0


def cmd_set_expire(args: argparse.Namespace) -> int:
    path = _path_arg(args)
    profile_config.set_expire_seconds(args.provider, args.seconds, path)
    print(f"Set {args.provider}.expire_seconds = {args.seconds}")
    return 0


def cmd_rescan(args: argparse.Namespace) -> int:
    """Force a fresh harvest and persist every signed-in profile."""
    path = _path_arg(args)
    # Wipe existing entries so the harvest is the sole source of truth.
    cfg = profile_config.load_config(path)
    cfg["providers"][args.provider]["profiles"] = {}
    profile_config.save_config(cfg, path)

    if args.provider == "perplexity":
        from .cookies import extract_cookies_all_profiles
        harvested = extract_cookies_all_profiles()
    else:
        from .grok.cookies import extract_grok_cookies_all_profiles
        harvested = extract_grok_cookies_all_profiles()

    if not harvested:
        print(
            f"No Chrome profile is signed in to {args.provider} — nothing saved.",
            file=sys.stderr,
        )
        return 1

    for name, cookies in harvested:
        profile_config.save_profile_entry(args.provider, name, cookies, path)
    print(f"Saved {args.provider} entries: {[name for name, _ in harvested]}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="perplexity-deep-research-config",
        description="Manage the perplexity-deep-research unified config store.",
    )
    parser.add_argument(
        "-c",
        "--config",
        help="Path to config.json (overrides PERPLEXITY_CONFIG_FILE).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_show = sub.add_parser("show", help="Print the current config as JSON.")
    p_show.add_argument(
        "--reveal",
        action="store_true",
        help="Print full cookie values (default: truncated for safety).",
    )
    p_show.set_defaults(func=cmd_show)

    p_export = sub.add_parser("export", help="Copy config.json to a destination path.")
    p_export.add_argument("dest", help="Destination file path.")
    p_export.set_defaults(func=cmd_export)

    p_import = sub.add_parser("import", help="Import a config.json.")
    p_import.add_argument("src", help="Source file path.")
    p_import.add_argument(
        "--replace",
        action="store_true",
        help="Replace the entire config (default: merge).",
    )
    p_import.set_defaults(func=cmd_import)

    p_expire = sub.add_parser(
        "set-expire", help="Set the expire_seconds for a provider."
    )
    p_expire.add_argument("provider", choices=("perplexity", "grok"))
    p_expire.add_argument("seconds", type=int)
    p_expire.set_defaults(func=cmd_set_expire)

    p_rescan = sub.add_parser(
        "rescan",
        help="Re-extract cookies for a provider and persist every signed-in profile.",
    )
    p_rescan.add_argument("provider", choices=("perplexity", "grok"))
    p_rescan.set_defaults(func=cmd_rescan)

    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
