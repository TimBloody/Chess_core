"""Helpers for advertising a LAN bind address."""

from __future__ import annotations

import socket


def lan_ipv4_addresses() -> tuple[str, ...]:
    addresses: list[str] = []
    hostname = socket.gethostname()
    try:
        packed = socket.getaddrinfo(hostname, None, socket.AF_INET)
    except socket.gaierror:
        packed = []
    for item in packed:
        address = item[4][0]
        if _is_lan(address) and address not in addresses:
            addresses.append(address)
    if not addresses:
        addresses.append("127.0.0.1")
    return tuple(addresses)


def _is_lan(address: str) -> bool:
    if address.startswith("127."):
        return True
    if address.startswith("10."):
        return True
    if address.startswith("192.168."):
        return True
    if address.startswith("172."):
        second = int(address.split(".")[1])
        return 16 <= second <= 31
    return False
