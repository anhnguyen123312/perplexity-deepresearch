"""Smoke-test POST /rest/app-chat/conversations/new with Grok 4.3 (beta) mode."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from curl_cffi import requests
from pycookiecheat import BrowserType, chrome_cookies


REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_DIR = REPO_ROOT / "docs" / "grok-mcp"
DOC_DIR.mkdir(parents=True, exist_ok=True)


GROK_43_MODE_ID = "grok-420-computer-use-sa"


def make_session():
    raw = chrome_cookies("https://grok.com/", browser=BrowserType.CHROME)
    sess = requests.Session(impersonate="chrome142")
    for k, v in raw.items():
        sess.cookies.set(k, v, domain=".grok.com")
    sess.headers.update({
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/147.0.0.0 Safari/537.36",
    })
    return sess


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--query", default="What is 2+2? Answer briefly.")
    p.add_argument("--mode-id", default=GROK_43_MODE_ID)
    p.add_argument("--model", default="grok-4")
    args = p.parse_args()

    sess = make_session()

    # Absolute minimum body
    body = {
        "modelName": args.model,
        "message": args.query,
        "modeId": args.mode_id,
    }

    print(f"[i] POST /rest/app-chat/conversations/new mode={args.mode_id} model={args.model}",
          flush=True)
    print(f"[i] query: {args.query!r}", flush=True)

    out = DOC_DIR / "grok43_stream.txt"
    chunks = []
    t0 = time.time()
    r = sess.post(
        "https://grok.com/rest/app-chat/conversations/new",
        json=body,
        timeout=120,
        stream=True,
    )
    print(f"[i] status={r.status_code} ct={r.headers.get('content-type')}",
          flush=True)
    if r.status_code != 200:
        err = r.text or ""
        print(f"[err] headers={dict(r.headers)}", flush=True)
        print(f"[err] body[len={len(err)}]={err[:2000]!r}", flush=True)
        # In stream mode body may already be consumed; try iter
        if not err:
            try:
                err = b"".join(r.iter_content()).decode("utf-8", "replace")
                print(f"[err] iter body={err[:2000]!r}", flush=True)
            except Exception as ee:
                print(f"[err] iter failed: {ee}", flush=True)
        (DOC_DIR / "grok43_error.txt").write_text(
            json.dumps({"status": r.status_code,
                        "headers": dict(r.headers), "body": err},
                       indent=2)
        )
        return 1

    first_line_logged = False
    for line in r.iter_lines():
        if not line:
            continue
        if isinstance(line, bytes):
            line = line.decode("utf-8", "replace")
        chunks.append(line)
        if not first_line_logged:
            print(f"[i] first line: {line[:300]}", flush=True)
            first_line_logged = True

    elapsed = time.time() - t0
    out.write_text("\n".join(chunks))
    print(f"[done] {len(chunks)} lines in {elapsed:.1f}s → {out}", flush=True)

    # Try to extract assistant token text from SSE/json chunks
    answer_parts = []
    for line in chunks:
        try:
            j = json.loads(line)
        except Exception:
            continue
        # Walk for token field
        def walk(o):
            if isinstance(o, dict):
                if "token" in o and isinstance(o["token"], str):
                    answer_parts.append(o["token"])
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(j)

    if answer_parts:
        ans = "".join(answer_parts)
        print(f"[ok] reconstructed answer ({len(ans)} chars):", flush=True)
        print(ans[:500], flush=True)
        (DOC_DIR / "grok43_answer.txt").write_text(ans)

    return 0


if __name__ == "__main__":
    sys.exit(main())
