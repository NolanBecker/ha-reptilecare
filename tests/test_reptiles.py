"""Tests for Reptile models, serialization, and repository behavior."""

from dataclasses import FrozenInstanceError, replace
from datetime import date
import json
from unittest.mock import AsyncMock

import pytest

from custom_components.reptilecare.domain.reptile import (
    DuplicateReptileError,
    InvalidReptileError,
    MemoryReptilePersistence,
    Reptile,
    ReptileNotFoundError,
    ReptileOverrides,
    ReptileRepository,
    ReptileSex,
    UnknownSpeciesProfileError,
    reptile_from_dict,
    reptile_to_dict,
)
from custom_components.reptilecare.domain.species import SpeciesProfileRegistry


@pytest.fixture
def pixel() -> Reptile:
    """Return the test-only Gargoyle Gecko named Pixel."""
    return Reptile(
        reptile_id="pixel",
        display_name="Pixel",
        species_profile_id="builtin:gargoyle_gecko",
        morph="Orange blotch",
        sex=ReptileSex.FEMALE,
        hatch_date=date(2024, 5, 10),
        acquired_date=date(2024, 9, 1),
        photo_reference="media-source://reptilecare/pixel",
        notes="Test fixture only.",
        enclosure_id="main_terrarium",
        overrides=ReptileOverrides({"environment.humidity.minimum": 55}),
    )


@pytest.fixture
def persistence() -> MemoryReptilePersistence:
    """Return empty Home Assistant-independent persistence."""
    return MemoryReptilePersistence()


@pytest.fixture
def repository(persistence: MemoryReptilePersistence) -> ReptileRepository:
    """Return a pure repository using bundled SpeciesProfiles."""
    return ReptileRepository(
        SpeciesProfileRegistry.load_builtin_profiles(), persistence
    )


def test_reptile_is_immutable_and_normalized(pixel: Reptile) -> None:
    """Reptile records normalize strings and remain immutable."""
    assert pixel.sex is ReptileSex.FEMALE
    with pytest.raises(FrozenInstanceError):
        pixel.display_name = "Changed"  # type: ignore[misc]

    values = {"environment.humidity.minimum": 55}
    overrides = ReptileOverrides(values)
    values["environment.humidity.minimum"] = 80
    assert overrides.values["environment.humidity.minimum"] == 55
    with pytest.raises(TypeError):
        overrides.values["new"] = True  # type: ignore[index]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"reptile_id": "Not Valid"}, "reptile_id"),
        ({"display_name": " "}, "display_name"),
        ({"enabled": 1}, "enabled"),
        ({"hatch_date": "2024-01-01"}, "hatch_date"),
        ({"sex": "other"}, "sex"),
        ({"overrides": {}}, "overrides"),
    ],
)
def test_reptile_rejects_invalid_values(
    pixel: Reptile, change: dict[str, object], message: str
) -> None:
    """Reptile fields enforce their explicit domain types."""
    with pytest.raises(InvalidReptileError, match=message):
        replace(pixel, **change)  # type: ignore[arg-type]


def test_overrides_reject_invalid_values() -> None:
    """Override keys and values remain JSON-compatible and deterministic."""
    with pytest.raises(InvalidReptileError, match="keys"):
        ReptileOverrides({"Not Valid": True})
    with pytest.raises(InvalidReptileError, match="scalars"):
        ReptileOverrides({"environment.value": [1]})  # type: ignore[dict-item]
    with pytest.raises(InvalidReptileError, match="finite"):
        ReptileOverrides({"environment.value": float("nan")})


def test_reptile_serialization_round_trip(pixel: Reptile) -> None:
    """Reptiles round-trip through explicit JSON-compatible serialization."""
    serialized = reptile_to_dict(pixel)
    restored = reptile_from_dict(json.loads(json.dumps(serialized)))
    assert restored == pixel
    assert restored.overrides.values == pixel.overrides.values


def test_reptile_deserialization_rejects_invalid_documents(pixel: Reptile) -> None:
    """Serialized reptiles reject unknown keys and invalid dates."""
    serialized = reptile_to_dict(pixel)
    serialized["unknown"] = True
    with pytest.raises(InvalidReptileError, match="unknown"):
        reptile_from_dict(serialized)

    serialized = reptile_to_dict(pixel)
    serialized["acquired_date"] = "not-a-date"
    with pytest.raises(InvalidReptileError, match="ISO date"):
        reptile_from_dict(serialized)


async def test_repository_crud(
    repository: ReptileRepository,
    persistence: MemoryReptilePersistence,
    pixel: Reptile,
) -> None:
    """Repository add, lookup, list, update, and remove persist atomically."""
    await repository.async_load()
    await repository.async_add(pixel)
    assert repository.get("pixel") is pixel
    assert repository.all() == (pixel,)
    assert persistence.reptiles == (pixel,)

    renamed = replace(pixel, display_name="Pixel Gecko")
    await repository.async_update(renamed)
    assert repository.get("pixel") == renamed

    removed = await repository.async_remove("pixel")
    assert removed == renamed
    assert repository.all() == ()
    assert persistence.reptiles == ()


async def test_repository_rejects_duplicate_ids(
    repository: ReptileRepository, pixel: Reptile
) -> None:
    """Permanent reptile identifiers remain unique."""
    await repository.async_load()
    await repository.async_add(pixel)
    with pytest.raises(DuplicateReptileError, match="pixel"):
        await repository.async_add(pixel)


async def test_repository_rejects_unknown_species_profile(
    repository: ReptileRepository, pixel: Reptile
) -> None:
    """Every reptile must reference one registered SpeciesProfile."""
    await repository.async_load()
    invalid = replace(pixel, species_profile_id="builtin:missing")
    with pytest.raises(UnknownSpeciesProfileError, match="builtin:missing"):
        await repository.async_add(invalid)


async def test_repository_enable_disable_and_filtering(
    repository: ReptileRepository, pixel: Reptile
) -> None:
    """Disabled reptiles are archived but remain addressable."""
    await repository.async_load()
    await repository.async_add(pixel)
    await repository.async_disable("pixel")
    assert not repository.get("pixel").enabled
    assert repository.all(include_disabled=False) == ()
    await repository.async_enable("pixel")
    assert repository.get("pixel").enabled


async def test_repository_lookup_failures(repository: ReptileRepository) -> None:
    """Missing update, removal, and lookup operations fail explicitly."""
    await repository.async_load()
    with pytest.raises(ReptileNotFoundError, match="missing"):
        repository.get("missing")
    with pytest.raises(ReptileNotFoundError, match="missing"):
        await repository.async_remove("missing")


async def test_repository_validates_loaded_collection(pixel: Reptile) -> None:
    """Duplicate and invalid persisted records never enter runtime state."""
    duplicate = ReptileRepository(
        SpeciesProfileRegistry.load_builtin_profiles(),
        MemoryReptilePersistence((pixel, pixel)),
    )
    with pytest.raises(DuplicateReptileError, match="pixel"):
        await duplicate.async_load()


async def test_failed_save_does_not_publish_reptile(
    repository: ReptileRepository,
    persistence: MemoryReptilePersistence,
    pixel: Reptile,
) -> None:
    """Repository state remains durable when persistence rejects a mutation."""
    await repository.async_load()
    persistence.async_save = AsyncMock(side_effect=OSError("disk unavailable"))
    with pytest.raises(OSError, match="disk unavailable"):
        await repository.async_add(pixel)
    assert repository.all() == ()
