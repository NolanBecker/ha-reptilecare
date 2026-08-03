"""Tests for the workflow graph registry."""

import json
from pathlib import Path

import pytest

from custom_components.reptilecare.domain.workflow import (
    DuplicateWorkflowError,
    InvalidWorkflowError,
    WorkflowActionDefinition,
    WorkflowActionType,
    WorkflowGraph,
    WorkflowNode,
    WorkflowNodeType,
    WorkflowNotFoundError,
    WorkflowRegistry,
    WorkflowTransition,
    WorkflowTrigger,
    WorkflowTriggerType,
    workflow_graph_to_dict,
)


def _graph(workflow_id: str) -> WorkflowGraph:
    return WorkflowGraph(
        workflow_id=workflow_id,
        display_name=workflow_id,
        description="Description",
        version=1,
        start_node="start",
        nodes=(
            WorkflowNode("start", WorkflowNodeType.START),
            WorkflowNode(
                "run",
                WorkflowNodeType.ACTION,
                action=WorkflowActionDefinition(
                    action_type=WorkflowActionType.COMPLETE_WORKFLOW,
                    display_name="Complete Workflow",
                ),
            ),
            WorkflowNode("complete", WorkflowNodeType.END),
        ),
        transitions=(
            WorkflowTransition(
                from_node="start",
                to_node="run",
                trigger=WorkflowTrigger(WorkflowTriggerType.MANUAL_TRIGGER),
            ),
            WorkflowTransition(
                from_node="run",
                to_node="complete",
                trigger=WorkflowTrigger(WorkflowTriggerType.TASK_COMPLETED),
            ),
        ),
    )


def test_builtin_registry_loads_feeding_cycle() -> None:
    """Bundled workflow graphs load as validated immutable models."""
    registry = WorkflowRegistry.load_builtin_workflows()
    workflow = registry.get("builtin:feeding_cycle")
    assert workflow.start_node == "start"
    assert [node.node_id for node in workflow.nodes] == [
        "complete_workflow",
        "create_next_feeding_task",
        "create_remove_food_task",
        "record_feeding_event",
        "start",
        "wait_before_cleanup",
    ]
    delayed = [transition for transition in workflow.transitions if transition.delay]
    assert len(delayed) == 1
    assert delayed[0].delay is not None
    assert delayed[0].delay.amount == 24
    assert delayed[0].delay.unit.value == "hours"


def test_registry_lookup_and_ordering() -> None:
    """Registry lookups are deterministic and explicit."""
    registry = WorkflowRegistry(
        (_graph("builtin:z_workflow"), _graph("builtin:a_workflow"))
    )
    assert [workflow.workflow_id for workflow in registry.all()] == [
        "builtin:a_workflow",
        "builtin:z_workflow",
    ]
    assert registry.contains("builtin:a_workflow")
    assert not registry.contains("builtin:missing")
    with pytest.raises(WorkflowNotFoundError, match="builtin:missing"):
        registry.get("builtin:missing")


def test_registry_rejects_duplicate_workflows() -> None:
    """Duplicate workflow identifiers fail registry construction."""
    workflow = _graph("builtin:duplicate")
    with pytest.raises(DuplicateWorkflowError, match="duplicate"):
        WorkflowRegistry((workflow, workflow))


def test_registry_loads_files_in_name_order(tmp_path: Path) -> None:
    """External file collections use the same strict loader."""
    for filename, workflow_id in (
        ("z.json", "builtin:z_workflow"),
        ("a.json", "builtin:a_workflow"),
    ):
        (tmp_path / filename).write_text(
            json.dumps(workflow_graph_to_dict(_graph(workflow_id))),
            encoding="utf-8",
        )
    registry = WorkflowRegistry.from_files(tmp_path.glob("*.json"))
    assert [workflow.workflow_id for workflow in registry.all()] == [
        "builtin:a_workflow",
        "builtin:z_workflow",
    ]


def test_registry_reports_invalid_json_file(tmp_path: Path) -> None:
    """Invalid packaged-style JSON produces a clear domain error."""
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json", encoding="utf-8")
    with pytest.raises(InvalidWorkflowError, match="invalid.json"):
        WorkflowRegistry.from_files((invalid,))
