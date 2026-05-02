from __future__ import annotations
import queue
import threading
import time
from typing import Any

from sim.clock import SimClock
from sim.events import SimEvent
from sim.fib import ForwardingTable
from sim.packet import Packet
from sim.stage import (
    FIBLookupStage,
    HeaderParserStage,
    MACRxStage,
    MACTxStage,
    PipelineStage,
)


class PipelineEngine:
    def __init__(self, clock: SimClock | None = None):
        self._clock = clock or SimClock()
        self._stages: list[PipelineStage] = []
        self._lock = threading.Lock()
        self._event_queue: queue.Queue[SimEvent] = queue.Queue()
        self._completed: list[Packet] = []
        self._dropped: list[tuple[Packet, str]] = []
        self._running = False
        self._thread: threading.Thread | None = None

        # State snapshot for GUI thread to read
        self._snapshot: dict[str, Any] = {}
        self._snapshot_lock = threading.Lock()

    # ── Stage management ──────────────────────────────────────────────────────

    def register_stage(self, stage: PipelineStage):
        with self._lock:
            self._stages.append(stage)

    def replace_stage(self, name: str, new_stage: PipelineStage):
        with self._lock:
            for i, s in enumerate(self._stages):
                if s.metrics.name == name:
                    self._stages[i] = new_stage
                    return
        raise KeyError(f"Stage '{name}' not found")

    def insert_stage_after(self, anchor_name: str, new_stage: PipelineStage):
        with self._lock:
            for i, s in enumerate(self._stages):
                if s.metrics.name == anchor_name:
                    self._stages.insert(i + 1, new_stage)
                    return
        raise KeyError(f"Anchor stage '{anchor_name}' not found")

    def get_stages(self) -> list[PipelineStage]:
        with self._lock:
            return list(self._stages)

    # ── Packet injection ──────────────────────────────────────────────────────

    def enqueue_packet(self, packet: Packet):
        with self._lock:
            if self._stages:
                self._stages[0].input_queue.append((packet, self._clock.cycle))

    # ── Simulation loop ───────────────────────────────────────────────────────

    def tick(self):
        cycle = self._clock.cycle
        events_this_tick: list[SimEvent] = []

        with self._lock:
            stages = list(self._stages)

        for i, stage in enumerate(stages):
            raw_events = stage.tick(cycle)
            for event_type, pkt, payload in raw_events:
                ev = SimEvent(cycle, pkt.pkt_id, stage.metrics.name, event_type, payload)
                self._clock.record(ev)
                self._event_queue.put(ev)
                events_this_tick.append(ev)

                if event_type == "drop":
                    self._dropped.append((pkt, payload.get("reason", "unknown")))

            # Move output of stage i into input of stage i+1
            with self._lock:
                next_stage = stages[i + 1] if i + 1 < len(stages) else None
            if next_stage is not None:
                while stage.output_queue:
                    pkt = stage.output_queue.popleft()
                    next_stage.input_queue.append((pkt, cycle))
            else:
                # Last stage — collect completed packets
                while stage.output_queue:
                    pkt = stage.output_queue.popleft()
                    self._completed.append(pkt)
                    ev = SimEvent(cycle, pkt.pkt_id, "pipeline", "complete", {})
                    self._clock.record(ev)
                    self._event_queue.put(ev)

        self._clock.cycle += 1
        self._update_snapshot()

    def run(self, packets: list[Packet] | None = None, max_cycles: int | None = None):
        """Run simulation to completion (blocking). Used in headless mode."""
        for pkt in (packets or []):
            self.enqueue_packet(pkt)

        cycle_limit = max_cycles or (len(packets or []) * 200 + 100)
        while self._clock.cycle < cycle_limit:
            self.tick()
            if self._all_done(packets):
                break

    def start_background(self, packets: list[Packet] | None = None):
        """Start simulation on a background thread."""
        self._running = True
        for pkt in (packets or []):
            self.enqueue_packet(pkt)

        def _loop():
            while self._running:
                self._clock.wait_if_paused()
                self.tick()
                time.sleep(self._clock.cycle_duration_s())

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def _all_done(self, packets: list[Packet] | None) -> bool:
        if packets is None:
            return False
        completed_ids = {p.pkt_id for p in self._completed}
        dropped_ids = {p.pkt_id for p, _ in self._dropped}
        return all(p.pkt_id in completed_ids or p.pkt_id in dropped_ids for p in packets)

    # ── Scrub support ─────────────────────────────────────────────────────────

    def scrub_to(self, target_cycle: int) -> list[SimEvent]:
        return self._clock.scrub_to(target_cycle)

    # ── State snapshot for GUI ────────────────────────────────────────────────

    def _update_snapshot(self):
        stages = self.get_stages()
        with self._snapshot_lock:
            self._snapshot = {
                "cycle": self._clock.cycle,
                "completed": len(self._completed),
                "dropped": len(self._dropped),
                "stages": [
                    {
                        "name": s.metrics.name,
                        "metrics": s.metrics,
                        "in_flight": len(s._in_flight),
                        "queued": len(s.input_queue),
                    }
                    for s in stages
                ],
            }

    def get_state_snapshot(self) -> dict:
        with self._snapshot_lock:
            return dict(self._snapshot)

    @property
    def event_queue(self) -> queue.Queue[SimEvent]:
        return self._event_queue

    @property
    def clock(self) -> SimClock:
        return self._clock

    @property
    def completed(self) -> list[Packet]:
        return self._completed

    @property
    def dropped(self) -> list[tuple[Packet, str]]:
        return self._dropped


def build_default_pipeline() -> PipelineEngine:
    fib = ForwardingTable()
    engine = PipelineEngine()
    engine.register_stage(MACRxStage())
    engine.register_stage(HeaderParserStage())
    engine.register_stage(FIBLookupStage(fib))
    engine.register_stage(MACTxStage())
    return engine
