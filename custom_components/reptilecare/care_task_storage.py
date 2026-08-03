"""Home Assistant persistence adapter for CareTask records."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any, cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .domain.care_task import CareTask, care_task_from_dict, care_task_to_dict

_LOGGER = logging.getLogger(__name__)

CARE_TASK_STORAGE_VERSION = 1
CARE_TASK_STORAGE_MINOR_VERSION = 1

type StoredCareTaskData = dict[str, Any]


class _VersionedCareTaskStore(Store[StoredCareTaskData]):
    """Home Assistant Store with explicit CareTask migration support."""

    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: StoredCareTaskData,
    ) -> StoredCareTaskData:
        """Migrate older CareTask payloads to the current schema."""
        return migrate_care_task_storage(old_major_version, old_minor_version, old_data)


def migrate_care_task_storage(
    old_major_version: int,
    old_minor_version: int,
    old_data: StoredCareTaskData,
) -> StoredCareTaskData:
    """Migrate persisted CareTask data to the current storage schema."""
    if old_major_version == CARE_TASK_STORAGE_VERSION:
        if old_minor_version < 1:
            care_tasks = old_data.get("care_tasks", [])
            return {"care_tasks": care_tasks if isinstance(care_tasks, list) else []}
        return old_data
    if old_major_version == 0:
        care_tasks = old_data.get("care_tasks", [])
        return {"care_tasks": care_tasks if isinstance(care_tasks, list) else []}
    version = f"{old_major_version}.{old_minor_version}"
    raise ValueError(f"Unsupported ReptileCare care task storage version {version}")


class HomeAssistantCareTaskPersistence:
    """CareTask persistence backed by a dedicated Home Assistant Store."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize storage for one ReptileCare config entry."""
        self._store = _VersionedCareTaskStore(
            hass,
            CARE_TASK_STORAGE_VERSION,
            f"{DOMAIN}.{entry_id}.care_tasks",
            minor_version=CARE_TASK_STORAGE_MINOR_VERSION,
        )

    async def async_load(self) -> tuple[CareTask, ...]:
        """Load CareTasks, recovering empty when persisted data is malformed."""
        try:
            stored = await self._store.async_load()
            return _deserialize_care_tasks(stored)
        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.warning("Unable to load ReptileCare care tasks: %s", err)
            return ()

    async def async_save(self, care_tasks: tuple[CareTask, ...]) -> None:
        """Persist the complete immutable CareTask collection."""
        await self._store.async_save(
            {"care_tasks": [care_task_to_dict(care_task) for care_task in care_tasks]}
        )


def _deserialize_care_tasks(
    stored: StoredCareTaskData | None,
) -> tuple[CareTask, ...]:
    """Deserialize a complete CareTask collection."""
    if stored is None:
        return ()
    raw_care_tasks = stored.get("care_tasks")
    if not isinstance(raw_care_tasks, list):
        raise ValueError("care task storage must contain a care_tasks list")
    care_tasks = []
    for raw_care_task in raw_care_tasks:
        if not isinstance(raw_care_task, Mapping):
            raise ValueError("stored care task must be an object")
        care_tasks.append(care_task_from_dict(cast("Mapping[str, Any]", raw_care_task)))
    return tuple(care_tasks)
