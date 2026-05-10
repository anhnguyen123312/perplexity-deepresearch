"""
Download grok.com Next.js chunks and grep for /rest/app-chat/ endpoints
plus likely request body field names.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from curl_cffi import requests
from pycookiecheat import BrowserType, chrome_cookies


REPO_ROOT = Path(__file__).resolve().parents[2]
DOC_DIR = REPO_ROOT / "docs" / "grok-mcp"
CHUNKS_DIR = DOC_DIR / "chunks"
CHUNKS_DIR.mkdir(parents=True, exist_ok=True)


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


def fetch_chunk(sess, path: str) -> tuple[str, str | None]:
    try:
        r = sess.get(f"https://grok.com/{path}", timeout=20)
        if r.status_code == 200:
            (CHUNKS_DIR / Path(path).name).write_text(r.text)
            return path, r.text
    except Exception as e:
        return path, f"__ERR__:{e}"
    return path, None


def main() -> int:
    homepage = (DOC_DIR / "homepage.html").read_text()
    chunks = sorted(set(re.findall(
        r"_next/static/chunks/[A-Za-z0-9_/.-]+\.js", homepage
    )))
    print(f"[i] {len(chunks)} chunks", flush=True)

    sess = make_session()
    bodies: list[tuple[str, str]] = []

    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = {pool.submit(fetch_chunk, sess, c): c for c in chunks}
        for fut in as_completed(futs):
            path, body = fut.result()
            if body and not body.startswith("__ERR__:"):
                bodies.append((path, body))

    print(f"[i] downloaded {len(bodies)} chunks", flush=True)

    # Hunt for /rest/app-chat/ endpoints
    endpoints: dict[str, set[str]] = {}
    for path, body in bodies:
        for m in re.finditer(r'"(/rest/[A-Za-z0-9_/\-\.{}]+)"', body):
            endpoints.setdefault(m.group(1), set()).add(path)

    print(f"\n[i] /rest/ endpoints found: {len(endpoints)}")
    for ep in sorted(endpoints):
        print(f"  {ep}  (in {len(endpoints[ep])} chunks)")

    # Hunt for likely chat-send field names near 'message' / 'modelName'
    # Find all chunks containing 'modelName' and dump 200-char windows
    print("\n[i] modelName/temporary/conversationId context windows:")
    seen = set()
    for path, body in bodies:
        for m in re.finditer(r"modelName", body):
            start = max(0, m.start() - 100)
            end = min(len(body), m.end() + 200)
            snippet = body[start:end].replace("\n", " ")
            key = snippet[:120]
            if key in seen:
                continue
            seen.add(key)
            print(f"  [{path}] …{snippet}…")
            if len(seen) >= 10:
                break
        if len(seen) >= 10:
            break

    # Save endpoints to file
    (DOC_DIR / "endpoints.txt").write_text(
        "\n".join(sorted(endpoints))
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
