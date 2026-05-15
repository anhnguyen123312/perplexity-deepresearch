"""
End-to-end smoke test: invoke the patched MCP client against real perplexity.ai
using the cached cookies. Confirms that the new payload schema is accepted
(no 400/401/403/422) and that an answer comes back.
"""

import sys
import time

from deep_research.perplexity.client import PerplexityClient


def run(mode: str, query: str, sources):
    client = PerplexityClient()
    print(f"\n=== mode={mode!r} sources={sources} query={query!r} ===", flush=True)
    t0 = time.time()
    try:
        result = client.search(
            query=query, mode=mode, sources=sources, language="en-US", follow_up=None
        )
    except Exception as e:
        print(f"[ERR mode={mode}] {type(e).__name__}: {e}", flush=True)
        return False
    dt = time.time() - t0
    answer = (result.get("answer") or "").strip()
    print(f"[OK mode={mode}] {dt:.1f}s | answer[:160]={answer[:160]!r}")
    print(f"  citations={len(result.get('citations',[]))} backend_uuid={result.get('backend_uuid')!r}")
    return True


def main():
    # Args: <mode> [<source1>,<source2>,...] [<query>]
    args = sys.argv[1:]
    mode = args[0] if args else "pro"
    sources = args[1].split(",") if len(args) > 1 else ["web"]
    query = args[2] if len(args) > 2 else "What is the capital of France? Answer in one sentence."
    ok = run(mode, query, sources)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
