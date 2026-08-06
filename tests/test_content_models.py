"""Tests for content-model validation and lookup helpers."""

from __future__ import annotations

from types import MappingProxyType

import pytest

from custom_components.reptilecare.content.loader import BuiltinContentBundle
from custom_components.reptilecare.content.models import (
    BuiltinCarePlanTemplate,
    BuiltinSpeciesPackage,
    ContentNotFoundError,
    ContentRegistry,
    DuplicateContentError,
    EnvironmentalTarget,
    InvalidContentError,
)
from custom_components.reptilecare.domain.care_plan import CarePlanScheduleUnit
from custom_components.reptilecare.domain.task_template import TaskPriority


def test_environmental_target_validates_bounds_and_identifiers() -> None:
    """Environmental targets should normalize valid input and reject bad values."""
    target = EnvironmentalTarget(
        target_id="humidity",
        display_name="Humidity",
        minimum=60,
        maximum=80,
        unit="%",
        warning_minimum=55,
        warning_maximum=85,
        notes="Night misting supported.",
    )

    assert target.target_id == "humidity"
    assert target.warning_minimum == 55
    assert target.warning_maximum == 85

    with pytest.raises(InvalidContentError, match="lowercase identifier"):
        EnvironmentalTarget(
            target_id="Humidity-Level",
            display_name="Humidity",
            minimum=60,
            maximum=80,
            unit="%",
        )

    with pytest.raises(InvalidContentError, match="minimum must not exceed maximum"):
        EnvironmentalTarget(
            target_id="temp",
            display_name="Temperature",
            minimum=80,
            maximum=70,
            unit="F",
        )


def test_care_plan_template_validates_json_metadata_and_ids() -> None:
    """Care plan templates should freeze JSON-compatible metadata."""
    template = BuiltinCarePlanTemplate(
        content_id="builtin:feed_daily",
        display_name="Feed Daily",
        description="Offer food daily.",
        task_template_id="builtin:feed_fruit",
        workflow_id="builtin:basic_care",
        every=1,
        unit=CarePlanScheduleUnit.DAYS,
        priority=TaskPriority.HIGH,
        metadata={"foods": ["fig", "papaya"], "hydration": {"required": True}},
    )

    assert template.priority is TaskPriority.HIGH
    assert template.metadata["foods"] == ("fig", "papaya")
    assert template.metadata["hydration"]["required"] is True

    with pytest.raises(InvalidContentError, match="positive integer"):
        BuiltinCarePlanTemplate(
            content_id="builtin:feed_daily",
            display_name="Feed Daily",
            description="Offer food daily.",
            task_template_id="builtin:feed_fruit",
            workflow_id="builtin:basic_care",
            every=0,
            unit=CarePlanScheduleUnit.DAYS,
        )

    with pytest.raises(InvalidContentError, match="JSON-compatible"):
        BuiltinCarePlanTemplate(
            content_id="builtin:feed_daily",
            display_name="Feed Daily",
            description="Offer food daily.",
            task_template_id="builtin:feed_fruit",
            workflow_id="builtin:basic_care",
            every=1,
            unit=CarePlanScheduleUnit.DAYS,
            metadata={"bad": object()},
        )


def test_species_package_validates_targets_and_search_terms() -> None:
    """Species packages should validate references and expose deterministic search."""
    package = BuiltinSpeciesPackage(
        species_id="builtin:gargoyle_gecko",
        display_name="Gargoyle Gecko",
        scientific_name="Rhacodactylus auriculatus",
        category="gecko",
        description="Arboreal New Caledonian gecko.",
        aliases=("Garg", "Rhac"),
        icon="mdi:lizard",
        husbandry_metadata=MappingProxyType({"humidity": {"day": 60}}),
        environmental_targets=(
            EnvironmentalTarget(
                target_id="humidity",
                display_name="Humidity",
                minimum=60,
                maximum=80,
                unit="%",
            ),
        ),
        recommended_care_plan_ids=("builtin:feed_fruit_every_2_days",),
        default_task_template_ids=("builtin:feed_fruit",),
    )

    assert package.search_terms() == (
        "builtin:gargoyle_gecko",
        "garg",
        "gargoyle gecko",
        "rhac",
        "rhacodactylus auriculatus",
    )

    with pytest.raises(
        InvalidContentError,
        match="environmental target IDs must be unique",
    ):
        BuiltinSpeciesPackage(
            species_id="builtin:gargoyle_gecko",
            display_name="Gargoyle Gecko",
            scientific_name="Rhacodactylus auriculatus",
            category="gecko",
            description="Arboreal New Caledonian gecko.",
            environmental_targets=(
                EnvironmentalTarget(
                    target_id="humidity",
                    display_name="Humidity",
                    minimum=60,
                    maximum=80,
                    unit="%",
                ),
                EnvironmentalTarget(
                    target_id="humidity",
                    display_name="Humidity",
                    minimum=50,
                    maximum=90,
                    unit="%",
                ),
            ),
        )

    with pytest.raises(InvalidContentError, match="recommended_care_plan_ids"):
        BuiltinSpeciesPackage(
            species_id="builtin:gargoyle_gecko",
            display_name="Gargoyle Gecko",
            scientific_name="Rhacodactylus auriculatus",
            category="gecko",
            description="Arboreal New Caledonian gecko.",
            recommended_care_plan_ids=("feed_daily",),
        )


def test_content_registry_and_bundle_support_lookup_search_and_errors() -> None:
    """Registries and bundles should stay deterministic and human-friendly."""
    species = BuiltinSpeciesPackage(
        species_id="builtin:leopard_gecko",
        display_name="Leopard Gecko",
        scientific_name="Eublepharis macularius",
        category="gecko",
        description="Terrestrial gecko.",
        aliases=("Leo",),
    )
    care_plan = BuiltinCarePlanTemplate(
        content_id="builtin:feed_insects_every_2_days",
        display_name="Feed Insects",
        description="Offer insects every two days.",
        task_template_id="builtin:feed_insects",
        workflow_id="builtin:basic_care",
        every=2,
        unit=CarePlanScheduleUnit.DAYS,
    )
    bundle = BuiltinContentBundle(
        species=ContentRegistry((species,), id_getter=lambda item: item.species_id),
        care_plans=ContentRegistry(
            (care_plan,),
            id_getter=lambda item: item.content_id,
        ),
    )

    assert bundle.search_species("") == (species,)
    assert bundle.search_species("leo") == (species,)
    assert bundle.get_species_by_display_name(" leopard gecko ") is species
    assert bundle.care_plans.get("builtin:feed_insects_every_2_days") is care_plan
    assert bundle.care_plans.contains("builtin:feed_insects_every_2_days") is True

    with pytest.raises(ContentNotFoundError, match="content not found"):
        bundle.care_plans.get("builtin:missing")

    with pytest.raises(InvalidContentError, match="species not found"):
        bundle.get_species_by_display_name("unknown")

    with pytest.raises(DuplicateContentError, match="duplicate content ID"):
        ContentRegistry(
            (species, species),
            id_getter=lambda item: item.species_id,
        )
