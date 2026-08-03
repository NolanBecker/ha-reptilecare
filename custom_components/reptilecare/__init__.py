"""The ReptileCare integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError

from .care_plan_storage import HomeAssistantCarePlanPersistence
from .coordinator import ReptileCareCoordinator
from .domain.care_plan import CarePlanError, CarePlanRepository
from .domain.reptile import ReptileError, ReptileRepository
from .domain.species import SpeciesProfileError, SpeciesProfileRegistry
from .domain.task_template import TaskTemplateError, TaskTemplateRegistry
from .domain.workflow import WorkflowError, WorkflowRegistry
from .reptile_storage import HomeAssistantReptilePersistence
from .storage import HomeAssistantCareEventStore

_LOGGER = logging.getLogger(__name__)

PLATFORMS: tuple[Platform, ...] = ()


async def async_setup_entry(hass: HomeAssistant, entry: ReptileCareConfigEntry) -> bool:
    """Set up ReptileCare from a config entry."""
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

    store = HomeAssistantCareEventStore(hass, entry.entry_id)
    await store.async_load()
    coordinator = ReptileCareCoordinator(
        hass=hass,
        config_entry=entry,
        event_store=store,
    )
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = ReptileCareRuntimeData(
        coordinator=coordinator,
        event_store=store,
        species_profiles=species_profiles,
        reptile_repository=reptile_repository,
        task_templates=task_templates,
        workflow_graphs=workflow_graphs,
        care_plan_repository=care_plan_repository,
    )
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    if PLATFORMS:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

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
        _LOGGER.info("ReptileCare unloaded")
    return unload_ok


async def _async_reload_entry(
    hass: HomeAssistant, entry: ReptileCareConfigEntry
) -> None:
    """Reload ReptileCare when its config entry is updated."""
    await hass.config_entries.async_reload(entry.entry_id)


from .models import ReptileCareRuntimeData  # noqa: E402

type ReptileCareConfigEntry = ConfigEntry[ReptileCareRuntimeData]
