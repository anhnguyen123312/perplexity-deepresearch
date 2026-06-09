#!/usr/bin/env bash
# Grok-web PROD refresh worker. Runs on a CF-CLEARABLE host (macOS / residential
# where CloakBrowser solves grok.com's Cloudflare). Captures a fresh grok session
# (cf_clearance + statsig) through the STICKY proxy and ships it to the datacenter
# prod, which serves rnet-only. Schedule via cron, e.g. every 5 min:
#   */5 * * * * GROK_PROXY=... PROD_HOST=root@IP /path/grok-refresh-ship.sh >> /tmp/grok-refresh.log 2>&1
#
# Why: grok's cf_clearance is bound to (exit IP, browser UA). The STICKY proxy
# (Oxylabs sessid) pins ONE exit IP shared by this host + prod; the prod serve
# pins the SAME UA via GROK_MAJOR/GROK_UA/GROK_SEC_CH_UA_PLATFORM. So a clearance
# earned here is valid from prod. cf_clearance/__cf_bm are short-lived → refresh.
#
# Env (required): GROK_PROXY (sticky), PROD_HOST (user@ip).
# Env (optional): SEED (login-only session json, default /tmp/grok_sess_clean.json),
#   PROD_SESSION (default /root/grok_session.json), PYBIN (default repo .venv python),
#   CHROME_PROFILE (default grok-prod).
set -euo pipefail
: "${GROK_PROXY:?set GROK_PROXY=sticky proxy url}"
: "${PROD_HOST:?set PROD_HOST=user@ip}"
SEED="${SEED:-/tmp/grok_sess_clean.json}"
PROD_SESSION="${PROD_SESSION:-/root/grok_session.json}"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PYBIN="${PYBIN:-$REPO/.venv/bin/python}"
WORK="$(mktemp /tmp/grok_refresh.XXXX.json)"
trap 'rm -f "$WORK"' EXIT
cp "$SEED" "$WORK"

# Capture a fresh cf_clearance+statsig through the sticky proxy (native browser).
PERPLEXITY_CONFIG_FILE="$WORK" GROK_PROXY="$GROK_PROXY" \
  CHROME_PROFILE="${CHROME_PROFILE:-grok-prod}" GROK_STATSIG_HEADLESS="${GROK_STATSIG_HEADLESS:-1}" \
  "$PYBIN" -c "from deep_research.grok.client import GrokClient
r=GrokClient().search('hi', mode='auto')
import sys; sys.exit(0 if not r.get('error') else 1)" \
  || { echo "$(date -u +%FT%TZ) capture FAILED" >&2; exit 1; }

scp -o StrictHostKeyChecking=no -q "$WORK" "$PROD_HOST:$PROD_SESSION"
echo "$(date -u +%FT%TZ) refreshed + shipped to $PROD_HOST:$PROD_SESSION"
