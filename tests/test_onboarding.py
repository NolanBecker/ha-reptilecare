"""Tests for onboarding and demo-data installation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from custom_components.reptilecare.content.loader import load_builtin_content
from custom_components.reptilecare.domain.care_plan import (
    CarePlanRepository,
    MemoryCarePlanPersistence,
)
from custom_components.reptilecare.domain.care_task import (
    CareTaskRepository,
    MemoryCareTaskPersistence,
)
from custom_components.reptilecare.domain.reptile import (
    MemoryReptilePersistence,
    ReptileRepository,
)
from custom_components.reptilecare.domain.species import SpeciesProfileRegistry
from custom_components.reptilecare.domain.task_template import TaskTemplateRegistry
from custom_components.reptilecare.domain.workflow import WorkflowRegistry
from custom_components.reptilecare.models import CareEventType
from custom_components.reptilecare.onboarding import (
    OnboardingRequest,
    async_apply_onboarding,
    async_import_demo_data,
)
from custom_components.reptilecare.storage import MemoryCareEventStore
from custom_components.reptilecare.task_generation import (
    CareTaskGenerator,
    ScheduleCalculator,
)


@dataclass
class _FakePublisher:
    published: list[tuple[object, ...]]

    async def async_publish(self, event: object) -> None:
        self.published.append((event,))

    async def async_publish_many(self, events: tuple[object, ...]) -> None:
        self.published.append(events)


@dataclass
class _Runtime:
    content: Any
    reptile_repository: ReptileRepository
    care_plan_repository: CarePlanRepository
    care_task_generator: CareTaskGenerator
    event_publisher: _FakePublisher
    event_store: MemoryCareEventStore


@pytest.mark.asyncio
async def test_apply_onboarding_creates_reptile_care_plans_and_tasks() -> None:
    """Onboarding should create a keeper-ready first reptile without service calls."""
    content = load_builtin_content().bundle
    species_profiles = SpeciesProfileRegistry.load_builtin_profiles()
    task_templates = TaskTemplateRegistry.load_builtin_templates()
    workflows = WorkflowRegistry.load_builtin_workflows()
    reptile_repository = ReptileRepository(species_profiles, MemoryReptilePersistence())
    care_plan_repository = CarePlanRepository(
        reptile_repository,
        task_templates,
        workflows,
        MemoryCarePlanPersistence(),
    )
    task_repository = CareTaskRepository(
        reptile_repository,
        care_plan_repository,
        task_templates,
        workflows,
        MemoryCareTaskPersistence(),
    )
    await reptile_repository.async_load()
    await care_plan_repository.async_load()
    await task_repository.async_load()
    event_store = MemoryCareEventStore()
    publisher = _FakePublisher([])
    runtime = _Runtime(
        content=content,
        reptile_repository=reptile_repository,
        care_plan_repository=care_plan_repository,
        care_task_generator=CareTaskGenerator(
            reptile_repository,
            care_plan_repository,
            task_templates,
            workflows,
            task_repository,
            ScheduleCalculator(),
            event_publisher=publisher,
        ),
        event_publisher=publisher,
        event_store=event_store,
    )

    result = await async_apply_onboarding(
        runtime,  # type: ignore[arg-type]
        OnboardingRequest(
            display_name="Pixel",
            nickname="Pix",
            species_id="builtin:gargoyle_gecko",
            selected_care_plan_ids=(
                "builtin:feed_fruit_every_2_days",
                "builtin:spot_clean_daily",
            ),
            generate_initial_tasks=True,
            notes="First reptile",
        ),
        now=datetime(2026, 8, 6, 12, 0, tzinfo=UTC),
    )

    assert result.reptile.slug == "pixel"
    assert result.reptile.species_profile_id == "builtin:gargoyle_gecko"
    assert "Nickname: Pix" in (result.reptile.notes or "")
    assert len(result.care_plans) == 2
    assert result.generated_task_ids
    assert len(runtime.reptile_repository.all()) == 1
    assert len(runtime.care_plan_repository.all()) == 2
    assert publisher.published


@pytest.mark.asyncio
async def test_import_demo_data_adds_history() -> None:
    """Optional demo data should install a reptile, care plans, and sample history."""
    content = load_builtin_content().bundle
    species_profiles = SpeciesProfileRegistry.load_builtin_profiles()
    task_templates = TaskTemplateRegistry.load_builtin_templates()
    workflows = WorkflowRegistry.load_builtin_workflows()
    reptile_repository = ReptileRepository(species_profiles, MemoryReptilePersistence())
    care_plan_repository = CarePlanRepository(
        reptile_repository,
        task_templates,
        workflows,
        MemoryCarePlanPersistence(),
    )
    task_repository = CareTaskRepository(
        reptile_repository,
        care_plan_repository,
        task_templates,
        workflows,
        MemoryCareTaskPersistence(),
    )
    await reptile_repository.async_load()
    await care_plan_repository.async_load()
    await task_repository.async_load()
    event_store = MemoryCareEventStore()
    publisher = _FakePublisher([])
    runtime = _Runtime(
        content=content,
        reptile_repository=reptile_repository,
        care_plan_repository=care_plan_repository,
        care_task_generator=CareTaskGenerator(
            reptile_repository,
            care_plan_repository,
            task_templates,
            workflows,
            task_repository,
            ScheduleCalculator(),
            event_publisher=publisher,
        ),
        event_publisher=publisher,
        event_store=event_store,
    )

    result = await async_import_demo_data(
        runtime,  # type: ignore[arg-type]
        now=datetime(2026, 8, 6, 12, 0, tzinfo=UTC),
    )

    assert result.reptile.display_name == "Pixel"
    events = await event_store.async_list_events()
    assert len(events) == 1
    assert events[0].event_type is CareEventType.FEEDING
