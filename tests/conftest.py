import pytest
from sim.fib import ForwardingTable
from sim.pipeline import PipelineEngine, build_default_pipeline
from sim.stage import MACRxStage, HeaderParserStage, FIBLookupStage, MACTxStage
from sim.packet import PacketFactory, IP_VERSIONS, PROTOCOLS, SIZES_BYTES


@pytest.fixture
def fib():
    return ForwardingTable()


@pytest.fixture
def engine():
    return build_default_pipeline()


@pytest.fixture
def all_packets():
    return PacketFactory.generate_permutations()


@pytest.fixture
def ipv4_tcp_1500():
    return PacketFactory.make(ip_version=4, proto="tcp", size=1500)


@pytest.fixture
def ipv6_udp_512():
    return PacketFactory.make(ip_version=6, proto="udp", size=512)
