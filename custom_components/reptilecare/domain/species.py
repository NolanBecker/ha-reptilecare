"""Species profile domain models, serialization, and registry."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from importlib.resources import files
from importlib.resources.abc import Traversable
import json
import math
import re
from types import MappingProxyType
from typing import Any, Self
from urllib.parse import urlparse

SPECIES_PROFILE_SCHEMA_VERSION = 1
BUILTIN_PROFILE_PACKAGE = "custom_components.reptilecare.profiles"
_NAMESPACED_ID = re.compile(r"^[a-z][a-z0-9_]*:[a-z0-9_]+$")
_LOCAL_ID = re.compile(r"^[a-z][a-z0-9_]*$")


class SpeciesProfileError(Exception):
    """Base exception for species profile operations."""


class InvalidSpeciesProfileError(SpeciesProfileError, ValueError):
    """Raised when a species profile is malformed or unsupported."""


class DuplicateSpeciesProfileError(SpeciesProfileError):
    """Raised for duplicate profile identifiers."""


class SpeciesProfileNotFoundError(SpeciesProfileError, LookupError):
    """Raised when a requested profile is not registered."""


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not (normalized := value.strip()):
        raise InvalidSpeciesProfileError(f"{name} must be a non-empty string")
    return normalized


def _optional_text(value: object, name: str) -> str | None:
    return None if value is None else _text(value, name)


def _number(value: object, name: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidSpeciesProfileError(f"{name} must be a number")
    if not math.isfinite(value):
        raise InvalidSpeciesProfileError(f"{name} must be finite")
    return value


@dataclass(frozen=True, slots=True)
class EnvironmentalTarget:
    """A generic recommended range for one environmental measurement."""

    target_id: str
    display_name: str
    minimum: int | float
    maximum: int | float
    unit: str
    warning_minimum: int | float | None = None
    warning_maximum: int | float | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        target_id = _text(self.target_id, "target_id")
        if _LOCAL_ID.fullmatch(target_id) is None:
            raise InvalidSpeciesProfileError("target_id must be a lowercase identifier")
        minimum = _number(self.minimum, "minimum")
        maximum = _number(self.maximum, "maximum")
        if minimum > maximum:
            raise InvalidSpeciesProfileError("minimum must not exceed maximum")
        warning_minimum = (
            None
            if self.warning_minimum is None
            else _number(self.warning_minimum, "warning_minimum")
        )
        warning_maximum = (
            None
            if self.warning_maximum is None
            else _number(self.warning_maximum, "warning_maximum")
        )
        if warning_minimum is not None and warning_minimum > minimum:
            raise InvalidSpeciesProfileError("warning_minimum must not exceed minimum")
        if warning_maximum is not None and warning_maximum < maximum:
            raise InvalidSpeciesProfileError(
                "warning_maximum must not be below maximum"
            )
        object.__setattr__(self, "target_id", target_id)
        object.__setattr__(
            self, "display_name", _text(self.display_name, "display_name")
        )
        object.__setattr__(self, "minimum", minimum)
        object.__setattr__(self, "maximum", maximum)
        object.__setattr__(self, "unit", _text(self.unit, "unit"))
        object.__setattr__(self, "warning_minimum", warning_minimum)
        object.__setattr__(self, "warning_maximum", warning_maximum)
        object.__setattr__(self, "notes", _optional_text(self.notes, "notes"))


@dataclass(frozen=True, slots=True)
class EnvironmentalTargets:
    """An immutable, deterministically ordered collection of targets."""

    targets: tuple[EnvironmentalTarget, ...] = ()

    def __post_init__(self) -> None:
        targets = tuple(self.targets)
        if not all(isinstance(item, EnvironmentalTarget) for item in targets):
            raise InvalidSpeciesProfileError(
                "environmental targets contain invalid values"
            )
        identifiers = [item.target_id for item in targets]
        if len(identifiers) != len(set(identifiers)):
            raise InvalidSpeciesProfileError("environmental target IDs must be unique")
        object.__setattr__(
            self, "targets", tuple(sorted(targets, key=lambda item: item.target_id))
        )


@dataclass(frozen=True, slots=True)
class ProfileReference:
    """A source supporting information published in a species profile."""

    title: str
    publisher: str
    url: str
    publication_date: date | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        url = _text(self.url, "reference.url")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise InvalidSpeciesProfileError(
                "reference.url must be an absolute HTTP(S) URL"
            )
        if self.publication_date is not None and not isinstance(
            self.publication_date, date
        ):
            raise InvalidSpeciesProfileError(
                "reference.publication_date must be a date"
            )
        object.__setattr__(self, "title", _text(self.title, "reference.title"))
        object.__setattr__(
            self, "publisher", _text(self.publisher, "reference.publisher")
        )
        object.__setattr__(self, "url", url)
        object.__setattr__(self, "notes", _optional_text(self.notes, "reference.notes"))


@dataclass(frozen=True, slots=True)
class SpeciesProfile:
    """Versioned, reusable defaults for a reptile species."""

    profile_id: str
    display_name: str
    scientific_name: str
    category: str
    description: str
    default_environmental_targets: EnvironmentalTargets = field(
        default_factory=EnvironmentalTargets
    )
    default_task_template_ids: tuple[str, ...] = ()
    references: tuple[ProfileReference, ...] = ()
    schema_version: int = SPECIES_PROFILE_SCHEMA_VERSION
    profile_version: int = 1

    def __post_init__(self) -> None:
        profile_id = _text(self.profile_id, "profile_id")
        if _NAMESPACED_ID.fullmatch(profile_id) is None:
            raise InvalidSpeciesProfileError(
                "profile_id must be a lowercase namespaced identifier"
            )
        for name, value in (
            ("schema_version", self.schema_version),
            ("profile_version", self.profile_version),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise InvalidSpeciesProfileError(f"{name} must be a positive integer")
        if not isinstance(self.default_environmental_targets, EnvironmentalTargets):
            raise InvalidSpeciesProfileError(
                "default_environmental_targets has an invalid type"
            )
        template_ids = tuple(
            _text(item, "task template ID") for item in self.default_task_template_ids
        )
        if any(_NAMESPACED_ID.fullmatch(item) is None for item in template_ids):
            raise InvalidSpeciesProfileError(
                "task template IDs must be namespaced identifiers"
            )
        if len(template_ids) != len(set(template_ids)):
            raise InvalidSpeciesProfileError("task template IDs must be unique")
        references = tuple(self.references)
        if not all(isinstance(item, ProfileReference) for item in references):
            raise InvalidSpeciesProfileError("references contain invalid values")
        object.__setattr__(self, "profile_id", profile_id)
        for name in ("display_name", "scientific_name", "category", "description"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "default_task_template_ids", template_ids)
        object.__setattr__(self, "references", references)


_PROFILE_KEYS = frozenset(
    {
        "profile_id",
        "display_name",
        "scientific_name",
        "category",
        "description",
        "default_environmental_targets",
        "default_task_template_ids",
        "references",
        "schema_version",
        "profile_version",
    }
)
_TARGET_REQUIRED = frozenset(
    {"target_id", "display_name", "minimum", "maximum", "unit"}
)
_TARGET_OPTIONAL = frozenset({"warning_minimum", "warning_maximum", "notes"})
_REFERENCE_REQUIRED = frozenset({"title", "publisher", "url"})
_REFERENCE_OPTIONAL = frozenset({"publication_date", "notes"})


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise InvalidSpeciesProfileError(f"{name} must be an object")
    return value


def _array(value: object, name: str) -> Sequence[Any]:
    if not isinstance(value, (list, tuple)):
        raise InvalidSpeciesProfileError(f"{name} must be an array")
    return value


def _keys(
    value: Mapping[str, Any],
    required: frozenset[str],
    optional: frozenset[str],
    name: str,
) -> None:
    if missing := required - set(value):
        raise InvalidSpeciesProfileError(
            f"{name} is missing keys: {', '.join(sorted(missing))}"
        )
    if unknown := set(value) - required - optional:
        raise InvalidSpeciesProfileError(
            f"{name} contains unknown keys: {', '.join(sorted(unknown))}"
        )


def species_profile_to_dict(profile: SpeciesProfile) -> dict[str, Any]:
    """Serialize a species profile to JSON-compatible values."""
    targets = []
    for target in profile.default_environmental_targets.targets:
        item: dict[str, Any] = {
            "target_id": target.target_id,
            "display_name": target.display_name,
            "minimum": target.minimum,
            "maximum": target.maximum,
            "unit": target.unit,
        }
        for name in ("warning_minimum", "warning_maximum", "notes"):
            if (value := getattr(target, name)) is not None:
                item[name] = value
        targets.append(item)
    references = []
    for reference in profile.references:
        item = {
            "title": reference.title,
            "publisher": reference.publisher,
            "url": reference.url,
        }
        if reference.publication_date is not None:
            item["publication_date"] = reference.publication_date.isoformat()
        if reference.notes is not None:
            item["notes"] = reference.notes
        references.append(item)
    return {
        "profile_id": profile.profile_id,
        "display_name": profile.display_name,
        "scientific_name": profile.scientific_name,
        "category": profile.category,
        "description": profile.description,
        "default_environmental_targets": targets,
        "default_task_template_ids": list(profile.default_task_template_ids),
        "references": references,
        "schema_version": profile.schema_version,
        "profile_version": profile.profile_version,
    }


def species_profile_from_dict(value: Mapping[str, Any]) -> SpeciesProfile:
    """Deserialize and strictly validate a species profile mapping."""
    data = _mapping(value, "species profile")
    _keys(data, _PROFILE_KEYS, frozenset(), "species profile")
    if data["schema_version"] != SPECIES_PROFILE_SCHEMA_VERSION:
        raise InvalidSpeciesProfileError(
            f"unsupported schema version: {data['schema_version']!r}"
        )
    targets = []
    for index, raw in enumerate(
        _array(data["default_environmental_targets"], "default_environmental_targets")
    ):
        item = _mapping(raw, f"environmental target {index}")
        _keys(item, _TARGET_REQUIRED, _TARGET_OPTIONAL, f"environmental target {index}")
        targets.append(
            EnvironmentalTarget(
                target_id=item["target_id"],
                display_name=item["display_name"],
                minimum=item["minimum"],
                maximum=item["maximum"],
                unit=item["unit"],
                warning_minimum=item.get("warning_minimum"),
                warning_maximum=item.get("warning_maximum"),
                notes=item.get("notes"),
            )
        )
    references = []
    for index, raw in enumerate(_array(data["references"], "references")):
        item = _mapping(raw, f"reference {index}")
        _keys(item, _REFERENCE_REQUIRED, _REFERENCE_OPTIONAL, f"reference {index}")
        raw_date = item.get("publication_date")
        if raw_date is not None:
            if not isinstance(raw_date, str):
                raise InvalidSpeciesProfileError(
                    f"reference {index}.publication_date must be an ISO date"
                )
            try:
                publication_date = date.fromisoformat(raw_date)
            except ValueError as err:
                raise InvalidSpeciesProfileError(
                    f"reference {index}.publication_date must be an ISO date"
                ) from err
        else:
            publication_date = None
        references.append(
            ProfileReference(
                title=item["title"],
                publisher=item["publisher"],
                url=item["url"],
                publication_date=publication_date,
                notes=item.get("notes"),
            )
        )
    return SpeciesProfile(
        profile_id=data["profile_id"],
        display_name=data["display_name"],
        scientific_name=data["scientific_name"],
        category=data["category"],
        description=data["description"],
        default_environmental_targets=EnvironmentalTargets(tuple(targets)),
        default_task_template_ids=tuple(
            _array(data["default_task_template_ids"], "default_task_template_ids")
        ),
        references=tuple(references),
        schema_version=data["schema_version"],
        profile_version=data["profile_version"],
    )


class SpeciesProfileRegistry:
    """Immutable lookup registry for validated species profiles."""

    def __init__(self, profiles: Iterable[SpeciesProfile] = ()) -> None:
        registered: dict[str, SpeciesProfile] = {}
        for profile in profiles:
            if not isinstance(profile, SpeciesProfile):
                raise InvalidSpeciesProfileError(
                    "registry values must be SpeciesProfile instances"
                )
            if profile.profile_id in registered:
                raise DuplicateSpeciesProfileError(
                    f"duplicate species profile ID: {profile.profile_id}"
                )
            registered[profile.profile_id] = profile
        self._profiles: Mapping[str, SpeciesProfile] = MappingProxyType(
            dict(sorted(registered.items()))
        )

    @classmethod
    def from_files(cls, profile_files: Iterable[Traversable]) -> Self:
        """Load profiles from JSON files."""
        profiles = []
        for profile_file in sorted(profile_files, key=lambda item: item.name):
            try:
                raw = json.loads(profile_file.read_text(encoding="utf-8"))
                profiles.append(
                    species_profile_from_dict(_mapping(raw, profile_file.name))
                )
            except (OSError, json.JSONDecodeError, SpeciesProfileError) as err:
                raise InvalidSpeciesProfileError(
                    f"unable to load {profile_file.name}: {err}"
                ) from err
        return cls(profiles)

    @classmethod
    def load_builtin_profiles(cls) -> Self:
        """Load all bundled species profiles from package resources."""
        directory = files(BUILTIN_PROFILE_PACKAGE)
        return cls.from_files(
            item
            for item in directory.iterdir()
            if item.is_file() and item.name.endswith(".json")
        )

    def get(self, profile_id: str) -> SpeciesProfile:
        """Return one registered profile."""
        try:
            return self._profiles[profile_id]
        except KeyError as err:
            raise SpeciesProfileNotFoundError(
                f"species profile not found: {profile_id}"
            ) from err

    def all(self) -> tuple[SpeciesProfile, ...]:
        """Return profiles in deterministic identifier order."""
        return tuple(self._profiles.values())

    def contains(self, profile_id: str) -> bool:
        """Return whether a profile is registered."""
        return profile_id in self._profiles
