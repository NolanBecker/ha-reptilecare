"""Tests for shared ReptileCare models."""

from datetime import UTC, datetime
from uuid import UUID

import pytest

from custom_components.reptilecare.domain.reptile import Reptile
from custom_components.reptilecare.models import CareEvent, CareEventType


def test_event_types_are_stable() -> None:
    """Test the canonical initial event vocabulary."""
    assert {event_type.value for event_type in CareEventType} == {
        "deep_clean",
        "feeding",
        "food_removed",
        "health_note",
        "photo",
        "shed",
        "spot_clean",
        "weight",
    }


def test_events_receive_unique_ids_and_freeze_metadata() -> None:
    """Test event identity, UTC normalization, and metadata immutability."""
    metadata = {"foods": ["cricket"]}
    first = CareEvent(
        reptile_id="pixel",
        event_type=CareEventType.FEEDING,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        metadata=metadata,
    )
    second = CareEvent(reptile_id="pixel", event_type=CareEventType.FEEDING)
    metadata["foods"].append("roach")

    assert isinstance(first.event_id, UUID)
    assert first.event_id != second.event_id
    assert first.timestamp.tzinfo is UTC
    assert first.metadata["foods"] == ("cricket",)
    with pytest.raises(TypeError):
        first.metadata["foods"] = ("roach",)


def test_event_rejects_naive_timestamp() -> None:
    """Test that event timestamps must identify a timezone."""
    with pytest.raises(ValueError, match="timezone-aware"):
        CareEvent(
            reptile_id="pixel",
            event_type=CareEventType.WEIGHT,
            timestamp=datetime(2026, 1, 1),  # noqa: DTZ001
        )


def test_reptile_model_uses_species_profile_identity() -> None:
    """Test the shared model import uses permanent SpeciesProfile identity."""
    pixel = Reptile(
        reptile_id="pixel",
        display_name="Pixel",
        species_profile_id="builtin:gargoyle_gecko",
    )

    assert pixel.display_name == "Pixel"
    assert pixel.species_profile_id == "builtin:gargoyle_gecko"
    assert pixel.morph is None
