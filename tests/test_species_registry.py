"""Tests for the species profile registry."""

import json
from pathlib import Path

import pytest

from custom_components.reptilecare.domain.species import (
    DuplicateSpeciesProfileError,
    InvalidSpeciesProfileError,
    ProfileOrigin,
    SpeciesProfile,
    SpeciesProfileNotFoundError,
    SpeciesProfileRegistry,
    species_profile_to_dict,
)


def _profile(profile_id: str) -> SpeciesProfile:
    return SpeciesProfile(profile_id, profile_id, "Testus", "gecko", "Description")


def test_builtin_registry_loads_gargoyle_gecko() -> None:
    """The packaged Gargoyle Gecko profile loads from the built-in content catalog."""
    registry = SpeciesProfileRegistry.load_builtin_profiles()
    profile = registry.get("builtin:gargoyle_gecko")
    assert profile.display_name == "Gargoyle Gecko"
    assert profile.scientific_name == "Rhacodactylus auriculatus"
    assert [
        target.target_id for target in profile.default_environmental_targets.targets
    ] == [
        "daytime_temperature",
        "humidity",
        "nighttime_temperature",
    ]
    assert profile.default_task_template_ids == (
        "builtin:feed_fruit",
        "builtin:spot_clean",
        "builtin:change_water",
        "builtin:deep_clean",
    )
    assert profile.references == ()
    assert profile.origin is ProfileOrigin.BUILTIN


def test_registry_lookup_and_ordering() -> None:
    """Registry lookups are deterministic and provide explicit misses."""
    registry = SpeciesProfileRegistry((_profile("test:z"), _profile("test:a")))
    assert [profile.profile_id for profile in registry.all()] == ["test:a", "test:z"]
    assert registry.contains("test:a")
    assert not registry.contains("test:missing")
    with pytest.raises(SpeciesProfileNotFoundError, match="test:missing"):
        registry.get("test:missing")


def test_registry_rejects_duplicate_profiles() -> None:
    """Duplicate profile identifiers fail registry construction."""
    profile = _profile("test:duplicate")
    with pytest.raises(DuplicateSpeciesProfileError, match="duplicate"):
        SpeciesProfileRegistry((profile, profile))


def test_registry_loads_files_in_name_order(tmp_path: Path) -> None:
    """External file collections use the same strict loader."""
    for filename, profile_id in (("z.json", "test:z"), ("a.json", "test:a")):
        (tmp_path / filename).write_text(
            json.dumps(species_profile_to_dict(_profile(profile_id))), encoding="utf-8"
        )
    registry = SpeciesProfileRegistry.from_files(tmp_path.glob("*.json"))
    assert [profile.profile_id for profile in registry.all()] == ["test:a", "test:z"]


def test_registry_reports_invalid_json_file(tmp_path: Path) -> None:
    """Invalid packaged-style JSON produces a clear domain error."""
    invalid = tmp_path / "invalid.json"
    invalid.write_text("not json", encoding="utf-8")
    with pytest.raises(InvalidSpeciesProfileError, match="invalid.json"):
        SpeciesProfileRegistry.from_files((invalid,))
