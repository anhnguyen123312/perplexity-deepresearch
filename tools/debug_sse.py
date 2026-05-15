"""
Debug: dump raw SSE response from real perplexity.ai using cookies.
Saves the raw stream to docs/perplexity-mcp-revert/sse_raw.txt and parses
each event message to understand the response shape.
"""

import json
from pathlib import Path

from deep_research.perplexity.client import PerplexityClient
from deep_research.config import ENDPOINT_SSE_ASK, SSE_REQUEST_HEADERS


OUT = Path("/Volumes/Data/Git/perlexity/docs/perplexity-mcp-revert/sse_raw.txt")
OUT_JSON = Path("/Volumes/Data/Git/perlexity/docs/perplexity-mcp-revert/sse_events.json")


def main():
    client = PerplexityClient()
    payload = client._build_payload(
        query="What is 2+2? Answer briefly.",
        payload_mode="copilot",
        model_preference="pplx_pro",
        sources=["web"],
        language="en-US",
        follow_up=None,
    )
    headers = dict(SSE_REQUEST_HEADERS)
    headers["x-request-id"] = payload["params"]["frontend_uuid"]

    response = client._request_with_retry(
        "POST", ENDPOINT_SSE_ASK, json=payload, stream=True, headers=headers
    )
    print(f"status={response.status_code}")

    raw_chunks = []
    parsed_events = []
    for chunk in response.iter_lines(delimiter=b"\r\n\r\n"):
        text = chunk.decode("utf-8", errors="replace")
        raw_chunks.append(text)
        # Try to parse event
        if text.startswith("event:"):
            lines = text.split("\r\n", 2)
            event_name = lines[0].split(":", 1)[1].strip() if ":" in lines[0] else ""
            data_line = ""
            for line in lines[1:]:
                if line.startswith("data:"):
                    data_line = line[len("data:"):].strip()
            try:
                payload_obj = json.loads(data_line) if data_line else None
            except Exception:
                payload_obj = data_line
            parsed_events.append({"event": event_name, "data": payload_obj})

    OUT.write_text("\n=====\n".join(raw_chunks[:80]))
    OUT_JSON.write_text(json.dumps(parsed_events, indent=2, default=str))
    print(f"wrote {len(raw_chunks)} chunks to {OUT}")
    print(f"wrote {len(parsed_events)} parsed events to {OUT_JSON}")
    print()
    print("Top-level keys observed across messages:")
    keys = set()
    for ev in parsed_events:
        if isinstance(ev["data"], dict):
            keys.update(ev["data"].keys())
    print(sorted(keys))


if __name__ == "__main__":
    main()
