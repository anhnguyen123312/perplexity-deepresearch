"""Replay the captured browser payload byte-for-byte through curl_cffi.

If this also fails with 'Error in processing query.', the issue is in headers
or TLS / cookie handling. If it succeeds, the difference is in our payload.
"""
import json
import sys
from pathlib import Path

from deep_research.perplexity.client import PerplexityClient
from deep_research.config import ENDPOINT_SSE_ASK, SSE_REQUEST_HEADERS

CAPTURED = json.load(open("/Volumes/Data/Git/perlexity/docs/perplexity-mcp-revert/captured.json"))
entry = CAPTURED[0]
print("Original captured headers:", list(entry["headers"].keys()))
print("Original payload keys:", list(entry["post_data"].keys()))

client = PerplexityClient()

# Use captured payload AS-IS
payload = entry["post_data"]
# Reset query to a fresh one so we don't hit dedup
payload["query_str"] = "What is 5 + 7? Answer briefly."
payload["params"]["dsl_query"] = payload["query_str"]

# Also forward the exact headers, but only the request-specific ones
headers = {
    "accept": entry["headers"].get("accept", "text/event-stream"),
    "content-type": entry["headers"].get("content-type", "application/json"),
    "x-perplexity-request-endpoint": entry["headers"].get("x-perplexity-request-endpoint", ENDPOINT_SSE_ASK),
    "x-perplexity-request-reason": entry["headers"].get("x-perplexity-request-reason", "ask-query-state-provider"),
    "x-perplexity-request-try-number": "1",
    "x-request-id": payload["params"]["frontend_uuid"],
    "referer": "https://www.perplexity.ai/",
}

response = client._request_with_retry(
    "POST", ENDPOINT_SSE_ASK, json=payload, stream=True, headers=headers
)
print(f"status={response.status_code}")

events = []
for chunk in response.iter_lines(delimiter=b"\r\n\r\n"):
    text = chunk.decode("utf-8", errors="replace")
    if text.startswith("event:"):
        lines = text.split("\r\n", 2)
        ev = lines[0].split(":", 1)[1].strip()
        data = ""
        for line in lines[1:]:
            if line.startswith("data:"):
                data = line[len("data:"):].strip()
        try:
            data_obj = json.loads(data)
        except Exception:
            data_obj = data
        events.append({"event": ev, "data": data_obj})

print(f"Got {len(events)} events")
for i, ev in enumerate(events):
    if isinstance(ev["data"], dict):
        status = ev["data"].get("status")
        text_field = ev["data"].get("text")
        text_preview = text_field if isinstance(text_field, str) else (json.dumps(text_field)[:80] if text_field else None)
        print(f"  [{i}] {ev['event']} status={status} text={text_preview!r}")
    else:
        print(f"  [{i}] {ev['event']} data={ev['data'][:80]!r}")

Path("/Volumes/Data/Git/perlexity/docs/perplexity-mcp-revert/replay_events.json").write_text(json.dumps(events, indent=2, default=str))
