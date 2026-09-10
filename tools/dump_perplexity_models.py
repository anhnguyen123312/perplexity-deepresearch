"""
Dump the Perplexity model catalog from the endpoint the web client itself uses.

Reads cookies from the config store via PerplexityClient, so it needs no
browser and burns no query quota.

Usage:
    .venv/bin/python tools/dump_perplexity_models.py [--provider ANTHROPIC] [--json out.json]
"""

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from deep_research.perplexity.client import PerplexityClient  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", help="Filter by provider (ANTHROPIC, OPENAI, ...)")
    ap.add_argument("--json", type=Path, help="Write the raw catalog to this file")
    args = ap.parse_args()

    catalog = PerplexityClient().get_models()
    if args.json:
        args.json.write_text(json.dumps(catalog, indent=1))
        print(f"[info] wrote {args.json}", file=sys.stderr)

    by_mode = defaultdict(list)
    for model_id, meta in catalog.items():
        if args.provider and (meta.get("provider") or "").upper() != args.provider.upper():
            continue
        by_mode[meta.get("mode")].append((model_id, meta))

    for mode in sorted(by_mode):
        # The payload `mode` the web client pairs with these models.
        payload_mode = "asi" if mode == "asi" else "copilot"
        print(f"\n=== mode={mode} (payload mode={payload_mode}) — {len(by_mode[mode])} ===")
        for model_id, meta in sorted(by_mode[mode]):
            print(f"  {model_id:46s} {str(meta.get('label')):32s} {meta.get('provider')}")


if __name__ == "__main__":
    main()
