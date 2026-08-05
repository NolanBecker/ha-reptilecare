"""Tests for the TaskOutcome value object."""

from __future__ import annotations

import math

import pytest

from custom_components.reptilecare.domain.task_outcome import (
    InvalidTaskOutcomeError,
    TaskOutcome,
    task_outcome_from_dict,
    task_outcome_to_dict,
)


def test_task_outcome_round_trips_json_compatible_metadata() -> None:
    """TaskOutcome preserves immutable structured metadata across serialization."""
    outcome = TaskOutcome(
        outcome_id="ate_normally",
        metadata={"foods": ["papaya"], "quantity": 2, "accepted": True},
    )

    serialized = task_outcome_to_dict(outcome)
    restored = task_outcome_from_dict(serialized)

    assert serialized == {
        "outcome_id": "ate_normally",
        "metadata": {"foods": ["papaya"], "quantity": 2, "accepted": True},
    }
    assert restored == outcome
    assert restored.metadata["foods"] == ("papaya",)


@pytest.mark.parametrize(
    ("outcome_id", "message"),
    [
        ("", "non-empty string"),
        ("NotLower", "lowercase identifier"),
    ],
)
def test_task_outcome_rejects_invalid_identifiers(
    outcome_id: str, message: str
) -> None:
    """TaskOutcome validation rejects malformed identifiers."""
    with pytest.raises(InvalidTaskOutcomeError, match=message):
        TaskOutcome(outcome_id=outcome_id)


@pytest.mark.parametrize(
    ("metadata", "message"),
    [
        ({"bad": object()}, "JSON-compatible"),
        ({"bad": math.inf}, "numbers must be finite"),
        ({1: "bad"}, "keys must be strings"),
    ],
)
def test_task_outcome_rejects_invalid_metadata(metadata: object, message: str) -> None:
    """TaskOutcome validation rejects malformed metadata."""
    with pytest.raises(InvalidTaskOutcomeError, match=message):
        TaskOutcome(outcome_id="ate_normally", metadata=metadata)


def test_task_outcome_from_dict_requires_exact_shape() -> None:
    """Deserialization rejects missing, unknown, and malformed keys."""
    with pytest.raises(InvalidTaskOutcomeError, match="missing keys: metadata"):
        task_outcome_from_dict({"outcome_id": "ate_normally"})
    with pytest.raises(InvalidTaskOutcomeError, match="unknown keys: extra"):
        task_outcome_from_dict(
            {"outcome_id": "ate_normally", "metadata": {}, "extra": True}
        )
    with pytest.raises(InvalidTaskOutcomeError, match="metadata must be an object"):
        task_outcome_from_dict({"outcome_id": "ate_normally", "metadata": []})
