"""Tests for the ReptileCare config flow."""

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.reptilecare.const import DOMAIN, INTEGRATION_NAME


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
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "finish"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={}
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
