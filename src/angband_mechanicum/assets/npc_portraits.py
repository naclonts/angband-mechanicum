"""NPC portrait database -- template-based unicode art portraits for NPCs.

Stores a mapping of entity_id -> portrait art string, with persistence
to a JSON file so portraits are stable across sessions.
"""

from __future__ import annotations

import json
import logging
import os
import random
from pathlib import Path
from typing import Any

logger: logging.Logger = logging.getLogger(__name__)


def _data_dir() -> Path:
    """Return the persistent data directory, respecting XDG_DATA_HOME."""
    xdg_data: str = os.environ.get(
        "XDG_DATA_HOME", os.path.expanduser("~/.local/share")
    )
    data_path: Path = Path(xdg_data) / "angband-mechanicum"
    data_path.mkdir(parents=True, exist_ok=True)
    return data_path


# ---------------------------------------------------------------------------
# NPC Portrait Templates
# ---------------------------------------------------------------------------
# Each template is ~20 chars wide x ~15 lines tall, using box-drawing and
# unicode characters. No Rich markup.

NPC_TEMPLATES: dict[str, str] = {
    "skitarii": """\
      ┌───────────┐
      │  ┌─────┐  │
      │  │ ◎ ◎ │  │
      │  │  ▼  │  │
      │  └──┬──┘  │
      │  ╔══╧══╗  │
      │  ║▒▒▒▒▒║  │
      │  ║▒ ⛨ ▒║  │
      │  ╚═╤═╤═╝  │
      ├──┐ │ │ ┌──┤
      │▓▓│ │ │ │▓▓│
      │▓▓│ │ │ │▓▓│
      │  │ │ │ │  │
      │  └─┘ └─┘  │
      └───────────┘
       SKITARII""",
    "enginseer": """\
      ┌───────────┐
      │  ╔═════╗  │
      │  ║ ◉ ◉ ║  │
      │  ║  ═  ║  │
      │  ╚══╤══╝  │
      │ ╱┌──┴──┐╲ │
      │╱ │═════│ ╲│
      ├──┤ ╬╬╬ ├──┤
      │░░│ ╬╬╬ │░░│
      │░░│     │░░│
      │  │ ┌─┐ │  │
      │  │ │⚙│ │  │
      │  │ └─┘ │  │
      │  └─────┘  │
      └───────────┘
      ENGINSEER""",
    "servitor": """\
      ┌───────────┐
      │  ┌─────┐  │
      │  │ □ □ │  │
      │  │ ─── │  │
      │  └──┬──┘  │
      │   ┌─┴─┐   │
      │   │███│   │
      │   │███│   │
      │ ┌─┤███├─┐ │
      │ │▒│   │▒│ │
      │ │▒│   │▒│ │
      │ └─┤   ├─┘ │
      │   │   │   │
      │   └───┘   │
      └───────────┘
       SERVITOR""",
    "magos": """\
      ┌───────────┐
      │  ╔═╦═╦═╗  │
      │  ║ ◉ ▫ ║  │
      │  ║  ▬  ║  │
      │  ╚══╤══╝  │
      │ ┌───┴───┐ │
      │ │ ╬═══╬ │ │
      │╱│ ╬═══╬ │╲│
      ├─┤       ├─┤
      │⚙│ ┌───┐ │⚙│
      │⚙│ │ ⛨ │ │⚙│
      │ │ └───┘ │ │
      │ │╱╱   ╲╲│ │
      │ └───────┘ │
      └───────────┘
    MAGOS DOMINUS""",
    "rogue_trader": """\
      ┌───────────┐
      │   ╱═══╲   │
      │  │ ◆ ◆ │  │
      │  │  ▽  │  │
      │   ╲═╤═╱   │
      │  ┌──┴──┐  │
      │  │ ┌┐  │  │
      │  │ └┘  │  │
      ├──┤═════├──┤
      │▓▓│     │▓▓│
      │▓▓│ ┌─┐ │▓▓│
      │  │ │$│ │  │
      │  │ └─┘ │  │
      │  └─────┘  │
      └───────────┘
     ROGUE TRADER""",
    "guardsman": """\
      ┌───────────┐
      │  ┌──═──┐  │
      │  │ ● ● │  │
      │  │  ▬  │  │
      │  └──┬──┘  │
      │  ┌──┴──┐  │
      │  │▓▓▓▓▓│  │
      │  │▓ ╬ ▓│  │
      ├──┤▓▓▓▓▓├──┤
      │  │     │  │
      │  │ ┌─┐ │  │
      │  │ │║│ │  │
      │  │ │║│ │  │
      │  └─┘ └─┘  │
      └───────────┘
       GUARDSMAN""",
    "hive_noble": """\
      ┌───────────┐
      │   ╔═╦═╗   │
      │   ║◇ ◇║   │
      │   ║ ─ ║   │
      │   ╚═╤═╝   │
      │  ╱──┴──╲  │
      │ ╱ ┌───┐ ╲ │
      │╱  │ ♦ │  ╲│
      ├───┤   ├───┤
      │   │ ┌┐│   │
      │   │ └┘│   │
      │   │   │   │
      │   │   │   │
      │   └───┘   │
      └───────────┘
      HIVE NOBLE""",
    "mechanicus_adept": """\
      ┌───────────┐
      │  ╔══⚙══╗  │
      │  ║ ◉ ◎ ║  │
      │  ║  ▬  ║  │
      │  ╚══╤══╝  │
      │  ┌──┴──┐  │
      │ ╱│ ═══ │╲ │
      │╱ │ ═══ │ ╲│
      ├──┤     ├──┤
      │▒▒│ ┌─┐ │▒▒│
      │▒▒│ │⚙│ │▒▒│
      │  │ └─┘ │  │
      │  │     │  │
      │  └─────┘  │
      └───────────┘
       MECH-ADEPT""",
    "tech_assassin": """\
      ┌───────────┐
      │  ┌─────┐  │
      │  │ ▪ ▪ │  │
      │  │ ─── │  │
      │  └──┬──┘  │
      │   ╔═╧═╗   │
      │   ║   ║   │
      │  ╱║   ║╲  │
      ├─╱ ╚═══╝ ╲─┤
      │╱    │    ╲│
      │     │     │
      │    ╱ ╲    │
      │   ╱   ╲   │
      │  ╱     ╲  │
      └───────────┘
     TECH-ASSASSIN""",
    "cyber_cherub": """\
      ┌───────────┐
      │   ╱───╲   │
      │  │ o o │  │
      │  │  ^  │  │
      │   ╲─┬─╱   │
      │ ╱╲ ─┴─ ╱╲ │
      │╱  ╲   ╱  ╲│
      │    │ │    │
      │╲  ╱│ │╲  ╱│
      │ ╲╱ │ │ ╲╱ │
      │    │ │    │
      │    │ │    │
      │    └─┘    │
      │           │
      └───────────┘
     CYBER-CHERUB""",
    "pit_slave": """\
      ┌───────────┐
      │  ┌─────┐  │
      │  │ ■ ○ │  │
      │  │ ~~~ │  │
      │  └──┬──┘  │
      │  ┌──┴──┐  │
      │  │█████│  │
      │  │█████│  │
      │──┤█████├──│
      │▓▓│     │░░│
      │▓▓│     │░░│
      │▓▓│     │░░│
      │  │     │  │
      │  └─────┘  │
      └───────────┘
       PIT SLAVE""",
    "electro_priest": """\
      ┌───────────┐
      │  ╔═╤═╤═╗  │
      │  ║ ⚡⚡ ║  │
      │  ║  ▬  ║  │
      │  ╚══╤══╝  │
      │  ┌──┴──┐  │
      │  │░░░░░│  │
      │  │░ ╬ ░│  │
      ├──┤░░░░░├──┤
      │⚡│     │⚡│
      │⚡│     │⚡│
      │  │     │  │
      │  │     │  │
      │  └─────┘  │
      └───────────┘
    ELECTRO-PRIEST""",
}

