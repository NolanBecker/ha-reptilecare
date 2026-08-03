"""Home Assistant persistence adapter for Reptile records."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any, cast

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .domain.reptile import Reptile, reptile_from_dict, reptile_to_dict

_LOGGER = logging.getLogger(__name__)

REPTILE_STORAGE_VERSION = 1
REPTILE_STORAGE_MINOR_VERSION = 2

type StoredReptileData = dict[str, Any]


class _VersionedReptileStore(Store[StoredReptileData]):
    """Home Assistant Store with explicit reptile migration support."""

    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: StoredReptileData,
    ) -> StoredReptileData:
        """Migrate older reptile payloads to the current schema."""
        return migrate_reptile_storage(old_major_version, old_minor_version, old_data)


def migrate_reptile_storage(
    old_major_version: int,
    old_minor_version: int,
    old_data: StoredReptileData,
) -> StoredReptileData:
    """Migrate persisted reptile data to the current storage schema."""
    if old_major_version == REPTILE_STORAGE_VERSION:
        if old_minor_version < 2:
            return _migrate_add_slug(old_data)
        return old_data
    if old_major_version == 0:
        reptiles = old_data.get("reptiles", [])
        return {"reptiles": reptiles if isinstance(reptiles, list) else []}
    version = f"{old_major_version}.{old_minor_version}"
    raise ValueError(f"Unsupported ReptileCare reptile storage version {version}")


class HomeAssistantReptilePersistence:
    """Reptile persistence backed by a dedicated Home Assistant Store."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        """Initialize storage for one ReptileCare config entry."""
        self._store = _VersionedReptileStore(
            hass,
            REPTILE_STORAGE_VERSION,
            f"{DOMAIN}.{entry_id}.reptiles",
            minor_version=REPTILE_STORAGE_MINOR_VERSION,
        )

    async def async_load(self) -> tuple[Reptile, ...]:
        """Load reptiles, recovering empty when persisted data is malformed."""
        try:
            stored = await self._store.async_load()
            return _deserialize_reptiles(stored)
        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.warning("Unable to load ReptileCare reptiles: %s", err)
            return ()

    async def async_save(self, reptiles: tuple[Reptile, ...]) -> None:
        """Persist the complete immutable reptile collection."""
        await self._store.async_save(
            {"reptiles": [reptile_to_dict(reptile) for reptile in reptiles]}
        )


def _migrate_add_slug(old_data: StoredReptileData) -> StoredReptileData:
    """Backfill the optional slug field for older reptile documents."""
    reptiles = old_data.get("reptiles")
    if not isinstance(reptiles, list):
        return {"reptiles": []}

    migrated: list[dict[str, Any]] = []
    for reptile in reptiles:
        if not isinstance(reptile, Mapping):
            return {"reptiles": []}
        migrated.append({"slug": None, **dict(reptile)})
    return {"reptiles": migrated}


def _deserialize_reptiles(
    stored: StoredReptileData | None,
) -> tuple[Reptile, ...]:
    """Deserialize a complete reptile collection."""
    if stored is None:
        return ()
    raw_reptiles = stored.get("reptiles")
    if not isinstance(raw_reptiles, list):
        raise ValueError("reptile storage must contain a reptiles list")
    reptiles = []
    for raw_reptile in raw_reptiles:
        if not isinstance(raw_reptile, Mapping):
            raise ValueError("stored reptile must be an object")
        reptiles.append(reptile_from_dict(cast("Mapping[str, Any]", raw_reptile)))
    return tuple(reptiles)
