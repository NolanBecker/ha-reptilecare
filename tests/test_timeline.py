"""Tests for event timeline queries."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.reptilecare.models import CareEvent, CareEventType
from custom_components.reptilecare.timeline import Timeline

BASE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


def _event(
    event_type: CareEventType,
    hour: int,
    reptile_id: str = "pixel",
) -> CareEvent:
    """Create a deterministic timeline event."""
    return CareEvent(
        reptile_id=reptile_id,
        event_type=event_type,
        timestamp=BASE_TIME + timedelta(hours=hour),
    )


def test_timeline_orders_and_filters_events() -> None:
    """Test ordering and reusable timeline filters."""
    feeding = _event(CareEventType.FEEDING, 1)
    weight = _event(CareEventType.WEIGHT, 2)
    other = _event(CareEventType.SHED, 3, "echo")
    clean = _event(CareEventType.SPOT_CLEAN, 4)
    timeline = Timeline((clean, other, weight, feeding))

    assert timeline.all_events() == (feeding, weight, other, clean)
    assert timeline.latest_event() is clean
    assert timeline.latest_event_of_type(CareEventType.WEIGHT) is weight
    assert timeline.latest_event_of_type(CareEventType.SHED, reptile_id="pixel") is None
    assert timeline.events_for_reptile("pixel") == (feeding, weight, clean)
    assert timeline.events_between(
        BASE_TIME + timedelta(hours=2),
        BASE_TIME + timedelta(hours=3),
    ) == (weight, other)
    assert timeline.event_count() == 4
    assert (
        timeline.event_count(reptile_id="pixel", event_type=CareEventType.FEEDING) == 1
    )


def test_empty_timeline_and_invalid_interval() -> None:
    """Test empty results and invalid interval validation."""
    timeline = Timeline()

    assert timeline.latest_event() is None
    assert timeline.event_count() == 0
    with pytest.raises(ValueError, match="timezone-aware"):
        timeline.events_between(datetime(2026, 1, 1), BASE_TIME)  # noqa: DTZ001
    with pytest.raises(ValueError, match="after end"):
        timeline.events_between(BASE_TIME + timedelta(hours=1), BASE_TIME)
