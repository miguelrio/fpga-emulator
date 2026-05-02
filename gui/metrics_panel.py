from __future__ import annotations
import pygame
from gui import colors
from ppa.estimator import PPAResult, PPAEstimator
from ppa.tech_nodes import VALID_NODES
from sim.stage import StageMetrics


class MetricsPanel:
    WIDTH = 260
    PADDING = 12

    def __init__(self, x: int, y: int, height: int):
        self.rect = pygame.Rect(x, y, self.WIDTH, height)
        self._snapshot: dict = {}
        self._ppa: PPAResult | None = None
        self._tech_node_idx = 2  # default: 7nm
        self._estimator = PPAEstimator(VALID_NODES[self._tech_node_idx])

    def update(self, snapshot: dict, stage_metrics: list[StageMetrics]):
        self._snapshot = snapshot
        if stage_metrics:
            self._estimator.tech_node = VALID_NODES[self._tech_node_idx]
            self._ppa = self._estimator.estimate(stage_metrics)

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_n:
                self._tech_node_idx = (self._tech_node_idx + 1) % len(VALID_NODES)

    def draw(self, surface: pygame.Surface, font_md: pygame.font.Font,
             font_sm: pygame.font.Font, font_xs: pygame.font.Font):
        pygame.draw.rect(surface, colors.PANEL_BG, self.rect)
        pygame.draw.rect(surface, colors.PANEL_BORDER, self.rect, 1)

        x = self.rect.x + self.PADDING
        y = self.rect.y + self.PADDING

        y = self._draw_section_header(surface, font_sm, "SIMULATION", x, y)
        snap = self._snapshot
        rows = [
            ("Cycle",      str(snap.get("cycle", 0))),
            ("Completed",  str(snap.get("completed", 0))),
            ("Dropped",    str(snap.get("dropped", 0))),
        ]
        y = self._draw_kv_rows(surface, font_xs, rows, x, y)
        y += 8

        stages = snap.get("stages", [])
        if stages:
            y = self._draw_section_header(surface, font_sm, "PIPELINE STAGES", x, y)
            for st in stages:
                m = st.get("metrics")
                if m is None:
                    continue
                name = m.name[:16]
                inflight = st.get("in_flight", 0)
                queued = st.get("queued", 0)
                text = f"  {name:<16}  ▶{inflight} Q{queued}"
                surf = font_xs.render(text, True, colors.TEXT_SECONDARY)
                surface.blit(surf, (x, y))
                y += 16
            y += 4

        y = self._draw_section_header(surface, font_sm, "FPGA RESOURCES", x, y)
        if self._ppa:
            for name, est in self._ppa.per_stage.items():
                surf = font_xs.render(f"  {name[:14]}", True, colors.TEXT_DIM)
                surface.blit(surf, (x, y))
                y += 14
                y = self._draw_bar(surface, "LUT", est.gate_equivalents // 6,
                                   4000, colors.BAR_LUT, x + 8, y, font_xs)
            y += 4

        y = self._draw_section_header(surface, font_sm, f"ASIC PPA  [{VALID_NODES[self._tech_node_idx]}]", x, y)
        node_hint = font_xs.render("(press N to change node)", True, colors.TEXT_DIM)
        surface.blit(node_hint, (x, y))
        y += 14

        if self._ppa:
            ppa_rows = [
                ("Fmax",     f"{self._ppa.fmax_ghz:.3f} GHz"),
                ("Area",     f"{self._ppa.die_area_mm2:.6f} mm²"),
                ("Dyn pwr",  f"{self._ppa.dynamic_power_mw:.3f} mW"),
                ("Leakage",  f"{self._ppa.leakage_power_mw:.3f} mW"),
                ("Total pwr",f"{self._ppa.total_power_mw:.3f} mW"),
                ("Total GE", f"{self._ppa.total_gate_equivalents:,}"),
            ]
            y = self._draw_kv_rows(surface, font_xs, ppa_rows, x, y)

    def _draw_section_header(self, surface, font, text, x, y) -> int:
        header_rect = pygame.Rect(x - self.PADDING, y, self.WIDTH, 20)
        pygame.draw.rect(surface, colors.PANEL_HEADER, header_rect)
        surf = font.render(text, True, colors.TEXT_HIGHLIGHT)
        surface.blit(surf, (x, y + 3))
        return y + 24

    def _draw_kv_rows(self, surface, font, rows, x, y) -> int:
        for key, val in rows:
            k_surf = font.render(f"  {key}:", True, colors.TEXT_SECONDARY)
            v_surf = font.render(val, True, colors.TEXT_PRIMARY)
            surface.blit(k_surf, (x, y))
            surface.blit(v_surf, (x + 110, y))
            y += 16
        return y

    def _draw_bar(self, surface, label, value, max_val, color, x, y, font) -> int:
        BAR_W = 160
        BAR_H = 8
        lbl = font.render(f"{label}:{value}", True, colors.TEXT_DIM)
        surface.blit(lbl, (x, y))
        y += 12
        bg_rect = pygame.Rect(x, y, BAR_W, BAR_H)
        pygame.draw.rect(surface, colors.BAR_BG, bg_rect, border_radius=2)
        fill_w = int(BAR_W * min(1.0, value / max(1, max_val)))
        if fill_w > 0:
            fill_rect = pygame.Rect(x, y, fill_w, BAR_H)
            pygame.draw.rect(surface, color, fill_rect, border_radius=2)
        return y + BAR_H + 4
