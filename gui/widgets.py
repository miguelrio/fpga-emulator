from __future__ import annotations
import math
from typing import Callable

import pygame

from gui import colors
from sim.packet import Packet


# ── StageBox ──────────────────────────────────────────────────────────────────

class StageBox:
    PADDING = 10
    WIDTH = 130
    HEIGHT = 80

    def __init__(self, name: str, x: int, y: int, is_plugin: bool = False):
        self.name = name
        self.rect = pygame.Rect(x, y, self.WIDTH, self.HEIGHT)
        self.is_plugin = is_plugin
        self.active = False           # packet currently inside
        self.flash_color: tuple | None = None
        self.flash_timer = 0.0       # seconds remaining
        self._glow_alpha = 0.0
        self._lut_count = 0
        self._cycle_latency = 0

    def update_metrics(self, lut_count: int, cycle_latency: int):
        self._lut_count = lut_count
        self._cycle_latency = cycle_latency

    def flash(self, color: tuple, duration: float = 0.5):
        self.flash_color = color
        self.flash_timer = duration

    def update(self, dt: float):
        if self.flash_timer > 0:
            self.flash_timer -= dt
            if self.flash_timer <= 0:
                self.flash_color = None
        target_alpha = 255.0 if self.active else 0.0
        self._glow_alpha += (target_alpha - self._glow_alpha) * min(1.0, dt * 8)

    def draw(self, surface: pygame.Surface, font_sm: pygame.font.Font, font_xs: pygame.font.Font):
        border_color = (
            self.flash_color if self.flash_color
            else (colors.BORDER_PLUGIN if self.is_plugin else
                  (colors.BORDER_ACTIVE if self.active else colors.BORDER_IDLE))
        )
        bg_color = colors.BG_STAGE_ACTIVE if self.active else colors.BG_STAGE

        # Glow rings
        if self._glow_alpha > 5:
            glow_src = colors.GLOW_PLUGIN if self.is_plugin else colors.GLOW_COLORS
            for i, gc in enumerate(glow_src):
                r = self.rect.inflate((i + 1) * 8, (i + 1) * 8)
                glow_surf = pygame.Surface(r.size, pygame.SRCALPHA)
                alpha = int(gc[3] * self._glow_alpha / 255)
                pygame.draw.rect(glow_surf, (*gc[:3], alpha), glow_surf.get_rect(), border_radius=8)
                surface.blit(glow_surf, r.topleft)

        pygame.draw.rect(surface, bg_color, self.rect, border_radius=6)
        pygame.draw.rect(surface, border_color, self.rect, 2, border_radius=6)

        # Stage name
        label = font_sm.render(self.name, True, colors.TEXT_PRIMARY)
        surface.blit(label, (self.rect.x + 8, self.rect.y + 8))

        # Metrics
        metrics_text = f"L:{self._cycle_latency}cy  {self._lut_count}LUT"
        m_surf = font_xs.render(metrics_text, True, colors.TEXT_SECONDARY)
        surface.blit(m_surf, (self.rect.x + 8, self.rect.y + self.HEIGHT - 22))

        if self.is_plugin:
            tag = font_xs.render("RTL", True, colors.BORDER_PLUGIN)
            surface.blit(tag, (self.rect.right - 28, self.rect.y + 8))


# ── WireSegment ───────────────────────────────────────────────────────────────

class WireSegment:
    def __init__(self, waypoints: list[tuple[int, int]]):
        self.waypoints = waypoints
        self.active = False
        self._active_alpha = 0.0

    def update(self, dt: float):
        target = 255.0 if self.active else 0.0
        self._active_alpha += (target - self._active_alpha) * min(1.0, dt * 6)

    def draw(self, surface: pygame.Surface):
        if len(self.waypoints) < 2:
            return
        alpha = self._active_alpha / 255.0
        r = int(colors.WIRE_IDLE[0] + (colors.WIRE_ACTIVE[0] - colors.WIRE_IDLE[0]) * alpha)
        g = int(colors.WIRE_IDLE[1] + (colors.WIRE_ACTIVE[1] - colors.WIRE_IDLE[1]) * alpha)
        b = int(colors.WIRE_IDLE[2] + (colors.WIRE_ACTIVE[2] - colors.WIRE_IDLE[2]) * alpha)
        color = (r, g, b)
        for i in range(len(self.waypoints) - 1):
            pygame.draw.line(surface, color, self.waypoints[i], self.waypoints[i + 1], 2)


# ── PacketToken ───────────────────────────────────────────────────────────────

