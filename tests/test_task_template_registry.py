"""Tests for the task template registry."""

import json
from pathlib import Path

import pytest

from custom_components.reptilecare.domain.task_template import (
    DuplicateTaskTemplateError,
    InvalidTaskTemplateError,
    TaskCategory,
    TaskTemplate,
    TaskTemplateNotFoundError,
    TaskTemplateRegistry,
    task_template_to_dict,
)


def _template(template_id: str) -> TaskTemplate:
    return TaskTemplate(
        template_id=template_id,
        display_name=template_id,
        description="Description",
        category=TaskCategory.CUSTOM,
    )


def test_builtin_registry_loads_feed_fruit() -> None:
    """Bundled task templates load with typed outcomes and field definitions."""
    registry = TaskTemplateRegistry.load_builtin_templates()
    template = registry.get("builtin:feed_fruit")
    assert template.category is TaskCategory.FEEDING
    assert template.default_priority.value == "normal"
    assert [outcome.outcome_id for outcome in template.expected_outcomes] == [
        "ate_normally",
        "ate_partially",
        "refused",
        "skipped",
        "cancelled",
    ]
    assert [field.field_id for field in template.context_fields] == [
        "food_used",
        "quantity",
        "notes",
    ]
    assert template.completion_behavior.workflow_graph_id == "builtin:feeding_cycle"


def test_registry_lookup_and_ordering() -> None:
    """Registry lookups are deterministic and provide explicit misses."""
    registry = TaskTemplateRegistry(
        (_template("builtin:z_task"), _template("builtin:a_task"))
    )
    assert [template.template_id for template in registry.all()] == [
        "builtin:a_task",
        "builtin:z_task",
    ]
    assert registry.contains("builtin:a_task")
    assert not registry.contains("builtin:missing")
    with pytest.raises(TaskTemplateNotFoundError, match="builtin:missing"):
        registry.get("builtin:missing")


def test_registry_rejects_duplicate_templates() -> None:
    """Duplicate task template identifiers fail registry construction."""
    template = _template("builtin:duplicate")
    with pytest.raises(DuplicateTaskTemplateError, match="duplicate"):
        TaskTemplateRegistry((template, template))


def test_registry_loads_files_in_name_order(tmp_path: Path) -> None:
    """External file collections use the same strict loader."""
    for filename, template_id in (
        ("z.json", "builtin:z_task"),
        ("a.json", "builtin:a_task"),
    ):
        (tmp_path / filename).write_text(
            json.dumps(task_template_to_dict(_template(template_id))),
            encoding="utf-8",
        )
    registry = TaskTemplateRegistry.from_files(tmp_path.glob("*.json"))
    assert [template.template_id for template in registry.all()] == [
        "builtin:a_task",
        "builtin:z_task",
    ]


def test_registry_reports_invalid_json_file(tmp_path: Path) -> None:
    """Invalid packaged-style JSON produces a clear domain error."""
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json", encoding="utf-8")
    with pytest.raises(InvalidTaskTemplateError, match="invalid.json"):
        TaskTemplateRegistry.from_files((invalid,))
