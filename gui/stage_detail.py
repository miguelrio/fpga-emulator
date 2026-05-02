from __future__ import annotations
import subprocess
import sys
import pygame
from gui import colors
from sim.stage import StageMetrics
from ppa.estimator import PPAEstimator, StageEstimate
from ppa.tech_nodes import VALID_NODES


class StageDetailPopup:
    WIDTH = 400
    HEIGHT = 380

    def __init__(self, screen_w: int, screen_h: int):
        self._visible = False
        self._metrics: StageMetrics | None = None
        self._estimate: StageEstimate | None = None
        self._screen_w = screen_w
        self._screen_h = screen_h
        self._rect = pygame.Rect(
            (screen_w - self.WIDTH) // 2,
            (screen_h - self.HEIGHT) // 2,
            self.WIDTH, self.HEIGHT,
        )
        self._close_rect = pygame.Rect(
            self._rect.right - 30, self._rect.top + 8, 22, 22
        )
        self._verilog_rect = pygame.Rect(
            self._rect.x + 12, self._rect.bottom - 44, 140, 30
        )
        self._tech_node = VALID_NODES[2]

    def show(self, metrics: StageMetrics, tech_node: str = "7nm"):
        self._metrics = metrics
        self._tech_node = tech_node
        est = PPAEstimator(tech_node).estimate_stage(
            metrics, __import__("ppa.tech_nodes", fromlist=["get_node"]).get_node(tech_node)
        )
        self._estimate = est
        self._visible = True

    def hide(self):
        self._visible = False

    @property
    def visible(self) -> bool:
        return self._visible

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Returns True if event was consumed."""
        if not self._visible:
            return False
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self._close_rect.collidepoint(event.pos):
                self.hide()
                return True
            if self._verilog_rect.collidepoint(event.pos) and self._metrics:
                self._open_verilog()
                return True
            if not self._rect.collidepoint(event.pos):
                self.hide()
                return True
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.hide()
            return True
        return False

    def draw(self, surface: pygame.Surface, font_md: pygame.font.Font,
             font_sm: pygame.font.Font, font_xs: pygame.font.Font):
        if not self._visible or self._metrics is None:
            return

        # Dim background
        overlay = pygame.Surface((self._screen_w, self._screen_h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        surface.blit(overlay, (0, 0))

        # Panel
        pygame.draw.rect(surface, colors.PANEL_BG, self._rect, border_radius=8)
        pygame.draw.rect(surface, colors.BORDER_ACTIVE, self._rect, 2, border_radius=8)

        # Close button
        pygame.draw.rect(surface, colors.BTN_NORMAL, self._close_rect, border_radius=4)
        x_surf = font_sm.render("✕", True, colors.TEXT_PRIMARY)
        surface.blit(x_surf, self._close_rect.move(4, 2))

        m = self._metrics
        x = self._rect.x + 14
        y = self._rect.y + 14

        title = font_md.render(m.name, True, colors.TEXT_HIGHLIGHT)
        surface.blit(title, (x, y))
        y += 28

        source_color = colors.BORDER_PLUGIN if m.source.startswith("rtl_plugin") else colors.TEXT_DIM
        src_surf = font_xs.render(f"Source: {m.source}", True, source_color)
        surface.blit(src_surf, (x, y))
        y += 20

        # Divider
        pygame.draw.line(surface, colors.PANEL_BORDER, (x, y), (self._rect.right - 14, y))
        y += 10

        # Resource table
        rows = [
            ("Cycle latency",  f"{m.cycle_latency} cycles"),
            ("Memory",         f"{m.memory_bytes:,} B"),
            ("LUT count",      str(m.lut_count)),
            ("FF count",       str(m.ff_count)),
            ("BRAM count",     str(m.bram_count)),
            ("Logic depth",    f"{m.logic_depth} levels"),
        ]
        for label, val in rows:
            k = font_xs.render(f"{label}:", True, colors.TEXT_SECONDARY)
            v = font_xs.render(val, True, colors.TEXT_PRIMARY)
            surface.blit(k, (x, y))
            surface.blit(v, (x + 140, y))
            y += 18

        y += 6
        pygame.draw.line(surface, colors.PANEL_BORDER, (x, y), (self._rect.right - 14, y))
        y += 10

        # PPA estimates
        ppa_title = font_sm.render(f"ASIC Estimate ({self._tech_node})", True, colors.TEXT_HIGHLIGHT)
        surface.blit(ppa_title, (x, y))
        y += 22

        if self._estimate:
            est = self._estimate
            ppa_rows = [
                ("Fmax",      f"{est.fmax_ghz:.3f} GHz"),
                ("Area",      f"{est.die_area_mm2:.8f} mm²"),
                ("Dyn power", f"{est.dynamic_power_mw:.4f} mW"),
                ("Leakage",   f"{est.leakage_power_mw:.4f} mW"),
                ("Total pwr", f"{est.total_power_mw:.4f} mW"),
                ("Gate equiv",f"{est.gate_equivalents:,}"),
            ]
            for label, val in ppa_rows:
                k = font_xs.render(f"{label}:", True, colors.TEXT_SECONDARY)
                v = font_xs.render(val, True, colors.TEXT_PRIMARY)
                surface.blit(k, (x, y))
                surface.blit(v, (x + 140, y))
                y += 17

        # View Verilog button (only for RTL plugins)
        if m.source.startswith("rtl_plugin"):
            pygame.draw.rect(surface, colors.BTN_NORMAL, self._verilog_rect, border_radius=4)
            pygame.draw.rect(surface, colors.BORDER_PLUGIN, self._verilog_rect, 1, border_radius=4)
            btn_text = font_xs.render("View Verilog source", True, colors.BTN_TEXT)
            surface.blit(btn_text, self._verilog_rect.move(8, 8))

    def _open_verilog(self):
        if self._metrics is None:
            return
        src = self._metrics.source
        if src.startswith("rtl_plugin:"):
            filename = src.split(":", 1)[1]
            import os
            path = os.path.join("rtl", "plugins", filename)
            if sys.platform == "darwin":
                subprocess.Popen(["open", "-t", path])
            elif sys.platform == "win32":
                subprocess.Popen(["notepad", path])
            else:
                subprocess.Popen(["xdg-open", path])
