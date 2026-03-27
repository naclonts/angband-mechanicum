"""Info panel -- displays current game state information."""

from __future__ import annotations

from textual.widgets import Static

DEFAULT_INFO: dict[str, str] = {
    "DESIGNATION": "Magos Explorator",
    "LOCATION": "Forge-Cathedral Alpha",
    "DATE": "0.123.999.M41",
    "FATIGUE": "[====------] 40%",
    "INTEGRITY": "[=========-] 95%",
    "NOOSPHERE": "CONNECTED",
}


class InfoPanel(Static):
    def update_info(self, data: dict[str, str]) -> None:
        max_key = max(len(k) for k in data)
        lines = [f"{k:<{max_key}}  {v}" for k, v in data.items()]
        self.update("\n".join(lines))
