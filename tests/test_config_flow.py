"""Tests for the ReptileCare config flow."""

from datetime import UTC, date, datetime
from types import SimpleNamespace

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.reptilecare.config_flow import (
    ReptileCareConfigFlow,
    ReptileCareOptionsFlow,
    _build_request,
    _coerce_date,
    _optional_text,
)
from custom_components.reptilecare.const import DOMAIN, INTEGRATION_NAME
from custom_components.reptilecare.content.loader import load_builtin_content
from custom_components.reptilecare.domain.care_task import CareTaskStatus
from custom_components.reptilecare.onboarding import (
    OnboardingRequest,
    async_apply_onboarding,
)


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    """Test the onboarding flow creates and loads the single entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reptile"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            "display_name": "Pixel",
            "nickname": "Pix",
            "morph": "Orange blotch",
            "sex": "unknown",
            "notes": "First reptile",
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "species"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"species_id": "builtin:gargoyle_gecko"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "recommended_care"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            "selected_care_plan_ids": [
                "builtin:feed_fruit_every_2_days",
                "builtin:spot_clean_daily",
            ]
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "initial_tasks"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"generate_initial_tasks": True}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == INTEGRATION_NAME
    assert result["data"]["onboarding"]["display_name"] == "Pixel"
    assert result["data"]["onboarding"]["species_id"] == "builtin:gargoyle_gecko"
    assert result["data"]["onboarding"]["generate_initial_tasks"] is True
    assert result["result"].state is ConfigEntryState.LOADED


async def test_user_flow_aborts_when_configured(hass: HomeAssistant) -> None:
    """Test that only one ReptileCare entry can be configured."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=INTEGRATION_NAME,
        data={},
        source=config_entries.SOURCE_USER,
        unique_id=DOMAIN,
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] in {"already_configured", "single_instance_allowed"}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (" Pixel ", "Pixel"),
        ("", None),
        (None, None),
        (1, None),
    ],
)
def test_optional_text_normalizes_expected_values(
    value: object, expected: str | None
) -> None:
    """Optional text helper should trim strings and ignore non-strings."""
    assert _optional_text(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("", None),
        ("2026-08-08", date(2026, 8, 8)),
        (date(2026, 8, 8), date(2026, 8, 8)),
    ],
)
def test_coerce_date_handles_empty_string_iso_text_and_date_objects(
    value: object, expected: date | None
) -> None:
    """Date coercion should accept plain dates and ISO-formatted strings."""
    assert _coerce_date(value) == expected


def test_build_request_normalizes_draft_payload() -> None:
    """Building an onboarding request should normalize optional fields."""
    request = _build_request(
        {
            "display_name": "Pixel",
            "nickname": " Pix ",
            "species_id": "builtin:gargoyle_gecko",
            "selected_care_plan_ids": ("builtin:spot_clean_daily",),
            "generate_initial_tasks": 1,
            "morph": " Orange blotch ",
            "sex": "unknown",
            "hatch_date": "2026-08-08",
            "notes": " First reptile ",
        }
    )

    assert request.display_name == "Pixel"
    assert request.nickname == "Pix"
    assert request.species_id == "builtin:gargoyle_gecko"
    assert request.selected_care_plan_ids == ("builtin:spot_clean_daily",)
    assert request.generate_initial_tasks is True
    assert request.morph == "Orange blotch"
    assert request.sex == "unknown"
    assert request.hatch_date == date(2026, 8, 8)
    assert request.notes == "First reptile"


def _fake_options_flow() -> ReptileCareOptionsFlow:
    content = load_builtin_content().bundle
    config_entry = SimpleNamespace(
        options={"generate_tasks_on_startup": False},
        runtime_data=SimpleNamespace(content=content),
    )
    return ReptileCareOptionsFlow(config_entry)


