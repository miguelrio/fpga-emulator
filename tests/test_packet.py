import itertools
import pytest
from sim.packet import PacketFactory, Packet, IP_VERSIONS, PROTOCOLS, SIZES_BYTES


def test_make_returns_packet():
    pkt = PacketFactory.make()
    assert isinstance(pkt, Packet)
    assert pkt.ip_version in (4, 6)
    assert pkt.proto in ("tcp", "udp")
    assert pkt.size_bytes > 0
    assert isinstance(pkt.raw_bytes, bytes)


def test_packet_ids_are_unique():
    pkts = [PacketFactory.make() for _ in range(20)]
    ids = [p.pkt_id for p in pkts]
    assert len(set(ids)) == len(ids)


def test_generate_permutations_count():
    pkts = PacketFactory.generate_permutations()
    expected = len(IP_VERSIONS) * len(PROTOCOLS) * len(SIZES_BYTES)
    assert len(pkts) == expected


@pytest.mark.parametrize("ip_ver,proto,size", [
    (v, p, s)
    for v in IP_VERSIONS
    for p in PROTOCOLS
    for s in SIZES_BYTES
])
def test_permutation_packet_fields(ip_ver, proto, size):
    pkt = PacketFactory.make(ip_version=ip_ver, proto=proto, size=size)
    assert pkt.ip_version == ip_ver
    assert pkt.proto == proto
    assert pkt.size_bytes == size
    assert len(pkt.raw_bytes) > 0


def test_packet_is_frozen():
    pkt = PacketFactory.make()
    with pytest.raises((AttributeError, TypeError)):
        pkt.size_bytes = 9999  # type: ignore


def test_packet_metadata_defaults_empty():
    pkt = PacketFactory.make()
    assert isinstance(pkt.metadata, dict)


def test_packet_custom_ips():
    pkt = PacketFactory.make(ip_version=4, src_ip="1.2.3.4", dst_ip="5.6.7.8")
    assert pkt.src_ip == "1.2.3.4"
    assert pkt.dst_ip == "5.6.7.8"
