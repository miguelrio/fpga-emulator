from dataclasses import dataclass, field
from typing import Any


@dataclass
class SimEvent:
    cycle: int
    packet_id: int
    stage_name: str
    event_type: str  # 'enter' | 'exit' | 'drop' | 'lookup_hit' | 'lookup_miss' | 'plugin_reloaded'
    payload: dict[str, Any] = field(default_factory=dict)
