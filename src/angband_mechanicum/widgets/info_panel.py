"""Info panel -- displays current game state information."""

from __future__ import annotations

from typing import Any

from textual.widgets import Static

DEFAULT_INFO: dict[str, str] = {
    "DESIGNATION": "Magos Explorator",
    "LOCATION": "Forge-Cathedral Alpha",
    "DATE": "0.123.999.M41",
    "NOOSPHERE": "CONNECTED",
}


def default_info(player_name: str = "Magos Explorator") -> dict[str, str]:
    """Return default info panel data with the given player name."""
    info = dict(DEFAULT_INFO)
    info["DESIGNATION"] = player_name
    return info

# Width of HP bars in characters (filled + empty segments)
_BAR_WIDTH: int = 8


def _hp_bar(hp: int, max_hp: int, width: int = _BAR_WIDTH) -> str:
    """Render an HP bar like ``[════──] 8/12``.

    Uses ``═`` for filled and ``─`` for empty segments.
    """
    if max_hp <= 0:
        filled = 0
    else:
        filled = round(width * hp / max_hp)
    empty = width - filled
    return f"[{'═' * filled}{'─' * empty}] {hp}/{max_hp}"


def _abbreviate_name(name: str, max_len: int = 10) -> str:
    """Shorten a party member name to fit the panel width.

    Strategy: use the last word of the name (e.g. "Skitarius Alpha-7" -> "Alpha-7").
    If still too long, truncate with ellipsis.
    """
    parts = name.split()
    short = parts[-1] if parts else name
    if len(short) > max_len:
        return short[: max_len - 1] + "\u2026"
    return short


class InfoPanel(Static):
    def update_info(self, data: dict[str, str]) -> None:
        """Update with simple key-value pairs (legacy method)."""
        max_key = max(len(k) for k in data)
        lines = [f"{k:<{max_key}}  {v}" for k, v in data.items()]
        self.update("\n".join(lines))

    def update_status(self, status: dict[str, Any]) -> None:
        """Update the full status display with info fields, integrity, and party HP.

        Expected *status* dict shape::

            {
                "info": {"DESIGNATION": "...", "LOCATION": "...", ...},
                "integrity": (current_hp, max_hp),
                "party": [
                    {"id": "...", "name": "Full Name", "hp": 8, "max_hp": 12},
                    ...
                ],
            }
        """
        lines: list[str] = []

        # -- Key-value info fields --
        info: dict[str, str] = status.get("info", {})
        if info:
            max_key = max(len(k) for k in info)
            for k, v in info.items():
                # Skip INTEGRITY/FATIGUE from LLM info — we render those deterministically
                if k.upper() in ("INTEGRITY", "FATIGUE"):
                    continue
                lines.append(f"{k:<{max_key}}  {v}")

        # -- Player integrity --
        integrity = status.get("integrity")
        if integrity:
            hp, max_hp = integrity
            lines.append("")
            lines.append(f"INTEGRITY  {_hp_bar(hp, max_hp)}")

        # -- Party members --
        party: list[dict[str, Any]] = status.get("party", [])
        if party:
            lines.append("")
            lines.append("++ PARTY ++")
            for member in party:
                name = _abbreviate_name(member["name"])
                bar = _hp_bar(member["hp"], member["max_hp"], width=6)
                lines.append(f"  {name:<10} {bar}")

        self.update("\n".join(lines))
