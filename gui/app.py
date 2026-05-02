from __future__ import annotations
import os
import queue
import sys

import pygame

from gui import colors
from gui.metrics_panel import MetricsPanel
from gui.renderer import PipelineRenderer
from gui.stage_detail import StageDetailPopup
from gui.timeline import TimelineBar
from gui.widgets import Button, Slider
from ppa.tech_nodes import VALID_NODES
from sim.events import SimEvent
from sim.packet import PacketFactory
from sim.pipeline import PipelineEngine


WIN_W = 1280
WIN_H = 720
FPS = 60


class FPGASimApp:
    STATE_RUNNING   = "running"
    STATE_PAUSED    = "paused"
    STATE_SCRUBBING = "scrubbing"
    STATE_DETAIL    = "detail"

    def __init__(self, engine: PipelineEngine):
        self._engine = engine
        self._state = self.STATE_PAUSED

        pygame.init()
        pygame.display.set_caption("FPGA Network Router Simulator")
        self._screen = pygame.display.set_mode((WIN_W, WIN_H))
        self._clock_fps = pygame.time.Clock()

        self._font_lg = pygame.font.SysFont("monospace", 18, bold=True)
        self._font_md = pygame.font.SysFont("monospace", 15, bold=True)
        self._font_sm = pygame.font.SysFont("monospace", 13)
        self._font_xs = pygame.font.SysFont("monospace", 11)

        panel_x = WIN_W - MetricsPanel.WIDTH
        self._metrics_panel = MetricsPanel(panel_x, 0, WIN_H - TimelineBar.HEIGHT)
        self._timeline = TimelineBar(0, WIN_H - TimelineBar.HEIGHT, panel_x)
        self._timeline.set_scrub_callback(self._on_scrub)

        self._renderer = PipelineRenderer(WIN_W, WIN_H, MetricsPanel.WIDTH)
        stages = engine.get_stages()
        self._renderer.build_layout(stages)

        self._popup = StageDetailPopup(WIN_W, WIN_H)

        # Speed slider
        self._speed_slider = Slider(
            pygame.Rect(panel_x + 12, WIN_H - TimelineBar.HEIGHT - 40, 160, 14),
            min_val=0.1, max_val=10.0, initial=1.0,
        )
        self._pause_btn = Button(
            "▶ Resume", pygame.Rect(panel_x + 12, WIN_H - TimelineBar.HEIGHT - 70, 90, 24),
            self._toggle_pause,
        )
        self._inject_btn = Button(
            "+ Inject", pygame.Rect(panel_x + 110, WIN_H - TimelineBar.HEIGHT - 70, 90, 24),
            self._inject_packets,
        )

        # Cached packet map for token creation
        self._packet_map: dict[int, object] = {}

        self._tech_node_idx = 2  # 7nm default

    def run(self):
        self._engine.start_background()
        while True:
            dt = self._clock_fps.tick(FPS) / 1000.0
            if not self._handle_events():
                break
            self._consume_sim_queue()
            self._update(dt)
            self._render()
            pygame.display.flip()

        self._engine.stop()
        pygame.quit()

    # ── Event handling ─────────────────────────────────────────────────────────

    def _handle_events(self) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_q:
                return False

            if self._popup.handle_event(event):
                continue

            scrubbed = self._timeline.handle_event(event)
            if scrubbed:
                if self._state == self.STATE_RUNNING:
                    self._engine.clock.paused = True
                    self._state = self.STATE_SCRUBBING
                elif event.type == pygame.MOUSEBUTTONUP and self._state == self.STATE_SCRUBBING:
                    self._engine.clock.paused = False
                    self._state = self.STATE_RUNNING
                continue

            self._speed_slider.handle_event(event)
            self._pause_btn.handle_event(event)
            self._inject_btn.handle_event(event)
            self._metrics_panel.handle_event(event)

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                stage_name = self._renderer.get_stage_at(event.pos)
                if stage_name:
                    for stage in self._engine.get_stages():
                        if stage.metrics.name == stage_name:
                            self._popup.show(stage.metrics, VALID_NODES[self._metrics_panel._tech_node_idx])
                            break

        return True

    def _toggle_pause(self):
        if self._state == self.STATE_PAUSED:
            self._engine.clock.paused = False
            self._state = self.STATE_RUNNING
            self._pause_btn.label = "⏸ Pause"
        else:
            self._engine.clock.paused = True
            self._state = self.STATE_PAUSED
            self._pause_btn.label = "▶ Resume"

    def _inject_packets(self):
        packets = PacketFactory.generate_permutations(self._engine.clock.cycle)
        for p in packets:
            self._packet_map[p.pkt_id] = p
            self._engine.enqueue_packet(p)

    def _on_scrub(self, target_cycle: int):
        events = self._engine.scrub_to(target_cycle)
        # Rebuild renderer state from replayed events
        for ev in events:
            pkt = self._packet_map.get(ev.packet_id)
            self._renderer.apply_event(ev, pkt, cycle_duration=0.0)

    # ── Sim queue ──────────────────────────────────────────────────────────────

    def _consume_sim_queue(self):
        self._engine.clock.speed_multiplier = self._speed_slider.value
        try:
            while True:
                ev: SimEvent = self._engine.event_queue.get_nowait()
                pkt = self._packet_map.get(ev.packet_id)
                cycle_dur = self._engine.clock.cycle_duration_s()
                self._renderer.apply_event(ev, pkt, cycle_dur)
        except queue.Empty:
            pass

    # ── Update ────────────────────────────────────────────────────────────────

    def _update(self, dt: float):
        self._renderer.update(dt)
        snap = self._engine.get_state_snapshot()
        stage_metrics = [s.metrics for s in self._engine.get_stages()]
        self._metrics_panel.update(snap, stage_metrics)
        self._renderer.update_stage_metrics_from_stages(self._engine.get_stages())
        cycle = snap.get("cycle", 0)
        max_cycle = max(cycle, len(self._engine.clock.event_log))
        self._timeline.update(cycle, max_cycle)

    # ── Render ────────────────────────────────────────────────────────────────

    def _render(self):
        self._screen.fill(colors.BG_DARK)

        # Title bar
        title = self._font_lg.render("FPGA Network Router Simulator", True, colors.TEXT_PRIMARY)
        self._screen.blit(title, (16, 16))

        state_label = self._font_sm.render(
            f"[{self._state.upper()}]  Speed: {self._speed_slider.value:.1f}x  "
            f"Q: quit  N: cycle tech node  Click stage for details",
            True, colors.TEXT_DIM,
        )
        self._screen.blit(state_label, (16, 42))

        self._renderer.render(self._screen, self._font_sm, self._font_xs)
        self._metrics_panel.draw(self._screen, self._font_md, self._font_sm, self._font_xs)
        self._timeline.draw(self._screen, self._font_xs)
        self._speed_slider.draw(self._screen, self._font_xs)
        self._pause_btn.draw(self._screen, self._font_xs)
        self._inject_btn.draw(self._screen, self._font_xs)
        self._popup.draw(self._screen, self._font_md, self._font_sm, self._font_xs)
