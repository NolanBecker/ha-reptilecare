"""Individual reptile models, serialization, and repository."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import date
from enum import StrEnum
import math
import re
from types import MappingProxyType
from typing import Any, Protocol
from uuid import UUID

from .species import SpeciesProfileRegistry

REPTILE_SCHEMA_VERSION = 1
_SLUG = re.compile(r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$")
_OVERRIDE_KEY = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)*$")

type ReptileOverrideValue = str | int | float | bool | None


class ReptileError(Exception):
    """Base exception for reptile operations."""


class InvalidReptileError(ReptileError, ValueError):
    """Raised when a reptile definition is invalid."""


class DuplicateReptileError(ReptileError):
    """Raised when a reptile identifier is already registered."""


class ReptileNotFoundError(ReptileError, LookupError):
    """Raised when a requested reptile is not registered."""


class UnknownSpeciesProfileError(ReptileError, LookupError):
    """Raised when a reptile references an unknown SpeciesProfile."""


class DuplicateReptileSlugError(ReptileError):
    """Raised when a reptile slug is already registered."""


class ReptileSex(StrEnum):
    """Keeper-recorded sex of an individual reptile."""

    FEMALE = "female"
    MALE = "male"
    UNKNOWN = "unknown"


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not (normalized := value.strip()):
        raise InvalidReptileError(f"{name} must be a non-empty string")
    return normalized


def _optional_text(value: object, name: str) -> str | None:
    return None if value is None else _text(value, name)


@dataclass(frozen=True, slots=True)
class ReptileOverrides:
    """Immutable keeper-specific values overriding SpeciesProfile guidance.

    Keys identify future recommendation or configuration values. Missing keys
    inherit from the referenced SpeciesProfile; the override never mutates the
    profile itself.
    """

    values: Mapping[str, ReptileOverrideValue] = field(
        default_factory=lambda: MappingProxyType({})
    )

    def __post_init__(self) -> None:
        if not isinstance(self.values, Mapping):
            raise InvalidReptileError("overrides must be an object")
        normalized: dict[str, ReptileOverrideValue] = {}
        for raw_key, value in self.values.items():
            key = _text(raw_key, "override key")
            if _OVERRIDE_KEY.fullmatch(key) is None:
                raise InvalidReptileError(
                    "override keys must be lowercase dotted identifiers"
                )
            if isinstance(value, float) and not math.isfinite(value):
                raise InvalidReptileError("override numbers must be finite")
            if value is not None and not isinstance(value, (str, int, float, bool)):
                raise InvalidReptileError("override values must be JSON scalars")
            normalized[key] = value
        object.__setattr__(self, "values", MappingProxyType(normalized))


@dataclass(frozen=True, slots=True)
class Reptile:
    """Immutable keeper-owned record for one individual reptile."""

    reptile_id: str
    display_name: str
    species_profile_id: str
    slug: str | None = None
    morph: str | None = None
    sex: ReptileSex | None = None
    hatch_date: date | None = None
    acquired_date: date | None = None
    photo_reference: str | None = None
    notes: str | None = None
    enabled: bool = True
    enclosure_id: str | None = None
    overrides: ReptileOverrides = field(default_factory=ReptileOverrides)

    def __post_init__(self) -> None:
        reptile_id = _text(self.reptile_id, "reptile_id")
        try:
            UUID(reptile_id)
        except ValueError as err:
            raise InvalidReptileError("reptile_id must be a UUID") from err
        species_profile_id = _text(self.species_profile_id, "species_profile_id")
        slug = _optional_text(self.slug, "slug")
        if slug is not None and _SLUG.fullmatch(slug) is None:
            raise InvalidReptileError(
                "slug must contain only lowercase letters, numbers, "
                "hyphens, or underscores"
            )
        if self.sex is not None:
            try:
                sex = ReptileSex(self.sex)
            except (TypeError, ValueError) as err:
                raise InvalidReptileError("sex is invalid") from err
        else:
            sex = None
        for name in ("hatch_date", "acquired_date"):
            value = getattr(self, name)
            if value is not None and type(value) is not date:
                raise InvalidReptileError(f"{name} must be a date")
        if not isinstance(self.enabled, bool):
            raise InvalidReptileError("enabled must be a boolean")
        if not isinstance(self.overrides, ReptileOverrides):
            raise InvalidReptileError("overrides has an invalid type")

        object.__setattr__(self, "reptile_id", reptile_id)
        object.__setattr__(self, "slug", slug)
        object.__setattr__(
            self, "display_name", _text(self.display_name, "display_name")
        )
        object.__setattr__(self, "species_profile_id", species_profile_id)
        object.__setattr__(self, "morph", _optional_text(self.morph, "morph"))
        object.__setattr__(self, "sex", sex)
        object.__setattr__(
            self,
            "photo_reference",
            _optional_text(self.photo_reference, "photo_reference"),
        )
        object.__setattr__(self, "notes", _optional_text(self.notes, "notes"))
        object.__setattr__(
            self, "enclosure_id", _optional_text(self.enclosure_id, "enclosure_id")
        )


class ReptilePersistence(Protocol):
    """Async persistence boundary used by ReptileRepository."""

    async def async_load(self) -> tuple[Reptile, ...]:
        """Load persisted reptiles."""
        ...

    async def async_save(self, reptiles: tuple[Reptile, ...]) -> None:
        """Persist the complete reptile collection."""
        ...


class ReptileRepository:
    """Validated async repository for keeper-owned reptile records."""

    def __init__(
        self,
        species_profiles: SpeciesProfileRegistry,
        persistence: ReptilePersistence,
    ) -> None:
        """Initialize an unloaded repository."""
        self._species_profiles = species_profiles
        self._persistence = persistence
        self._reptiles: Mapping[str, Reptile] = MappingProxyType({})
        self._slugs: Mapping[str, str] = MappingProxyType({})
        self._write_lock = asyncio.Lock()

    async def async_load(self) -> None:
        """Load and validate all persisted reptiles."""
        reptiles = await self._persistence.async_load()
        self._publish(reptiles)

    async def async_add(self, reptile: Reptile) -> None:
        """Add and persist a new reptile."""
        async with self._write_lock:
            if reptile.reptile_id in self._reptiles:
                raise DuplicateReptileError(
                    f"duplicate reptile ID: {reptile.reptile_id}"
                )
            self._validate_profile(reptile)
            await self._save((*self._reptiles.values(), reptile))

    async def async_update(self, reptile: Reptile) -> None:
        """Replace and persist an existing reptile with the same permanent ID."""
        async with self._write_lock:
            if reptile.reptile_id not in self._reptiles:
                raise ReptileNotFoundError(f"reptile not found: {reptile.reptile_id}")
            self._validate_profile(reptile)
            updated = dict(self._reptiles)
            updated[reptile.reptile_id] = reptile
            await self._save(tuple(updated.values()))

    async def async_remove(self, reptile_id: str) -> Reptile:
        """Remove a reptile record without touching its historical CareEvents."""
        async with self._write_lock:
            reptile = self.get(reptile_id)
            updated = dict(self._reptiles)
            del updated[reptile.reptile_id]
            await self._save(tuple(updated.values()))
            return reptile

    async def async_enable(self, reptile_id: str) -> None:
        """Enable an existing reptile."""
        await self.async_update(replace(self.get(reptile_id), enabled=True))

    async def async_disable(self, reptile_id: str) -> None:
        """Disable an existing reptile as the preferred archival strategy."""
        await self.async_update(replace(self.get(reptile_id), enabled=False))

    def get(self, reptile_id: str) -> Reptile:
        """Return one reptile by permanent identifier."""
        try:
            return self._reptiles[reptile_id]
        except KeyError as err:
            raise ReptileNotFoundError(f"reptile not found: {reptile_id}") from err

    def contains_slug(self, slug: str) -> bool:
        """Return whether a reptile slug is registered."""
        return slug in self._slugs

    def get_by_slug(self, slug: str) -> Reptile:
        """Return one reptile by its optional automation slug."""
        try:
            reptile_id = self._slugs[slug]
        except KeyError as err:
            raise ReptileNotFoundError(f"reptile slug not found: {slug}") from err
        return self._reptiles[reptile_id]

    def all(self, *, include_disabled: bool = True) -> tuple[Reptile, ...]:
        """List reptiles in deterministic identifier order."""
        reptiles = tuple(self._reptiles.values())
        if include_disabled:
            return reptiles
        return tuple(reptile for reptile in reptiles if reptile.enabled)

    async def _save(self, reptiles: tuple[Reptile, ...]) -> None:
        """Persist then publish a validated replacement collection."""
        validated, _ = self._validated_state(reptiles)
        ordered = tuple(validated.values())
        await self._persistence.async_save(ordered)
        self._publish(ordered)

    def _publish(self, reptiles: tuple[Reptile, ...]) -> None:
        """Publish validated reptile and slug indexes together."""
        self._reptiles, self._slugs = self._validated_state(reptiles)

    def _validated_state(
        self, reptiles: tuple[Reptile, ...]
    ) -> tuple[Mapping[str, Reptile], Mapping[str, str]]:
        """Validate and deterministically index reptile and slug mappings."""
        indexed: dict[str, Reptile] = {}
        slugs: dict[str, str] = {}
        for reptile in reptiles:
            if not isinstance(reptile, Reptile):
                raise InvalidReptileError("repository values must be Reptile instances")
            if reptile.reptile_id in indexed:
                raise DuplicateReptileError(
                    f"duplicate reptile ID: {reptile.reptile_id}"
                )
            self._validate_profile(reptile)
            indexed[reptile.reptile_id] = reptile
            if reptile.slug is not None:
                if reptile.slug in slugs:
                    raise DuplicateReptileSlugError(
                        f"duplicate reptile slug: {reptile.slug}"
                    )
                slugs[reptile.slug] = reptile.reptile_id
        return (
            MappingProxyType(dict(sorted(indexed.items()))),
            MappingProxyType(dict(sorted(slugs.items()))),
        )

    def _validate_profile(self, reptile: Reptile) -> None:
        """Ensure the referenced SpeciesProfile is registered."""
        if not self._species_profiles.contains(reptile.species_profile_id):
            raise UnknownSpeciesProfileError(
                f"unknown species profile: {reptile.species_profile_id}"
            )


def reptile_to_dict(reptile: Reptile) -> dict[str, Any]:
    """Serialize a Reptile to explicit JSON-compatible values."""
    return {
        "reptile_id": reptile.reptile_id,
        "slug": reptile.slug,
        "display_name": reptile.display_name,
        "species_profile_id": reptile.species_profile_id,
        "morph": reptile.morph,
        "sex": None if reptile.sex is None else reptile.sex.value,
        "hatch_date": _serialize_date(reptile.hatch_date),
        "acquired_date": _serialize_date(reptile.acquired_date),
        "photo_reference": reptile.photo_reference,
        "notes": reptile.notes,
        "enabled": reptile.enabled,
        "enclosure_id": reptile.enclosure_id,
        "overrides": dict(reptile.overrides.values),
    }


def reptile_from_dict(value: Mapping[str, Any]) -> Reptile:
    """Deserialize and strictly validate a serialized Reptile."""
    required = {
        "reptile_id",
        "slug",
        "display_name",
        "species_profile_id",
        "morph",
        "sex",
        "hatch_date",
        "acquired_date",
        "photo_reference",
        "notes",
        "enabled",
        "enclosure_id",
        "overrides",
    }
    if not all(isinstance(key, str) for key in value):
        raise InvalidReptileError("reptile keys must be strings")
    if set(value) != required:
        missing = required - set(value)
        unknown = set(value) - required
        detail = ", ".join(sorted(missing or unknown))
        kind = "missing" if missing else "unknown"
        raise InvalidReptileError(f"reptile contains {kind} keys: {detail}")
    overrides = value["overrides"]
    if not isinstance(overrides, Mapping):
        raise InvalidReptileError("overrides must be an object")
    return Reptile(
        reptile_id=value["reptile_id"],
        slug=value["slug"],
        display_name=value["display_name"],
        species_profile_id=value["species_profile_id"],
        morph=value["morph"],
        sex=value["sex"],
        hatch_date=_deserialize_date(value["hatch_date"], "hatch_date"),
        acquired_date=_deserialize_date(value["acquired_date"], "acquired_date"),
        photo_reference=value["photo_reference"],
        notes=value["notes"],
        enabled=value["enabled"],
        enclosure_id=value["enclosure_id"],
        overrides=ReptileOverrides(overrides),
    )


def _serialize_date(value: date | None) -> str | None:
    return None if value is None else value.isoformat()


def _deserialize_date(value: object, name: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidReptileError(f"{name} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as err:
        raise InvalidReptileError(f"{name} must be an ISO date") from err


class MemoryReptilePersistence:
    """In-memory persistence adapter for domain tests and development."""

    def __init__(self, reptiles: tuple[Reptile, ...] = ()) -> None:
        """Initialize with an immutable reptile collection."""
        self.reptiles = tuple(reptiles)

    async def async_load(self) -> tuple[Reptile, ...]:
        """Return the current in-memory collection."""
        return self.reptiles

    async def async_save(self, reptiles: tuple[Reptile, ...]) -> None:
        """Replace the in-memory collection."""
        self.reptiles = tuple(reptiles)