async def _setup_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title=INTEGRATION_NAME, data={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry


@pytest.mark.asyncio
async def test_options_flow_menu_and_forms_render() -> None:
    """Options flow should expose each management step as a form or menu."""
    flow = _fake_options_flow()

    menu = await flow.async_step_init()
    add_reptile = await flow.async_step_add_reptile()
    species = await flow.async_step_add_reptile_species()
    install_content = await flow.async_step_install_builtin_content()
    import_demo = await flow.async_step_import_demo_data()
    general = await flow.async_step_general_settings()

    assert menu["type"] is FlowResultType.MENU
    assert menu["menu_options"] == [
        "add_reptile",
        "manage_care_plans",
        "install_builtin_content",
        "import_demo_data",
        "general_settings",
    ]
    assert add_reptile["type"] is FlowResultType.FORM
    assert add_reptile["step_id"] == "add_reptile"
    assert species["type"] is FlowResultType.FORM
    assert species["step_id"] == "add_reptile_species"
    assert install_content["type"] is FlowResultType.FORM
    assert install_content["step_id"] == "install_builtin_content"
    assert import_demo["type"] is FlowResultType.FORM
    assert import_demo["step_id"] == "import_demo_data"
    assert general["type"] is FlowResultType.FORM
    assert general["step_id"] == "general_settings"


@pytest.mark.asyncio
async def test_options_flow_add_reptile_alias_route_executes_onboarding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Legacy route names should still reach the add-reptile onboarding path."""
    flow = _fake_options_flow()
    calls: list[object] = []

    async def _apply(runtime: object, request: object) -> None:
        calls.extend((runtime, request))

    monkeypatch.setattr(
        "custom_components.reptilecare.config_flow.async_apply_onboarding", _apply
    )

    result = await flow.async_step_reptile(
        {
            "display_name": "Pixel",
            "nickname": "Pix",
            "morph": "Orange blotch",
            "sex": "unknown",
            "notes": "First reptile",
        }
    )
    assert result["step_id"] == "add_reptile_species"

    result = await flow.async_step_species({"species_id": "builtin:gargoyle_gecko"})
    assert result["step_id"] == "add_reptile_care"

    result = await flow.async_step_recommended_care(
        {"selected_care_plan_ids": ["builtin:spot_clean_daily"]}
    )
    assert result["step_id"] == "add_reptile_tasks"

    result = await flow.async_step_initial_tasks({"generate_initial_tasks": True})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert len(calls) == 2
    assert calls[0] is flow._runtime
    assert calls[1].display_name == "Pixel"
    assert calls[1].selected_care_plan_ids == ("builtin:spot_clean_daily",)
    assert calls[1].generate_initial_tasks is True


@pytest.mark.asyncio
async def test_options_flow_add_reptile_creates_second_reptile(
    hass: HomeAssistant,
) -> None:
    """Add Reptile should create a second reptile without affecting the first."""
    entry = await _setup_entry(hass)
    runtime = entry.runtime_data
    await async_apply_onboarding(
        runtime,
        OnboardingRequest(
            display_name="Pixel",
            species_id="builtin:gargoyle_gecko",
            selected_care_plan_ids=("builtin:spot_clean_daily",),
            generate_initial_tasks=True,
        ),
        now=datetime(2026, 8, 8, 14, tzinfo=UTC),
    )

    flow = ReptileCareOptionsFlow(entry)
    result = await flow.async_step_add_reptile(
        {
            "display_name": "Beans",
            "nickname": "Beanie",
            "sex": "unknown",
            "notes": "Second reptile",
        }
    )
    assert result["step_id"] == "add_reptile_species"

    result = await flow.async_step_add_reptile_species(
        {"species_id": "builtin:crested_gecko"}
    )
    assert result["step_id"] == "add_reptile_care"

    result = await flow.async_step_add_reptile_care(
        {
            "selected_care_plan_ids": [
                "builtin:spot_clean_daily",
                "builtin:change_water_daily",
            ]
        }
    )
    assert result["step_id"] == "add_reptile_tasks"

    result = await flow.async_step_add_reptile_tasks({"generate_initial_tasks": True})
    assert result["type"] is FlowResultType.CREATE_ENTRY

    reptiles = runtime.reptile_repository.all()
    assert len(reptiles) == 2
    assert {reptile.display_name for reptile in reptiles} == {"Pixel", "Beans"}
    beans = next(reptile for reptile in reptiles if reptile.display_name == "Beans")
    assert runtime.care_plan_repository.for_reptile(beans.reptile_id)
    assert runtime.care_task_repository.for_reptile(beans.reptile_id)


@pytest.mark.asyncio
async def test_species_library_navigation_uses_real_library_steps() -> None:
    """Species Library should navigate to a real detail step instead of a blank form."""
    flow = _fake_options_flow()

    result = await flow.async_step_install_builtin_content(
        {"species_id": "builtin:gargoyle_gecko"}
    )
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "species_library_detail"
    assert result["menu_options"] == ["species_library_back"]

    result = await flow.async_step_species_library_back()
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "install_builtin_content"


@pytest.mark.asyncio
async def test_options_flow_manage_care_plans_updates_assignments(
    hass: HomeAssistant,
) -> None:
    """Care-plan management should enable, disable, and generate tasks coherently."""
    entry = await _setup_entry(hass)
    runtime = entry.runtime_data
    await async_apply_onboarding(
        runtime,
        OnboardingRequest(
            display_name="Pixel",
            species_id="builtin:gargoyle_gecko",
            selected_care_plan_ids=("builtin:spot_clean_daily",),
            generate_initial_tasks=True,
        ),
        now=datetime(2026, 8, 8, 14, tzinfo=UTC),
    )

    reptile = runtime.reptile_repository.all()[0]
    flow = ReptileCareOptionsFlow(entry)

    result = await flow.async_step_manage_care_plans()
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "manage_care_plans_selection"

    result = await flow.async_step_manage_care_plans_selection(
        {
            "selected_care_plan_ids": [
                "builtin:spot_clean_daily",
                "builtin:change_water_daily",
            ]
        }
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY

    enabled_plans = runtime.care_plan_repository.for_reptile(
        reptile.reptile_id, include_disabled=False
    )
    assert {plan.display_name for plan in enabled_plans} == {
        "Spot Cleaning",
        "Change Water",
    }
    change_water_plan = next(
        plan for plan in enabled_plans if plan.display_name == "Change Water"
    )
    assert runtime.care_task_repository.for_care_plan(change_water_plan.care_plan_id)

    result = await flow.async_step_manage_care_plans_selection(
        {"selected_care_plan_ids": ["builtin:change_water_daily"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY

    enabled_plans = runtime.care_plan_repository.for_reptile(
        reptile.reptile_id, include_disabled=False
    )
    assert {plan.display_name for plan in enabled_plans} == {"Change Water"}

    disabled_spot_clean = next(
        plan
        for plan in runtime.care_plan_repository.for_reptile(
            reptile.reptile_id, include_disabled=True
        )
        if plan.display_name == "Spot Cleaning"
    )
    assert disabled_spot_clean.enabled is False
    assert all(
        task.status is not CareTaskStatus.PENDING
        for task in runtime.care_task_repository.for_care_plan(
            disabled_spot_clean.care_plan_id
        )
    )


@pytest.mark.asyncio
async def test_options_flow_import_demo_and_general_settings_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Options flow should support demo import confirmation and general settings."""
    flow = _fake_options_flow()
    imported: list[object] = []

    async def _import_demo(runtime: object) -> None:
        imported.append(runtime)

    monkeypatch.setattr(
        "custom_components.reptilecare.config_flow.async_import_demo_data",
        _import_demo,
    )

    result = await flow.async_step_import_demo_data({"confirm_import": False})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert imported == []

    result = await flow.async_step_import_demo_data({"confirm_import": True})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert imported == [flow._runtime]

    result = await flow.async_step_install_builtin_content(
        {"species_id": "builtin:gargoyle_gecko"}
    )
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "species_library_detail"

    result = await flow.async_step_general_settings({"generate_tasks_on_startup": True})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"generate_tasks_on_startup": True}


