"""Tests for species profile domain models and serialization."""

from dataclasses import FrozenInstanceError
from datetime import date
import json

import pytest

from custom_components.reptilecare.domain.species import (
    EnvironmentalRecommendation,
    EnvironmentalRecommendationSet,
    InvalidSpeciesProfileError,
    ProfileOrigin,
    ProfileReference,
    SpeciesProfile,
    species_profile_from_dict,
    species_profile_to_dict,
)


def _profile() -> SpeciesProfile:
    return SpeciesProfile(
        profile_id="test:profile",
        display_name="Test Gecko",
        scientific_name="Testus gecko",
        category="gecko",
        description="A profile used by domain tests.",
        default_environmental_targets=EnvironmentalRecommendationSet(
            (
                EnvironmentalRecommendation(
                    target_id="temperature",
                    display_name="Temperature",
                    minimum=20,
                    maximum=25,
                    unit="°C",
                    warning_minimum=18,
                    warning_maximum=27,
                    notes="Example only.",
                ),
            )
        ),
        default_task_template_ids=("test:feeding",),
        references=(
            ProfileReference(
                title="Example reference",
                publisher="Example publisher",
                url="https://example.com/reference",
                publication_date=date(2026, 1, 2),
                notes="Used only in tests.",
            ),
        ),
    )


def test_profile_is_immutable_and_normalized() -> None:
    """Profiles copy input collections and cannot be mutated."""
    task_ids = ["test:feeding"]
    profile = SpeciesProfile(
        profile_id=" test:profile ",
        display_name=" Test ",
        scientific_name="Testus",
        category="gecko",
        description="Description",
        default_task_template_ids=task_ids,  # type: ignore[arg-type]
    )
    task_ids.append("test:cleaning")
    assert profile.profile_id == "test:profile"
    assert profile.default_task_template_ids == ("test:feeding",)
    with pytest.raises(FrozenInstanceError):
        profile.display_name = "Changed"  # type: ignore[misc]


def test_environmental_recommendations_are_sorted_and_unique() -> None:
    """Recommendation sets provide immutable deterministic ordering."""
    first = EnvironmentalRecommendation("humidity", "Humidity", 50, 60, "%")
    second = EnvironmentalRecommendation(
        "air_temperature", "Air temperature", 20, 25, "°C"
    )
    recommendations = EnvironmentalRecommendationSet((first, second))
    assert [item.target_id for item in recommendations.targets] == [
        "air_temperature",
        "humidity",
    ]
    with pytest.raises(InvalidSpeciesProfileError, match="unique"):
        EnvironmentalRecommendationSet((first, first))


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"target_id": "Not Valid"}, "target_id"),
        ({"minimum": 30, "maximum": 20}, "minimum"),
        ({"minimum": True}, "minimum"),
        ({"warning_minimum": 22}, "warning_minimum"),
        ({"warning_maximum": 22}, "warning_maximum"),
    ],
)
def test_environmental_recommendation_rejects_invalid_ranges(
    kwargs: dict[str, object], message: str
) -> None:
    """Environmental ranges reject malformed and contradictory values."""
    values: dict[str, object] = {
        "target_id": "temperature",
        "display_name": "Temperature",
        "minimum": 20,
        "maximum": 25,
        "unit": "°C",
    }
    values.update(kwargs)
    with pytest.raises(InvalidSpeciesProfileError, match=message):
        EnvironmentalRecommendation(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "url", ["relative/path", "ftp://example.com/profile", "https:///missing-host"]
)
def test_reference_rejects_invalid_url(url: str) -> None:
    """References require absolute HTTP or HTTPS URLs."""
    with pytest.raises(InvalidSpeciesProfileError, match="HTTP"):
        ProfileReference("Title", "Publisher", url)


def test_serialization_round_trip_is_json_compatible() -> None:
    """Profiles round-trip through explicit JSON-compatible serialization."""
    profile = _profile()
    serialized = species_profile_to_dict(profile)
    assert species_profile_from_dict(json.loads(json.dumps(serialized))) == profile


def test_serialization_omits_absent_optional_fields() -> None:
    """Optional target and reference fields have a canonical absent form."""
    profile = SpeciesProfile(
        "test:minimal", "Minimal", "Testus", "gecko", "Description"
    )
    assert species_profile_to_dict(profile)["references"] == []


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ({"unknown": True}, "unknown keys"),
        ({"schema_version": 2}, "unsupported schema"),
        ({"profile_version": 0}, "positive integer"),
        ({"profile_id": "INVALID"}, "namespaced"),
        ({"default_task_template_ids": ["invalid"]}, "namespaced"),
        ({"default_environmental_targets": {}}, "array"),
        ({"origin": "remote"}, "origin"),
        ({"references": {}}, "array"),
    ],
)
def test_deserialization_rejects_invalid_profiles(
    mutation: dict[str, object], message: str
) -> None:
    """Strict deserialization rejects unsupported profile documents."""
    data = species_profile_to_dict(_profile())
    data.update(mutation)
    with pytest.raises(InvalidSpeciesProfileError, match=message):
        species_profile_from_dict(data)


def test_deserialization_rejects_invalid_nested_fields() -> None:
    """Strict deserialization validates nested objects and dates."""
    data = species_profile_to_dict(_profile())
    data["references"][0]["publication_date"] = "not-a-date"
    with pytest.raises(InvalidSpeciesProfileError, match="ISO date"):
        species_profile_from_dict(data)
    data = species_profile_to_dict(_profile())
    data["default_environmental_targets"][0]["unexpected"] = True
    with pytest.raises(InvalidSpeciesProfileError, match="unknown keys"):
        species_profile_from_dict(data)


def test_profile_rejects_duplicate_template_ids() -> None:
    """Profiles reject ambiguous task template collections."""
    with pytest.raises(InvalidSpeciesProfileError, match="unique"):
        SpeciesProfile(
            "test:duplicate",
            "Duplicate",
            "Testus",
            "gecko",
            "Description",
            default_task_template_ids=("test:task", "test:task"),
        )


def test_profile_origin_is_typed_and_serializable() -> None:
    """Profiles default to the built-in origin and serialize its stable value."""
    profile = _profile()
    assert profile.origin is ProfileOrigin.BUILTIN
    assert species_profile_to_dict(profile)["origin"] == "builtin"

    user_profile = SpeciesProfile(
        "test:user",
        "User profile",
        "Testus",
        "gecko",
        "Description",
        origin=ProfileOrigin.USER,
    )
    assert user_profile.origin is ProfileOrigin.USER

    legacy_data = species_profile_to_dict(profile)
    del legacy_data["origin"]
    assert species_profile_from_dict(legacy_data).origin is ProfileOrigin.BUILTIN
