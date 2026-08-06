"""Pure built-in content models independent from Home Assistant."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
import math
import re
from types import MappingProxyType
from typing import Any

from ..domain.care_plan import CarePlanScheduleUnit
from ..domain.task_template import TaskPriority

_NAMESPACED_ID = re.compile(r"^[a-z][a-z0-9_]*:[a-z0-9_]+$")
_LOCAL_ID = re.compile(r"^[a-z][a-z0-9_]*$")


class ContentError(Exception):
    """Base exception for built-in content operations."""


class InvalidContentError(ContentError, ValueError):
    """Raised when packaged content is malformed."""


class DuplicateContentError(ContentError):
    """Raised when multiple content items share the same identifier."""


class ContentNotFoundError(ContentError, LookupError):
    """Raised when a content lookup misses."""


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not (normalized := value.strip()):
        raise InvalidContentError(f"{name} must be a non-empty string")
    return normalized


def _optional_text(value: object, name: str) -> str | None:
    return None if value is None else _text(value, name)


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise InvalidContentError(f"{name} must be an object")
    return value


def _json_value(value: object, name: str) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InvalidContentError(f"{name} numbers must be finite")
        return value
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise InvalidContentError(f"{name} keys must be strings")
        return MappingProxyType(
            {key: _json_value(item, name) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_json_value(item, name) for item in value)
    raise InvalidContentError(f"{name} must contain only JSON-compatible values")


@dataclass(frozen=True, slots=True)
class EnvironmentalTarget:
    """One built-in environmental target recommendation."""

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
            raise InvalidContentError("target_id must be a lowercase identifier")
        minimum = self._number(self.minimum, "minimum")
        maximum = self._number(self.maximum, "maximum")
        if minimum > maximum:
            raise InvalidContentError("minimum must not exceed maximum")
        warning_minimum = (
            None
            if self.warning_minimum is None
            else self._number(self.warning_minimum, "warning_minimum")
        )
        warning_maximum = (
            None
            if self.warning_maximum is None
            else self._number(self.warning_maximum, "warning_maximum")
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

    @staticmethod
    def _number(value: object, name: str) -> int | float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise InvalidContentError(f"{name} must be a number")
        if not math.isfinite(value):
            raise InvalidContentError(f"{name} must be finite")
        return value


@dataclass(frozen=True, slots=True)
class BuiltinCarePlanTemplate:
    """Descriptive built-in care plan content."""

    content_id: str
    display_name: str
    description: str
    task_template_id: str
    workflow_id: str
    every: int
    unit: CarePlanScheduleUnit
    priority: TaskPriority = TaskPriority.NORMAL
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        content_id = _text(self.content_id, "content_id")
        if _NAMESPACED_ID.fullmatch(content_id) is None:
            raise InvalidContentError(
                "content_id must be a lowercase namespaced identifier"
            )
        if (
            isinstance(self.every, bool)
            or not isinstance(self.every, int)
            or self.every < 1
        ):
            raise InvalidContentError("every must be a positive integer")
        for name, value in (
            ("task_template_id", self.task_template_id),
            ("workflow_id", self.workflow_id),
        ):
            normalized = _text(value, name)
            if _NAMESPACED_ID.fullmatch(normalized) is None:
                raise InvalidContentError(
                    f"{name} must be a lowercase namespaced identifier"
                )
            object.__setattr__(self, name, normalized)
        object.__setattr__(self, "content_id", content_id)
        object.__setattr__(
            self, "display_name", _text(self.display_name, "display_name")
        )
        object.__setattr__(self, "description", _text(self.description, "description"))
        object.__setattr__(self, "unit", CarePlanScheduleUnit(self.unit))
        object.__setattr__(self, "priority", TaskPriority(self.priority))
        metadata = _json_value(self.metadata, "metadata")
        if not isinstance(metadata, Mapping):
            raise InvalidContentError("metadata must be an object")
        object.__setattr__(self, "metadata", metadata)


@dataclass(frozen=True, slots=True)
class BuiltinSpeciesPackage:
    """Keeper-facing built-in species content package."""

    species_id: str
    display_name: str
    scientific_name: str
    category: str
    description: str
    aliases: tuple[str, ...] = ()
    icon: str | None = None
    husbandry_metadata: Mapping[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )
    environmental_targets: tuple[EnvironmentalTarget, ...] = ()
    recommended_care_plan_ids: tuple[str, ...] = ()
    default_task_template_ids: tuple[str, ...] = ()
    schema_version: int = 1
    package_version: int = 1

    def __post_init__(self) -> None:
        species_id = _text(self.species_id, "species_id")
        if _NAMESPACED_ID.fullmatch(species_id) is None:
            raise InvalidContentError(
                "species_id must be a lowercase namespaced identifier"
            )
        for name, value in (
            ("schema_version", self.schema_version),
            ("package_version", self.package_version),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise InvalidContentError(f"{name} must be a positive integer")
        aliases = tuple(_text(alias, "alias") for alias in self.aliases)
        targets = tuple(self.environmental_targets)
        if not all(isinstance(item, EnvironmentalTarget) for item in targets):
            raise InvalidContentError("environmental_targets contain invalid values")
        target_ids = [item.target_id for item in targets]
        if len(target_ids) != len(set(target_ids)):
            raise InvalidContentError("environmental target IDs must be unique")
        recommended_care_plan_ids = tuple(
            _text(item, "recommended_care_plan_id")
            for item in self.recommended_care_plan_ids
        )
        if any(
            _NAMESPACED_ID.fullmatch(item) is None for item in recommended_care_plan_ids
        ):
            raise InvalidContentError(
                "recommended_care_plan_ids must be namespaced identifiers"
            )
        default_task_template_ids = tuple(
            _text(item, "default_task_template_id")
            for item in self.default_task_template_ids
        )
        if any(
            _NAMESPACED_ID.fullmatch(item) is None for item in default_task_template_ids
        ):
            raise InvalidContentError(
                "default_task_template_ids must be namespaced identifiers"
            )
        husbandry_metadata = _json_value(self.husbandry_metadata, "husbandry_metadata")
        if not isinstance(husbandry_metadata, Mapping):
            raise InvalidContentError("husbandry_metadata must be an object")
        object.__setattr__(self, "species_id", species_id)
        object.__setattr__(
            self, "display_name", _text(self.display_name, "display_name")
        )
        object.__setattr__(
            self, "scientific_name", _text(self.scientific_name, "scientific_name")
        )
        object.__setattr__(self, "category", _text(self.category, "category"))
        object.__setattr__(self, "description", _text(self.description, "description"))
        object.__setattr__(self, "aliases", aliases)
        object.__setattr__(self, "icon", _optional_text(self.icon, "icon"))
        object.__setattr__(self, "husbandry_metadata", husbandry_metadata)
        object.__setattr__(self, "environmental_targets", targets)
        object.__setattr__(self, "recommended_care_plan_ids", recommended_care_plan_ids)
        object.__setattr__(self, "default_task_template_ids", default_task_template_ids)

    def search_terms(self) -> tuple[str, ...]:
        """Return normalized terms for user-facing search."""
        return tuple(
            sorted(
                {
                    self.species_id.casefold(),
                    self.display_name.casefold(),
                    self.scientific_name.casefold(),
                    *(alias.casefold() for alias in self.aliases),
                }
            )
        )


class ContentRegistry[T]:
    """Small immutable lookup registry for content items."""

    def __init__(
        self,
        items: Iterable[T] = (),
        *,
        id_getter: Callable[[T], str],
    ) -> None:
        indexed: dict[str, T] = {}
        for item in items:
            item_id = id_getter(item)
            if item_id in indexed:
                raise DuplicateContentError(f"duplicate content ID: {item_id}")
            indexed[item_id] = item
        self._id_getter = id_getter
        self._items: Mapping[str, T] = MappingProxyType(dict(sorted(indexed.items())))

    def get(self, item_id: str) -> T:
        """Return one content item by permanent ID."""
        try:
            return self._items[item_id]
        except KeyError as err:
            raise ContentNotFoundError(f"content not found: {item_id}") from err

    def all(self) -> tuple[T, ...]:
        """Return all items in deterministic ID order."""
        return tuple(self._items.values())

    def contains(self, item_id: str) -> bool:
        """Return whether an item is registered."""
        return item_id in self._items
