"""Discover IPv4 addresses that a LAN guest can use to reach this host."""

from __future__ import annotations

import socket


def lan_ipv4_addresses() -> tuple[str, ...]:
    found: list[str] = []
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            address = probe.getsockname()[0]
            if _is_lan(address):
                found.append(address)
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            if _is_lan(address) and address not in found:
                found.append(address)
    except OSError:
        pass
    return tuple(found)


def _is_lan(address: str) -> bool:
    return bool(address) and not address.startswith("127.")
