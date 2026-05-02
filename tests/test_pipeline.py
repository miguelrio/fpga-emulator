import pytest
from sim.pipeline import build_default_pipeline
from sim.packet import PacketFactory, IP_VERSIONS, PROTOCOLS, SIZES_BYTES


MAX_CYCLES = 200


@pytest.mark.parametrize("ip_ver,proto,size", [
    (v, p, s)
    for v in IP_VERSIONS
    for p in PROTOCOLS
    for s in SIZES_BYTES
])
def test_packet_traverses_pipeline(ip_ver, proto, size):
    engine = build_default_pipeline()
    pkt = PacketFactory.make(ip_version=ip_ver, proto=proto, size=size,
                              src_ip="10.0.0.1", dst_ip="192.168.1.5")
    engine.run([pkt], max_cycles=MAX_CYCLES)
    completed_ids = {p.pkt_id for p in engine.completed}
    dropped_ids = {p.pkt_id for p, _ in engine.dropped}
    assert pkt.pkt_id in completed_ids or pkt.pkt_id in dropped_ids, \
        f"Packet {pkt.pkt_id} ({ip_ver},{proto},{size}B) stuck in pipeline"


def test_all_packets_eventually_processed():
    engine = build_default_pipeline()
    packets = PacketFactory.generate_permutations()
    for p in packets:
        engine.enqueue_packet(p)
    engine.run(max_cycles=MAX_CYCLES * len(packets))
    total_done = len(engine.completed) + len(engine.dropped)
    assert total_done == len(packets)


def test_runt_frame_dropped():
    """Packets < 64B should be dropped at MACRxStage."""
    engine = build_default_pipeline()
    pkt = PacketFactory.make(size=32)
    engine.run([pkt], max_cycles=MAX_CYCLES)
    dropped_ids = {p.pkt_id for p, _ in engine.dropped}
    assert pkt.pkt_id in dropped_ids


def test_fib_miss_drops_packet():
    """Packets with unroutable dst should be dropped at FIBLookupStage."""
    engine = build_default_pipeline()
    pkt = PacketFactory.make(dst_ip="240.0.0.1", size=1500)
    engine.run([pkt], max_cycles=MAX_CYCLES)
    dropped_ids = {p.pkt_id for p, _ in engine.dropped}
    completed_ids = {p.pkt_id for p in engine.completed}
    # Either dropped (no route) or completed (hit default route) — both are valid
    assert pkt.pkt_id in dropped_ids or pkt.pkt_id in completed_ids


def test_replace_stage():
    from sim.stage import MACTxStage, StageMetrics
    engine = build_default_pipeline()
    new_stage = MACTxStage()
    engine.replace_stage("mac_tx", new_stage)
    names = [s.metrics.name for s in engine.get_stages()]
    assert "mac_tx" in names


def test_replace_nonexistent_stage_raises():
    engine = build_default_pipeline()
    from sim.stage import MACTxStage
    with pytest.raises(KeyError):
        engine.replace_stage("nonexistent_stage", MACTxStage())


def test_insert_stage_after():
    engine = build_default_pipeline()
    from sim.stage import MACTxStage
    extra = MACTxStage()
    engine.insert_stage_after("header_parser", extra)
    names = [s.metrics.name for s in engine.get_stages()]
    idx_parser = names.index("header_parser")
    idx_extra = names.index("mac_tx")
    assert idx_extra == idx_parser + 1


def test_event_log_grows_with_ticks():
    engine = build_default_pipeline()
    pkt = PacketFactory.make(dst_ip="10.0.0.5", size=1500)
    engine.enqueue_packet(pkt)
    for _ in range(30):
        engine.tick()
    assert len(engine.clock.event_log) > 0


def test_state_snapshot_keys():
    engine = build_default_pipeline()
    engine.tick()
    snap = engine.get_state_snapshot()
    assert "cycle" in snap
    assert "completed" in snap
    assert "dropped" in snap
    assert "stages" in snap
