"""Tests for ReptileCare setup and lifecycle."""

from datetime import datetime

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.reptilecare.const import DOMAIN, INTEGRATION_NAME
from custom_components.reptilecare.domain.reptile import Reptile
from custom_components.reptilecare.models import (
    CareEvent,
    CareEventType,
    ReptileCareRuntimeData,
    ReptileCareSnapshot,
)
from custom_components.reptilecare.task_generation import TaskGenerationResult

PIXEL_ID = "550e8400-e29b-41d4-a716-446655440000"


async def test_setup_and_unload_entry(hass: HomeAssistant) -> None:
    """Test setting up and unloading ReptileCare."""
    entry = MockConfigEntry(domain=DOMAIN, title=INTEGRATION_NAME, data={})
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert isinstance(entry.runtime_data, ReptileCareRuntimeData)
    assert entry.runtime_data.coordinator.data.events == ()
    assert entry.runtime_data.coordinator.timeline.all_events() == ()
    assert entry.runtime_data.timeline.all_events() == ()
    assert len(entry.runtime_data.content.species.all()) == 5
    assert entry.runtime_data.content.species.contains("builtin:gargoyle_gecko")
    assert entry.runtime_data.species_profiles.contains("builtin:gargoyle_gecko")
    assert entry.runtime_data.task_templates.contains("builtin:feed_fruit")
    assert entry.runtime_data.workflow_graphs.contains("builtin:feeding_cycle")
    assert entry.runtime_data.care_plan_repository.all() == ()
    assert entry.runtime_data.care_task_repository.all() == ()
    assert entry.runtime_data.reptile_repository.all() == ()
    assert entry.runtime_data.workflow_evaluator is not None
    assert entry.runtime_data.care_engine is not None

    event = CareEvent(reptile_id=PIXEL_ID, event_type=CareEventType.FEEDING)
    snapshot = ReptileCareSnapshot(events=(event,))
    entry.runtime_data.coordinator.async_handle_event(snapshot)
    assert entry.runtime_data.coordinator.timeline.latest_event() is event

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_setup_uses_executor_for_builtin_loaders(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Setup should route built-in loader file I/O through the executor."""
    from custom_components.reptilecare import async_setup_entry
    from custom_components.reptilecare.content.loader import load_builtin_content
    from custom_components.reptilecare.domain.species import SpeciesProfileRegistry
    from custom_components.reptilecare.domain.task_template import TaskTemplateRegistry
    from custom_components.reptilecare.domain.workflow import WorkflowRegistry

    calls: list[object] = []
    original = hass.async_add_executor_job

    async def _spy(func, *args):
        calls.append(func)
        return await original(func, *args)

    monkeypatch.setattr(hass, "async_add_executor_job", _spy)

    entry = MockConfigEntry(domain=DOMAIN, title=INTEGRATION_NAME, data={})
    assert await async_setup_entry(hass, entry)

    assert load_builtin_content in calls
    assert SpeciesProfileRegistry.load_builtin_profiles in calls
    assert TaskTemplateRegistry.load_builtin_templates in calls
    assert WorkflowRegistry.load_builtin_workflows in calls


async def test_reload_rebuilds_species_registry(hass: HomeAssistant) -> None:
    """Reloading reconstructs and exposes the built-in profile registry."""
    entry = MockConfigEntry(domain=DOMAIN, title=INTEGRATION_NAME, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    original_registry = entry.runtime_data.species_profiles
    original_content = entry.runtime_data.content
    original_repository = entry.runtime_data.reptile_repository
    original_templates = entry.runtime_data.task_templates
    original_workflows = entry.runtime_data.workflow_graphs
    original_care_plans = entry.runtime_data.care_plan_repository
    original_tasks = entry.runtime_data.care_task_repository
    original_evaluator = entry.runtime_data.workflow_evaluator
    original_engine = entry.runtime_data.care_engine
    pixel = Reptile(
        reptile_id=PIXEL_ID,
        display_name="Pixel",
        species_profile_id="builtin:gargoyle_gecko",
        slug="pixel",
    )
    await original_repository.async_add(pixel)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.species_profiles is not original_registry
    assert entry.runtime_data.content is not original_content
    assert entry.runtime_data.reptile_repository is not original_repository
    assert entry.runtime_data.task_templates is not original_templates
    assert entry.runtime_data.workflow_graphs is not original_workflows
    assert entry.runtime_data.care_plan_repository is not original_care_plans
    assert entry.runtime_data.care_task_repository is not original_tasks
    assert entry.runtime_data.workflow_evaluator is not original_evaluator
    assert entry.runtime_data.care_engine is not original_engine
    assert entry.runtime_data.reptile_repository.get(PIXEL_ID) == pixel
    assert entry.runtime_data.species_profiles.contains("builtin:gargoyle_gecko")
    assert entry.runtime_data.task_templates.contains("builtin:feed_fruit")
    assert entry.runtime_data.workflow_graphs.contains("builtin:feeding_cycle")
    assert entry.runtime_data.care_plan_repository.all() == ()
    assert entry.runtime_data.care_task_repository.all() == ()


async def test_setup_applies_pending_onboarding_request(hass: HomeAssistant) -> None:
    """Setup materializes reptiles and care plans from pending onboarding data."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=INTEGRATION_NAME,
        data={
            "onboarding": {
                "display_name": "Pixel",
                "nickname": "Pix",
                "species_id": "builtin:gargoyle_gecko",
                "selected_care_plan_ids": [
                    "builtin:feed_fruit_every_2_days",
                    "builtin:spot_clean_daily",
                ],
                "generate_initial_tasks": True,
                "notes": "First reptile",
            }
        },
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    reptiles = entry.runtime_data.reptile_repository.all()
    care_plans = entry.runtime_data.care_plan_repository.all()
    tasks = entry.runtime_data.care_task_repository.all()

    assert len(reptiles) == 1
    assert reptiles[0].display_name == "Pixel"
    assert reptiles[0].slug == "pixel"
    assert len(care_plans) == 2
    assert {plan.display_name for plan in care_plans} == {
        "Feed Fruit Mix",
        "Spot Cleaning",
    }
    assert tasks


async def test_setup_runs_reconciliation_before_task_generation(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Setup reconciles persisted care operations before generating new tasks."""
    from custom_components.reptilecare import CareTaskGenerator
    from custom_components.reptilecare.application import CareEngine

    steps: list[str] = []
    calls: list[datetime] = []

    async def _reconcile(self: CareEngine) -> tuple[str, ...]:
        steps.append("reconcile")
        return ()

    async def _generate(
        self: CareTaskGenerator,
        *,
        now: datetime,
        **_: object,
    ) -> TaskGenerationResult:
        steps.append("generate")
        calls.append(now)
        return TaskGenerationResult()

    monkeypatch.setattr(CareEngine, "async_reconcile_pending_operations", _reconcile)
    monkeypatch.setattr(CareTaskGenerator, "async_generate", _generate)

    entry = MockConfigEntry(domain=DOMAIN, title=INTEGRATION_NAME, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert steps == ["reconcile", "generate"]
    assert len(calls) == 1
    assert calls[0].tzinfo is not None


async def test_invalid_builtin_profile_fails_setup(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invalid bundled profile data fails setup with a clear config-entry error."""
    from custom_components.reptilecare import (
        SpeciesProfileRegistry,
        async_setup_entry,
    )
    from custom_components.reptilecare.domain.species import InvalidSpeciesProfileError

    def _raise_invalid_profile() -> None:
        raise InvalidSpeciesProfileError("invalid packaged profile")

    monkeypatch.setattr(
        SpeciesProfileRegistry, "load_builtin_profiles", _raise_invalid_profile
    )
    entry = MockConfigEntry(domain=DOMAIN, title=INTEGRATION_NAME, data={})
    with pytest.raises(ConfigEntryError, match="built-in species profiles"):
        await async_setup_entry(hass, entry)


async def test_invalid_builtin_content_fails_setup(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fatal built-in content errors should fail setup cleanly."""
    from custom_components.reptilecare import async_setup_entry
    from custom_components.reptilecare.content.models import InvalidContentError

    def _raise_invalid_content() -> None:
        raise InvalidContentError("invalid packaged content")

    monkeypatch.setattr(
        "custom_components.reptilecare.content.async_loader.load_builtin_content",
        _raise_invalid_content,
    )

    entry = MockConfigEntry(domain=DOMAIN, title=INTEGRATION_NAME, data={})
    with pytest.raises(ConfigEntryError, match="built-in ReptileCare content"):
        await async_setup_entry(hass, entry)


async def test_invalid_builtin_task_template_fails_setup(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invalid bundled task template data fails setup clearly."""
    from custom_components.reptilecare import TaskTemplateRegistry, async_setup_entry
    from custom_components.reptilecare.domain.task_template import (
        InvalidTaskTemplateError,
    )

    def _raise_invalid_template() -> None:
        raise InvalidTaskTemplateError("invalid packaged task template")

    monkeypatch.setattr(
        TaskTemplateRegistry, "load_builtin_templates", _raise_invalid_template
    )
    entry = MockConfigEntry(domain=DOMAIN, title=INTEGRATION_NAME, data={})
    with pytest.raises(ConfigEntryError, match="built-in task templates"):
        await async_setup_entry(hass, entry)


async def test_invalid_builtin_workflow_graph_fails_setup(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invalid bundled workflow graph data fails setup clearly."""
    from custom_components.reptilecare import WorkflowRegistry, async_setup_entry
    from custom_components.reptilecare.domain.workflow import InvalidWorkflowError

    def _raise_invalid_workflow() -> None:
        raise InvalidWorkflowError("invalid packaged workflow graph")

    monkeypatch.setattr(
        WorkflowRegistry, "load_builtin_workflows", _raise_invalid_workflow
    )
    entry = MockConfigEntry(domain=DOMAIN, title=INTEGRATION_NAME, data={})
    with pytest.raises(ConfigEntryError, match="built-in workflow graphs"):
        await async_setup_entry(hass, entry)


async def test_reptile_repository_load_failure_fails_setup(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reptile persistence load failures surface as config-entry errors."""
    from custom_components.reptilecare import ReptileRepository, async_setup_entry
    from custom_components.reptilecare.domain.reptile import ReptileError

    async def _raise_reptile_error(self: ReptileRepository) -> None:
        raise ReptileError("unable to load reptiles")

    monkeypatch.setattr(ReptileRepository, "async_load", _raise_reptile_error)
    entry = MockConfigEntry(domain=DOMAIN, title=INTEGRATION_NAME, data={})
    with pytest.raises(ConfigEntryError, match="load ReptileCare reptiles"):
        await async_setup_entry(hass, entry)


async def test_care_plan_repository_load_failure_fails_setup(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CarePlan persistence load failures surface as config-entry errors."""
    from custom_components.reptilecare import CarePlanRepository, async_setup_entry
    from custom_components.reptilecare.domain.care_plan import CarePlanError

    async def _raise_care_plan_error(self: CarePlanRepository) -> None:
        raise CarePlanError("unable to load care plans")

    monkeypatch.setattr(CarePlanRepository, "async_load", _raise_care_plan_error)
    entry = MockConfigEntry(domain=DOMAIN, title=INTEGRATION_NAME, data={})
    with pytest.raises(ConfigEntryError, match="load ReptileCare care plans"):
        await async_setup_entry(hass, entry)


async def test_care_task_repository_load_failure_fails_setup(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CareTask persistence load failures surface as config-entry errors."""
    from custom_components.reptilecare import CareTaskRepository, async_setup_entry
    from custom_components.reptilecare.domain.care_task import CareTaskError

    async def _raise_care_task_error(self: CareTaskRepository) -> None:
        raise CareTaskError("unable to load care tasks")

    monkeypatch.setattr(CareTaskRepository, "async_load", _raise_care_task_error)
    entry = MockConfigEntry(domain=DOMAIN, title=INTEGRATION_NAME, data={})
    with pytest.raises(ConfigEntryError, match="load ReptileCare care tasks"):
        await async_setup_entry(hass, entry)


async def test_platform_forwarding_and_unload_paths(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Setup forwards configured platforms and unload returns platform result."""
    from custom_components import reptilecare
    from custom_components.reptilecare import async_setup_entry, async_unload_entry
    from custom_components.reptilecare.coordinator import ReptileCareCoordinator

    entry = MockConfigEntry(domain=DOMAIN, title=INTEGRATION_NAME, data={})
    forwarded: list[tuple[str, tuple[str, ...]]] = []
    unloaded: list[tuple[str, tuple[str, ...]]] = []
    refreshed: list[str] = []

    monkeypatch.setattr(reptilecare, "PLATFORMS", ("sensor",))

    async def _forward_entry_setups(
        config_entry: MockConfigEntry, platforms: tuple[str, ...]
    ) -> None:
        forwarded.append((config_entry.entry_id, platforms))

    async def _unload_platforms(
        config_entry: MockConfigEntry, platforms: tuple[str, ...]
    ) -> bool:
        unloaded.append((config_entry.entry_id, platforms))
        return False

    monkeypatch.setattr(
        hass.config_entries, "async_forward_entry_setups", _forward_entry_setups
    )
    monkeypatch.setattr(
        hass.config_entries, "async_unload_platforms", _unload_platforms
    )

    async def _first_refresh(self: ReptileCareCoordinator) -> None:
        refreshed.append(self.config_entry.entry_id)

    monkeypatch.setattr(
        ReptileCareCoordinator, "async_config_entry_first_refresh", _first_refresh
    )

    assert await async_setup_entry(hass, entry)
    assert refreshed == [entry.entry_id]
    assert forwarded == [(entry.entry_id, ("sensor",))]
    assert await async_unload_entry(hass, entry) is False
    assert unloaded == [(entry.entry_id, ("sensor",))]


async def test_setup_falls_back_to_async_refresh_for_direct_invocation(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Direct setup calls fall back to plain refresh outside HA setup state."""
    from custom_components.reptilecare import async_setup_entry
    from custom_components.reptilecare.coordinator import ReptileCareCoordinator

    entry = MockConfigEntry(domain=DOMAIN, title=INTEGRATION_NAME, data={})
    calls: list[str] = []

    async def _first_refresh(self: ReptileCareCoordinator) -> None:
        calls.append("first_refresh")
        raise ConfigEntryError(
            "`async_config_entry_first_refresh` called when config entry state is "
            "ConfigEntryState.NOT_LOADED"
        )

    async def _refresh(self: ReptileCareCoordinator) -> None:
        calls.append("refresh")

    monkeypatch.setattr(
        ReptileCareCoordinator, "async_config_entry_first_refresh", _first_refresh
    )
    monkeypatch.setattr(ReptileCareCoordinator, "async_refresh", _refresh)

    assert await async_setup_entry(hass, entry)
    assert calls == ["first_refresh", "refresh"]


async def test_setup_logs_generation_warnings(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Setup logs bounded generation warnings without failing startup."""
    from custom_components.reptilecare import CareTaskGenerator, async_setup_entry

    async def _generate(
        self: CareTaskGenerator,
        *,
        now: datetime,
        **_: object,
    ) -> TaskGenerationResult:
        return TaskGenerationResult(errors={PIXEL_ID: "missing template"})

    monkeypatch.setattr(CareTaskGenerator, "async_generate", _generate)

    entry = MockConfigEntry(domain=DOMAIN, title=INTEGRATION_NAME, data={})
    assert await async_setup_entry(hass, entry)
    assert "CareTask generation skipped plan" in caplog.text


async def test_setup_reraises_unexpected_first_refresh_error(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-state refresh failures are not swallowed by the direct-call fallback."""
    from custom_components.reptilecare import async_setup_entry
    from custom_components.reptilecare.coordinator import ReptileCareCoordinator

    async def _first_refresh(self: ReptileCareCoordinator) -> None:
        raise ConfigEntryError("coordinator exploded unexpectedly")

    monkeypatch.setattr(
        ReptileCareCoordinator, "async_config_entry_first_refresh", _first_refresh
    )

    entry = MockConfigEntry(domain=DOMAIN, title=INTEGRATION_NAME, data={})
    with pytest.raises(ConfigEntryError, match="unexpectedly"):
        await async_setup_entry(hass, entry)


async def test_reload_listener_delegates_to_config_entries(
    hass: HomeAssistant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reload callback forwards to Home Assistant's config-entry reload."""
    from custom_components.reptilecare import _async_reload_entry

    entry = MockConfigEntry(domain=DOMAIN, title=INTEGRATION_NAME, data={})
    reloaded: list[str] = []

    async def _reload(entry_id: str) -> bool:
        reloaded.append(entry_id)
        return True

    monkeypatch.setattr(hass.config_entries, "async_reload", _reload)
    await _async_reload_entry(hass, entry)
    assert reloaded == [entry.entry_id]
