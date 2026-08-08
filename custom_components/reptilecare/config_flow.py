"""Config and options flow for ReptileCare."""

from __future__ import annotations

from datetime import date
import logging
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
import voluptuous as vol

from .const import DOMAIN, INTEGRATION_NAME
from .content.async_loader import async_load_builtin_content
from .content.loader import BuiltinContentBundle
from .models import ReptileCareRuntimeData
from .onboarding import (
    OnboardingRequest,
    async_apply_onboarding,
    async_import_demo_data,
    recommended_care_plan_choices,
    serialize_request,
    species_choices,
)

_LOGGER = logging.getLogger(__name__)


class ReptileCareConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ReptileCare."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        self._content: BuiltinContentBundle | None = None
        self._draft: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Welcome the user into onboarding."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return await self.async_step_reptile()

        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

    async def async_step_reptile(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the first reptile's basic details."""
        errors: dict[str, str] = {}
        if user_input is not None:
            self._draft.update(user_input)
            return await self.async_step_species()

        return self.async_show_form(
            step_id="reptile",
            data_schema=vol.Schema(
                {
                    vol.Required("display_name"): str,
                    vol.Optional("nickname"): str,
                    vol.Optional("morph"): str,
                    vol.Optional(
                        "sex",
                        default="unknown",
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=["female", "male", "unknown"],
                            translation_key="reptile_sex",
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional("hatch_date"): selector.DateSelector(),
                    vol.Optional("notes"): selector.TextSelector(
                        selector.TextSelectorConfig(multiline=True)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_species(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select a species from the built-in catalog."""
        content = await self._async_get_content()
        if content is None:
            return self.async_abort(reason="content_unavailable")

        if user_input is not None:
            self._draft.update(user_input)
            return await self.async_step_recommended_care()

        options = [
            selector.SelectOptionDict(value=value, label=label)
            for value, label in species_choices(content)
        ]
        return self.async_show_form(
            step_id="species",
            data_schema=vol.Schema(
                {
                    vol.Required("species_id"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_recommended_care(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select recommended care plans for the chosen species."""
        content = await self._async_get_content()
        if content is None:
            return self.async_abort(reason="content_unavailable")

        species_id = str(self._draft["species_id"])
        options = [
            selector.SelectOptionDict(value=value, label=label)
            for value, label in recommended_care_plan_choices(content, species_id)
        ]
        default = [
            value
            for value, _label in recommended_care_plan_choices(content, species_id)
        ]
        if user_input is not None:
            self._draft["selected_care_plan_ids"] = tuple(
                user_input.get("selected_care_plan_ids", ())
            )
            return await self.async_step_initial_tasks()

        return self.async_show_form(
            step_id="recommended_care",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "selected_care_plan_ids", default=default
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            multiple=True,
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def async_step_initial_tasks(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose whether to generate today's care immediately."""
        if user_input is not None:
            self._draft["generate_initial_tasks"] = bool(
                user_input.get("generate_initial_tasks", True)
            )
            return await self.async_step_finish()

        return self.async_show_form(
            step_id="initial_tasks",
            data_schema=vol.Schema(
                {
                    vol.Required("generate_initial_tasks", default=True): bool,
                }
            ),
        )

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the config entry with pending onboarding data."""
        _ = user_input
        return self.async_create_entry(
            title=INTEGRATION_NAME,
            data={"onboarding": serialize_request(_build_request(self._draft))},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Return the ReptileCare options flow."""
        return ReptileCareOptionsFlow(config_entry)

    async def _async_get_content(self) -> BuiltinContentBundle | None:
        """Load and cache built-in content through Home Assistant's executor."""
        if self._content is not None:
            return self._content
        try:
            content_result = await async_load_builtin_content(self.hass)
        except Exception:
            _LOGGER.exception("Unable to load built-in onboarding content")
            return None
        for warning in content_result.warnings:
            _LOGGER.warning("Built-in content warning: %s", warning)
        self._content = content_result.bundle
        return self._content


class ReptileCareOptionsFlow(OptionsFlow):
    """Manage reptiles and built-in content after setup."""

    def __init__(self, config_entry) -> None:
        self._config_entry = config_entry
        self._runtime: ReptileCareRuntimeData = config_entry.runtime_data
        self._content = self._runtime.content
        self._draft: dict[str, Any] = {}

    async def _async_get_content(self) -> BuiltinContentBundle | None:
        """Reuse already-loaded runtime content without hitting the filesystem."""
        return self._content

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Present management actions."""
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "add_reptile",
                "install_builtin_content",
                "import_demo_data",
                "general_settings",
            ],
        )

    async def async_step_add_reptile(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect reptile details for a later install step."""
        if user_input is not None:
            self._draft.update(user_input)
            return await self.async_step_add_reptile_species()
        return await ReptileCareConfigFlow.async_step_reptile(self, user_input)

    async def async_step_add_reptile_species(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect species selection for the new reptile."""
        if user_input is not None:
            self._draft.update(user_input)
            return await self.async_step_add_reptile_care()
        return await ReptileCareConfigFlow.async_step_species(self, user_input)

    async def async_step_add_reptile_care(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect selected recommended care plans."""
        if user_input is not None:
            self._draft["selected_care_plan_ids"] = tuple(
                user_input.get("selected_care_plan_ids", ())
            )
            return await self.async_step_add_reptile_tasks()
        return await ReptileCareConfigFlow.async_step_recommended_care(self, user_input)

    async def async_step_add_reptile_tasks(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Finalize the add-reptile workflow."""
        if user_input is not None:
            self._draft["generate_initial_tasks"] = bool(
                user_input.get("generate_initial_tasks", True)
            )
            await async_apply_onboarding(self._runtime, _build_request(self._draft))
            return self.async_create_entry(title="", data={})
        return await ReptileCareConfigFlow.async_step_initial_tasks(self, user_input)

    async def async_step_install_builtin_content(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the bundled catalog summary."""
        if user_input is not None:
            return self.async_create_entry(title="", data={})
        return self.async_show_form(
            step_id="install_builtin_content",
            data_schema=vol.Schema({}),
        )

    async def async_step_import_demo_data(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Install optional demo data."""
        if user_input is not None:
            if bool(user_input.get("confirm_import", False)):
                await async_import_demo_data(self._runtime)
            return self.async_create_entry(title="", data={})
        return self.async_show_form(
            step_id="import_demo_data",
            data_schema=vol.Schema(
                {vol.Required("confirm_import", default=False): bool}
            ),
        )

    async def async_step_general_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Persist lightweight general settings."""
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    "generate_tasks_on_startup": bool(
                        user_input.get("generate_tasks_on_startup", True)
                    )
                },
            )
        return self.async_show_form(
            step_id="general_settings",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "generate_tasks_on_startup",
                        default=self._config_entry.options.get(
                            "generate_tasks_on_startup", True
                        ),
                    ): bool
                }
            ),
        )


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _coerce_date(value: object) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _build_request(data: dict[str, Any]) -> OnboardingRequest:
    return OnboardingRequest(
        display_name=str(data["display_name"]),
        nickname=_optional_text(data.get("nickname")),
        species_id=str(data["species_id"]),
        selected_care_plan_ids=tuple(data["selected_care_plan_ids"]),
        generate_initial_tasks=bool(data["generate_initial_tasks"]),
        morph=_optional_text(data.get("morph")),
        sex=_optional_text(data.get("sex")),
        hatch_date=_coerce_date(data.get("hatch_date")),
        notes=_optional_text(data.get("notes")),
    )
