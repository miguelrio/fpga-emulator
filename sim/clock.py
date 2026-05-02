import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sim.events import SimEvent


@dataclass
class SimClock:
    cycle: int = 0
    speed_multiplier: float = 1.0  # 1.0 = ~1 packet traversal per second
    _paused: bool = False
    _pause_event: threading.Event = field(default_factory=threading.Event)
    event_log: list = field(default_factory=list)

    def __post_init__(self):
        self._pause_event.set()  # not paused initially

    @property
    def paused(self) -> bool:
        return self._paused

    @paused.setter
    def paused(self, value: bool):
        self._paused = value
        if value:
            self._pause_event.clear()
        else:
            self._pause_event.set()

    def wait_if_paused(self):
        self._pause_event.wait()

    def record(self, event: "SimEvent"):
        self.event_log.append(event)

    def scrub_to(self, target_cycle: int) -> list:
        return [ev for ev in self.event_log if ev.cycle <= target_cycle]

    def cycle_duration_s(self) -> float:
        """Wall-clock seconds per simulated cycle for animation pacing."""
        base = 0.033  # 30 cycles/sec at 1x → ~1 full traversal/sec
        return base / max(self.speed_multiplier, 0.01)
