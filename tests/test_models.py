"""Tests for shared LizardCare models."""

from custom_components.lizardcare.models import EventType


def test_event_types_are_stable() -> None:
    """Test the canonical initial event vocabulary."""
    assert {event_type.value for event_type in EventType} == {
        "deep_clean",
        "feeding",
        "food_removed",
        "health_note",
        "photo",
        "shed",
        "spot_clean",
        "weight",
    }
