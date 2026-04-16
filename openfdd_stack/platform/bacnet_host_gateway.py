"""Docker/Linux helpers for reaching the DIY BACnet gateway from bridge-networked containers.

``bacnet-server`` is often ``network_mode: host`` and listens on the host's TCP :8080. The API
and scrapers use ``http://host.docker.internal:8080`` (``extra_hosts: host.docker.internal:host-gateway``).
On many Linux hosts **hairpin routing is broken**: both ``host.docker.internal`` and the bridge
gateway (e.g. ``172.19.0.1``) time out while ``curl http://localhost:8080`` on the host works.
Then use the same host IPv4 as ``OFDD_BACNET_ADDRESS`` (e.g. ``192.168.204.18/24:47808`` →
``http://192.168.204.18:8080``) so bridge containers reach the gateway on the LAN address.
"""

from __future__ import annotations

import os
import re
import socket
import struct

# First IPv4 in OFDD_BACNET_ADDRESS like ``192.168.204.18/24:47808`` (BACnet/IP bind; HTTP JSON-RPC is :8080).
_BACNET_ADDR_IPV4_RE = re.compile(
    r"^\s*(\d{1,3}(?:\.\d{1,3}){3})\s*/",
    re.ASCII,
)


def linux_default_ipv4_gateway() -> str | None:
    """Return the IPv4 default gateway from ``/proc/net/route``, or None if unavailable."""
    try:
        with open("/proc/net/route", encoding="ascii", errors="ignore") as fh:
            lines = fh.readlines()
    except OSError:
        return None

    def _parse_gw(gw_hex: str) -> str | None:
        if not gw_hex or gw_hex == "00000000":
            return None
        try:
            return socket.inet_ntoa(struct.pack("<I", int(gw_hex, 16)))
        except (OSError, ValueError, struct.error):
            return None

    # Prefer default route with RTF_GATEWAY (0x0002).
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 4:
            continue
        dest, gw_hex, flags_hex = parts[1], parts[2], parts[3]
        if dest != "00000000":
            continue
        try:
            flags = int(flags_hex, 16)
        except ValueError:
            continue
        if flags & 0x0002:
            got = _parse_gw(gw_hex)
            if got:
                return got

    # Fallback: default destination with any non-zero gateway (some route layouts omit flags).
    for line in lines[1:]:
        parts = line.split()
        if len(parts) < 3:
            continue
        if parts[1] != "00000000":
            continue
        got = _parse_gw(parts[2])
        if got:
            return got
    return None


def host_http_url_from_bacnet_address_env() -> str | None:
    """``OFDD_BACNET_ADDRESS`` → ``http://<host-ipv4>:8080`` for diy-bacnet JSON-RPC."""
    raw = (os.environ.get("OFDD_BACNET_ADDRESS") or "").strip()
    if not raw:
        return None
    m = _BACNET_ADDR_IPV4_RE.match(raw)
    if not m:
        return None
    return f"http://{m.group(1)}:8080"


def bacnet_rpc_base_candidates(primary: str) -> list[str]:
    """
    Ordered base URLs to try for JSON-RPC (no trailing slash).

    After ``primary``, try the host LAN URL derived from ``OFDD_BACNET_ADDRESS`` when set
    (fixes Linux Docker hairpin to ``network_mode: host`` gateway). Then try replacing
    ``host.docker.internal`` with the default-route gateway IP.
    """
    p = primary.strip().rstrip("/")
    if not p:
        return []
    out: list[str] = []
    seen: set[str] = set()

    def add(u: str) -> None:
        u = u.strip().rstrip("/")
        if u and u not in seen:
            seen.add(u)
            out.append(u)

    add(p)
    from_addr = host_http_url_from_bacnet_address_env()
    if from_addr:
        add(from_addr)
    if "host.docker.internal" in p.lower():
        gw = linux_default_ipv4_gateway()
        if gw:
            alt = re.sub(r"(?i)host\.docker\.internal", gw, p, count=1)
            add(alt)
    return out
