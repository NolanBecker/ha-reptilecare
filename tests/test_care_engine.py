"""Pure-Python tests for the CareEngine execution loop."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from custom_components.reptilecare.application import (
    CareEngine,
    CareEnginePersistenceError,
    CareTaskResolutionNotAllowedError,
    CareTaskResolutionRequest,
    ConflictingTaskResolutionError,
    CreateTaskEffect,
    InvalidTaskContextError,
    InvalidTaskOutcomeSelectionError,
    InvalidWorkflowEffectError,
    MissingTaskTemplateReferenceError,
    MissingWorkflowGraphReferenceError,
    NoOpEffect,
    ResolutionAction,
    WorkflowEvaluator,
)
from custom_components.reptilecare.domain.care_plan import (
    CarePlan,
    CarePlanRepository,
    CarePlanScheduleUnit,
    IntervalSchedule,
    MemoryCarePlanPersistence,
)
from custom_components.reptilecare.domain.care_task import (
    CareTask,
    CareTaskGenerationReason,
    CareTaskRepository,
    CareTaskStatus,
    MemoryCareTaskPersistence,
)
from custom_components.reptilecare.domain.reptile import (
    MemoryReptilePersistence,
    Reptile,
    ReptileRepository,
)
from custom_components.reptilecare.domain.species import SpeciesProfileRegistry
from custom_components.reptilecare.domain.task_outcome import TaskOutcome
from custom_components.reptilecare.domain.task_template import (
    CompletionBehavior,
    ContextFieldType,
    TaskContextFieldDefinition,
    TaskTemplateRegistry,
)
from custom_components.reptilecare.domain.workflow import (
    WorkflowActionDefinition,
    WorkflowActionType,
    WorkflowDelay,
    WorkflowDelayUnit,
    WorkflowGraph,
    WorkflowNode,
    WorkflowNodeType,
    WorkflowRegistry,
    WorkflowTransition,
    WorkflowTrigger,
    WorkflowTriggerType,
)
from custom_components.reptilecare.storage import MemoryCareEventStore

PIXEL_ID = "550e8400-e29b-41d4-a716-446655440000"
PLAN_ID = "123e4567-e89b-12d3-a456-426614174000"
TASK_ID = "223e4567-e89b-12d3-a456-426614174000"


def _pixel() -> Reptile:
    return Reptile(
        reptile_id=PIXEL_ID,
        display_name="Pixel",
        species_profile_id="builtin:gargoyle_gecko",
        slug="pixel",
    )


def _plan() -> CarePlan:
    return CarePlan(
        care_plan_id=PLAN_ID,
        reptile_id=PIXEL_ID,
        task_template_id="builtin:feed_fruit",
        workflow_id="builtin:feeding_cycle",
        display_name="Feed Fruit",
        schedule=IntervalSchedule(every=2, unit=CarePlanScheduleUnit.DAYS),
        effective_date=date(2026, 8, 3),
    )


def _feed_task() -> CareTask:
    return CareTask(
        task_id=TASK_ID,
        reptile_id=PIXEL_ID,
        care_plan_id=PLAN_ID,
        task_template_id="builtin:feed_fruit",
        workflow_id="builtin:feeding_cycle",
        due_at=datetime(2026, 8, 3, 12, tzinfo=UTC),
        created_at=datetime(2026, 8, 3, 10, tzinfo=UTC),
        generation_key="feed|pixel|2026-08-03T12:00:00+00:00",
        generated_by="care_plan:123e4567-e89b-12d3-a456-426614174000:v1",
        workflow_chain_id="323e4567-e89b-12d3-a456-426614174000",
        workflow_node_id="start",
    )


async def _build_engine(
    *tasks: CareTask,
) -> tuple[CareEngine, CareTaskRepository, MemoryCareEventStore]:
    reptile_repository = ReptileRepository(
        SpeciesProfileRegistry.load_builtin_profiles(),
        MemoryReptilePersistence(),
    )
    await reptile_repository.async_load()
    await reptile_repository.async_add(_pixel())
    task_templates = TaskTemplateRegistry.load_builtin_templates()
    workflow_graphs = WorkflowRegistry.load_builtin_workflows()
    care_plan_repository = CarePlanRepository(
        reptile_repository,
        task_templates,
        workflow_graphs,
        MemoryCarePlanPersistence((_plan(),)),
    )
    await care_plan_repository.async_load()
    task_repository = CareTaskRepository(
        reptile_repository,
        care_plan_repository,
        task_templates,
        workflow_graphs,
        MemoryCareTaskPersistence(tasks),
    )
    await task_repository.async_load()
    event_store = MemoryCareEventStore()
    engine = CareEngine(
        task_repository,
        task_templates,
        workflow_graphs,
        event_store,
        WorkflowEvaluator(workflow_graphs),
    )
    return engine, task_repository, event_store


def test_complete_feed_task_creates_event_and_follow_up() -> None:
    """Completing Feed Fruit creates one feeding event and Remove Food follow-up."""

    async def _run() -> None:
        engine, task_repository, event_store = await _build_engine(_feed_task())
        result = await engine.async_resolve_task(
            TASK_ID,
            CareTaskResolutionRequest(
                action=ResolutionAction.COMPLETE,
                outcome_id="ate_normally",
                outcome_metadata={"food_used": "papaya", "quantity": 30},
                notes="Ate normally",
                source="test",
                actor_id="keeper-1",
                completed_at=datetime(2026, 8, 3, 12, 30, tzinfo=UTC),
                environmental_context={"temperature_f": 78},
            ),
        )

        assert result.task.status is CareTaskStatus.COMPLETED
        assert result.care_event.event_type.value == "feeding"
        assert result.care_event.task_id == TASK_ID
        assert result.care_event.outcome_id == "ate_normally"
        assert result.care_event.actor_id == "keeper-1"
        assert result.care_event.source == "test"
        assert result.care_event.environmental_snapshot["temperature_f"] == 78
        assert len(result.created_follow_up_tasks) == 1
        follow_up = result.created_follow_up_tasks[0]
        assert follow_up.task_template_id == "builtin:remove_food"
        assert follow_up.generation_reason is CareTaskGenerationReason.FOLLOW_UP
        assert follow_up.workflow_node_id == "create_remove_food_task"
        assert follow_up.parent_task_id == TASK_ID
        assert follow_up.due_at == datetime(2026, 8, 4, 12, 30, tzinfo=UTC)
        assert len(await event_store.async_list_events()) == 1
        assert len(task_repository.all()) == 2

    asyncio.run(_run())


def test_same_request_replays_without_duplicate_event_or_task() -> None:
    """Reapplying the same resolution reuses the first result."""

    async def _run() -> None:
        engine, _, event_store = await _build_engine(_feed_task())
        request = CareTaskResolutionRequest(
            action=ResolutionAction.COMPLETE,
            outcome_id="ate_partially",
            completed_at=datetime(2026, 8, 3, 12, 45, tzinfo=UTC),
        )
        first = await engine.async_resolve_task(TASK_ID, request)
        second = await engine.async_resolve_task(TASK_ID, request)

        assert not first.replayed_existing_result
        assert second.replayed_existing_result
        assert first.care_event.event_id == second.care_event.event_id
        assert len(first.created_follow_up_tasks) == 1
        assert second.created_follow_up_tasks == ()
        assert len(second.existing_follow_up_tasks) == 1
        assert len(await event_store.async_list_events()) == 1

    asyncio.run(_run())


def test_conflicting_second_resolution_fails() -> None:
    """A conflicting second terminal resolution is rejected clearly."""

    async def _run() -> None:
        engine, _, _ = await _build_engine(_feed_task())
        await engine.async_resolve_task(
            TASK_ID,
            CareTaskResolutionRequest(
                action=ResolutionAction.COMPLETE,
                outcome_id="ate_normally",
                completed_at=datetime(2026, 8, 3, 12, 30, tzinfo=UTC),
            ),
        )
        with pytest.raises(ConflictingTaskResolutionError, match=TASK_ID):
            await engine.async_resolve_task(
                TASK_ID,
                CareTaskResolutionRequest(
                    action=ResolutionAction.SKIP,
                    completed_at=datetime(2026, 8, 3, 12, 31, tzinfo=UTC),
                ),
            )

    asyncio.run(_run())


def test_invalid_outcome_and_context_fail_clearly() -> None:
    """Unknown outcomes and bad context fields are rejected before persistence."""

    async def _run() -> None:
        engine, _, _ = await _build_engine(_feed_task())
        with pytest.raises(InvalidTaskOutcomeSelectionError, match="does not allow"):
            await engine.async_resolve_task(
                TASK_ID,
                CareTaskResolutionRequest(
                    action=ResolutionAction.COMPLETE,
                    outcome_id="unknown_outcome",
                ),
            )
        with pytest.raises(InvalidTaskContextError, match="unknown context fields"):
            await engine.async_resolve_task(
                TASK_ID,
                CareTaskResolutionRequest(
                    action=ResolutionAction.COMPLETE,
                    outcome_id="ate_normally",
                    outcome_metadata={"unknown_field": "value"},
                ),
            )

    asyncio.run(_run())


def test_skip_path_creates_event_without_follow_up() -> None:
    """Skipping Feed Fruit creates one event and follows the graph end path only."""

    async def _run() -> None:
        engine, task_repository, event_store = await _build_engine(_feed_task())
        result = await engine.async_resolve_task(
            TASK_ID,
            CareTaskResolutionRequest(
                action=ResolutionAction.SKIP,
                completed_at=datetime(2026, 8, 3, 12, tzinfo=UTC),
            ),
        )

        assert result.task.status is CareTaskStatus.SKIPPED
        assert result.care_event.event_type.value == "feeding"
        assert result.created_follow_up_tasks == ()
        assert result.existing_follow_up_tasks == ()
        assert result.workflow_completed
        assert len(task_repository.all()) == 1
        assert len(await event_store.async_list_events()) == 1

    asyncio.run(_run())


def test_remove_food_resolution_creates_next_feeding_task() -> None:
    """Completing Remove Food creates a food_removed event and next feed task."""

    async def _run() -> None:
        remove_food = CareTask(
            task_id="423e4567-e89b-12d3-a456-426614174000",
            reptile_id=PIXEL_ID,
            care_plan_id=PLAN_ID,
            task_template_id="builtin:remove_food",
            workflow_id="builtin:feeding_cycle",
            due_at=datetime(2026, 8, 4, 12, tzinfo=UTC),
            created_at=datetime(2026, 8, 3, 12, 30, tzinfo=UTC),
            generation_key="remove|pixel|2026-08-04T12:00:00+00:00",
            generated_by="care_engine:feed:create_remove_food_task",
            parent_task_id=TASK_ID,
            workflow_chain_id="323e4567-e89b-12d3-a456-426614174000",
            workflow_node_id="create_remove_food_task",
            generation_reason=CareTaskGenerationReason.FOLLOW_UP,
        )
        engine, task_repository, _ = await _build_engine(remove_food)
        result = await engine.async_resolve_task(
            remove_food.task_id,
            CareTaskResolutionRequest(
                action=ResolutionAction.COMPLETE,
                outcome_id="completed",
                completed_at=datetime(2026, 8, 4, 12, 5, tzinfo=UTC),
            ),
        )

        assert result.care_event.event_type.value == "food_removed"
        assert len(result.created_follow_up_tasks) == 1
        next_feed = result.created_follow_up_tasks[0]
        assert next_feed.task_template_id == "builtin:feed_fruit"
        assert next_feed.workflow_node_id == "start"
        assert next_feed.parent_task_id == remove_food.task_id
        assert next_feed.generation_reason is CareTaskGenerationReason.FOLLOW_UP
        assert len(task_repository.all()) == 2

    asyncio.run(_run())


def test_reconcile_pending_operation_finishes_missing_follow_up() -> None:
    """Startup reconciliation resumes an interrupted terminal resolution safely."""

    async def _run() -> None:
        feed_task = replace(
            _feed_task(),
            status=CareTaskStatus.COMPLETED,
            completed_at=datetime(2026, 8, 3, 12, 30, tzinfo=UTC),
            outcome=TaskOutcome(outcome_id="ate_normally"),
            resolution_action="complete",
            resolution_source="test",
            resolution_key="reconcile-key",
        )
        engine, task_repository, event_store = await _build_engine(feed_task)
        reconciled = await engine.async_reconcile_pending_operations()

        assert reconciled == (TASK_ID,)
        updated = task_repository.get(TASK_ID)
        assert updated.resolution_reconciled_at is not None
        assert len(await event_store.async_list_events()) == 1
        assert len(task_repository.all()) == 2

    asyncio.run(_run())


def test_resolution_request_normalizes_and_freezes_json_payloads() -> None:
    """Resolution requests normalize text and freeze JSON-compatible values."""
    request = CareTaskResolutionRequest(
        action="complete",
        outcome_id=" ate_normally ",
        outcome_metadata={"quantity": 2, "foods": ["papaya"]},
        notes=" finished ",
        attachment_references=(" photo-1 ",),
        actor_id=" keeper-1 ",
        source=" service ",
        completed_at=datetime(2026, 8, 3, 12, tzinfo=UTC),
        environmental_context={"temperatures": [78, 79]},
    )

    assert request.outcome_id == "ate_normally"
    assert request.notes == "finished"
    assert request.attachment_references == ("photo-1",)
    assert request.actor_id == "keeper-1"
    assert request.source == "service"
    assert request.outcome_metadata["foods"] == ("papaya",)
    assert request.environmental_context["temperatures"] == (78, 79)


def test_resolution_request_rejects_non_json_metadata() -> None:
    """Resolution requests reject non-JSON-compatible structured metadata."""
    with pytest.raises(ValueError, match="JSON-compatible"):
        CareTaskResolutionRequest(
            action=ResolutionAction.COMPLETE,
            outcome_metadata={"bad": object()},
        )


def test_resolve_missing_task_fails_clearly() -> None:
    """Resolving a missing task surfaces a task-not-found error."""

    async def _run() -> None:
        engine, _, _ = await _build_engine()
        with pytest.raises(CareTaskResolutionNotAllowedError, match="task not found"):
            await engine.async_resolve_task(
                TASK_ID,
                CareTaskResolutionRequest(action=ResolutionAction.COMPLETE),
            )

    asyncio.run(_run())


def test_cancel_defaults_cancelled_outcome() -> None:
    """Cancel requests use the template's cancelled outcome automatically."""

    async def _run() -> None:
        engine, _, _ = await _build_engine(_feed_task())
        result = await engine.async_resolve_task(
            TASK_ID,
            CareTaskResolutionRequest(
                action=ResolutionAction.CANCEL,
                completed_at=datetime(2026, 8, 3, 12, 5, tzinfo=UTC),
            ),
        )

        assert result.task.status is CareTaskStatus.CANCELLED
        assert result.task.outcome is not None
        assert result.task.outcome.outcome_id == "cancelled"

    asyncio.run(_run())


