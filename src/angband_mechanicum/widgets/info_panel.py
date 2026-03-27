"""Info panel — displays current game state information."""

from textual.widgets import Static

DEFAULT_INFO = {
    "DESIGNATION": "Magos Explorator",
    "LOCATION": "Forge-Cathedral Alpha",
    "DATE": "0.123.999.M41",
    "FATIGUE": "[====------] 40%",
    "INTEGRITY": "[=========-] 95%",
    "NOOSPHERE": "CONNECTED",
}


class InfoPanel(Static):
    def update_info(self, data: dict) -> None:
        max_key = max(len(k) for k in data)
        lines = [f"{k:<{max_key}}  {v}" for k, v in data.items()]
        self.update("\n".join(lines))
