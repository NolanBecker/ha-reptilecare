"""Tests for task template domain models and serialization."""

from dataclasses import FrozenInstanceError
import json

import pytest

from custom_components.reptilecare.domain.task_template import (
    CompletionBehavior,
    ContextFieldType,
    InvalidTaskTemplateError,
    TaskCategory,
    TaskContextFieldDefinition,
    TaskOutcomeDefinition,
    TaskPriority,
    TaskTemplate,
    task_template_from_dict,
    task_template_to_dict,
)


def _template() -> TaskTemplate:
    return TaskTemplate(
        template_id="builtin:feed_fruit",
        display_name="Feed Fruit Mix",
        description="Offer prepared fruit mix.",
        category=TaskCategory.FEEDING,
        icon="mdi:food-apple",
        expected_outcomes=(
            TaskOutcomeDefinition(
                outcome_id="ate_normally",
                display_name="Ate Normally",
                description="The reptile ate the offered food.",
            ),
            TaskOutcomeDefinition(
                outcome_id="refused",
                display_name="Refused",
            ),
        ),
        context_fields=(
            TaskContextFieldDefinition(
                field_id="food_used",
                display_name="Food Used",
                field_type=ContextFieldType.TEXT,
            ),
            TaskContextFieldDefinition(
                field_id="quantity",
                display_name="Quantity",
                field_type=ContextFieldType.NUMBER,
                unit="g",
            ),
        ),
        default_priority=TaskPriority.NORMAL,
        estimated_duration=10,
        completion_behavior=CompletionBehavior(
            create_care_event=True,
            supports_follow_up_task=True,
            supports_workflow=True,
        ),
        workflow_definition={"future": {"enabled": True}},
        metadata={"group": "feeding"},
    )


def test_task_template_is_immutable_and_normalized() -> None:
    """Templates copy input collections and remain immutable."""
    outcomes = [TaskOutcomeDefinition("completed", "Completed")]
    template = TaskTemplate(
        template_id="builtin:spot_clean",
        display_name=" Spot Clean ",
        description=" Cleaning task ",
        category=TaskCategory.CLEANING,
        expected_outcomes=outcomes,  # type: ignore[arg-type]
    )
    outcomes.append(TaskOutcomeDefinition("skipped", "Skipped"))
    assert template.display_name == "Spot Clean"
    assert len(template.expected_outcomes) == 1
    with pytest.raises(FrozenInstanceError):
        template.display_name = "Changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"template_id": "feed"}, "template_id"),
        ({"category": "not_a_category"}, "category"),
        ({"default_priority": "not_a_priority"}, "default_priority"),
        ({"estimated_duration": 0}, "estimated_duration"),
        ({"workflow_definition": []}, "workflow_definition"),
        ({"metadata": []}, "metadata"),
    ],
)
def test_task_template_rejects_invalid_values(
    mutation: dict[str, object], message: str
) -> None:
    """Template fields reject malformed values and unsupported types."""
    values: dict[str, object] = {
        "template_id": "builtin:spot_clean",
        "display_name": "Spot Clean",
        "description": "Remove visible waste.",
        "category": TaskCategory.CLEANING,
    }
    values.update(mutation)
    with pytest.raises(InvalidTaskTemplateError, match=message):
        TaskTemplate(**values)  # type: ignore[arg-type]


def test_outcomes_and_context_fields_reject_duplicates_and_invalid_ids() -> None:
    """Nested definitions keep stable identifiers explicit and unique."""
    with pytest.raises(InvalidTaskTemplateError, match="outcome_id"):
        TaskOutcomeDefinition("Not Valid", "Bad")
    with pytest.raises(InvalidTaskTemplateError, match="field_id"):
        TaskContextFieldDefinition("Not Valid", "Bad", ContextFieldType.TEXT)
    with pytest.raises(InvalidTaskTemplateError, match="expected_outcome IDs"):
        TaskTemplate(
            template_id="builtin:duplicate_outcome",
            display_name="Duplicate Outcome",
            description="Description",
            category=TaskCategory.CUSTOM,
            expected_outcomes=(
                TaskOutcomeDefinition("completed", "Completed"),
                TaskOutcomeDefinition("completed", "Completed Again"),
            ),
        )
    with pytest.raises(InvalidTaskTemplateError, match="context field IDs"):
        TaskTemplate(
            template_id="builtin:duplicate_field",
            display_name="Duplicate Field",
            description="Description",
            category=TaskCategory.CUSTOM,
            context_fields=(
                TaskContextFieldDefinition(
                    "notes",
                    "Notes",
                    ContextFieldType.TEXT,
                ),
                TaskContextFieldDefinition(
                    "notes",
                    "Notes Again",
                    ContextFieldType.TEXT,
                ),
            ),
        )


def test_serialization_round_trip_is_json_compatible() -> None:
    """Templates round-trip through explicit JSON-compatible serialization."""
    template = _template()
    serialized = task_template_to_dict(template)
    assert task_template_from_dict(json.loads(json.dumps(serialized))) == template


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"unknown": True}, "unknown keys"),
        ({"schema_version": 2}, "unsupported schema"),
        ({"expected_outcomes": {}}, "array"),
        ({"context_fields": {}}, "array"),
        ({"completion_behavior": []}, "object"),
        ({"default_priority": "invalid"}, "default_priority"),
    ],
)
def test_deserialization_rejects_invalid_templates(
    mutation: dict[str, object], message: str
) -> None:
    """Strict deserialization rejects unsupported template documents."""
    data = task_template_to_dict(_template())
    data.update(mutation)
    with pytest.raises(InvalidTaskTemplateError, match=message):
        task_template_from_dict(data)


def test_deserialization_rejects_invalid_nested_fields() -> None:
    """Strict deserialization validates nested outcome and field objects."""
    data = task_template_to_dict(_template())
    data["expected_outcomes"][0]["unexpected"] = True
    with pytest.raises(InvalidTaskTemplateError, match="unknown keys"):
        task_template_from_dict(data)

    data = task_template_to_dict(_template())
    data["context_fields"][0]["field_type"] = "unknown"
    with pytest.raises(InvalidTaskTemplateError, match="field_type"):
        task_template_from_dict(data)
