"""Tests for the built-in content catalog."""

from pathlib import Path

import pytest

from custom_components.reptilecare.content.loader import (
    BuiltinContentLoader,
    load_builtin_content,
)
from custom_components.reptilecare.content.models import InvalidContentError


def test_builtin_content_loads_species_and_care_plans() -> None:
    """The packaged content library exposes a reusable engine-plus-content catalog."""
    result = load_builtin_content()
    bundle = result.bundle

    assert result.warnings == ()
    assert len(bundle.species.all()) == 5
    assert bundle.species.contains("builtin:gargoyle_gecko")
    assert bundle.care_plans.contains("builtin:feed_fruit_every_2_days")
    assert bundle.care_plans.contains("builtin:change_water_daily")


def test_species_search_matches_aliases() -> None:
    """Species search supports display names and aliases without internal IDs."""
    bundle = load_builtin_content().bundle

    assert bundle.search_species("royal python")[0].species_id == "builtin:ball_python"
    assert bundle.search_species("leo")[0].species_id == "builtin:leopard_gecko"


def test_loader_helpers_validate_yaml_and_skip_bad_files(tmp_path: Path) -> None:
    """Loader helpers should surface friendly validation errors and warnings."""
    loader = BuiltinContentLoader()
    species_dir = tmp_path / "species"
    care_plan_dir = tmp_path / "care_plans"
    species_dir.mkdir()
    care_plan_dir.mkdir()

    good_species = species_dir / "good.yaml"
    good_species.write_text(
        "\n".join(
            (
                "species_id: builtin:test_species",
                "display_name: Test Species",
                "scientific_name: Testus species",
                "category: gecko",
                "description: Test species.",
                "recommended_care_plan_ids:",
                "  - builtin:test_plan",
            )
        ),
        encoding="utf-8",
    )
    bad_species = species_dir / "bad.yaml"
    bad_species.write_text("- not-an-object\n", encoding="utf-8")

    good_plan = care_plan_dir / "good.yaml"
    good_plan.write_text(
        "\n".join(
            (
                "content_id: builtin:test_plan",
                "display_name: Test Plan",
                "description: Test plan.",
                "task_template_id: builtin:feed_fruit",
                "workflow_id: builtin:basic_care",
                "schedule:",
                "  every: 2",
                "  unit: days",
            )
        ),
        encoding="utf-8",
    )
    bad_plan = care_plan_dir / "bad.yaml"
    bad_plan.write_text("[]\n", encoding="utf-8")

    species_items, species_warnings, species_files = loader._load_species(species_dir)
    care_plan_items, care_plan_warnings, care_plan_files = loader._load_care_plans(
        care_plan_dir
    )

    assert [item.species_id for item in species_items] == ["builtin:test_species"]
    assert species_files == ["good.yaml"]
    assert len(species_warnings) == 1
    assert "bad.yaml" in species_warnings[0]
    assert [item.content_id for item in care_plan_items] == ["builtin:test_plan"]
    assert care_plan_files == ["good.yaml"]
    assert len(care_plan_warnings) == 1
    assert "bad.yaml" in care_plan_warnings[0]
    assert {item.name for item in loader._yaml_files(species_dir)} == {
        "bad.yaml",
        "good.yaml",
    }


def test_loader_read_yaml_mapping_and_object_validation(tmp_path: Path) -> None:
    """Low-level loader helpers should reject non-object YAML content cleanly."""
    loader = BuiltinContentLoader()
    mapping_file = tmp_path / "mapping.yaml"
    mapping_file.write_text("key: value\n", encoding="utf-8")
    list_file = tmp_path / "list.yaml"
    list_file.write_text("- nope\n", encoding="utf-8")

    assert loader._read_yaml_mapping(mapping_file) == {"key": "value"}
    with pytest.raises(InvalidContentError, match="top-level object"):
        loader._read_yaml_mapping(list_file)
