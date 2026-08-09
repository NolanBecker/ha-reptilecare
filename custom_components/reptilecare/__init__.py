"""The ReptileCare integration."""

from __future__ import annotations

from datetime import UTC, datetime
import logging

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    OperationNotAllowed,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError

from .application import CareEngine, WorkflowEvaluator
from .care_plan_storage import HomeAssistantCarePlanPersistence
from .care_task_storage import HomeAssistantCareTaskPersistence
from .content.async_loader import async_load_builtin_content
from .content.models import ContentError
from .coordinator import ReptileCareCoordinator
from .domain.care_plan import CarePlanError, CarePlanRepository
from .domain.care_task import CareTaskError, CareTaskRepository
from .domain.reptile import ReptileError, ReptileRepository
from .domain.species import SpeciesProfileError, SpeciesProfileRegistry
from .domain.task_template import TaskTemplateError, TaskTemplateRegistry
from .domain.workflow import WorkflowError, WorkflowRegistry
from .entity_projection import ReptileCareEntityProjection
from .frontend_support import (
    async_register_frontend_assets,
    async_unregister_frontend_assets,
)
from .models import ReptileCareRuntimeData
from .onboarding import async_apply_onboarding, deserialize_request
from .reptile_storage import HomeAssistantReptilePersistence
from .runtime_updates import HomeAssistantRuntimeEventPublisher
from .services import async_register_services, async_unregister_services
from .storage import HomeAssistantCareEventStore
from .task_generation import CareTaskGenerator, ScheduleCalculator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: tuple[Platform, ...] = (
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
)


async def async_setup_entry(hass: HomeAssistant, entry: ReptileCareConfigEntry) -> bool:
    """Set up ReptileCare from a config entry."""
    try:
        content_result = await async_load_builtin_content(hass)
    except (ContentError, OSError) as err:
        raise ConfigEntryError("Unable to load built-in ReptileCare content") from err
    for warning in content_result.warnings:
        _LOGGER.warning("Built-in content warning: %s", warning)
    try:
        species_profiles = await hass.async_add_executor_job(
            SpeciesProfileRegistry.load_builtin_profiles
        )
    except SpeciesProfileError as err:
        raise ConfigEntryError("Unable to load built-in species profiles") from err
    try:
        task_templates = await hass.async_add_executor_job(
            TaskTemplateRegistry.load_builtin_templates
        )
    except TaskTemplateError as err:
        raise ConfigEntryError("Unable to load built-in task templates") from err
    try:
        workflow_graphs = await hass.async_add_executor_job(
            WorkflowRegistry.load_builtin_workflows
        )
    except WorkflowError as err:
        raise ConfigEntryError("Unable to load built-in workflow graphs") from err

    reptile_repository = ReptileRepository(
        species_profiles,
        HomeAssistantReptilePersistence(hass, entry.entry_id),
    )
    try:
        await reptile_repository.async_load()
    except ReptileError as err:
        raise ConfigEntryError("Unable to load ReptileCare reptiles") from err
    care_plan_repository = CarePlanRepository(
        reptile_repository,
        task_templates,
        workflow_graphs,
        HomeAssistantCarePlanPersistence(hass, entry.entry_id),
    )
    try:
        await care_plan_repository.async_load()
    except CarePlanError as err:
        raise ConfigEntryError("Unable to load ReptileCare care plans") from err
    care_task_repository = CareTaskRepository(
        reptile_repository,
        care_plan_repository,
        task_templates,
        workflow_graphs,
        HomeAssistantCareTaskPersistence(hass, entry.entry_id),
    )
    try:
        await care_task_repository.async_load()
    except CareTaskError as err:
        raise ConfigEntryError("Unable to load ReptileCare care tasks") from err

    schedule_calculator = ScheduleCalculator()
    store = HomeAssistantCareEventStore(hass, entry.entry_id)
    await store.async_load()
    workflow_evaluator = WorkflowEvaluator(workflow_graphs)
    coordinator = ReptileCareCoordinator(
        hass=hass,
        config_entry=entry,
        event_store=store,
    )
    event_publisher = HomeAssistantRuntimeEventPublisher(hass, coordinator, store)
    care_engine = CareEngine(
        care_task_repository,
        task_templates,
        workflow_graphs,
        store,
        workflow_evaluator,
        event_publisher=event_publisher,
    )
    care_task_generator = CareTaskGenerator(
        reptile_repository,
        care_plan_repository,
        task_templates,
        workflow_graphs,
        care_task_repository,
        schedule_calculator,
        event_publisher=event_publisher,
    )
    entry.runtime_data = ReptileCareRuntimeData(
        coordinator=coordinator,
        event_store=store,
        content=content_result.bundle,
        species_profiles=species_profiles,
        reptile_repository=reptile_repository,
        task_templates=task_templates,
        workflow_graphs=workflow_graphs,
        care_plan_repository=care_plan_repository,
        care_task_repository=care_task_repository,
        schedule_calculator=schedule_calculator,
        care_task_generator=care_task_generator,
        workflow_evaluator=workflow_evaluator,
        care_engine=care_engine,
        entity_projection=None,  # type: ignore[arg-type]
        event_publisher=event_publisher,
    )

    onboarding_data = entry.data.get("onboarding")
    if isinstance(onboarding_data, dict) and not reptile_repository.all():
        await async_apply_onboarding(
            entry.runtime_data,
            deserialize_request(onboarding_data),
            now=datetime.now(UTC),
        )
        hass.config_entries.async_update_entry(entry, data={})

    await care_engine.async_reconcile_pending_operations()

    generation_result = None
    if entry.options.get("generate_tasks_on_startup", True):
        generation_result = await care_task_generator.async_generate(
            now=datetime.now(UTC)
        )
    if generation_result is not None and generation_result.errors:
        for care_plan_id, message in generation_result.errors.items():
            _LOGGER.warning(
                "CareTask generation skipped plan %s during setup: %s",
                care_plan_id,
                message,
            )

    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryError as err:
        if "async_config_entry_first_refresh" not in str(err):
            raise
        await coordinator.async_refresh()
    entity_projection = ReptileCareEntityProjection(
        reptile_repository,
        care_plan_repository,
        care_task_repository,
        task_templates,
        species_profiles,
        lambda: coordinator.timeline,
    )

    entry.runtime_data.entity_projection = entity_projection
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    async_register_services(hass)
    await async_register_frontend_assets(hass)

    if PLATFORMS:
        try:
            await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        except OperationNotAllowed:
            if entry.state is not ConfigEntryState.NOT_LOADED:
                raise

    _LOGGER.info("ReptileCare initialized")
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ReptileCareConfigEntry
) -> bool:
    """Unload a ReptileCare config entry."""
    unload_ok = not PLATFORMS or await hass.config_entries.async_unload_platforms(
        entry, PLATFORMS
    )
    if unload_ok:
        async_unregister_frontend_assets(hass)
        async_unregister_services(hass)
        _LOGGER.info("ReptileCare unloaded")
    return unload_ok


async def _async_reload_entry(
    hass: HomeAssistant, entry: ReptileCareConfigEntry
) -> None:
    """Reload ReptileCare when its config entry is updated."""
    await hass.config_entries.async_reload(entry.entry_id)


type ReptileCareConfigEntry = ConfigEntry[ReptileCareRuntimeData]
