from __future__ import annotations
import pygame
from gui import colors
from gui.widgets import StageBox, WireSegment, PacketToken
from sim.events import SimEvent
from sim.packet import Packet
from sim.stage import PipelineStage


class PipelineRenderer:
    STAGE_GAP = 60      # horizontal gap between stage boxes
    TOP_MARGIN = 80
    SIDE_MARGIN = 30

    def __init__(self, width: int, height: int, panel_width: int):
        self._width = width
        self._height = height
        self._panel_width = panel_width
        self._stage_boxes: list[StageBox] = []
        self._wires: list[WireSegment] = []
        self._tokens: dict[int, PacketToken] = {}  # pkt_id → token
        self._flash_events: list[tuple[str, float]] = []  # (stage_name, ttl)

    def build_layout(self, stages: list[PipelineStage]):
        self._stage_boxes.clear()
        self._wires.clear()

        pipeline_width = self._width - self._panel_width - self.SIDE_MARGIN * 2
        n = len(stages)
        if n == 0:
            return

        box_w = StageBox.WIDTH
        box_h = StageBox.HEIGHT
        total_w = n * box_w + (n - 1) * self.STAGE_GAP
        start_x = self.SIDE_MARGIN + max(0, (pipeline_width - total_w) // 2)
        center_y = self.TOP_MARGIN + box_h // 2

        boxes = []
        for i, stage in enumerate(stages):
            x = start_x + i * (box_w + self.STAGE_GAP)
            y = center_y
            is_plugin = stage.metrics.source.startswith("rtl_plugin")
            box = StageBox(stage.metrics.name, x, y, is_plugin)
            box.update_metrics(stage.metrics.lut_count, stage.metrics.cycle_latency)
            boxes.append(box)
            self._stage_boxes.append(box)

        # Build wires between boxes (Manhattan: horizontal only for same row)
        for i in range(len(boxes) - 1):
            src = boxes[i]
            dst = boxes[i + 1]
            start = (src.rect.right, src.rect.centery)
            end = (dst.rect.left, dst.rect.centery)
            mid_x = (start[0] + end[0]) // 2
            waypoints = [start, (mid_x, start[1]), (mid_x, end[1]), end]
            self._wires.append(WireSegment(waypoints))

        # "Incoming" wire on the left of first box
        first = boxes[0]
        entry = WireSegment([
            (self.SIDE_MARGIN, first.rect.centery),
            (first.rect.left, first.rect.centery),
        ])
        self._wires.insert(0, entry)

        # "Outgoing" wire after last box
        last = boxes[-1]
        exit_wire = WireSegment([
            (last.rect.right, last.rect.centery),
            (last.rect.right + 50, last.rect.centery),
        ])
        self._wires.append(exit_wire)

    def apply_event(self, ev: SimEvent, packet: Packet | None = None, cycle_duration: float = 1.0):
        stage_idx = self._stage_index(ev.stage_name)

        if ev.event_type == "enter":
            if packet and ev.packet_id not in self._tokens:
                token = PacketToken(packet)
                self._tokens[ev.packet_id] = token
            if ev.packet_id in self._tokens and stage_idx is not None:
                box = self._stage_boxes[stage_idx]
                box.active = True
                wire_idx = stage_idx + 1  # +1 because index 0 is the entry wire
                if wire_idx < len(self._wires):
                    self._wires[wire_idx].active = True
                # Move token to center of stage box
                token = self._tokens[ev.packet_id]
                cx, cy = box.rect.center
                token.set_path([(cx, cy)], duration_s=cycle_duration)

        elif ev.event_type == "exit":
            if stage_idx is not None:
                self._stage_boxes[stage_idx].active = False
                wire_idx = stage_idx + 2  # wire after this stage
                if wire_idx < len(self._wires):
                    self._wires[wire_idx].active = True
                if stage_idx + 1 < len(self._stage_boxes):
                    next_box = self._stage_boxes[stage_idx + 1]
                    if ev.packet_id in self._tokens:
                        token = self._tokens[ev.packet_id]
                        cx, cy = next_box.rect.centerx - StageBox.WIDTH // 2, next_box.rect.centery
                        token.set_path([(cx, cy)], duration_s=cycle_duration * 0.5)

        elif ev.event_type == "drop":
            if ev.packet_id in self._tokens:
                self._tokens[ev.packet_id].trigger_drop()
            if stage_idx is not None:
                self._stage_boxes[stage_idx].flash(colors.FLASH_DROP, 0.6)

        elif ev.event_type == "lookup_hit":
            if stage_idx is not None:
                self._stage_boxes[stage_idx].flash(colors.FLASH_HIT, 0.4)

        elif ev.event_type == "plugin_reloaded":
            if stage_idx is not None:
                self._stage_boxes[stage_idx].flash(colors.FLASH_RELOAD, 2.0)

        elif ev.event_type == "complete":
            # Animate token off screen
            if ev.packet_id in self._tokens:
                token = self._tokens[ev.packet_id]
                x, y = token.pos
                token.set_path([(int(x), int(y)), (self._width - self._panel_width + 20, int(y))],
                               duration_s=0.3)

    def update(self, dt: float):
        for box in self._stage_boxes:
            box.update(dt)
        for wire in self._wires:
            wire.update(dt)
        done_ids = []
        for pid, token in self._tokens.items():
            token.update(dt)
            if token.done:
                done_ids.append(pid)
        for pid in done_ids:
            del self._tokens[pid]

    def render(self, surface: pygame.Surface, font_sm: pygame.font.Font, font_xs: pygame.font.Font):
        for wire in self._wires:
            wire.draw(surface)
        for box in self._stage_boxes:
            box.draw(surface, font_sm, font_xs)
        for token in self._tokens.values():
            token.draw(surface)

    def get_stage_at(self, pos: tuple[int, int]) -> str | None:
        for box in self._stage_boxes:
            if box.rect.collidepoint(pos):
                return box.name
        return None

    def update_stage_metrics_from_stages(self, stages: list[PipelineStage]):
        for box in self._stage_boxes:
            for stage in stages:
                if stage.metrics.name == box.name:
                    box.update_metrics(stage.metrics.lut_count, stage.metrics.cycle_latency)
                    box.is_plugin = stage.metrics.source.startswith("rtl_plugin")
                    break

    def _stage_index(self, name: str) -> int | None:
        for i, box in enumerate(self._stage_boxes):
            if box.name == name:
                return i
        return None
