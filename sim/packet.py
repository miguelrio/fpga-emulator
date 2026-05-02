from __future__ import annotations
import itertools
from dataclasses import dataclass, field
from typing import Any

try:
    from scapy.layers.inet import IP, TCP, UDP
    from scapy.layers.inet6 import IPv6
    from scapy.layers.l2 import Ether
    from scapy.packet import Raw
    SCAPY_AVAILABLE = True
except ImportError:
    SCAPY_AVAILABLE = False


@dataclass(frozen=True)
class Packet:
    pkt_id: int
    timestamp_cycle: int
    src_ip: str
    dst_ip: str
    ip_version: int          # 4 or 6
    proto: str               # 'tcp' | 'udp'
    size_bytes: int
    raw_bytes: bytes
    metadata: dict[str, Any] = field(default_factory=dict)

    def __hash__(self):
        return hash(self.pkt_id)

    def __eq__(self, other):
        return isinstance(other, Packet) and self.pkt_id == other.pkt_id


_PKT_COUNTER = itertools.count(1)

_IPV4_PAIRS = [
    ("10.0.0.1", "192.168.1.100"),
    ("172.16.0.5", "10.10.10.20"),
    ("192.168.0.50", "8.8.8.8"),
]
_IPV6_PAIRS = [
    ("2001:db8::1", "2001:db8::2"),
    ("fe80::1", "fe80::2"),
    ("::1", "::2"),
]

IP_VERSIONS = [4, 6]
PROTOCOLS = ["tcp", "udp"]
SIZES_BYTES = [64, 512, 1500, 9000]


def _build_raw(ip_version: int, proto: str, size: int, src: str, dst: str) -> bytes:
    if not SCAPY_AVAILABLE:
        return bytes(size)

    if ip_version == 4:
        ip_layer = IP(src=src, dst=dst)
    else:
        ip_layer = IPv6(src=src, dst=dst)

    if proto == "tcp":
        transport = TCP(sport=12345, dport=80)
    else:
        transport = UDP(sport=12345, dport=53)

    header = Ether() / ip_layer / transport
    header_bytes = bytes(header)
    payload_len = max(0, size - len(header_bytes))
    pkt = header / Raw(b"\x00" * payload_len)
    raw = bytes(pkt)
    return raw[:size] if len(raw) > size else raw + b"\x00" * (size - len(raw))


class PacketFactory:
    @staticmethod
    def make(
        ip_version: int = 4,
        proto: str = "tcp",
        size: int = 1500,
        src_ip: str | None = None,
        dst_ip: str | None = None,
        timestamp_cycle: int = 0,
        metadata: dict | None = None,
    ) -> Packet:
        if src_ip is None or dst_ip is None:
            pairs = _IPV4_PAIRS if ip_version == 4 else _IPV6_PAIRS
            src_ip, dst_ip = pairs[next(_PKT_COUNTER) % len(pairs)]
        raw = _build_raw(ip_version, proto, size, src_ip, dst_ip)
        return Packet(
            pkt_id=next(_PKT_COUNTER),
            timestamp_cycle=timestamp_cycle,
            src_ip=src_ip,
            dst_ip=dst_ip,
            ip_version=ip_version,
            proto=proto,
            size_bytes=size,
            raw_bytes=raw,
            metadata=metadata or {},
        )

    @staticmethod
    def generate_permutations(timestamp_cycle: int = 0) -> list[Packet]:
        """All 16 combinations of {IPv4,IPv6} × {TCP,UDP} × {64,512,1500,9000}."""
        packets = []
        for ip_ver, proto, size in itertools.product(IP_VERSIONS, PROTOCOLS, SIZES_BYTES):
            packets.append(PacketFactory.make(ip_ver, proto, size, timestamp_cycle=timestamp_cycle))
        return packets
