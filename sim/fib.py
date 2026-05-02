from __future__ import annotations
import ipaddress
from dataclasses import dataclass


@dataclass
class FIBEntry:
    network: str        # e.g. "10.0.0.0/8"
    next_hop: str
    interface: str
    prefix_len: int = 0

    def __post_init__(self):
        net = ipaddress.ip_network(self.network, strict=False)
        self.prefix_len = net.prefixlen
        self._net_obj = net

    def matches(self, addr: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
        return addr in self._net_obj


DEFAULT_IPV4_ROUTES = [
    FIBEntry("10.0.0.0/8",      "10.0.0.1",  "eth0"),
    FIBEntry("172.16.0.0/12",   "172.16.0.1", "eth1"),
    FIBEntry("192.168.0.0/16",  "192.168.0.1","eth0"),
    FIBEntry("192.168.1.0/24",  "192.168.1.1","eth1"),
    FIBEntry("8.8.8.0/24",      "1.2.3.4",   "eth2"),
    FIBEntry("8.0.0.0/8",       "1.2.3.1",   "eth2"),
    FIBEntry("203.0.113.0/24",  "203.0.113.1","eth3"),
    FIBEntry("198.51.100.0/24", "198.51.100.1","eth3"),
    FIBEntry("100.64.0.0/10",   "100.64.0.1", "eth0"),
    FIBEntry("0.0.0.0/0",       "1.1.1.1",   "eth2"),  # default
]

DEFAULT_IPV6_ROUTES = [
    FIBEntry("2001:db8::/32",   "2001:db8::1", "eth0"),
    FIBEntry("fe80::/10",       "fe80::1",     "eth0"),
    FIBEntry("fc00::/7",        "fc00::1",     "eth1"),
    FIBEntry("2400::/12",       "2400::1",     "eth2"),
    FIBEntry("2600::/12",       "2600::1",     "eth2"),
    FIBEntry("::1/128",         "::1",         "lo"),
    FIBEntry("::/0",            "2001:db8::ff","eth2"),  # default
]


class ForwardingTable:
    def __init__(self):
        self._entries: list[FIBEntry] = []
        for r in DEFAULT_IPV4_ROUTES + DEFAULT_IPV6_ROUTES:
            self._entries.append(r)
        self._entries.sort(key=lambda e: e.prefix_len, reverse=True)

    def lookup(self, dst_ip: str) -> FIBEntry | None:
        try:
            addr = ipaddress.ip_address(dst_ip)
        except ValueError:
            return None
        for entry in self._entries:
            if entry.matches(addr):
                return entry
        return None

    def add_route(self, network: str, next_hop: str, interface: str):
        entry = FIBEntry(network, next_hop, interface)
        self._entries.append(entry)
        self._entries.sort(key=lambda e: e.prefix_len, reverse=True)

    def load_from_csv(self, path: str):
        import csv
        with open(path) as f:
            for row in csv.DictReader(f):
                self.add_route(row["network"], row["next_hop"], row["interface"])

    def __len__(self) -> int:
        return len(self._entries)
