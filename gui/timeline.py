from __future__ import annotations
import pygame
from gui import colors


class TimelineBar:
    HEIGHT = 28
    CURSOR_W = 4

    def __init__(self, x: int, y: int, width: int):
        self.rect = pygame.Rect(x, y, width, self.HEIGHT)
        self._max_cycle = 1
        self._current_cycle = 0
        self._dragging = False
        self._scrub_callback = None  # Callable[[int], None]

    def set_scrub_callback(self, cb):
        self._scrub_callback = cb

    def update(self, current_cycle: int, max_cycle: int):
        self._current_cycle = current_cycle
        self._max_cycle = max(1, max_cycle)

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Returns True if a scrub action occurred."""
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.rect.collidepoint(event.pos):
                self._dragging = True
                self._do_scrub(event.pos[0])
                return True
        elif event.type == pygame.MOUSEBUTTONUP:
            was = self._dragging
            self._dragging = False
            return was
        elif event.type == pygame.MOUSEMOTION and self._dragging:
            self._do_scrub(event.pos[0])
            return True
        return False

    def _do_scrub(self, x: int):
        ratio = (x - self.rect.x) / max(1, self.rect.width)
        ratio = max(0.0, min(1.0, ratio))
        target_cycle = int(ratio * self._max_cycle)
        self._current_cycle = target_cycle
        if self._scrub_callback:
            self._scrub_callback(target_cycle)

    def draw(self, surface: pygame.Surface, font: pygame.font.Font):
        pygame.draw.rect(surface, colors.TIMELINE_BG, self.rect)
        pygame.draw.rect(surface, colors.PANEL_BORDER, self.rect, 1)

        ratio = self._current_cycle / self._max_cycle
        fill_w = int(self.rect.width * ratio)
        if fill_w > 0:
            fill = pygame.Rect(self.rect.x, self.rect.y, fill_w, self.rect.height)
            pygame.draw.rect(surface, colors.TIMELINE_FILL, fill)

        # Cursor
        cx = self.rect.x + fill_w
        pygame.draw.rect(
            surface, colors.TIMELINE_CURSOR,
            pygame.Rect(cx - self.CURSOR_W // 2, self.rect.y, self.CURSOR_W, self.rect.height)
        )

        # Labels
        label = font.render(f"Cycle {self._current_cycle} / {self._max_cycle}", True, colors.TEXT_SECONDARY)
        surface.blit(label, (self.rect.x + 6, self.rect.y + 6))
        hint = font.render("drag to scrub", True, colors.TEXT_DIM)
        surface.blit(hint, (self.rect.right - hint.get_width() - 6, self.rect.y + 6))
