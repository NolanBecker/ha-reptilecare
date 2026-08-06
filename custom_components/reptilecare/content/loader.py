"""Content discovery and validation for packaged ReptileCare data."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from importlib.resources import files
from importlib.resources.abc import Traversable
import logging
from types import MappingProxyType
from typing import Any

import yaml

from .models import (
    BuiltinCarePlanTemplate,
    BuiltinSpeciesPackage,
    ContentRegistry,
    EnvironmentalTarget,
    InvalidContentError,
)

_LOGGER = logging.getLogger(__name__)

CONTENT_PACKAGE = "custom_components.reptilecare.content"
SPECIES_DIRECTORY = "species"
CARE_PLAN_DIRECTORY = "care_plans"


@dataclass(frozen=True, slots=True)
class BuiltinContentBundle:
    """Validated content registries available at runtime."""

    species: ContentRegistry[BuiltinSpeciesPackage]
    care_plans: ContentRegistry[BuiltinCarePlanTemplate]

    def search_species(self, query: str) -> tuple[BuiltinSpeciesPackage, ...]:
        """Search species by display name, scientific name, or aliases."""
        normalized = query.strip().casefold()
        if not normalized:
            return self.species.all()
        matches = [
            item
            for item in self.species.all()
            if any(normalized in term for term in item.search_terms())
        ]
        return tuple(matches)

    def get_species_by_display_name(self, display_name: str) -> BuiltinSpeciesPackage:
        """Resolve one species by exact display name."""
        normalized = display_name.strip().casefold()
        for item in self.species.all():
            if item.display_name.casefold() == normalized:
                return item
        raise InvalidContentError(f"species not found: {display_name}")


@dataclass(frozen=True, slots=True)
class BuiltinContentLoadResult:
    """Detailed loader result including non-fatal warnings."""

    bundle: BuiltinContentBundle
    warnings: tuple[str, ...] = ()
    loaded_files: Mapping[str, tuple[str, ...]] = field(
        default_factory=lambda: MappingProxyType({})
    )


class BuiltinContentLoader:
    """Discover and validate packaged YAML content."""

    def __init__(self, package: str = CONTENT_PACKAGE) -> None:
        self._package = package

    def load(self) -> BuiltinContentLoadResult:
        """Load all packaged content, skipping malformed items with warnings."""
        root = files(self._package)
        species_items, species_warnings, species_files = self._load_species(
            root.joinpath(SPECIES_DIRECTORY)
        )
        care_plan_items, care_plan_warnings, care_plan_files = self._load_care_plans(
            root.joinpath(CARE_PLAN_DIRECTORY)
        )

        warnings = [*species_warnings, *care_plan_warnings]
        care_plans = ContentRegistry(
            care_plan_items,
            id_getter=lambda item: item.content_id,
        )
        species = []
        for item in species_items:
            missing = [
                content_id
                for content_id in item.recommended_care_plan_ids
                if not care_plans.contains(content_id)
            ]
            if missing:
                warnings.append(
                    "species package "
                    f"{item.species_id} references missing care plans: "
                    f"{', '.join(sorted(missing))}"
                )
                continue
            species.append(item)

        bundle = BuiltinContentBundle(
            species=ContentRegistry(species, id_getter=lambda item: item.species_id),
            care_plans=care_plans,
        )
        return BuiltinContentLoadResult(
            bundle=bundle,
            warnings=tuple(warnings),
            loaded_files=MappingProxyType(
                {
                    "species": tuple(species_files),
                    "care_plans": tuple(care_plan_files),
                }
            ),
        )

    def _load_species(
        self,
        directory: Traversable,
    ) -> tuple[
        list[BuiltinSpeciesPackage],
        list[str],
        list[str],
    ]:
        items: list[BuiltinSpeciesPackage] = []
        warnings: list[str] = []
        loaded_files: list[str] = []
        for item in sorted(self._yaml_files(directory), key=lambda entry: entry.name):
            try:
                data = self._read_yaml_mapping(item)
                species = self._species_from_mapping(data)
            except (OSError, InvalidContentError, yaml.YAMLError) as err:
                message = f"unable to load species package {item.name}: {err}"
                warnings.append(message)
                _LOGGER.warning(message)
                continue
            items.append(species)
            loaded_files.append(item.name)
        return items, warnings, loaded_files

    def _load_care_plans(
        self,
        directory: Traversable,
    ) -> tuple[
        list[BuiltinCarePlanTemplate],
        list[str],
        list[str],
    ]:
        items: list[BuiltinCarePlanTemplate] = []
        warnings: list[str] = []
        loaded_files: list[str] = []
        for item in sorted(self._yaml_files(directory), key=lambda entry: entry.name):
            try:
                data = self._read_yaml_mapping(item)
                care_plan = self._care_plan_from_mapping(data)
            except (OSError, InvalidContentError, yaml.YAMLError) as err:
                message = f"unable to load care plan package {item.name}: {err}"
                warnings.append(message)
                _LOGGER.warning(message)
                continue
            items.append(care_plan)
            loaded_files.append(item.name)
        return items, warnings, loaded_files

    @staticmethod
    def _yaml_files(directory: Traversable) -> tuple[Traversable, ...]:
        return tuple(
            item
            for item in directory.iterdir()
            if item.is_file() and item.name.endswith((".yaml", ".yml"))
        )

    @staticmethod
    def _read_yaml_mapping(item: Traversable) -> Mapping[str, Any]:
        raw = yaml.safe_load(item.read_text(encoding="utf-8"))
        if not isinstance(raw, Mapping) or not all(isinstance(key, str) for key in raw):
            raise InvalidContentError(f"{item.name} must contain a top-level object")
        return raw

    def _species_from_mapping(self, data: Mapping[str, Any]) -> BuiltinSpeciesPackage:
        targets = data.get("environmental_targets", ())
        if not isinstance(targets, Sequence) or isinstance(targets, str):
            raise InvalidContentError("environmental_targets must be an array")
        return BuiltinSpeciesPackage(
            species_id=data["species_id"],
            display_name=data["display_name"],
            scientific_name=data["scientific_name"],
            category=data["category"],
            description=data["description"],
            aliases=tuple(data.get("aliases", ())),
            icon=data.get("icon"),
            husbandry_metadata=_object(data.get("husbandry_metadata", {}), "husbandry"),
            environmental_targets=tuple(
                EnvironmentalTarget(
                    target_id=target["target_id"],
                    display_name=target["display_name"],
                    minimum=target["minimum"],
                    maximum=target["maximum"],
                    unit=target["unit"],
                    warning_minimum=target.get("warning_minimum"),
                    warning_maximum=target.get("warning_maximum"),
                    notes=target.get("notes"),
                )
                for target in (
                    _object(item, "environmental target") for item in targets
                )
            ),
            recommended_care_plan_ids=tuple(data.get("recommended_care_plan_ids", ())),
            default_task_template_ids=tuple(data.get("default_task_template_ids", ())),
            schema_version=int(data.get("schema_version", 1)),
            package_version=int(data.get("package_version", 1)),
        )

    def _care_plan_from_mapping(
        self, data: Mapping[str, Any]
    ) -> BuiltinCarePlanTemplate:
        schedule = _object(data.get("schedule"), "schedule")
        return BuiltinCarePlanTemplate(
            content_id=data["content_id"],
            display_name=data["display_name"],
            description=data["description"],
            task_template_id=data["task_template_id"],
            workflow_id=data["workflow_id"],
            every=schedule["every"],
            unit=schedule["unit"],
            priority=data.get("priority", "normal"),
            metadata=_object(data.get("metadata", {}), "metadata"),
        )


def _object(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise InvalidContentError(f"{name} must be an object")
    return value


def load_builtin_content() -> BuiltinContentLoadResult:
    """Load packaged content using the default loader."""
    return BuiltinContentLoader().load()
