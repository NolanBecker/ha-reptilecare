"""Home Assistant persistence adapter for CarePlan records."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any, cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .domain.care_plan import CarePlan, care_plan_from_dict, care_plan_to_dict

_LOGGER = logging.getLogger(__name__)

CARE_PLAN_STORAGE_VERSION = 1
CARE_PLAN_STORAGE_MINOR_VERSION = 1

type StoredCarePlanData = dict[str, Any]


class _VersionedCarePlanStore(Store[StoredCarePlanData]):
    """Home Assistant Store with explicit CarePlan migration support."""

    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: StoredCarePlanData,
    ) -> StoredCarePlanData:
        """Migrate older CarePlan payloads to the current schema."""
        return migrate_care_plan_storage(old_major_version, old_minor_version, old_data)


def migrate_care_plan_storage(
    old_major_version: int,
    old_minor_version: int,
    old_data: StoredCarePlanData,
) -> StoredCarePlanData:
    """Migrate persisted CarePlan data to the current storage schema."""
    if old_major_version == CARE_PLAN_STORAGE_VERSION:
        if old_minor_version < 1:
            care_plans = old_data.get("care_plans", [])
            return {"care_plans": care_plans if isinstance(care_plans, list) else []}
        return old_data
    if old_major_version == 0:
        care_plans = old_data.get("care_plans", [])
        return {"care_plans": care_plans if isinstance(care_plans, list) else []}
    version = f"{old_major_version}.{old_minor_version}"
    raise ValueError(f"Unsupported ReptileCare care plan storage version {version}")


class HomeAssistantCarePlanPersistence:
    """CarePlan persistence backed by a dedicated Home Assistant Store."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize storage for one ReptileCare config entry."""
        self._store = _VersionedCarePlanStore(
            hass,
            CARE_PLAN_STORAGE_VERSION,
            f"{DOMAIN}.{entry_id}.care_plans",
            minor_version=CARE_PLAN_STORAGE_MINOR_VERSION,
        )

    async def async_load(self) -> tuple[CarePlan, ...]:
        """Load CarePlans, recovering empty when persisted data is malformed."""
        try:
            stored = await self._store.async_load()
            return _deserialize_care_plans(stored)
        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.warning("Unable to load ReptileCare care plans: %s", err)
            return ()

    async def async_save(self, care_plans: tuple[CarePlan, ...]) -> None:
        """Persist the complete immutable CarePlan collection."""
        await self._store.async_save(
            {"care_plans": [care_plan_to_dict(care_plan) for care_plan in care_plans]}
        )


def _deserialize_care_plans(
    stored: StoredCarePlanData | None,
) -> tuple[CarePlan, ...]:
    """Deserialize a complete CarePlan collection."""
    if stored is None:
        return ()
    raw_care_plans = stored.get("care_plans")
    if not isinstance(raw_care_plans, list):
        raise ValueError("care plan storage must contain a care_plans list")
    care_plans = []
    for raw_care_plan in raw_care_plans:
        if not isinstance(raw_care_plan, Mapping):
            raise ValueError("stored care plan must be an object")
        care_plans.append(care_plan_from_dict(cast("Mapping[str, Any]", raw_care_plan)))
    return tuple(care_plans)