# Mapping from descriptive keywords to template keys, used for auto-assignment.
_KEYWORD_MAP: dict[str, list[str]] = {
    "skitarii": ["skitarii"],
    "ranger": ["skitarii"],
    "vanguard": ["skitarii"],
    "enginseer": ["enginseer"],
    "servitor": ["servitor"],
    "magos": ["magos"],
    "dominus": ["magos"],
    "fabricator": ["magos"],
    "rogue": ["rogue_trader"],
    "trader": ["rogue_trader"],
    "guard": ["guardsman"],
    "soldier": ["guardsman"],
    "trooper": ["guardsman"],
    "noble": ["hive_noble"],
    "lord": ["hive_noble"],
    "aristocrat": ["hive_noble"],
    "adept": ["mechanicus_adept"],
    "tech-priest": ["mechanicus_adept"],
    "techpriest": ["mechanicus_adept"],
    "assassin": ["tech_assassin"],
    "operative": ["tech_assassin"],
    "cherub": ["cyber_cherub"],
    "slave": ["pit_slave"],
    "labourer": ["pit_slave"],
    "worker": ["pit_slave"],
    "priest": ["electro_priest"],
    "electro": ["electro_priest"],
    "fulgurite": ["electro_priest"],
    "corpuscarii": ["electro_priest"],
}


