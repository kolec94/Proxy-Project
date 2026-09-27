"""Exact domain allowlist and pinned, globally routable IPv4 destinations."""
import asyncio
import ipaddress
import re
import socket


class PolicyError(ValueError):
    pass


def hostname(value):
    if not isinstance(value, str) or value != value.strip() or len(value) > 253:
        raise PolicyError("invalid hostname")
    name = value.lower().rstrip(".")
    if not name or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                       for label in name.split(".")):
        raise PolicyError("ASCII DNS hostname required")
    try:
        ipaddress.ip_address(name)
    except ValueError:
        pass
    else:
        raise PolicyError("literal IP addresses are not allowed")
    return name


class Policy:
    def __init__(self, hosts, ports=(443,)):
        self.hosts = frozenset(hostname(h) for h in hosts)
        self.ports = frozenset(ports)
        if not self.hosts or not self.ports or any(type(p) is not int or not 1 <= p <= 65535 for p in self.ports):
            raise PolicyError("nonempty domain and port allowlists required")

    def check(self, host, port):
        name = hostname(host)
        if name not in self.hosts or type(port) is not int or port not in self.ports:
            raise PolicyError("destination is outside participant policy")
        return name

    async def resolve(self, host, port):
        name = self.check(host, port)
        results = await asyncio.wait_for(asyncio.get_running_loop().getaddrinfo(
            name, port, family=socket.AF_INET, type=socket.SOCK_STREAM), 10)
        addresses = sorted({row[4][0] for row in results})
        if not addresses:
            raise PolicyError("no IPv4 address")
        # Reject the entire answer if any candidate is unsafe. Connect to the
        # selected numeric address, never perform another hostname resolution.
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if (not ip.is_global or ip.is_multicast or ip.is_reserved
                    or ip.is_loopback or ip.is_link_local or ip.is_unspecified):
                raise PolicyError("nonpublic DNS answer")
        return addresses[0]