def test_missing_required_context_field_fails() -> None:
    """Required context definitions are enforced before persistence."""

    async def _run() -> None:
        engine, _, _ = await _build_engine(_feed_task())
        definition = TaskContextFieldDefinition(
            field_id="photo",
            display_name="Photo",
            field_type=ContextFieldType.PHOTO,
            required=True,
        )
        template = replace(
            engine._task_templates.get("builtin:feed_fruit"),  # type: ignore[attr-defined]
            context_fields=(definition,),
        )
        task = _feed_task()
        with pytest.raises(InvalidTaskContextError, match="missing required context"):
            engine._normalize_request(  # type: ignore[attr-defined]
                task,
                template,
                CareTaskResolutionRequest(
                    action=ResolutionAction.COMPLETE,
                    outcome_id="ate_normally",
                ),
            )

    asyncio.run(_run())


def test_context_value_validation_rejects_wrong_types() -> None:
    """Each context field type rejects incompatible values."""
    checks = (
        (
            TaskContextFieldDefinition(
                field_id="text_field",
                display_name="Text",
                field_type=ContextFieldType.TEXT,
            ),
            12,
            "must be text",
        ),
        (
            TaskContextFieldDefinition(
                field_id="number_field",
                display_name="Number",
                field_type=ContextFieldType.NUMBER,
            ),
            True,
            "must be numeric",
        ),
        (
            TaskContextFieldDefinition(
                field_id="duration_field",
                display_name="Duration",
                field_type=ContextFieldType.DURATION,
            ),
            -1,
            "non-negative duration",
        ),
        (
            TaskContextFieldDefinition(
                field_id="photo_field",
                display_name="Photo",
                field_type=ContextFieldType.PHOTO,
            ),
            5,
            "photo reference string",
        ),
    )

    for definition, value, message in checks:
        with pytest.raises(InvalidTaskContextError, match=message):
            CareEngine._validate_context_value(definition.field_id, definition, value)


