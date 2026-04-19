#!/usr/bin/env bash
# Smoke-test the same hop as ./scripts/bootstrap.sh --verify "BACnet (API→gateway)":
# openfdd_api container -> POST http://127.0.0.1:8000/bacnet/server_hello (Open-FDD API; includes docker-exec fallback).
#
# Or: ./scripts/bootstrap.sh --smoke-bacnet-api-gateway   (alias: --smoke-bacnet-api)
#     ./scripts/bootstrap.sh --verify --smoke-bacnet-api-gateway
#
# Run on the Docker host (needs docker CLI + openfdd_api running).
# Exit 0 when API reports ok: true; exit 1 otherwise.
set -euo pipefail

if ! docker info >/dev/null 2>&1; then
  echo "FAIL: Docker daemon not reachable (run on the stack host with permission to use docker)."
  exit 1
fi
if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -qx openfdd_api; then
  echo "FAIL: container openfdd_api is not running. Start the stack first."
  exit 1
fi

exec docker exec openfdd_api python3 - <<'PYCHECK'
import os
import sys
import time

import httpx

url = "http://127.0.0.1:8000/bacnet/server_hello"
headers = {"Content-Type": "application/json"}
api_key = (os.environ.get("OFDD_API_KEY") or "").strip()
if api_key:
    headers["Authorization"] = "Bearer " + api_key
last_err = None
for _ in range(12):
    try:
        r = httpx.post(url, json={}, headers=headers, timeout=20.0, trust_env=False)
    except Exception as exc:
        last_err = exc
        time.sleep(1.5)
        continue
    if not r.is_success:
        last_err = "HTTP %s %s" % (r.status_code, (r.text or "")[:200])
        time.sleep(1.5)
        continue
    try:
        data = r.json()
    except Exception:
        last_err = "non-JSON " + (r.text or "")[:200]
        time.sleep(1.5)
        continue
    if isinstance(data, dict) and data.get("ok"):
        print("OK   BACnet (API→gateway) via Open-FDD", url)
        sys.exit(0)
    print("FAIL BACnet (API→gateway):", data)
    sys.exit(1)
print("FAIL BACnet (API→gateway):", last_err)
sys.exit(1)
PYCHECK
