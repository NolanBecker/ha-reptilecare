"""Tests for the LizardCare config flow."""

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lizardcare.const import DOMAIN, INTEGRATION_NAME


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    """Test that the user flow creates and loads the single entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == INTEGRATION_NAME
    assert result["data"] == {}
    assert result["result"].state is ConfigEntryState.LOADED


async def test_user_flow_aborts_when_configured(hass: HomeAssistant) -> None:
    """Test that only one LizardCare entry can be configured."""
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
