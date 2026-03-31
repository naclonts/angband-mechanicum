"""Dungeon item definitions and live item instances for map exploration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _humanize_item_id(item_id: str) -> str:
    return item_id.replace("_", " ").replace("-", " ").title()


@dataclass(frozen=True)
class DungeonItemDefinition:
    """Static item template metadata."""

    template_id: str
    display_name: str
    description: str
    glyph: str = "!"
    color: str = "#ffd700"
    use_kind: str | None = None
    use_amount: int = 0
    consumable: bool = False

    @property
    def usable(self) -> bool:
        return self.use_kind is not None


@dataclass
class DungeonItem:
    """A concrete item instance tracked by the dungeon session."""

    instance_id: str
    template_id: str
    display_name: str
    description: str
    glyph: str = "!"
    color: str = "#ffd700"
    use_kind: str | None = None
    use_amount: int = 0
    consumable: bool = False

    @property
    def usable(self) -> bool:
        return self.use_kind is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "instance_id": self.instance_id,
            "template_id": self.template_id,
            "display_name": self.display_name,
            "description": self.description,
            "glyph": self.glyph,
            "color": self.color,
            "use_kind": self.use_kind,
            "use_amount": self.use_amount,
            "consumable": self.consumable,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DungeonItem":
        return cls(
            instance_id=str(data["instance_id"]),
            template_id=str(data.get("template_id", data["instance_id"])),
            display_name=str(data.get("display_name", _humanize_item_id(str(data["instance_id"])))),
            description=str(data.get("description", "")),
            glyph=str(data.get("glyph", "!")),
            color=str(data.get("color", "#ffd700")),
            use_kind=str(data["use_kind"]) if data.get("use_kind") is not None else None,
            use_amount=int(data.get("use_amount", 0)),
            consumable=bool(data.get("consumable", False)),
        )


_ITEM_DEFINITIONS: dict[str, DungeonItemDefinition] = {
    "toolkit": DungeonItemDefinition(
        template_id="toolkit",
        display_name="Field Toolkit",
        description="Sacred tools and quick-seal unguents for emergency repairs.",
        use_kind="heal",
        use_amount=4,
        consumable=True,
    ),
    "field-kit": DungeonItemDefinition(
        template_id="field-kit",
        display_name="Field Kit",
        description="A compact kit of medicae patches and repair staples.",
        use_kind="heal",
        use_amount=4,
        consumable=True,
    ),
    "repair-kit": DungeonItemDefinition(
        template_id="repair-kit",
        display_name="Repair Kit",
        description="Spare cabling and blessed sealant for restoring damaged systems.",
        use_kind="heal",
        use_amount=5,
        consumable=True,
    ),
    "stimm-pack": DungeonItemDefinition(
        template_id="stimm-pack",
        display_name="Stimm Pack",
        description="A combat injector that keeps flesh and augmetics functioning.",
        use_kind="heal",
        use_amount=6,
        consumable=True,
    ),
    "sealant-foam": DungeonItemDefinition(
        template_id="sealant-foam",
        display_name="Sealant Foam",
        description="Rapid-curing foam for sealing breaches and stabilizing armor gaps.",
        use_kind="heal",
        use_amount=4,
        consumable=True,
    ),
}


def item_definition(template_id: str) -> DungeonItemDefinition:
    """Return the registered template or a sensible generic fallback."""
    if template_id in _ITEM_DEFINITIONS:
        return _ITEM_DEFINITIONS[template_id]
    return DungeonItemDefinition(
        template_id=template_id,
        display_name=_humanize_item_id(template_id),
        description=f"A recovered dungeon item: {_humanize_item_id(template_id)}.",
        glyph="*",
        color="#b8b8b8",
    )


def build_item_instance(template_id: str, *, instance_id: str) -> DungeonItem:
    """Instantiate a live dungeon item from a template ID."""
    definition = item_definition(template_id)
    return DungeonItem(
        instance_id=instance_id,
        template_id=definition.template_id,
        display_name=definition.display_name,
        description=definition.description,
        glyph=definition.glyph,
        color=definition.color,
        use_kind=definition.use_kind,
        use_amount=definition.use_amount,
        consumable=definition.consumable,
    )