def test_async_get_options_flow_returns_options_flow_instance() -> None:
    """Config flow should expose the dedicated options flow implementation."""
    flow = ReptileCareConfigFlow.async_get_options_flow(
        SimpleNamespace(
            runtime_data=SimpleNamespace(content=load_builtin_content().bundle)
        )
    )
    assert isinstance(flow, ReptileCareOptionsFlow)


def test_config_flow_init_does_not_load_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ConfigFlow construction must not perform blocking content I/O."""
    calls: list[str] = []

    async def _raise_if_called(*_args: object, **_kwargs: object) -> object:
        calls.append("called")
        raise AssertionError("content loading should not happen in __init__")

    monkeypatch.setattr(
        "custom_components.reptilecare.config_flow.async_load_builtin_content",
        _raise_if_called,
    )

    ReptileCareConfigFlow()

    assert calls == []


async def test_content_loading_uses_executor_once_per_config_flow(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Onboarding content should load through the executor once and be reused."""
    calls: list[object] = []
    original = hass.async_add_executor_job

    async def _spy(func, *args):
        calls.append(func)
        return await original(func, *args)

    monkeypatch.setattr(hass, "async_add_executor_job", _spy)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"display_name": "Pixel", "sex": "unknown"},
    )
    assert result["step_id"] == "species"
    assert calls.count(load_builtin_content) == 1

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"species_id": "builtin:gargoyle_gecko"},
    )
    assert result["step_id"] == "recommended_care"
    assert calls.count(load_builtin_content) == 1


async def test_content_loading_failure_aborts_flow_gracefully(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed content should abort onboarding instead of crashing Home Assistant."""

    async def _raise_content_error(*_args: object, **_kwargs: object) -> object:
        raise RuntimeError("invalid packaged content")

    monkeypatch.setattr(
        "custom_components.reptilecare.config_flow.async_load_builtin_content",
        _raise_content_error,
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={"display_name": "Pixel", "sex": "unknown"},
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "content_unavailable"


@pytest.mark.asyncio
async def test_options_flow_reuses_runtime_content_without_loading(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Options flow should reuse runtime content and avoid filesystem loading."""
    flow = _fake_options_flow()

    async def _raise_if_called(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("options flow should not load content from disk")

    monkeypatch.setattr(
        "custom_components.reptilecare.config_flow.async_load_builtin_content",
        _raise_if_called,
    )

    result = await flow.async_step_add_reptile_species()
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "add_reptile_species"
