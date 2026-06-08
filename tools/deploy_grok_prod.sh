#!/usr/bin/env bash
# Deploy grok-web (perplexity-deep-research) to a headless datacenter host.
# Cloudflare blocks the server IP for grok.com, so ALL grok traffic (CloakBrowser
# capture + rnet hot path) routes through GROK_PROXY; the server earns its own
# cf_clearance on the proxy IP. Login (sso) is shipped from a machine with Chrome.
#
# Prereqs on host: uv + Chromium shared libs (this script installs them).
# Env (required): HOST (user@ip), GROK_PROXY, GIT_URL (incl. token), SESSION_JSON.
set -euo pipefail
: "${HOST:?set HOST=root@ip}"; : "${GROK_PROXY:?set GROK_PROXY}"
: "${GIT_URL:?set GIT_URL (git+https://...@github.com/...)}"
: "${SESSION_JSON:?set SESSION_JSON=/path/to/grok_session.json}"
SSH="ssh -o StrictHostKeyChecking=no -o ConnectTimeout=15 $HOST"

echo "== 1. install uv + Chromium deps =="
$SSH 'command -v uv >/dev/null 2>&1 || curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null 2>&1; \
  export DEBIAN_FRONTEND=noninteractive; \
  dpkg -s libnss3 >/dev/null 2>&1 || (apt-get update -qq && apt-get install -y -qq \
  libnss3 libnspr4 libatk1.0-0t64 libatk-bridge2.0-0t64 libcups2t64 libdrm2 libxkbcommon0 \
  libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2t64 libpango-1.0-0 \
  libcairo2 libatspi2.0-0t64 fonts-liberation) >/dev/null 2>&1; echo deps-ok'

echo "== 2. install deep-research from git =="
$SSH "\$HOME/.local/bin/uv tool install --force '$GIT_URL' 2>&1 | tail -3"

echo "== 3. ship grok login session =="
scp -o StrictHostKeyChecking=no "$SESSION_JSON" "$HOST:/root/grok_session.json"

echo "== 4. warm CloakBrowser binary (downloads bundled Chromium once) =="
$SSH "\$HOME/.local/bin/uv tool run --from deep-research python -c 'from cloakbrowser import binary_info; print(binary_info())' 2>&1 | tail -2 || true"

echo "== 5. smoke test grok through proxy on the host =="
$SSH "export PERPLEXITY_CONFIG_FILE=/root/grok_session.json GROK_PROXY='$GROK_PROXY' \
  CHROME_PROFILE=grok-prod GROK_STATSIG_HEADLESS=1; \
  \$HOME/.local/bin/uv tool run --from deep-research python -u -c '
import time
from deep_research.grok.client import GrokClient
t0=time.time(); r=GrokClient().search(\"What is 2+2? Reply with just the number.\", mode=\"auto\")
print(\"PROD-GROK err=\",r.get(\"error\"),\"ans=\",repr((r.get(\"answer\") or \"\")[:60]),\"secs=\",round(time.time()-t0,1))'"

echo "== done =="
