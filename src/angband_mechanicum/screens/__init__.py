from __future__ import annotations

from textual.binding import Binding


# Bindings that let arrow keys navigate between focusable widgets, mirroring
# the existing Tab / Shift+Tab behaviour.  Mix into any menu-style Screen's
# BINDINGS list.
ARROW_NAV_BINDINGS: list[Binding] = [
    Binding("down", "app.focus_next", "Next", show=False),
    Binding("up", "app.focus_previous", "Previous", show=False),
]
