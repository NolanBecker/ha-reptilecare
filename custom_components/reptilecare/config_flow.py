"""Config and options flow for ReptileCare."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import selector
import voluptuous as vol

from .application import CarePlanUpdated
from .const import DOMAIN, INTEGRATION_NAME
from .content.async_loader import async_load_builtin_content
from .content.loader import BuiltinContentBundle
from .content.models import BuiltinCarePlanTemplate, BuiltinSpeciesPackage
from .domain.care_task import CareTaskStatus
from .models import ReptileCareRuntimeData
from .onboarding import (
    OnboardingRequest,
    async_apply_onboarding,
    async_import_demo_data,
    build_builtin_care_plan,
    builtin_template_matches_care_plan,
    recommended_care_plan_choices,
    serialize_request,
    species_choices,
)
from .runtime_updates import async_notify_runtime_updated

_LOGGER = logging.getLogger(__name__)


def _selector_options(
    values: tuple[tuple[str, str], ...],
) -> list[selector.SelectOptionDict]:
    return [
        selector.SelectOptionDict(value=value, label=label) for value, label in values
    ]


def _cadence_label(template: BuiltinCarePlanTemplate) -> str:
    unit = template.unit.value
    if template.every == 1:
        if unit == "days":
            return "Every day"
        if unit == "weeks":
            return "Every week"
        if unit == "months":
            return "Every month"
        if unit == "hours":
            return "Every hour"
    return f"Every {template.every} {unit}"


def _care_plan_option_label(template: BuiltinCarePlanTemplate) -> str:
    return f"{template.display_name} ({_cadence_label(template)})"


def _reptile_schema() -> vol.Schema:
    return vol.Schema(
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
    )


def _species_schema(content: BuiltinContentBundle) -> vol.Schema:
    options = _selector_options(species_choices(content))
    return vol.Schema(
        {
            vol.Required("species_id"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
        }
    )


def _recommended_care_schema(
    content: BuiltinContentBundle,
    species_id: str,
    *,
    selected_ids: tuple[str, ...] | None = None,
) -> vol.Schema:
    template_choices = tuple(
        (plan_id, _care_plan_option_label(content.care_plans.get(plan_id)))
        for plan_id, _label in recommended_care_plan_choices(content, species_id)
    )
    default = (
        list(selected_ids)
        if selected_ids is not None
        else [plan_id for plan_id, _label in template_choices]
    )
    return vol.Schema(
        {
            vol.Required(
                "selected_care_plan_ids", default=default
            ): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=_selector_options(template_choices),
                    multiple=True,
                    mode=selector.SelectSelectorMode.LIST,
                )
            )
        }
    )


def _initial_tasks_schema(*, default: bool = True) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("generate_initial_tasks", default=default): bool,
        }
    )


def _general_settings_schema(*, default: bool) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required("generate_tasks_on_startup", default=default): bool,
        }
    )


def _reptile_name_placeholder(data: dict[str, Any]) -> str:
    display_name = data.get("display_name")
    if isinstance(display_name, str) and display_name.strip():
        return display_name.strip()
    return "this reptile"


def _species_detail_placeholders(
    content: BuiltinContentBundle,
    species: BuiltinSpeciesPackage,
) -> dict[str, str]:
    targets = (
        "\n".join(
            f"- {target.display_name}: {target.minimum}-{target.maximum} {target.unit}"
            for target in species.environmental_targets
        )
        or "No environmental targets are bundled yet."
    )
    recommended = (
        "\n".join(
            f"- {_care_plan_option_label(content.care_plans.get(plan_id))}"
            for plan_id in species.recommended_care_plan_ids
        )
        or "No recommended care plans are bundled yet."
    )
    aliases = ", ".join(species.aliases) if species.aliases else "None"
    return {
        "species_name": species.display_name,
        "scientific_name": species.scientific_name,
        "category": species.category,
        "aliases": aliases,
        "description": species.description,
        "environmental_targets": targets,
        "recommended_care_plans": recommended,
    }


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
        if user_input is not None:
            self._draft.update(user_input)
            return await self.async_step_species()

        return self.async_show_form(
            step_id="reptile",
            data_schema=_reptile_schema(),
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

        return self.async_show_form(
            step_id="species",
            data_schema=_species_schema(content),
        )

    async def async_step_recommended_care(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select recommended care plans for the chosen species."""
        content = await self._async_get_content()
        if content is None:
            return self.async_abort(reason="content_unavailable")

        species_id = str(self._draft["species_id"])
        if user_input is not None:
            self._draft["selected_care_plan_ids"] = tuple(
                user_input.get("selected_care_plan_ids", ())
            )
            return await self.async_step_initial_tasks()

        return self.async_show_form(
            step_id="recommended_care",
            data_schema=_recommended_care_schema(content, species_id),
            description_placeholders={
                "reptile_name": _reptile_name_placeholder(self._draft)
            },
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
            data_schema=_initial_tasks_schema(),
            description_placeholders={
                "reptile_name": _reptile_name_placeholder(self._draft)
            },
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
        _ = user_input
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "add_reptile",
                "manage_care_plans",
                "install_builtin_content",
                "import_demo_data",
                "general_settings",
            ],
        )

    async def async_step_reptile(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Backward-compatible alias for older add-reptile routes."""
        return await self.async_step_add_reptile(user_input)

    async def async_step_species(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Backward-compatible alias for older add-reptile routes."""
        return await self.async_step_add_reptile_species(user_input)

    async def async_step_recommended_care(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Backward-compatible alias for older add-reptile routes."""
        return await self.async_step_add_reptile_care(user_input)

    async def async_step_initial_tasks(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Backward-compatible alias for older add-reptile routes."""
        return await self.async_step_add_reptile_tasks(user_input)

    async def async_step_add_reptile(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect reptile details for a later install step."""
        if user_input is not None:
            self._draft.update(user_input)
            return await self.async_step_add_reptile_species()
        return self.async_show_form(
            step_id="add_reptile",
            data_schema=_reptile_schema(),
        )

    async def async_step_add_reptile_species(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect species selection for the new reptile."""
        content = await self._async_get_content()
        if content is None:
            return self.async_abort(reason="content_unavailable")
        if user_input is not None:
            self._draft.update(user_input)
            return await self.async_step_add_reptile_care()
        return self.async_show_form(
            step_id="add_reptile_species",
            data_schema=_species_schema(content),
        )

    async def async_step_add_reptile_care(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect selected recommended care plans."""
        content = await self._async_get_content()
        if content is None:
            return self.async_abort(reason="content_unavailable")
        species_id = str(self._draft["species_id"])
        if user_input is not None:
            self._draft["selected_care_plan_ids"] = tuple(
                user_input.get("selected_care_plan_ids", ())
            )
            return await self.async_step_add_reptile_tasks()
        return self.async_show_form(
            step_id="add_reptile_care",
            data_schema=_recommended_care_schema(content, species_id),
            description_placeholders={
                "reptile_name": _reptile_name_placeholder(self._draft)
            },
        )

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
        return self.async_show_form(
            step_id="add_reptile_tasks",
            data_schema=_initial_tasks_schema(),
            description_placeholders={
                "reptile_name": _reptile_name_placeholder(self._draft)
            },
        )

    async def async_step_install_builtin_content(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Browse the bundled species library."""
        content = await self._async_get_content()
        if content is None:
            return self.async_abort(reason="content_unavailable")
        if user_input is not None:
            self._draft["species_library_species_id"] = str(user_input["species_id"])
            return await self.async_step_species_library_detail()
        return self.async_show_form(
            step_id="install_builtin_content",
            data_schema=_species_schema(content),
        )

    async def async_step_species_library_detail(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show a read-only summary of one bundled species package."""
        _ = user_input
        content = await self._async_get_content()
        if content is None:
            return self.async_abort(reason="content_unavailable")
        species_id = self._draft.get("species_library_species_id")
        if not isinstance(species_id, str):
            return await self.async_step_install_builtin_content()
        species = content.species.get(species_id)
        return self.async_show_menu(
            step_id="species_library_detail",
            menu_options=["species_library_back"],
            description_placeholders=_species_detail_placeholders(content, species),
        )

    async def async_step_species_library_back(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Return from one species detail view to the library list."""
        _ = user_input
        return await self.async_step_install_builtin_content()

    async def async_step_manage_care_plans(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose which reptile to manage when multiple reptiles exist."""
        reptiles = self._runtime.reptile_repository.all()
        if not reptiles:
            return self.async_show_menu(
                step_id="manage_care_plans_empty",
                menu_options=["add_reptile"],
            )
        if len(reptiles) == 1:
            self._draft["care_plan_reptile_id"] = reptiles[0].reptile_id
            return await self.async_step_manage_care_plans_selection()
        if user_input is not None:
            self._draft["care_plan_reptile_id"] = str(user_input["reptile_id"])
            return await self.async_step_manage_care_plans_selection()
        reptile_options = tuple(
            (
                reptile.reptile_id,
                f"{reptile.display_name} ({reptile.slug or reptile.reptile_id})",
            )
            for reptile in reptiles
        )
        return self.async_show_form(
            step_id="manage_care_plans",
            data_schema=vol.Schema(
                {
                    vol.Required("reptile_id"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=_selector_options(reptile_options),
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_manage_care_plans_selection(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Assign or unassign bundled care plans for one existing reptile."""
        reptile_id = self._draft.get("care_plan_reptile_id")
        if not isinstance(reptile_id, str):
            return await self.async_step_manage_care_plans()
        reptile = self._runtime.reptile_repository.get(reptile_id)
        template_ids, default_ids = self._care_plan_selection_state(reptile_id)
        if user_input is not None:
            selected_ids = tuple(user_input.get("selected_care_plan_ids", ()))
            await self._async_apply_care_plan_selection(reptile_id, selected_ids)
            return self.async_create_entry(
                title="",
                data={
                    "reptile_id": reptile_id,
                    "selected_care_plan_ids": list(selected_ids),
                },
            )
        template_options = tuple(
            (
                template_id,
                _care_plan_option_label(self._content.care_plans.get(template_id)),
            )
            for template_id in template_ids
        )
        current_plans = self._runtime.care_plan_repository.for_reptile(
            reptile_id, include_disabled=False
        )
        current_summary = (
            "\n".join(f"- {plan.display_name}" for plan in current_plans)
            or "No care plans are currently assigned."
        )
        return self.async_show_form(
            step_id="manage_care_plans_selection",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "selected_care_plan_ids",
                        default=list(default_ids),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=_selector_options(template_options),
                            multiple=True,
                            mode=selector.SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            description_placeholders={
                "reptile_name": reptile.display_name,
                "current_care_plans": current_summary,
            },
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
            data_schema=_general_settings_schema(
                default=self._config_entry.options.get(
                    "generate_tasks_on_startup", True
                )
            ),
        )

    def _care_plan_selection_state(
        self,
        reptile_id: str,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Return available built-in template IDs and currently selected IDs."""
        reptile = self._runtime.reptile_repository.get(reptile_id)
        species = self._content.species.get(reptile.species_profile_id)
        existing_plans = self._runtime.care_plan_repository.for_reptile(
            reptile_id, include_disabled=True
        )
        available_ids = list(species.recommended_care_plan_ids)
        default_ids: list[str] = []
        for template_id in species.recommended_care_plan_ids:
            template = self._content.care_plans.get(template_id)
            if any(
                builtin_template_matches_care_plan(plan, template) and plan.enabled
                for plan in existing_plans
            ):
                default_ids.append(template_id)
        for plan in existing_plans:
            for template in self._content.care_plans.all():
                if builtin_template_matches_care_plan(plan, template):
                    if template.content_id not in available_ids:
                        available_ids.append(template.content_id)
                    if plan.enabled and template.content_id not in default_ids:
                        default_ids.append(template.content_id)
                    break
        return tuple(available_ids), tuple(default_ids)

    async def _async_apply_care_plan_selection(
        self,
        reptile_id: str,
        selected_template_ids: tuple[str, ...],
    ) -> None:
        """Enable, disable, or create built-in CarePlans for one reptile."""
        now = datetime.now(UTC)
        repository = self._runtime.care_plan_repository
        existing = list(repository.for_reptile(reptile_id, include_disabled=True))
        available_ids, _default_ids = self._care_plan_selection_state(reptile_id)

        changed_plans = []
        created_or_enabled_plan_ids: list[str] = []
        for template_id in available_ids:
            template = self._content.care_plans.get(template_id)
            matching = [
                plan
                for plan in existing
                if builtin_template_matches_care_plan(plan, template)
            ]
            enabled_matches = [plan for plan in matching if plan.enabled]
            disabled_matches = [plan for plan in matching if not plan.enabled]

            if template_id in selected_template_ids:
                keeper = None
                if enabled_matches:
                    keeper = enabled_matches[0]
                    for duplicate in enabled_matches[1:]:
                        updated = replace(
                            duplicate,
                            enabled=False,
                            plan_version=duplicate.plan_version + 1,
                        )
                        await repository.async_update(updated)
                        changed_plans.append(updated)
                        await self._async_cancel_pending_tasks(updated.care_plan_id)
                elif disabled_matches:
                    previous = disabled_matches[0]
                    keeper = build_builtin_care_plan(
                        reptile_id=reptile_id,
                        template=template,
                        effective_date=now.date(),
                        tracking_started_at=now,
                        care_plan_id=previous.care_plan_id,
                        enabled=True,
                        plan_version=previous.plan_version + 1,
                    )
                    await repository.async_update(keeper)
                    changed_plans.append(keeper)
                else:
                    keeper = build_builtin_care_plan(
                        reptile_id=reptile_id,
                        template=template,
                        effective_date=now.date(),
                        tracking_started_at=now,
                    )
                    await repository.async_add(keeper)
                    existing.append(keeper)
                    changed_plans.append(keeper)

                if keeper is not None:
                    created_or_enabled_plan_ids.append(keeper.care_plan_id)
                continue

            for plan in enabled_matches:
                updated = replace(
                    plan,
                    enabled=False,
                    plan_version=plan.plan_version + 1,
                )
                await repository.async_update(updated)
                changed_plans.append(updated)
                await self._async_cancel_pending_tasks(updated.care_plan_id)

        care_plan_events = tuple(
            CarePlanUpdated(
                reptile_id=plan.reptile_id,
                care_plan_id=plan.care_plan_id,
                enabled=plan.enabled,
            )
            for plan in changed_plans
        )
        if care_plan_events:
            await self._runtime.event_publisher.async_publish_many(care_plan_events)

        for care_plan_id in created_or_enabled_plan_ids:
            await self._runtime.care_task_generator.async_generate(
                now=now,
                care_plan_id=care_plan_id,
                look_ahead=timedelta(),
                look_back=timedelta(),
            )

        async_notify_runtime_updated(self.hass)

    async def _async_cancel_pending_tasks(self, care_plan_id: str) -> None:
        """Cancel pending operational tasks for one disabled care plan."""
        for task in self._runtime.care_task_repository.for_care_plan(care_plan_id):
            if task.status is CareTaskStatus.PENDING:
                await self._runtime.care_task_repository.async_disable(task.task_id)
