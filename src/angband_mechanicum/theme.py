"""CRT green terminal theme for Angband Mechanicum."""

from __future__ import annotations

from textual.theme import Theme

CRT_GREEN: Theme = Theme(
    name="crt-green",
    primary="#00ff41",
    secondary="#00cc33",
    foreground="#00ff41",
    background="#0a0a0a",
    surface="#0d1a0d",
    panel="#0d260d",
    accent="#00ff41",
    warning="#33ff33",
    error="#ff3333",
    success="#00ff41",
    dark=True,
)
