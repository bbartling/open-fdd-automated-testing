#!/usr/bin/env bash
# Smoke-test the same hop as ./scripts/bootstrap.sh --verify "BACnet (API→gateway)":
# openfdd_api container -> OFDD_BACNET_SERVER_URL -> POST /server_hello (JSON-RPC).
#
# Run on the Docker host (needs docker CLI + openfdd_api running).
# Exit 0 on first successful candidate URL; exit 1 on total failure.
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

import httpx

from openfdd_stack.platform.bacnet_host_gateway import bacnet_rpc_base_candidates

primary = (os.environ.get("OFDD_BACNET_SERVER_URL") or "http://host.docker.internal:8080").rstrip(
    "/"
)
headers = {}
key = (os.environ.get("OFDD_BACNET_SERVER_API_KEY") or "").strip()
if key:
    headers["Authorization"] = "Bearer " + key
payload = {"jsonrpc": "2.0", "id": "0", "method": "server_hello", "params": {}}
last_err = None
for base in bacnet_rpc_base_candidates(primary):
    url = base + "/server_hello"
    try:
        r = httpx.post(url, json=payload, headers=headers, timeout=8.0, trust_env=False)
    except Exception as exc:
        last_err = exc
        continue
    if not r.is_success:
        last_err = "HTTP %s %s" % (r.status_code, (r.text or "")[:120])
        continue
    try:
        data = r.json()
    except Exception:
        last_err = "non-JSON"
        continue
    if isinstance(data, dict) and data.get("error"):
        last_err = data.get("error")
        continue
    print("OK   BACnet (API→gateway) via", base)
    sys.exit(0)
print("FAIL BACnet (API→gateway):", last_err, "| tried:", bacnet_rpc_base_candidates(primary))
sys.exit(1)
PYCHECK
