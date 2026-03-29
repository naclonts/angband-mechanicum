from __future__ import annotations

from textual.binding import Binding
from textual.widget import Widget


class MenuNavigationMixin:
    """Shared focus-order helpers for menu-style screens."""

    MENU_NAVIGATION_SELECTOR = "Button, Input"

    def _menu_navigation_controls(self) -> list[Widget]:
        """Return actionable controls in DOM order, skipping containers."""
        controls = [
            widget
            for widget in self.query(self.MENU_NAVIGATION_SELECTOR)
            if widget.can_focus and not getattr(widget, "disabled", False)
        ]
        return controls

    def focus_default_menu_control(self) -> None:
        """Focus the first actionable widget on the screen."""
        controls = self._menu_navigation_controls()
        if controls:
            controls[0].focus()

    def _move_menu_focus(self, step: int) -> None:
        controls = self._menu_navigation_controls()
        if not controls:
            return

        current = self.focused
        if current not in controls:
            target = controls[0 if step > 0 else -1]
        else:
            index = controls.index(current)
            target = controls[(index + step) % len(controls)]
        target.focus()

    def action_focus_next_control(self) -> None:
        """Advance to the next actionable menu control."""
        self._move_menu_focus(1)

    def action_focus_previous_control(self) -> None:
        """Move to the previous actionable menu control."""
        self._move_menu_focus(-1)


# Bindings that let arrow keys navigate between actionable widgets, while
# skipping scroll containers and other non-actionable chrome.
ARROW_NAV_BINDINGS: list[Binding] = [
    Binding("down", "focus_next_control", "Next", show=False, priority=True),
    Binding("up", "focus_previous_control", "Previous", show=False, priority=True),
]
