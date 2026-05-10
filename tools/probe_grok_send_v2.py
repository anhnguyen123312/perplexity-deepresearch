"""Smoke test: reuse captured x-statsig-id with curl_cffi to call Grok 4.3."""

from __future__ import annotations

import argparse
import json
import sys
import time
import uuid
from pathlib import Path

from curl_cffi import requests
from pycookiecheat import BrowserType, chrome_cookies


REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_DIR = REPO_ROOT / "docs" / "grok-mcp"


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--query", default="What is 2+2? Answer briefly.")
    p.add_argument("--mode-id", default="grok-420-computer-use-sa")
    args = p.parse_args()

    captured = json.loads((DOC_DIR / "statsig_id.json").read_text())
    statsig_id = captured["chat_send_headers"]["x-statsig-id"]
    print(f"[i] reusing x-statsig-id: {statsig_id[:40]}…", flush=True)

    raw = chrome_cookies("https://grok.com/", browser=BrowserType.CHROME)
    sess = requests.Session(impersonate="chrome142")
    for k, v in raw.items():
        sess.cookies.set(k, v, domain=".grok.com")

    headers = {
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/147.0.0.0 Safari/537.36",
        "accept": "*/*",
        "accept-language": "en-US",
        "content-type": "application/json",
        "origin": "https://grok.com",
        "referer": "https://grok.com/",
        "sec-ch-ua": '"Not.A;Brand";v="99", "Chrome";v="147", "Chromium";v="147"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "x-statsig-id": statsig_id,
        "x-xai-request-id": str(uuid.uuid4()),
    }

    body = {
        "temporary": False,
        "message": args.query,
        "fileAttachments": [],
        "imageAttachments": [],
        "disableSearch": False,
        "enableImageGeneration": True,
        "returnImageBytes": False,
        "returnRawGrokInXaiRequest": False,
        "enableImageStreaming": True,
        "imageGenerationCount": 2,
        "forceConcise": False,
        "enableSideBySide": True,
        "sendFinalMetadata": True,
        "disableTextFollowUps": False,
        "responseMetadata": {},
        "disableMemory": False,
        "forceSideBySide": False,
        "isAsyncChat": False,
        "disableSelfHarmShortCircuit": False,
        "collectionIds": [],
        "disabledConnectorIds": [],
        "deviceEnvInfo": {
            "darkModeEnabled": False,
            "devicePixelRatio": 1,
            "screenWidth": 1280,
            "screenHeight": 720,
            "viewportWidth": 1280,
            "viewportHeight": 720,
        },
        "modeId": args.mode_id,
    }

    print(f"[i] POST conversations/new mode={args.mode_id} q={args.query!r}",
          flush=True)
    t0 = time.time()
    r = sess.post(
        "https://grok.com/rest/app-chat/conversations/new",
        json=body,
        headers=headers,
        timeout=120,
        stream=True,
    )
    print(f"[i] status={r.status_code} ct={r.headers.get('content-type')}",
          flush=True)
    if r.status_code != 200:
        body_text = b"".join(r.iter_content()).decode("utf-8", "replace")
        print(f"[err] {body_text[:1500]}", flush=True)
        (DOC_DIR / "grok43_error.txt").write_text(body_text)
        return 1

    chunks = []
    for line in r.iter_lines():
        if not line:
            continue
        if isinstance(line, bytes):
            line = line.decode("utf-8", "replace")
        chunks.append(line)
        if len(chunks) <= 3:
            print(f"  [{len(chunks):03d}] {line[:200]}", flush=True)

    elapsed = time.time() - t0
    out = DOC_DIR / "grok43_stream.txt"
    out.write_text("\n".join(chunks))
    print(f"[done] {len(chunks)} lines in {elapsed:.1f}s → {out}",
          flush=True)

    # Try to reconstruct answer
    answer_parts = []
    for line in chunks:
        try:
            j = json.loads(line)
        except Exception:
            continue
        def walk(o):
            if isinstance(o, dict):
                tok = o.get("token")
                if isinstance(tok, str):
                    answer_parts.append(tok)
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)
        walk(j)

    if answer_parts:
        ans = "".join(answer_parts)
        print(f"\n[ok] answer ({len(ans)} chars):\n{ans[:500]}", flush=True)
        (DOC_DIR / "grok43_answer.txt").write_text(ans)
    return 0


if __name__ == "__main__":
    sys.exit(main())