def test_workflow_evaluator_returns_noop_when_no_transition_matches() -> None:
    """No matching transition returns a declarative no-op effect."""
    graph = WorkflowGraph(
        workflow_id="custom:test_graph",
        display_name="Test Graph",
        description="No-op",
        version=1,
        start_node="start",
        nodes=(
            WorkflowNode(node_id="start", node_type=WorkflowNodeType.START),
            WorkflowNode(node_id="end", node_type=WorkflowNodeType.END),
        ),
        transitions=(
            WorkflowTransition(
                from_node="start",
                to_node="end",
                trigger=WorkflowTrigger(
                    trigger_type=WorkflowTriggerType.OUTCOME_SELECTED,
                    outcome_id="ate_normally",
                ),
            ),
        ),
    )
    evaluator = WorkflowEvaluator(WorkflowRegistry((graph,)))
    effects = evaluator.evaluate(
        task=replace(_feed_task(), workflow_id=graph.workflow_id),
        template=TaskTemplateRegistry.load_builtin_templates().get(
            "builtin:feed_fruit"
        ),
        resolution=CareTaskResolutionRequest(
            action=ResolutionAction.COMPLETE,
            outcome_id="refused",
        ),
    )

    assert len(effects) == 1
    assert isinstance(effects[0], NoOpEffect)


