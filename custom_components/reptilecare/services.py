"""Home Assistant service adapters for ReptileCare."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
import math
from types import MappingProxyType
from typing import Any, cast
from uuid import uuid4

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
import voluptuous as vol

from .application import (
    CareEngineError,
    CareTaskResolutionRequest,
    ConflictingTaskResolutionError,
)
from .const import DOMAIN
from .domain.care_plan import (
    CarePlan,
    CarePlanError,
    CarePlanNotFoundError,
    CarePlanScheduleUnit,
    IntervalSchedule,
    InvalidCarePlanError,
    ReminderConfiguration,
    ReminderLeadTime,
    ReminderLeadTimeUnit,
    ReminderRepeatPolicy,
    care_plan_to_dict,
)
from .domain.care_task import (
    CareTask,
    CareTaskNotFoundError,
    CareTaskStatus,
    InvalidCareTaskError,
    care_task_to_dict,
    project_due_state,
)
from .domain.reptile import (
    DuplicateReptileSlugError,
    InvalidReptileError,
    Reptile,
    ReptileError,
    ReptileNotFoundError,
    ReptileOverrides,
    ReptileSex,
    reptile_to_dict,
)
from .domain.task_template import TaskPriority, TaskTemplateNotFoundError
from .domain.workflow import WorkflowNotFoundError
from .models import CareEvent, CareEventType, ReptileCareRuntimeData

SOURCE_HOME_ASSISTANT_SERVICE = "home_assistant_service"

SERVICE_CREATE_REPTILE = "create_reptile"
SERVICE_UPDATE_REPTILE = "update_reptile"
SERVICE_ENABLE_REPTILE = "enable_reptile"
SERVICE_DISABLE_REPTILE = "disable_reptile"
SERVICE_CREATE_CARE_PLAN = "create_care_plan"
SERVICE_UPDATE_CARE_PLAN = "update_care_plan"
SERVICE_ENABLE_CARE_PLAN = "enable_care_plan"
SERVICE_DISABLE_CARE_PLAN = "disable_care_plan"
SERVICE_GENERATE_TASKS = "generate_tasks"
SERVICE_RESOLVE_TASK = "resolve_task"
SERVICE_LOG_EVENT = "log_event"
SERVICE_GET_TASKS = "get_tasks"
SERVICE_GET_TIMELINE = "get_timeline"

_SERVICE_DATA = vol.Schema({}, extra=vol.ALLOW_EXTRA)


def async_register_services(hass: HomeAssistant) -> None:
    """Register ReptileCare services once."""
    if hass.services.has_service(DOMAIN, SERVICE_CREATE_REPTILE):
        return

    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_REPTILE,
        _async_handle_create_reptile,
        schema=_SERVICE_DATA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_REPTILE,
        _async_handle_update_reptile,
        schema=_SERVICE_DATA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ENABLE_REPTILE,
        _async_handle_enable_reptile,
        schema=_SERVICE_DATA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DISABLE_REPTILE,
        _async_handle_disable_reptile,
        schema=_SERVICE_DATA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CREATE_CARE_PLAN,
        _async_handle_create_care_plan,
        schema=_SERVICE_DATA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UPDATE_CARE_PLAN,
        _async_handle_update_care_plan,
        schema=_SERVICE_DATA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ENABLE_CARE_PLAN,
        _async_handle_enable_care_plan,
        schema=_SERVICE_DATA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_DISABLE_CARE_PLAN,
        _async_handle_disable_care_plan,
        schema=_SERVICE_DATA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GENERATE_TASKS,
        _async_handle_generate_tasks,
        schema=_SERVICE_DATA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RESOLVE_TASK,
        _async_handle_resolve_task,
        schema=_SERVICE_DATA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LOG_EVENT,
        _async_handle_log_event,
        schema=_SERVICE_DATA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_TASKS,
        _async_handle_get_tasks,
        schema=_SERVICE_DATA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_TIMELINE,
        _async_handle_get_timeline,
        schema=_SERVICE_DATA,
        supports_response=SupportsResponse.ONLY,
    )


def async_unregister_services(hass: HomeAssistant) -> None:
    """Remove registered ReptileCare services."""
    for service in (
        SERVICE_CREATE_REPTILE,
        SERVICE_UPDATE_REPTILE,
        SERVICE_ENABLE_REPTILE,
        SERVICE_DISABLE_REPTILE,
        SERVICE_CREATE_CARE_PLAN,
        SERVICE_UPDATE_CARE_PLAN,
        SERVICE_ENABLE_CARE_PLAN,
        SERVICE_DISABLE_CARE_PLAN,
        SERVICE_GENERATE_TASKS,
        SERVICE_RESOLVE_TASK,
        SERVICE_LOG_EVENT,
        SERVICE_GET_TASKS,
        SERVICE_GET_TIMELINE,
    ):
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)


def _runtime(hass: HomeAssistant) -> ReptileCareRuntimeData:
    entries = [
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED and hasattr(entry, "runtime_data")
    ]
    if not entries:
        raise HomeAssistantError("ReptileCare is not set up")
    if len(entries) != 1:
        raise HomeAssistantError("ReptileCare requires exactly one active config entry")
    return cast("ReptileCareRuntimeData", entries[0].runtime_data)


def _actor_id(call: ServiceCall) -> str | None:
    return call.context.user_id


def _field_present(call: ServiceCall, field: str) -> bool:
    return field in call.data


def _require_text(call: ServiceCall, field: str) -> str:
    value = call.data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise HomeAssistantError(f"{field} must be a non-empty string")
    return value.strip()


def _optional_text(call: ServiceCall, field: str) -> str | None:
    if not _field_present(call, field):
        return None
    value = call.data.get(field)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise HomeAssistantError(f"{field} must be a non-empty string when provided")
    return value.strip()


def _optional_date(call: ServiceCall, field: str) -> date | None:
    if not _field_present(call, field):
        return None
    return _parse_date(call.data.get(field), field)


def _optional_datetime(call: ServiceCall, field: str) -> datetime | None:
    if not _field_present(call, field):
        return None
    return _parse_datetime(call.data.get(field), field)


def _parse_date(value: object, field: str) -> date | None:
    if value is None:
        return None
    if type(value) is date:
        return value
    if not isinstance(value, str):
        raise HomeAssistantError(f"{field} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as err:
        raise HomeAssistantError(f"{field} must be an ISO date") from err


def _parse_datetime(value: object, field: str) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError as err:
            raise HomeAssistantError(f"{field} must be an ISO datetime") from err
    else:
        raise HomeAssistantError(f"{field} must be an ISO datetime")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise HomeAssistantError(f"{field} must be timezone-aware")
    return parsed.astimezone(UTC)


def _json_value(value: object, field: str) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise HomeAssistantError(f"{field} numbers must be finite")
        return value
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise HomeAssistantError(f"{field} keys must be strings")
        return MappingProxyType(
            {key: _json_value(item, field) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_json_value(item, field) for item in value)
    raise HomeAssistantError(f"{field} must contain only JSON-compatible values")


def _json_object(call: ServiceCall, field: str) -> Mapping[str, Any]:
    value = call.data.get(field, {})
    if not isinstance(value, Mapping):
        raise HomeAssistantError(f"{field} must be an object")
    normalized = _json_value(value, field)
    return cast("Mapping[str, Any]", normalized)


def _attachments(call: ServiceCall, field: str) -> tuple[str, ...]:
    if not _field_present(call, field):
        return ()
    value = call.data.get(field)
    if not isinstance(value, (list, tuple)):
        raise HomeAssistantError(f"{field} must be an array of strings")
    attachments: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise HomeAssistantError(f"{field} must contain non-empty strings")
        attachments.append(item.strip())
    return tuple(attachments)


def _parse_reptile_identifier(
    runtime: ReptileCareRuntimeData,
    call: ServiceCall,
    *,
    reptile_id_precedence: bool = False,
) -> str:
    reptile_id = _optional_text(call, "reptile_id")
    slug = _optional_text(call, "slug")
    if reptile_id_precedence and reptile_id is not None:
        try:
            return runtime.reptile_repository.get(reptile_id).reptile_id
        except ReptileNotFoundError as err:
            raise HomeAssistantError(str(err)) from err
    if (reptile_id is None) == (slug is None):
        raise HomeAssistantError("Provide exactly one of reptile_id or slug")
    try:
        if reptile_id is not None:
            return runtime.reptile_repository.get(reptile_id).reptile_id
        return runtime.reptile_repository.get_by_slug(slug).reptile_id  # type: ignore[arg-type]
    except ReptileNotFoundError as err:
        raise HomeAssistantError(str(err)) from err


def _parse_schedule(data: object) -> IntervalSchedule:
    if not isinstance(data, Mapping):
        raise HomeAssistantError("schedule must be an object")
    schedule_type = data.get("schedule_type", "interval")
    if schedule_type != "interval":
        raise HomeAssistantError("schedule_type must be 'interval'")
    try:
        return IntervalSchedule(
            every=int(data["every"]),
            unit=CarePlanScheduleUnit(str(data["unit"])),
        )
    except KeyError as err:
        raise HomeAssistantError(f"schedule is missing key: {err.args[0]}") from err
    except (TypeError, ValueError, InvalidCarePlanError) as err:
        raise HomeAssistantError(f"invalid schedule: {err}") from err


def _parse_reminder(data: object | None) -> ReminderConfiguration:
    if data is None:
        return ReminderConfiguration()
    if not isinstance(data, Mapping):
        raise HomeAssistantError("reminder_configuration must be an object")
    lead_time_value = data.get("lead_time")
    if lead_time_value is None:
        lead_time = None
    else:
        if not isinstance(lead_time_value, Mapping):
            raise HomeAssistantError("reminder lead_time must be an object")
        try:
            lead_time = ReminderLeadTime(
                amount=int(lead_time_value["amount"]),
                unit=ReminderLeadTimeUnit(str(lead_time_value["unit"])),
            )
        except KeyError as err:
            raise HomeAssistantError(
                f"reminder lead_time is missing key: {err.args[0]}"
            ) from err
        except (TypeError, ValueError, InvalidCarePlanError) as err:
            raise HomeAssistantError(f"invalid reminder lead_time: {err}") from err
    try:
        return ReminderConfiguration(
            enabled=bool(data.get("enabled", False)),
            lead_time=lead_time,
            repeat_policy=ReminderRepeatPolicy(str(data.get("repeat_policy", "once"))),
            metadata=cast(
                "Mapping[str, Any]",
                _json_value(data.get("metadata", {}), "reminder metadata"),
            ),
        )
    except (TypeError, ValueError, InvalidCarePlanError) as err:
        raise HomeAssistantError(f"invalid reminder_configuration: {err}") from err


def _parse_timedelta(value: object, field: str) -> timedelta:
    if not isinstance(value, Mapping):
        raise HomeAssistantError(f"{field} must be a duration object")
    allowed = {"days", "hours", "minutes", "seconds", "weeks"}
    unknown = set(value) - allowed
    if unknown:
        raise HomeAssistantError(
            f"{field} contains unsupported keys: {', '.join(sorted(unknown))}"
        )
    kwargs: dict[str, int | float] = {}
    for key, item in value.items():
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise HomeAssistantError(f"{field}.{key} must be numeric")
        if item < 0:
            raise HomeAssistantError(f"{field}.{key} must not be negative")
        kwargs[key] = item
    return timedelta(**kwargs)


def _serialize_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _serialize_json(item) for key, item in value.items()}
    if isinstance(value, (tuple, frozenset)):
        return [_serialize_json(item) for item in value]
    return value


def _serialize_reptile(reptile: Reptile) -> dict[str, Any]:
    return reptile_to_dict(reptile)


def _serialize_care_plan(care_plan: CarePlan) -> dict[str, Any]:
    return care_plan_to_dict(care_plan)


def _serialize_care_task(
    task: CareTask, *, now: datetime | None = None
) -> dict[str, Any]:
    data = care_task_to_dict(task)
    if now is not None:
        data["due_state"] = project_due_state(task, now=now).value
    return data


def _serialize_event(event: CareEvent) -> dict[str, Any]:
    return {
        "event_id": str(event.event_id),
        "reptile_id": event.reptile_id,
        "event_type": event.event_type.value,
        "timestamp": event.timestamp.isoformat(),
        "task_id": event.task_id,
        "care_plan_id": event.care_plan_id,
        "outcome_id": event.outcome_id,
        "context": _serialize_json(event.context),
        "actor_id": event.actor_id,
        "source": event.source,
        "environmental_snapshot": _serialize_json(event.environmental_snapshot),
        "attachment_references": list(event.attachment_references),
        "metadata": _serialize_json(event.metadata),
    }


async def _async_handle_create_reptile(call: ServiceCall) -> dict[str, Any]:
    runtime = _runtime(call.hass)
    try:
        sex = None
        if _field_present(call, "sex") and call.data.get("sex") is not None:
            sex = ReptileSex(str(call.data["sex"]))
        reptile = Reptile(
            reptile_id=str(uuid4()),
            display_name=_require_text(call, "display_name"),
            species_profile_id=_require_text(call, "species_profile_id"),
            slug=_optional_text(call, "slug"),
            morph=_optional_text(call, "morph"),
            sex=sex,
            hatch_date=_optional_date(call, "hatch_date"),
            acquired_date=_optional_date(call, "acquired_date"),
            photo_reference=_optional_text(call, "photo_reference"),
            notes=_optional_text(call, "notes"),
            enclosure_id=_optional_text(call, "enclosure_id"),
            overrides=ReptileOverrides(_json_object(call, "overrides")),
        )
        await runtime.reptile_repository.async_add(reptile)
    except (
        InvalidReptileError,
        DuplicateReptileSlugError,
        ReptileError,
        ValueError,
    ) as err:
        raise HomeAssistantError(str(err)) from err
    return {"reptile": _serialize_reptile(reptile)}


async def _async_handle_update_reptile(call: ServiceCall) -> dict[str, Any]:
    runtime = _runtime(call.hass)
    reptile_id = _parse_reptile_identifier(runtime, call, reptile_id_precedence=True)
    current = runtime.reptile_repository.get(reptile_id)
    changes: dict[str, Any] = {}
    for field in (
        "display_name",
        "species_profile_id",
        "slug",
        "morph",
        "photo_reference",
        "notes",
        "enclosure_id",
    ):
        if _field_present(call, field):
            if field in {"display_name", "species_profile_id"}:
                changes[field] = _require_text(call, field)
            else:
                changes[field] = _optional_text(call, field)
    if _field_present(call, "sex"):
        value = call.data.get("sex")
        changes["sex"] = None if value is None else ReptileSex(str(value))
    for field in ("hatch_date", "acquired_date"):
        if _field_present(call, field):
            changes[field] = _parse_date(call.data.get(field), field)
    if _field_present(call, "overrides"):
        changes["overrides"] = ReptileOverrides(_json_object(call, "overrides"))
    try:
        updated = replace(current, **changes)
        await runtime.reptile_repository.async_update(updated)
    except (
        InvalidReptileError,
        DuplicateReptileSlugError,
        ReptileError,
        ValueError,
    ) as err:
        raise HomeAssistantError(str(err)) from err
    return {"reptile": _serialize_reptile(updated)}


async def _async_handle_enable_reptile(call: ServiceCall) -> dict[str, Any]:
    runtime = _runtime(call.hass)
    reptile_id = _parse_reptile_identifier(runtime, call)
    try:
        await runtime.reptile_repository.async_enable(reptile_id)
    except ReptileError as err:
        raise HomeAssistantError(str(err)) from err
    return {"reptile": _serialize_reptile(runtime.reptile_repository.get(reptile_id))}


async def _async_handle_disable_reptile(call: ServiceCall) -> dict[str, Any]:
    runtime = _runtime(call.hass)
    reptile_id = _parse_reptile_identifier(runtime, call)
    try:
        await runtime.reptile_repository.async_disable(reptile_id)
    except ReptileError as err:
        raise HomeAssistantError(str(err)) from err
    return {"reptile": _serialize_reptile(runtime.reptile_repository.get(reptile_id))}


async def _async_handle_create_care_plan(call: ServiceCall) -> dict[str, Any]:
    runtime = _runtime(call.hass)
    reptile_id = _parse_reptile_identifier(runtime, call)
    try:
        care_plan = CarePlan(
            reptile_id=reptile_id,
            task_template_id=_require_text(call, "task_template_id"),
            workflow_id=_require_text(call, "workflow_id"),
            display_name=_require_text(call, "display_name"),
            enabled=bool(call.data.get("enabled", True)),
            priority=TaskPriority(str(call.data.get("priority", "normal"))),
            schedule=_parse_schedule(call.data.get("schedule")),
            effective_date=(
                _parse_date(call.data.get("effective_date"), "effective_date")
                or datetime.now(UTC).date()
            ),
            optional_end_date=_parse_date(
                call.data.get("optional_end_date"),
                "optional_end_date",
            ),
            reminder_configuration=_parse_reminder(
                call.data.get("reminder_configuration")
            ),
            metadata=_json_object(call, "metadata"),
        )
        await runtime.care_plan_repository.async_add(care_plan)
    except (
        InvalidCarePlanError,
        CarePlanError,
        TaskTemplateNotFoundError,
        WorkflowNotFoundError,
        ValueError,
    ) as err:
        raise HomeAssistantError(str(err)) from err
    return {"care_plan": _serialize_care_plan(care_plan)}


async def _async_handle_update_care_plan(call: ServiceCall) -> dict[str, Any]:
    runtime = _runtime(call.hass)
    care_plan_id = _require_text(call, "care_plan_id")
    try:
        current = runtime.care_plan_repository.get(care_plan_id)
    except CarePlanError as err:
        raise HomeAssistantError(str(err)) from err
    changes: dict[str, Any] = {}
    for field in ("task_template_id", "workflow_id", "display_name"):
        if _field_present(call, field):
            changes[field] = _require_text(call, field)
    if _field_present(call, "enabled"):
        changes["enabled"] = cv.boolean(call.data["enabled"])
    if _field_present(call, "priority"):
        changes["priority"] = TaskPriority(str(call.data["priority"]))
    if _field_present(call, "schedule"):
        changes["schedule"] = _parse_schedule(call.data["schedule"])
    if _field_present(call, "effective_date"):
        changes["effective_date"] = _parse_date(
            call.data.get("effective_date"), "effective_date"
        )
    if _field_present(call, "optional_end_date"):
        changes["optional_end_date"] = _parse_date(
            call.data.get("optional_end_date"), "optional_end_date"
        )
    if _field_present(call, "reminder_configuration"):
        changes["reminder_configuration"] = _parse_reminder(
            call.data.get("reminder_configuration")
        )
    if _field_present(call, "metadata"):
        changes["metadata"] = _json_object(call, "metadata")
    try:
        updated = replace(current, **changes)
        await runtime.care_plan_repository.async_update(updated)
    except (
        CarePlanNotFoundError,
        InvalidCarePlanError,
        CarePlanError,
        ValueError,
    ) as err:
        raise HomeAssistantError(str(err)) from err
    return {"care_plan": _serialize_care_plan(updated)}


async def _async_handle_enable_care_plan(call: ServiceCall) -> dict[str, Any]:
    runtime = _runtime(call.hass)
    care_plan_id = _require_text(call, "care_plan_id")
    try:
        await runtime.care_plan_repository.async_enable(care_plan_id)
    except CarePlanError as err:
        raise HomeAssistantError(str(err)) from err
    return {
        "care_plan": _serialize_care_plan(
            runtime.care_plan_repository.get(care_plan_id)
        )
    }


async def _async_handle_disable_care_plan(call: ServiceCall) -> dict[str, Any]:
    runtime = _runtime(call.hass)
    care_plan_id = _require_text(call, "care_plan_id")
    try:
        await runtime.care_plan_repository.async_disable(care_plan_id)
    except CarePlanError as err:
        raise HomeAssistantError(str(err)) from err
    return {
        "care_plan": _serialize_care_plan(
            runtime.care_plan_repository.get(care_plan_id)
        )
    }


async def _async_handle_generate_tasks(call: ServiceCall) -> dict[str, Any]:
    runtime = _runtime(call.hass)
    reptile_id = (
        _parse_reptile_identifier(runtime, call)
        if _field_present(call, "reptile_id") or _field_present(call, "slug")
        else None
    )
    care_plan_id = _optional_text(call, "care_plan_id")
    if care_plan_id is not None:
        try:
            care_plan = runtime.care_plan_repository.get(care_plan_id)
        except CarePlanError as err:
            raise HomeAssistantError(str(err)) from err
        if reptile_id is not None and care_plan.reptile_id != reptile_id:
            raise HomeAssistantError(
                f"care plan {care_plan_id} does not belong to reptile {reptile_id}"
            )
    look_ahead = (
        _parse_timedelta(call.data["horizon_duration"], "horizon_duration")
        if _field_present(call, "horizon_duration")
        else None
    )
    now = (
        _parse_datetime(call.data.get("now"), "now")
        if _field_present(call, "now")
        else datetime.now(UTC)
    )
    if _field_present(call, "horizon_end"):
        horizon_end = _parse_datetime(call.data.get("horizon_end"), "horizon_end")
        if horizon_end is None or horizon_end < now:
            raise HomeAssistantError("horizon_end must not be earlier than now")
        look_ahead = horizon_end - now
    result = await runtime.care_task_generator.async_generate(
        now=now,
        look_ahead=look_ahead,
        reptile_id=reptile_id,
        care_plan_id=care_plan_id,
    )
    return {
        "created_task_ids": list(result.created_task_ids),
        "existing_task_ids": list(result.existing_task_ids),
        "skipped_plan_ids": list(result.skipped_plan_ids),
        "warnings": list(result.warnings),
        "errors": dict(result.errors),
    }


async def _async_handle_resolve_task(call: ServiceCall) -> dict[str, Any]:
    runtime = _runtime(call.hass)
    task_id = _require_text(call, "task_id")
    try:
        result = await runtime.care_engine.async_resolve_task(
            task_id,
            CareTaskResolutionRequest(
                action=_require_text(call, "action"),
                outcome_id=_optional_text(call, "outcome_id"),
                outcome_metadata=_json_object(call, "outcome_metadata"),
                notes=_optional_text(call, "notes"),
                attachment_references=_attachments(call, "attachment_references"),
                actor_id=_actor_id(call),
                source=SOURCE_HOME_ASSISTANT_SERVICE,
                completed_at=_optional_datetime(call, "completed_at"),
                environmental_context=_json_object(call, "environmental_context"),
            ),
        )
    except (
        CareTaskNotFoundError,
        ConflictingTaskResolutionError,
        CareEngineError,
        InvalidCareTaskError,
        ValueError,
    ) as err:
        raise HomeAssistantError(str(err)) from err
    await runtime.coordinator.async_refresh()
    return {
        "task": _serialize_care_task(result.task),
        "care_event": _serialize_event(result.care_event),
        "created_follow_up_tasks": [
            _serialize_care_task(task) for task in result.created_follow_up_tasks
        ],
        "existing_follow_up_tasks": [
            _serialize_care_task(task) for task in result.existing_follow_up_tasks
        ],
        "workflow_completed": result.workflow_completed,
        "replayed_existing_result": result.replayed_existing_result,
        "warnings": list(result.warnings),
    }


async def _async_handle_log_event(call: ServiceCall) -> dict[str, Any]:
    runtime = _runtime(call.hass)
    reptile_id = _parse_reptile_identifier(runtime, call)
    notes = _optional_text(call, "notes")
    try:
        event = CareEvent(
            reptile_id=reptile_id,
            event_type=CareEventType(_require_text(call, "event_type")),
            timestamp=_optional_datetime(call, "timestamp") or datetime.now(UTC),
            context=_json_object(call, "context"),
            actor_id=_actor_id(call),
            source=SOURCE_HOME_ASSISTANT_SERVICE,
            environmental_snapshot=_json_object(call, "environmental_context"),
            attachment_references=_attachments(call, "attachment_references"),
            metadata=MappingProxyType({} if notes is None else {"notes": notes}),
        )
        await runtime.event_store.async_append_event(event)
    except (ValueError, ReptileError) as err:
        raise HomeAssistantError(str(err)) from err
    await runtime.coordinator.async_refresh()
    return {"care_event": _serialize_event(event)}


async def _async_handle_get_tasks(call: ServiceCall) -> dict[str, Any]:
    runtime = _runtime(call.hass)
    now = datetime.now(UTC)
    tasks = runtime.care_task_repository.all()
    if _field_present(call, "reptile_id") or _field_present(call, "slug"):
        reptile_id = _parse_reptile_identifier(runtime, call)
        tasks = tuple(task for task in tasks if task.reptile_id == reptile_id)
    if _field_present(call, "care_plan_id"):
        care_plan_id = _require_text(call, "care_plan_id")
        tasks = tuple(task for task in tasks if task.care_plan_id == care_plan_id)
    if _field_present(call, "status"):
        try:
            status = CareTaskStatus(_require_text(call, "status"))
        except ValueError as err:
            raise HomeAssistantError("status is invalid") from err
        tasks = tuple(task for task in tasks if task.status is status)
    include_terminal = cv.boolean(call.data.get("include_terminal", False))
    if not include_terminal:
        tasks = tuple(task for task in tasks if task.status is CareTaskStatus.PENDING)
    if _field_present(call, "due_before"):
        due_before = _parse_datetime(call.data.get("due_before"), "due_before")
        tasks = tuple(task for task in tasks if task.due_at <= due_before)
    if _field_present(call, "due_after"):
        due_after = _parse_datetime(call.data.get("due_after"), "due_after")
        tasks = tuple(task for task in tasks if task.due_at >= due_after)
    if _field_present(call, "due_state"):
        due_state = _require_text(call, "due_state")
        tasks = tuple(
            task
            for task in tasks
            if project_due_state(task, now=now).value == due_state
        )
    limit = call.data.get("limit")
    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise HomeAssistantError("limit must be a positive integer")
        tasks = tasks[:limit]
    return {"tasks": [_serialize_care_task(task, now=now) for task in tasks]}


async def _async_handle_get_timeline(call: ServiceCall) -> dict[str, Any]:
    runtime = _runtime(call.hass)
    events = runtime.timeline.all_events()
    if _field_present(call, "reptile_id") or _field_present(call, "slug"):
        reptile_id = _parse_reptile_identifier(runtime, call)
        events = tuple(event for event in events if event.reptile_id == reptile_id)
    if _field_present(call, "event_type"):
        try:
            event_type = CareEventType(_require_text(call, "event_type"))
        except ValueError as err:
            raise HomeAssistantError("event_type is invalid") from err
        events = tuple(event for event in events if event.event_type is event_type)
    if _field_present(call, "start"):
        start = _parse_datetime(call.data.get("start"), "start")
        events = tuple(event for event in events if event.timestamp >= start)
    if _field_present(call, "end"):
        end = _parse_datetime(call.data.get("end"), "end")
        events = tuple(event for event in events if event.timestamp <= end)
    limit = call.data.get("limit")
    if limit is not None:
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise HomeAssistantError("limit must be a positive integer")
        events = events[:limit]
    return {"events": [_serialize_event(event) for event in events]}
