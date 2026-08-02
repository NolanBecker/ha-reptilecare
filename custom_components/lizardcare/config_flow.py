"""Config flow for LizardCare."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
import voluptuous as vol

from .const import DOMAIN, INTEGRATION_NAME


class LizardCareConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for LizardCare."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the single LizardCare config entry."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(title=INTEGRATION_NAME, data={})

        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))
