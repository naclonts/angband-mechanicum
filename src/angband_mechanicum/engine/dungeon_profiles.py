"""Structured dungeon-generation profiles shared by story, travel, and saves."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from angband_mechanicum.engine.story_starts import StoryStart


@dataclass(frozen=True)
class DungeonGenerationProfile:
    """Canonical dungeon-generation inputs for a session or story start."""

    environment: str
    profile_id: str | None = None
    location_name: str | None = None
    hostile_tags: tuple[str, ...] = ()
    friendly_tags: tuple[str, ...] = ()
    neutral_tags: tuple[str, ...] = ()
    preferred_themed_room_tags: tuple[str, ...] = ()
    required_themed_room_names: tuple[str, ...] = ()
    excluded_contact_tags: tuple[str, ...] = ()
    excluded_contact_names: tuple[str, ...] = ()
    excluded_themed_room_names: tuple[str, ...] = ()
    excluded_themed_room_tags: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "environment": self.environment,
            "profile_id": self.profile_id,
            "location_name": self.location_name,
            "hostile_tags": list(self.hostile_tags),
            "friendly_tags": list(self.friendly_tags),
            "neutral_tags": list(self.neutral_tags),
            "preferred_themed_room_tags": list(self.preferred_themed_room_tags),
            "required_themed_room_names": list(self.required_themed_room_names),
            "excluded_contact_tags": list(self.excluded_contact_tags),
            "excluded_contact_names": list(self.excluded_contact_names),
            "excluded_themed_room_names": list(self.excluded_themed_room_names),
            "excluded_themed_room_tags": list(self.excluded_themed_room_tags),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "DungeonGenerationProfile | None":
        if not data:
            return None
        return cls(
            environment=str(data.get("environment", "forge")),
            profile_id=data.get("profile_id"),
            location_name=data.get("location_name"),
            hostile_tags=tuple(str(tag) for tag in data.get("hostile_tags", [])),
            friendly_tags=tuple(str(tag) for tag in data.get("friendly_tags", [])),
            neutral_tags=tuple(str(tag) for tag in data.get("neutral_tags", [])),
            preferred_themed_room_tags=tuple(
                str(tag) for tag in data.get("preferred_themed_room_tags", [])
            ),
            required_themed_room_names=tuple(
                str(name) for name in data.get("required_themed_room_names", [])
            ),
            excluded_contact_tags=tuple(
                str(tag) for tag in data.get("excluded_contact_tags", [])
            ),
            excluded_contact_names=tuple(
                str(name) for name in data.get("excluded_contact_names", [])
            ),
            excluded_themed_room_names=tuple(
                str(name) for name in data.get("excluded_themed_room_names", [])
            ),
            excluded_themed_room_tags=tuple(
                str(tag) for tag in data.get("excluded_themed_room_tags", [])
            ),
        )


_STORY_PROFILE_OVERRIDES: dict[str, DungeonGenerationProfile] = {
    "silent-forge": DungeonGenerationProfile(
        environment="forge",
        profile_id="story:silent-forge",
        preferred_themed_room_tags=("machine_cult", "forge"),
    ),
    "xenos-incursion": DungeonGenerationProfile(
        environment="manufactorum",
        profile_id="story:xenos-incursion",
        hostile_tags=("bioform", "tyranid"),
        excluded_contact_tags=("clerk",),
    ),
    "space-hulk": DungeonGenerationProfile(
        environment="voidship",
        profile_id="story:space-hulk",
        hostile_tags=("boarding", "void", "predator"),
        preferred_themed_room_tags=("breach", "boarding"),
    ),
    "chaos-incursion": DungeonGenerationProfile(
        environment="corrupted",
        profile_id="story:chaos-incursion",
        hostile_tags=("warp", "daemon", "cult", "heretek"),
        preferred_themed_room_tags=("warp", "ritual"),
    ),
    "necron-tomb": DungeonGenerationProfile(
        environment="tomb",
        profile_id="story:necron-tomb",
        hostile_tags=("necron", "tomb"),
        preferred_themed_room_tags=("necron", "reliquary"),
        excluded_contact_tags=("clerk", "gang"),
    ),
    "titan-recovery": DungeonGenerationProfile(
        environment="ash_dune_outpost",
        profile_id="story:titan-recovery",
        hostile_tags=("ork", "loota", "scavenger", "ash"),
        neutral_tags=("surveyor", "survivor", "reclaimator"),
        preferred_themed_room_tags=("titan", "wreck", "ork"),
        required_themed_room_names=("Titan Hull Breach",),
        excluded_contact_tags=("clerk", "scribe"),
        excluded_themed_room_tags=("chapel", "vault"),
    ),
    "stc-fragment": DungeonGenerationProfile(
        environment="data_vault",
        profile_id="story:stc-fragment",
        hostile_tags=("vault", "intruder", "saboteur"),
        preferred_themed_room_tags=("vault", "stc"),
    ),
    "daemon-forge": DungeonGenerationProfile(
        environment="corrupted",
        profile_id="story:daemon-forge",
        hostile_tags=("warp", "daemon", "heretek", "machine_cult"),
        preferred_themed_room_tags=("warp", "machine_cult"),
    ),
    "hive-depths": DungeonGenerationProfile(
        environment="hive",
        profile_id="story:hive-depths",
        hostile_tags=("gang", "underhive", "criminal", "mutant"),
        preferred_themed_room_tags=("underhive",),
    ),
    "explorator-mission": DungeonGenerationProfile(
        environment="forge",
        profile_id="story:explorator-mission",
        hostile_tags=("forge", "custodian", "raider"),
        preferred_themed_room_tags=("forge",),
    ),
}


def build_story_dungeon_profile(story_start: "StoryStart | None") -> DungeonGenerationProfile:
    """Return the explicit dungeon profile for a curated story start."""
    if story_start is None:
        return DungeonGenerationProfile(environment="forge", profile_id="story:default")

    override = _STORY_PROFILE_OVERRIDES.get(story_start.id)
    if override is not None:
        return DungeonGenerationProfile(
            environment=override.environment,
            profile_id=override.profile_id,
            location_name=story_start.location,
            hostile_tags=override.hostile_tags,
            friendly_tags=override.friendly_tags,
            neutral_tags=override.neutral_tags,
            preferred_themed_room_tags=override.preferred_themed_room_tags,
            required_themed_room_names=override.required_themed_room_names,
            excluded_contact_tags=override.excluded_contact_tags,
            excluded_contact_names=override.excluded_contact_names,
            excluded_themed_room_names=override.excluded_themed_room_names,
            excluded_themed_room_tags=override.excluded_themed_room_tags,
        )

    text = " ".join(
        (
            story_start.id,
            story_start.title,
            story_start.description,
            story_start.location,
        )
    ).lower()
    if any(keyword in text for keyword in ("space hulk", "void", "breach")):
        environment = "voidship"
    elif any(keyword in text for keyword in ("ash", "waste", "dune")):
        environment = "ash_dune_outpost"
    elif any(keyword in text for keyword in ("tomb", "necron", "crypt")):
        environment = "tomb"
    elif any(keyword in text for keyword in ("hive", "underhive")):
        environment = "hive"
    elif any(keyword in text for keyword in ("vault", "stc", "archive")):
        environment = "data_vault"
    elif any(keyword in text for keyword in ("warp", "daemon", "heretek", "corrupt")):
        environment = "corrupted"
    elif any(keyword in text for keyword in ("manufactorum", "factory")):
        environment = "manufactorum"
    else:
        environment = "forge"
    return DungeonGenerationProfile(
        environment=environment,
        profile_id=f"story:{story_start.id}",
        location_name=story_start.location,
    )


def build_travel_dungeon_profile(
    *,
    environment: str,
    location_name: str,
) -> DungeonGenerationProfile:
    """Build the canonical dungeon profile for a travel destination."""
    return DungeonGenerationProfile(
        environment=environment,
        profile_id=f"travel:{environment}",
        location_name=location_name,
    )
