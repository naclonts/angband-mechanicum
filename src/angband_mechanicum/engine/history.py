"""History and entity tracking system for structured game memory.

Provides step-by-step history, entity registries (places, characters, items),
cross-references between steps and entities, and context construction for LLM agents.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EntityType(Enum):
    PLACE = "place"
    CHARACTER = "character"
    ITEM = "item"


@dataclass
class Entity:
    id: str
    name: str
    type: EntityType
    description: str
    step_ids: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type.value,
            "description": self.description,
            "step_ids": list(self.step_ids),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Entity:
        return cls(
            id=data["id"],
            name=data["name"],
            type=EntityType(data["type"]),
            description=data["description"],
            step_ids=data.get("step_ids", []),
        )


@dataclass
class Step:
    step_number: int
    player_input: str
    narrative_text: str
    entity_ids: list[str] = field(default_factory=list)
    info_update: dict[str, str] | None = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_number": self.step_number,
            "player_input": self.player_input,
            "narrative_text": self.narrative_text,
            "entity_ids": list(self.entity_ids),
            "info_update": self.info_update,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Step:
        return cls(
            step_number=data["step_number"],
            player_input=data["player_input"],
            narrative_text=data["narrative_text"],
            entity_ids=data.get("entity_ids", []),
            info_update=data.get("info_update"),
            timestamp=data.get("timestamp", 0.0),
        )


def _slugify(name: str) -> str:
    """Convert a name to a URL-safe slug for use as an entity ID."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug


class GameHistory:
    """Manages step history and entity registries for structured game memory.

    Tracks every player turn as a Step with full interaction data, maintains
    indexed registries for places/characters/items, and provides context
    construction APIs for LLM agents.
    """

    def __init__(self) -> None:
        self._steps: list[Step] = []
        self._entities: dict[str, Entity] = {}  # id -> Entity
        self._name_index: dict[str, str] = {}  # normalized name -> id

    @property
    def step_count(self) -> int:
        return len(self._steps)

    @property
    def entities(self) -> dict[str, Entity]:
        return dict(self._entities)

    def get_step(self, step_number: int) -> Step | None:
        """Get a step by its 1-based step number."""
        if 0 < step_number <= len(self._steps):
            return self._steps[step_number - 1]
        return None

    def _normalize_name(self, name: str) -> str:
        return name.lower().strip()

    def _generate_id(self, name: str) -> str:
        """Generate a unique slug ID from a name."""
        base = _slugify(name)
        if not base:
            base = "entity"
        if base not in self._entities:
            return base
        counter = 2
        while f"{base}-{counter}" in self._entities:
            counter += 1
        return f"{base}-{counter}"

    def register_entity(
        self,
        name: str,
        entity_type: EntityType,
        description: str,
    ) -> Entity:
        """Register a new entity or return existing one if name matches.

        If an entity with the same normalized name already exists, updates its
        description (if non-empty) and returns it. Otherwise creates a new entity
        with a generated slug ID.
        """
        normalized = self._normalize_name(name)
        if normalized in self._name_index:
            existing = self._entities[self._name_index[normalized]]
            if description:
                existing.description = description
            return existing

        entity_id = self._generate_id(name)
        entity = Entity(
            id=entity_id,
            name=name,
            type=entity_type,
            description=description,
        )
        self._entities[entity_id] = entity
        self._name_index[normalized] = entity_id
        return entity

    def get_entity(self, entity_id: str) -> Entity | None:
        """Look up an entity by ID."""
        return self._entities.get(entity_id)

    def add_step(
        self,
        player_input: str,
        narrative_text: str,
        entity_ids: list[str],
        info_update: dict[str, str] | None = None,
    ) -> Step:
        """Record a new step and cross-reference it with entities."""
        step_number = len(self._steps) + 1
        step = Step(
            step_number=step_number,
            player_input=player_input,
            narrative_text=narrative_text,
            entity_ids=entity_ids,
            info_update=info_update,
        )
        self._steps.append(step)

        for eid in entity_ids:
            entity = self._entities.get(eid)
            if entity:
                entity.step_ids.append(step_number)

        return step

    def get_entity_chain(self, entity_id: str) -> list[Step]:
        """Get all steps involving an entity, in chronological order."""
        entity = self._entities.get(entity_id)
        if not entity:
            return []
        return [
            self._steps[sn - 1]
            for sn in entity.step_ids
            if 0 < sn <= len(self._steps)
        ]

    def get_related_entities(self, entity_id: str) -> set[str]:
        """Get entity IDs that co-occur with the given entity in any step."""
        chain = self.get_entity_chain(entity_id)
        related: set[str] = set()
        for step in chain:
            related.update(step.entity_ids)
        related.discard(entity_id)
        return related

    def get_entity_context(self, entity_id: str, max_steps: int = 5) -> str:
        """Build an LLM-ready context summary for an entity.

        Returns a markdown-formatted block with the entity's description,
        recent interaction history, and related entities. Suitable for
        injection into an LLM system prompt or context window.
        """
        entity = self._entities.get(entity_id)
        if not entity:
            return ""

        lines: list[str] = [
            f"## {entity.name} ({entity.type.value})",
            entity.description,
            "",
        ]

        chain = self.get_entity_chain(entity_id)
        if chain:
            recent = chain[-max_steps:]
            lines.append("### Recent interactions:")
            for step in recent:
                preview = step.narrative_text[:200]
                if len(step.narrative_text) > 200:
                    preview += "..."
                lines.append(
                    f"- Step {step.step_number}: "
                    f'Player: "{step.player_input}" -> {preview}'
                )
            lines.append("")

        related_ids = self.get_related_entities(entity_id)
        if related_ids:
            lines.append("### Related entities:")
            for rid in sorted(related_ids):
                rel = self._entities.get(rid)
                if rel:
                    lines.append(f"- {rel.id} ({rel.type.value}): {rel.name}")

        return "\n".join(lines)

    def get_registry_context(self) -> str:
        """Build a compact entity registry for injection into the LLM system prompt.

        Returns a formatted block listing all known entities by type, with IDs
        and names. Includes instructions for the LLM on how to reference entities.
        """
        if not self._entities:
            return ""

        by_type: dict[EntityType, list[Entity]] = {}
        for entity in self._entities.values():
            by_type.setdefault(entity.type, []).append(entity)

        lines: list[str] = ["## Known Entities"]
        for etype in EntityType:
            entities = by_type.get(etype, [])
            if entities:
                entries = ", ".join(f'{e.id} ("{e.name}")' for e in entities)
                lines.append(f"**{etype.value.title()}s:** {entries}")

        lines.append("")
        lines.append(
            "Reference known entities by their id. "
            "For new entities not in this list, provide name, type, and description."
        )
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        """Serialize full history state for saving."""
        return {
            "steps": [s.to_dict() for s in self._steps],
            "entities": {eid: e.to_dict() for eid, e in self._entities.items()},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GameHistory:
        """Restore history state from a saved dict."""
        history = cls()
        for step_data in data.get("steps", []):
            history._steps.append(Step.from_dict(step_data))
        for eid, entity_data in data.get("entities", {}).items():
            entity = Entity.from_dict(entity_data)
            history._entities[eid] = entity
            history._name_index[history._normalize_name(entity.name)] = eid
        return history
