from __future__ import annotations
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sim.packet import Packet
    from sim.fib import ForwardingTable


@dataclass
class StageMetrics:
    name: str
    cycle_latency: int
    memory_bytes: int
    lut_count: int
    ff_count: int
    bram_count: int
    logic_depth: int
    source: str = "builtin"  # 'builtin' | 'rtl_plugin:<filename>'


class PipelineStage(ABC):
    def __init__(self):
        self.input_queue: deque[tuple[Packet, int]] = deque()  # (packet, arrival_cycle)
        self.output_queue: deque[Packet] = deque()
        self._in_flight: deque[tuple[Packet, int]] = deque()  # (packet, release_cycle)

    @property
    @abstractmethod
    def metrics(self) -> StageMetrics: ...

    @abstractmethod
    def _process_packet(self, packet: "Packet") -> "Packet | None":
        """Apply stage logic to packet. Return None to drop."""
        ...

    def tick(self, cycle: int) -> list[tuple[str, "Packet", dict]]:
        """Advance one clock cycle. Returns list of (event_type, packet, payload)."""
        events = []

        # Accept one packet from input queue
        if self.input_queue:
            pkt, _ = self.input_queue.popleft()
            processed = self._process_packet(pkt)
            if processed is not None:
                release_at = cycle + self.metrics.cycle_latency
                self._in_flight.append((processed, release_at))
                events.append(("enter", pkt, {}))
            else:
                events.append(("drop", pkt, {"reason": "stage_drop"}))

        # Release packets that have completed latency
        while self._in_flight and self._in_flight[0][1] <= cycle:
            pkt, _ = self._in_flight.popleft()
            self.output_queue.append(pkt)
            events.append(("exit", pkt, {}))

        return events


class MACRxStage(PipelineStage):
    """Ethernet frame reception: CRC check, deframe."""

    _METRICS = StageMetrics(
        name="mac_rx",
        cycle_latency=12,
        memory_bytes=2048,
        lut_count=320,
        ff_count=180,
        bram_count=1,
        logic_depth=8,
    )

    @property
    def metrics(self) -> StageMetrics:
        return self._METRICS

    def _process_packet(self, packet: "Packet") -> "Packet | None":
        # Drop runt frames (< 64 bytes)
        if packet.size_bytes < 64:
            return None
        return packet


class HeaderParserStage(PipelineStage):
    """Parse Ethernet/IP/TCP/UDP headers, dispatch by EtherType."""

    _METRICS = StageMetrics(
        name="header_parser",
        cycle_latency=4,
        memory_bytes=256,
        lut_count=480,
        ff_count=96,
        bram_count=0,
        logic_depth=12,
    )

    @property
    def metrics(self) -> StageMetrics:
        return self._METRICS

    def _process_packet(self, packet: "Packet") -> "Packet | None":
        # Minimum IPv4 header requires 34 bytes (14 Eth + 20 IP)
        if packet.ip_version == 4 and packet.size_bytes < 34:
            return None
        # Minimum IPv6 header requires 54 bytes (14 Eth + 40 IPv6)
        if packet.ip_version == 6 and packet.size_bytes < 54:
            return None
        return packet


class FIBLookupStage(PipelineStage):
    """Longest-prefix-match routing table lookup."""

    def __init__(self, fib: "ForwardingTable"):
        super().__init__()
        self._fib = fib
        self._hit_count = 0
        self._miss_count = 0

    _BASE_METRICS = StageMetrics(
        name="fib_lookup",
        cycle_latency=8,
        memory_bytes=65536,
        lut_count=1200,
        ff_count=320,
        bram_count=4,
        logic_depth=16,
    )

    @property
    def metrics(self) -> StageMetrics:
        m = self._BASE_METRICS
        return StageMetrics(
            name=m.name,
            cycle_latency=m.cycle_latency,
            memory_bytes=len(self._fib) * 64,  # ~64 bytes/entry
            lut_count=m.lut_count,
            ff_count=m.ff_count,
            bram_count=m.bram_count,
            logic_depth=m.logic_depth,
        )

    def _process_packet(self, packet: "Packet") -> "Packet | None":
        entry = self._fib.lookup(packet.dst_ip)
        if entry is None:
            self._miss_count += 1
            return None  # drop: no route
        self._hit_count += 1
        # Attach next-hop into metadata (frozen dataclass → rebuild)
        new_meta = {**packet.metadata, "next_hop": entry.next_hop, "interface": entry.interface}
        import dataclasses
        return dataclasses.replace(packet, metadata=new_meta)

    @property
    def hit_count(self) -> int:
        return self._hit_count

    @property
    def miss_count(self) -> int:
        return self._miss_count


class MACTxStage(PipelineStage):
    """Checksum recalculation, frame serialization, egress."""

    _METRICS = StageMetrics(
        name="mac_tx",
        cycle_latency=6,
        memory_bytes=4096,
        lut_count=240,
        ff_count=128,
        bram_count=1,
        logic_depth=6,
    )

    @property
    def metrics(self) -> StageMetrics:
        return self._METRICS

    def _process_packet(self, packet: "Packet") -> "Packet | None":
        return packet


class RTLPluginStage(PipelineStage):
    """Pipeline stage driven by an RTLProfile parsed from a Verilog file."""

    def __init__(self, profile: "RTLProfile"):  # type: ignore[name-defined]
        super().__init__()
        self._profile = profile

    @property
    def metrics(self) -> StageMetrics:
        p = self._profile
        return StageMetrics(
            name=p.module_name,
            cycle_latency=p.estimated_cycle_latency,
            memory_bytes=p.estimated_brams * 18 * 1024 // 8,  # 18Kb per BRAM
            lut_count=p.estimated_luts,
            ff_count=p.estimated_ffs,
            bram_count=p.estimated_brams,
            logic_depth=p.max_expression_depth,
            source=f"rtl_plugin:{p.source_file}",
        )

    def _process_packet(self, packet: "Packet") -> "Packet | None":
        return packet
