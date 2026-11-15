from __future__ import annotations

import ipaddress
import socket


def local_ipv4_addresses() -> list[str]:
    """Best-effort detection of private IPv4 addresses on the host's LAN."""
    addresses: set[str] = set()

    # UDP connect asks the OS to select a route/interface; no packet is sent.
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("192.0.2.1", 9))
            candidate = ipaddress.ip_address(sock.getsockname()[0])
            if candidate.is_private and not candidate.is_loopback and not candidate.is_link_local:
                addresses.add(str(candidate))
        finally:
            sock.close()
    except OSError:
        pass

    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            candidate = ipaddress.ip_address(item[4][0])
            if candidate.is_private and not candidate.is_loopback and not candidate.is_link_local:
                addresses.add(str(candidate))
    except OSError:
        pass

    return sorted(addresses)