def test_workflow_evaluator_supports_create_event_effect() -> None:
    """Create-care-event nodes produce declarative event effects."""
    graph = WorkflowGraph(
        workflow_id="custom:test_graph",
        display_name="Test Graph",
        description="Create event",
        version=1,
        start_node="start",
        nodes=(
            WorkflowNode(node_id="start", node_type=WorkflowNodeType.START),
            WorkflowNode(
                node_id="event_node",
                node_type=WorkflowNodeType.ACTION,
                action=WorkflowActionDefinition(
                    action_type=WorkflowActionType.CREATE_CARE_EVENT,
                    display_name="Create event",
                    metadata={"event_type": "feeding"},
                ),
            ),
            WorkflowNode(node_id="end", node_type=WorkflowNodeType.END),
        ),
        transitions=(
            WorkflowTransition(
                from_node="start",
                to_node="event_node",
                trigger=WorkflowTrigger(
                    trigger_type=WorkflowTriggerType.OUTCOME_SELECTED,
                    outcome_id="ate_normally",
                ),
            ),
            WorkflowTransition(
                from_node="event_node",
                to_node="end",
                trigger=WorkflowTrigger(
                    trigger_type=WorkflowTriggerType.TASK_COMPLETED,
                ),
            ),
        ),
    )
    evaluator = WorkflowEvaluator(WorkflowRegistry((graph,)))
    effects = evaluator.evaluate(
        task=replace(_feed_task(), workflow_id=graph.workflow_id),
        template=TaskTemplateRegistry.load_builtin_templates().get(
            "builtin:feed_fruit"
        ),
        resolution=CareTaskResolutionRequest(
            action=ResolutionAction.COMPLETE,
            outcome_id="ate_normally",
        ),
    )

    assert len(effects) == 1
    assert effects[0].effect_id == "event_node"


