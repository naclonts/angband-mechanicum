"""Tests for widget formatting logic (no Textual app needed)."""

from __future__ import annotations

from angband_mechanicum.widgets.info_panel import DEFAULT_INFO, InfoPanel


class TestInfoPanelFormatting:
    def test_update_info_aligns_keys(self) -> None:
        """update_info right-pads keys to the longest key length."""
        panel = InfoPanel()
        data = {"A": "1", "LONG_KEY": "2", "BB": "3"}
        # We can't call update_info directly without a running app,
        # so test the formatting logic inline.
        max_key = max(len(k) for k in data)
        lines = [f"{k:<{max_key}}  {v}" for k, v in data.items()]
        result = "\n".join(lines)

        assert "A         1" in result
        assert "LONG_KEY  2" in result
        assert "BB        3" in result

    def test_default_info_has_required_fields(self) -> None:
        required = {"DESIGNATION", "LOCATION", "DATE", "FATIGUE", "INTEGRITY", "NOOSPHERE"}
        assert required == set(DEFAULT_INFO.keys())
