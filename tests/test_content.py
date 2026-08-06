"""Tests for the built-in content catalog."""

from custom_components.reptilecare.content.loader import load_builtin_content


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