def test_workflow_evaluator_reports_invalid_effect_definitions() -> None:
    """Malformed workflow action metadata fails clearly."""
    create_task_graph = WorkflowGraph(
        workflow_id="custom:bad_task_graph",
        display_name="Bad Task Graph",
        description="Invalid task effect",
        version=1,
        start_node="start",
        nodes=(
            WorkflowNode(node_id="start", node_type=WorkflowNodeType.START),
            WorkflowNode(
                node_id="task_node",
                node_type=WorkflowNodeType.ACTION,
                action=WorkflowActionDefinition(
                    action_type=WorkflowActionType.CREATE_TASK,
                    display_name="Create task",
                    metadata={},
                ),
            ),
            WorkflowNode(node_id="end", node_type=WorkflowNodeType.END),
        ),
        transitions=(
            WorkflowTransition(
                from_node="start",
                to_node="task_node",
                trigger=WorkflowTrigger(
                    trigger_type=WorkflowTriggerType.OUTCOME_SELECTED,
                    outcome_id="ate_normally",
                ),
            ),
            WorkflowTransition(
                from_node="task_node",
                to_node="end",
                trigger=WorkflowTrigger(
                    trigger_type=WorkflowTriggerType.TASK_COMPLETED,
                ),
            ),
        ),
    )
    event_graph = WorkflowGraph(
        workflow_id="custom:bad_event_graph",
        display_name="Bad Event Graph",
        description="Invalid event effect",
        version=1,
        start_node="start",
        nodes=(
            WorkflowNode(node_id="start", node_type=WorkflowNodeType.START),
            WorkflowNode(
                node_id="event_node",
                node_type=WorkflowNodeType.ACTION,
                action=WorkflowActionDefinition(
                    action_type=WorkflowActionType.CREATE_CARE_EVENT,
                    display_name="Create event",
                    metadata={},
                ),
            ),
            WorkflowNode(node_id="end", node_type=WorkflowNodeType.END),
        ),
        transitions=(
            WorkflowTransition(
                from_node="start",
                to_node="event_node",
                trigger=WorkflowTrigger(
                    trigger_type=WorkflowTriggerType.OUTCOME_SELECTED,
                    outcome_id="ate_normally",
                ),
            ),
            WorkflowTransition(
                from_node="event_node",
                to_node="end",
                trigger=WorkflowTrigger(
                    trigger_type=WorkflowTriggerType.TASK_COMPLETED,
                ),
            ),
        ),
    )

    for graph, message in (
        (create_task_graph, "template_id"),
        (event_graph, "event_type"),
    ):
        evaluator = WorkflowEvaluator(WorkflowRegistry((graph,)))
        with pytest.raises(InvalidWorkflowEffectError, match=message):
            evaluator.evaluate(
                task=replace(_feed_task(), workflow_id=graph.workflow_id),
                template=TaskTemplateRegistry.load_builtin_templates().get(
                    "builtin:feed_fruit"
                ),
                resolution=CareTaskResolutionRequest(
                    action=ResolutionAction.COMPLETE,
                    outcome_id="ate_normally",
                ),
            )