def _pick_template_for(name: str, description: str) -> str:
    """Pick a portrait template key based on an NPC's name and description.

    Scans both fields for keywords. Falls back to a random template if no
    keyword matches.
    """
    combined = (name + " " + description).lower()
    for keyword, template_keys in _KEYWORD_MAP.items():
        if keyword in combined:
            return random.choice(template_keys)
    # No keyword match -- pick a random template
    return random.choice(list(NPC_TEMPLATES.keys()))


class NPCPortraitStore:
    """Manages persistent NPC portrait assignments.

    Assigns template-based portraits to NPCs and persists the mapping
    to ``~/.local/share/angband-mechanicum/npc_portraits.json`` so that
    portraits are stable across sessions.
    """

    def __init__(self) -> None:
        self._assignments: dict[str, str] = {}  # entity_id -> template_key
        self._save_path: Path = _data_dir() / "npc_portraits.json"
        self._load()

    def _load(self) -> None:
        """Load persisted portrait assignments from disk."""
        if self._save_path.exists():
            try:
                with open(self._save_path, "r") as f:
                    data: dict[str, Any] = json.load(f)
                self._assignments = data.get("assignments", {})
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to load NPC portraits: %s", exc)
                self._assignments = {}

    def _save(self) -> None:
        """Persist current portrait assignments to disk."""
        try:
            with open(self._save_path, "w") as f:
                json.dump({"assignments": self._assignments}, f, indent=2)
        except OSError as exc:
            logger.warning("Failed to save NPC portraits: %s", exc)

    def get_portrait(self, entity_id: str) -> str | None:
        """Return the portrait art for an NPC, or None if not assigned."""
        template_key = self._assignments.get(entity_id)
        if template_key and template_key in NPC_TEMPLATES:
            return NPC_TEMPLATES[template_key]
        return None

    def assign_portrait(
        self,
        entity_id: str,
        name: str = "",
        description: str = "",
    ) -> str:
        """Assign a portrait to an NPC and return the art string.

        If the NPC already has a portrait, returns that. Otherwise picks
        a template based on name/description keywords and persists the
        assignment.
        """
        existing = self.get_portrait(entity_id)
        if existing is not None:
            return existing

        template_key = _pick_template_for(name, description)
        self._assignments[entity_id] = template_key
        self._save()
        return NPC_TEMPLATES[template_key]

    def has_portrait(self, entity_id: str) -> bool:
        """Check whether an NPC already has a portrait assigned."""
        return entity_id in self._assignments
