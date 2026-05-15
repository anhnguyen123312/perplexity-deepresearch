"""End-to-end smoke test for grok_search MCP package.

Usage:
    python tools/grok_smoke_test.py "What is 2+2?"
    python tools/grok_smoke_test.py "Latest news on x" --mode auto
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from deep_research.grok import GrokClient
from deep_research.grok.config import (
    MODE_GROK_4_3_BETA,
    VALID_MODES,
    get_statsig_cache_path,
)
from deep_research.grok.statsig import store_statsig_id


REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_DIR = REPO_ROOT / "docs" / "grok-mcp"


def seed_statsig_from_capture() -> None:
    """If we have a recorded statsig_id.json from capture_statsig_via_chrome,
    seed it into the cache so the smoke test doesn't have to re-capture."""
    src = DOC_DIR / "statsig_id.json"
    if not src.exists():
        return
    try:
        captured = json.loads(src.read_text())
        sid = captured["chat_send_headers"].get("x-statsig-id")
        if sid:
            store_statsig_id("/rest/app-chat/conversations/new", "POST", sid)
            print(f"[i] seeded x-statsig-id from {src.name}", flush=True)
    except Exception as e:
        print(f"[warn] couldn't seed statsig: {e}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("query", nargs="?", default="What is 2+2? Answer briefly.")
    parser.add_argument("--mode", default=MODE_GROK_4_3_BETA,
                        choices=sorted(VALID_MODES))
    args = parser.parse_args()

    print(f"[i] cache: {get_statsig_cache_path()}", flush=True)
    seed_statsig_from_capture()

    client = GrokClient()
    print(f"[i] sending: mode={args.mode!r} query={args.query!r}", flush=True)
    result = client.search(query=args.query, mode=args.mode)

    if "error" in result:
        print(f"[err] {result['error']}", flush=True)
        return 1

    print(f"\n[ok] mode={result['mode']} elapsed={result['elapsed_secs']}s "
          f"lines={result['stream_lines']}", flush=True)
    print(f"     conversation_id={result['conversation_id']}")
    print(f"     response_id={result['response_id']}")
    print(f"\n--- ANSWER ---\n{result['answer']}\n--- END ---")
    return 0


if __name__ == "__main__":
    sys.exit(main())