class PacketToken:
    BASE_WIDTH = 18
    HEIGHT = 12

    def __init__(self, packet: Packet):
        self.packet = packet
        self._waypoints: list[tuple[int, int]] = []
        self._t = 0.0           # progress along current path [0, 1]
        self._speed = 1.0       # path units per second
        self._pos: tuple[float, float] = (0.0, 0.0)
        self._done = False
        self._drop_flash = 0.0

    def set_path(self, waypoints: list[tuple[int, int]], duration_s: float = 1.0):
        self._waypoints = waypoints
        self._t = 0.0
        self._speed = 1.0 / max(duration_s, 0.001)
        if waypoints:
            self._pos = (float(waypoints[0][0]), float(waypoints[0][1]))

    def trigger_drop(self):
        self._drop_flash = 0.5

    @property
    def done(self) -> bool:
        return self._done

    @property
    def pos(self) -> tuple[float, float]:
        return self._pos

    def update(self, dt: float):
        if self._drop_flash > 0:
            self._drop_flash -= dt
        if not self._waypoints or self._done:
            return
        self._t = min(1.0, self._t + self._speed * dt)
        self._pos = _interpolate_path(self._waypoints, self._t)
        if self._t >= 1.0:
            self._done = True

    def draw(self, surface: pygame.Surface):
        x, y = int(self._pos[0]), int(self._pos[1])
        w = max(8, int(self.BASE_WIDTH + math.log2(max(1, self.packet.size_bytes / 64)) * 4))
        rect = pygame.Rect(x - w // 2, y - self.HEIGHT // 2, w, self.HEIGHT)

        if self._drop_flash > 0:
            color = colors.TOKEN_DROP
        elif self.packet.ip_version == 4:
            color = colors.TOKEN_IPV4_TCP if self.packet.proto == "tcp" else colors.TOKEN_IPV4_UDP
        else:
            color = colors.TOKEN_IPV6_TCP if self.packet.proto == "tcp" else colors.TOKEN_IPV6_UDP

        if self.packet.proto == "udp" and self._drop_flash <= 0:
            # Dashed outline style for UDP
            pygame.draw.rect(surface, (*color, 120), rect, border_radius=3)
            pygame.draw.rect(surface, color, rect, 2, border_radius=3)
        else:
            pygame.draw.rect(surface, color, rect, border_radius=3)


def _interpolate_path(waypoints: list[tuple[int, int]], t: float) -> tuple[float, float]:
    if not waypoints:
        return (0.0, 0.0)
    if len(waypoints) == 1:
        return (float(waypoints[0][0]), float(waypoints[0][1]))

    # Compute total length and find segment at t
    segments = []
    total = 0.0
    for i in range(len(waypoints) - 1):
        dx = waypoints[i + 1][0] - waypoints[i][0]
        dy = waypoints[i + 1][1] - waypoints[i][1]
        seg_len = math.sqrt(dx * dx + dy * dy)
        segments.append(seg_len)
        total += seg_len

    if total == 0:
        return (float(waypoints[-1][0]), float(waypoints[-1][1]))

    target_dist = t * total
    accum = 0.0
    for i, seg_len in enumerate(segments):
        if accum + seg_len >= target_dist or i == len(segments) - 1:
            local_t = (target_dist - accum) / max(seg_len, 0.001)
            x = waypoints[i][0] + local_t * (waypoints[i + 1][0] - waypoints[i][0])
            y = waypoints[i][1] + local_t * (waypoints[i + 1][1] - waypoints[i][1])
            return (x, y)
        accum += seg_len

    return (float(waypoints[-1][0]), float(waypoints[-1][1]))


# ── Button ────────────────────────────────────────────────────────────────────

class Button:
    def __init__(self, label: str, rect: pygame.Rect, callback: Callable[[], None]):
        self.label = label
        self.rect = rect
        self.callback = callback
        self._hover = False

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.MOUSEMOTION:
            self._hover = self.rect.collidepoint(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self.callback()

    def draw(self, surface: pygame.Surface, font: pygame.font.Font):
        color = colors.BTN_HOVER if self._hover else colors.BTN_NORMAL
        pygame.draw.rect(surface, color, self.rect, border_radius=4)
        pygame.draw.rect(surface, colors.BORDER_IDLE, self.rect, 1, border_radius=4)
        text = font.render(self.label, True, colors.BTN_TEXT)
        tr = text.get_rect(center=self.rect.center)
        surface.blit(text, tr)


# ── Slider ────────────────────────────────────────────────────────────────────

class Slider:
    def __init__(self, rect: pygame.Rect, min_val: float, max_val: float, initial: float):
        self.rect = rect
        self.min_val = min_val
        self.max_val = max_val
        self.value = initial
        self._dragging = False

    def handle_event(self, event: pygame.event.Event):
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self._dragging = True
                self._update_value(event.pos[0])
        elif event.type == pygame.MOUSEBUTTONUP:
            self._dragging = False
        elif event.type == pygame.MOUSEMOTION and self._dragging:
            self._update_value(event.pos[0])

    def _update_value(self, x: int):
        ratio = (x - self.rect.x) / max(1, self.rect.width)
        ratio = max(0.0, min(1.0, ratio))
        self.value = self.min_val + ratio * (self.max_val - self.min_val)

    def draw(self, surface: pygame.Surface, font: pygame.font.Font):
        pygame.draw.rect(surface, colors.BAR_BG, self.rect, border_radius=3)
        ratio = (self.value - self.min_val) / max(0.001, self.max_val - self.min_val)
        fill_w = int(self.rect.width * ratio)
        fill_rect = pygame.Rect(self.rect.x, self.rect.y, fill_w, self.rect.height)
        pygame.draw.rect(surface, colors.TIMELINE_FILL, fill_rect, border_radius=3)
        pygame.draw.rect(surface, colors.BORDER_IDLE, self.rect, 1, border_radius=3)
        label = font.render(f"{self.value:.1f}x", True, colors.TEXT_PRIMARY)
        surface.blit(label, (self.rect.right + 6, self.rect.y - 2))