def test_workflow_evaluator_raises_for_missing_graph_reference() -> None:
    """Missing workflow references fail through the evaluator boundary."""
    evaluator = WorkflowEvaluator(WorkflowRegistry(()))
    with pytest.raises(MissingWorkflowGraphReferenceError, match="missing workflow"):
        evaluator.evaluate(
            task=_feed_task(),
            template=TaskTemplateRegistry.load_builtin_templates().get(
                "builtin:feed_fruit"
            ),
            resolution=CareTaskResolutionRequest(
                action=ResolutionAction.COMPLETE,
                outcome_id="ate_normally",
            ),
        )


def test_engine_static_helpers_cover_delay_and_identity_branches() -> None:
    """Static helpers preserve deterministic identity and delay behavior."""
    task = _feed_task()
    effect = replace(
        next(
            effect
            for effect in WorkflowEvaluator(
                WorkflowRegistry.load_builtin_workflows()
            ).evaluate(
                task=_feed_task(),
                template=TaskTemplateRegistry.load_builtin_templates().get(
                    "builtin:feed_fruit"
                ),
                resolution=CareTaskResolutionRequest(
                    action=ResolutionAction.COMPLETE,
                    outcome_id="ate_normally",
                ),
            )
            if effect.__class__.__name__ == "CreateTaskEffect"
        ),
        delay=WorkflowDelay(amount=2, unit=WorkflowDelayUnit.MINUTES),
    )
    invalid_chain_task = type(
        "TaskLike",
        (),
        {
            "task_id": task.task_id,
            "workflow_id": task.workflow_id,
            "generation_key": task.generation_key,
            "workflow_chain_id": "not-a-uuid",
        },
    )()

    assert (
        len(
            CareEngine._resolution_key(
                task, CareTaskResolutionRequest(action=ResolutionAction.SKIP)
            )
        )
        == 64
    )
    assert len(CareEngine._follow_up_generation_key(invalid_chain_task, effect)) == 64
    assert CareEngine._apply_delay(
        datetime(2026, 1, 31, 12, tzinfo=UTC),
        WorkflowDelay(amount=1, unit=WorkflowDelayUnit.MONTHS),
    ) == datetime(2026, 2, 28, 12, tzinfo=UTC)
    assert CareEngine._apply_delay(
        datetime(2026, 8, 3, 12, tzinfo=UTC),
        WorkflowDelay(amount=1, unit=WorkflowDelayUnit.WEEKS),
    ) == datetime(2026, 8, 10, 12, tzinfo=UTC)
    assert CareEngine._apply_delay(
        datetime(2026, 8, 3, 12, tzinfo=UTC),
        effect.delay,
    ) == datetime(2026, 8, 3, 12, 2, tzinfo=UTC)


def test_engine_helper_errors_are_reported_clearly() -> None:
    """Helper methods fail clearly for invalid template event metadata and keys."""
    with pytest.raises(CareEnginePersistenceError, match="resolution_key"):
        CareEngine._primary_event_id(_feed_task())
    with pytest.raises(InvalidWorkflowEffectError, match="event_type is required"):
        CareEngine._event_type_for_template(CompletionBehavior(metadata={}))


def test_follow_up_missing_template_fails() -> None:
    """Missing follow-up template references surface as application errors."""

    async def _run() -> None:
        engine, _, _ = await _build_engine(_feed_task())
        with pytest.raises(MissingTaskTemplateReferenceError, match="missing"):
            await engine._ensure_follow_up_task(  # type: ignore[attr-defined]
                replace(
                    _feed_task(),
                    status=CareTaskStatus.COMPLETED,
                    completed_at=datetime(2026, 8, 3, 12, tzinfo=UTC),
                    resolution_key="follow-up-test",
                ),
                effect=CreateTaskEffect(
                    effect_id="missing_task",
                    template_id="builtin:missing",
                    workflow_node_id="missing_task",
                ),
            )

    asyncio.run(_run())
