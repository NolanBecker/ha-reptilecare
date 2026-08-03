"""Care plan domain models, scheduling, serialization, and repository."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import date
from enum import StrEnum
import math
import re
from types import MappingProxyType
from typing import Any, Protocol
from uuid import UUID, uuid4

from .reptile import ReptileNotFoundError, ReptileRepository
from .task_template import (
    TaskPriority,
    TaskTemplateNotFoundError,
    TaskTemplateRegistry,
)
from .workflow import WorkflowNotFoundError, WorkflowRegistry

CARE_PLAN_SCHEMA_VERSION = 1
_NAMESPACED_ID = re.compile(r"^[a-z][a-z0-9_]*:[a-z0-9_]+$")


class CarePlanError(Exception):
    """Base exception for care plan operations."""


class InvalidCarePlanError(CarePlanError, ValueError):
    """Raised when a care plan definition is malformed or unsupported."""


class DuplicateCarePlanError(CarePlanError):
    """Raised when a care plan identifier is already registered."""


class CarePlanNotFoundError(CarePlanError, LookupError):
    """Raised when a requested care plan is not registered."""


class UnknownReptileError(CarePlanError, LookupError):
    """Raised when a care plan references an unknown reptile."""


class UnknownTaskTemplateError(CarePlanError, LookupError):
    """Raised when a care plan references an unknown task template."""


class UnknownWorkflowGraphError(CarePlanError, LookupError):
    """Raised when a care plan references an unknown workflow graph."""


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not (normalized := value.strip()):
        raise InvalidCarePlanError(f"{name} must be a non-empty string")
    return normalized


def _optional_text(value: object, name: str) -> str | None:
    return None if value is None else _text(value, name)


def _json_value(value: object, name: str) -> Any:
    """Recursively validate JSON-compatible metadata values."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InvalidCarePlanError(f"{name} numbers must be finite")
        return value
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise InvalidCarePlanError(f"{name} keys must be strings")
        return MappingProxyType(
            {key: _json_value(item, name) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_json_value(item, name) for item in value)
    raise InvalidCarePlanError(f"{name} must contain only JSON-compatible values")


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise InvalidCarePlanError(f"{name} must be an object")
    return value


def _keys(
    value: Mapping[str, Any],
    required: frozenset[str],
    optional: frozenset[str],
    name: str,
) -> None:
    if missing := required - set(value):
        raise InvalidCarePlanError(
            f"{name} is missing keys: {', '.join(sorted(missing))}"
        )
    if unknown := set(value) - required - optional:
        raise InvalidCarePlanError(
            f"{name} contains unknown keys: {', '.join(sorted(unknown))}"
        )


class CarePlanScheduleType(StrEnum):
    """Supported descriptive schedule kinds."""

    INTERVAL = "interval"


class CarePlanScheduleUnit(StrEnum):
    """Supported recurring interval units."""

    HOURS = "hours"
    DAYS = "days"
    WEEKS = "weeks"
    MONTHS = "months"


class ReminderLeadTimeUnit(StrEnum):
    """Supported descriptive reminder lead-time units."""

    MINUTES = "minutes"
    HOURS = "hours"
    DAYS = "days"
    WEEKS = "weeks"


class ReminderRepeatPolicy(StrEnum):
    """Supported descriptive reminder repetition policies."""

    ONCE = "once"
    REPEAT_UNTIL_DUE = "repeat_until_due"


@dataclass(frozen=True, slots=True)
class IntervalSchedule:
    """Descriptive keeper intent for a recurring interval schedule."""

    every: int
    unit: CarePlanScheduleUnit
    schedule_type: CarePlanScheduleType = CarePlanScheduleType.INTERVAL

    def __post_init__(self) -> None:
        if (
            isinstance(self.every, bool)
            or not isinstance(self.every, int)
            or self.every < 1
        ):
            raise InvalidCarePlanError("schedule interval must be a positive integer")
        try:
            unit = CarePlanScheduleUnit(self.unit)
        except (TypeError, ValueError) as err:
            raise InvalidCarePlanError("schedule unit is invalid") from err
        try:
            schedule_type = CarePlanScheduleType(self.schedule_type)
        except (TypeError, ValueError) as err:
            raise InvalidCarePlanError("schedule_type is invalid") from err
        if schedule_type is not CarePlanScheduleType.INTERVAL:
            raise InvalidCarePlanError("unsupported schedule_type")
        object.__setattr__(self, "unit", unit)
        object.__setattr__(self, "schedule_type", schedule_type)


@dataclass(frozen=True, slots=True)
class ReminderLeadTime:
    """A descriptive lead-time value for future reminder scheduling."""

    amount: int
    unit: ReminderLeadTimeUnit

    def __post_init__(self) -> None:
        if (
            isinstance(self.amount, bool)
            or not isinstance(self.amount, int)
            or self.amount < 1
        ):
            raise InvalidCarePlanError(
                "reminder lead_time amount must be a positive integer"
            )
        try:
            unit = ReminderLeadTimeUnit(self.unit)
        except (TypeError, ValueError) as err:
            raise InvalidCarePlanError("reminder lead_time unit is invalid") from err
        object.__setattr__(self, "unit", unit)


@dataclass(frozen=True, slots=True)
class ReminderConfiguration:
    """Descriptive reminder settings for a CarePlan."""

    enabled: bool = False
    lead_time: ReminderLeadTime | None = None
    repeat_policy: ReminderRepeatPolicy = ReminderRepeatPolicy.ONCE
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        if not isinstance(self.enabled, bool):
            raise InvalidCarePlanError("reminder enabled must be a boolean")
        if self.lead_time is not None and not isinstance(
            self.lead_time, ReminderLeadTime
        ):
            raise InvalidCarePlanError("reminder lead_time has an invalid type")
        try:
            repeat_policy = ReminderRepeatPolicy(self.repeat_policy)
        except (TypeError, ValueError) as err:
            raise InvalidCarePlanError("reminder repeat_policy is invalid") from err
        metadata = _json_value(self.metadata, "reminder metadata")
        if not isinstance(metadata, Mapping):
            raise InvalidCarePlanError("reminder metadata must be an object")
        if self.enabled and self.lead_time is None:
            raise InvalidCarePlanError(
                "reminder lead_time is required when reminders are enabled"
            )
        object.__setattr__(self, "repeat_policy", repeat_policy)
        object.__setattr__(self, "metadata", metadata)


@dataclass(frozen=True, slots=True)
class CarePlan:
    """Immutable keeper-owned intent describing one recurring care routine."""

    reptile_id: str
    task_template_id: str
    workflow_id: str
    display_name: str
    schedule: IntervalSchedule
    effective_date: date
    care_plan_id: str = field(default_factory=lambda: str(uuid4()))
    enabled: bool = True
    priority: TaskPriority = TaskPriority.NORMAL
    optional_end_date: date | None = None
    reminder_configuration: ReminderConfiguration = field(
        default_factory=ReminderConfiguration
    )
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))
    schema_version: int = CARE_PLAN_SCHEMA_VERSION
    plan_version: int = 1

    def __post_init__(self) -> None:
        care_plan_id = _text(self.care_plan_id, "care_plan_id")
        try:
            UUID(care_plan_id)
        except ValueError as err:
            raise InvalidCarePlanError("care_plan_id must be a UUID") from err
        reptile_id = _text(self.reptile_id, "reptile_id")
        try:
            UUID(reptile_id)
        except ValueError as err:
            raise InvalidCarePlanError("reptile_id must be a UUID") from err
        for name, value in (
            ("task_template_id", self.task_template_id),
            ("workflow_id", self.workflow_id),
        ):
            normalized = _text(value, name)
            if _NAMESPACED_ID.fullmatch(normalized) is None:
                raise InvalidCarePlanError(
                    f"{name} must be a lowercase namespaced identifier"
                )
            object.__setattr__(self, name, normalized)
        for name, value in (
            ("schema_version", self.schema_version),
            ("plan_version", self.plan_version),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise InvalidCarePlanError(f"{name} must be a positive integer")
        if type(self.effective_date) is not date:
            raise InvalidCarePlanError("effective_date must be a date")
        if (
            self.optional_end_date is not None
            and type(self.optional_end_date) is not date
        ):
            raise InvalidCarePlanError("optional_end_date must be a date")
        if (
            self.optional_end_date is not None
            and self.optional_end_date < self.effective_date
        ):
            raise InvalidCarePlanError(
                "optional_end_date must not be earlier than effective_date"
            )
        if not isinstance(self.enabled, bool):
            raise InvalidCarePlanError("enabled must be a boolean")
        try:
            priority = TaskPriority(self.priority)
        except (TypeError, ValueError) as err:
            raise InvalidCarePlanError("priority is invalid") from err
        if not isinstance(self.schedule, IntervalSchedule):
            raise InvalidCarePlanError("schedule has an invalid type")
        if not isinstance(self.reminder_configuration, ReminderConfiguration):
            raise InvalidCarePlanError("reminder_configuration has an invalid type")
        metadata = _json_value(self.metadata, "metadata")
        if not isinstance(metadata, Mapping):
            raise InvalidCarePlanError("metadata must be an object")

        object.__setattr__(self, "care_plan_id", care_plan_id)
        object.__setattr__(self, "reptile_id", reptile_id)
        object.__setattr__(
            self, "display_name", _text(self.display_name, "display_name")
        )
        object.__setattr__(self, "priority", priority)
        object.__setattr__(self, "metadata", metadata)


class CarePlanPersistence(Protocol):
    """Async persistence boundary used by CarePlanRepository."""

    async def async_load(self) -> tuple[CarePlan, ...]:
        """Load persisted care plans."""
        ...

    async def async_save(self, care_plans: tuple[CarePlan, ...]) -> None:
        """Persist the complete care plan collection."""
        ...


class CarePlanRepository:
    """Validated async repository for keeper-owned CarePlans."""

    def __init__(
        self,
        reptile_repository: ReptileRepository,
        task_templates: TaskTemplateRegistry,
        workflow_graphs: WorkflowRegistry,
        persistence: CarePlanPersistence,
    ) -> None:
        """Initialize an unloaded repository."""
        self._reptile_repository = reptile_repository
        self._task_templates = task_templates
        self._workflow_graphs = workflow_graphs
        self._persistence = persistence
        self._care_plans: Mapping[str, CarePlan] = MappingProxyType({})
        self._write_lock = asyncio.Lock()

    async def async_load(self) -> None:
        """Load and validate all persisted care plans."""
        care_plans = await self._persistence.async_load()
        self._publish(care_plans)

    async def async_add(self, care_plan: CarePlan) -> None:
        """Add and persist a new CarePlan."""
        async with self._write_lock:
            if care_plan.care_plan_id in self._care_plans:
                raise DuplicateCarePlanError(
                    f"duplicate care plan ID: {care_plan.care_plan_id}"
                )
            self._validate_references(care_plan)
            await self._save((*self._care_plans.values(), care_plan))

    async def async_update(self, care_plan: CarePlan) -> None:
        """Replace and persist an existing CarePlan."""
        async with self._write_lock:
            if care_plan.care_plan_id not in self._care_plans:
                raise CarePlanNotFoundError(
                    f"care plan not found: {care_plan.care_plan_id}"
                )
            self._validate_references(care_plan)
            updated = dict(self._care_plans)
            updated[care_plan.care_plan_id] = care_plan
            await self._save(tuple(updated.values()))

    async def async_remove(self, care_plan_id: str) -> CarePlan:
        """Remove a CarePlan without touching reptile or event history."""
        async with self._write_lock:
            care_plan = self.get(care_plan_id)
            updated = dict(self._care_plans)
            del updated[care_plan.care_plan_id]
            await self._save(tuple(updated.values()))
            return care_plan

    async def async_enable(self, care_plan_id: str) -> None:
        """Enable an existing CarePlan."""
        await self.async_update(replace(self.get(care_plan_id), enabled=True))

    async def async_disable(self, care_plan_id: str) -> None:
        """Disable an existing CarePlan."""
        await self.async_update(replace(self.get(care_plan_id), enabled=False))

    def get(self, care_plan_id: str) -> CarePlan:
        """Return one CarePlan by permanent identifier."""
        try:
            return self._care_plans[care_plan_id]
        except KeyError as err:
            raise CarePlanNotFoundError(f"care plan not found: {care_plan_id}") from err

    def all(self, *, include_disabled: bool = True) -> tuple[CarePlan, ...]:
        """List CarePlans in deterministic identifier order."""
        care_plans = tuple(self._care_plans.values())
        if include_disabled:
            return care_plans
        return tuple(care_plan for care_plan in care_plans if care_plan.enabled)

    def for_reptile(
        self, reptile_id: str, *, include_disabled: bool = True
    ) -> tuple[CarePlan, ...]:
        """List CarePlans referencing one reptile."""
        return tuple(
            care_plan
            for care_plan in self.all(include_disabled=include_disabled)
            if care_plan.reptile_id == reptile_id
        )

    def for_template(
        self, task_template_id: str, *, include_disabled: bool = True
    ) -> tuple[CarePlan, ...]:
        """List CarePlans referencing one TaskTemplate."""
        return tuple(
            care_plan
            for care_plan in self.all(include_disabled=include_disabled)
            if care_plan.task_template_id == task_template_id
        )

    def for_enabled(self, enabled: bool = True) -> tuple[CarePlan, ...]:
        """List CarePlans by enabled state."""
        return tuple(
            care_plan
            for care_plan in self._care_plans.values()
            if care_plan.enabled is enabled
        )

    async def _save(self, care_plans: tuple[CarePlan, ...]) -> None:
        """Persist then publish a validated replacement collection."""
        validated = self._validated_state(care_plans)
        ordered = tuple(validated.values())
        await self._persistence.async_save(ordered)
        self._publish(ordered)

    def _publish(self, care_plans: tuple[CarePlan, ...]) -> None:
        """Publish validated CarePlan mappings."""
        self._care_plans = self._validated_state(care_plans)

    def _validated_state(
        self, care_plans: tuple[CarePlan, ...]
    ) -> Mapping[str, CarePlan]:
        """Validate and deterministically index CarePlans."""
        indexed: dict[str, CarePlan] = {}
        for care_plan in care_plans:
            if not isinstance(care_plan, CarePlan):
                raise InvalidCarePlanError(
                    "repository values must be CarePlan instances"
                )
            if care_plan.care_plan_id in indexed:
                raise DuplicateCarePlanError(
                    f"duplicate care plan ID: {care_plan.care_plan_id}"
                )
            self._validate_references(care_plan)
            indexed[care_plan.care_plan_id] = care_plan
        return MappingProxyType(dict(sorted(indexed.items())))

    def _validate_references(self, care_plan: CarePlan) -> None:
        """Ensure the referenced reptile, template, and workflow exist."""
        try:
            self._reptile_repository.get(care_plan.reptile_id)
        except ReptileNotFoundError as err:
            raise UnknownReptileError(
                f"unknown reptile: {care_plan.reptile_id}"
            ) from err
        try:
            self._task_templates.get(care_plan.task_template_id)
        except TaskTemplateNotFoundError as err:
            raise UnknownTaskTemplateError(
                f"unknown task template: {care_plan.task_template_id}"
            ) from err
        try:
            self._workflow_graphs.get(care_plan.workflow_id)
        except WorkflowNotFoundError as err:
            raise UnknownWorkflowGraphError(
                f"unknown workflow graph: {care_plan.workflow_id}"
            ) from err


_CARE_PLAN_REQUIRED_KEYS = frozenset(
    {
        "care_plan_id",
        "reptile_id",
        "task_template_id",
        "workflow_id",
        "display_name",
        "enabled",
        "priority",
        "schedule",
        "effective_date",
        "optional_end_date",
        "reminder_configuration",
        "metadata",
        "schema_version",
        "plan_version",
    }
)
_SCHEDULE_REQUIRED_KEYS = frozenset({"schedule_type", "every", "unit"})
_REMINDER_REQUIRED_KEYS = frozenset(
    {"enabled", "lead_time", "repeat_policy", "metadata"}
)
_LEAD_TIME_REQUIRED_KEYS = frozenset({"amount", "unit"})


def care_plan_to_dict(care_plan: CarePlan) -> dict[str, Any]:
    """Serialize a CarePlan to explicit JSON-compatible values."""
    return {
        "care_plan_id": care_plan.care_plan_id,
        "reptile_id": care_plan.reptile_id,
        "task_template_id": care_plan.task_template_id,
        "workflow_id": care_plan.workflow_id,
        "display_name": care_plan.display_name,
        "enabled": care_plan.enabled,
        "priority": care_plan.priority.value,
        "schedule": {
            "schedule_type": care_plan.schedule.schedule_type.value,
            "every": care_plan.schedule.every,
            "unit": care_plan.schedule.unit.value,
        },
        "effective_date": care_plan.effective_date.isoformat(),
        "optional_end_date": None
        if care_plan.optional_end_date is None
        else care_plan.optional_end_date.isoformat(),
        "reminder_configuration": {
            "enabled": care_plan.reminder_configuration.enabled,
            "lead_time": None
            if care_plan.reminder_configuration.lead_time is None
            else {
                "amount": care_plan.reminder_configuration.lead_time.amount,
                "unit": care_plan.reminder_configuration.lead_time.unit.value,
            },
            "repeat_policy": care_plan.reminder_configuration.repeat_policy.value,
            "metadata": _to_json_compatible(care_plan.reminder_configuration.metadata),
        },
        "metadata": _to_json_compatible(care_plan.metadata),
        "schema_version": care_plan.schema_version,
        "plan_version": care_plan.plan_version,
    }


def _to_json_compatible(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _to_json_compatible(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_to_json_compatible(item) for item in value]
    return value


def care_plan_from_dict(value: Mapping[str, Any]) -> CarePlan:
    """Deserialize and strictly validate a serialized CarePlan."""
    data = _mapping(value, "care plan")
    _keys(data, _CARE_PLAN_REQUIRED_KEYS, frozenset(), "care plan")
    if data["schema_version"] != CARE_PLAN_SCHEMA_VERSION:
        raise InvalidCarePlanError(
            f"unsupported schema version: {data['schema_version']!r}"
        )

    schedule = _mapping(data["schedule"], "schedule")
    _keys(schedule, _SCHEDULE_REQUIRED_KEYS, frozenset(), "schedule")

    reminder = _mapping(data["reminder_configuration"], "reminder_configuration")
    _keys(reminder, _REMINDER_REQUIRED_KEYS, frozenset(), "reminder_configuration")
    lead_time_value = reminder["lead_time"]
    if lead_time_value is None:
        lead_time = None
    else:
        lead_time_item = _mapping(lead_time_value, "reminder lead_time")
        _keys(
            lead_time_item,
            _LEAD_TIME_REQUIRED_KEYS,
            frozenset(),
            "reminder lead_time",
        )
        lead_time = ReminderLeadTime(
            amount=lead_time_item["amount"],
            unit=lead_time_item["unit"],
        )

    return CarePlan(
        care_plan_id=data["care_plan_id"],
        reptile_id=data["reptile_id"],
        task_template_id=data["task_template_id"],
        workflow_id=data["workflow_id"],
        display_name=data["display_name"],
        enabled=data["enabled"],
        priority=data["priority"],
        schedule=IntervalSchedule(
            schedule_type=schedule["schedule_type"],
            every=schedule["every"],
            unit=schedule["unit"],
        ),
        effective_date=_deserialize_date(data["effective_date"], "effective_date"),
        optional_end_date=_deserialize_date(
            data["optional_end_date"], "optional_end_date"
        ),
        reminder_configuration=ReminderConfiguration(
            enabled=reminder["enabled"],
            lead_time=lead_time,
            repeat_policy=reminder["repeat_policy"],
            metadata=reminder["metadata"],
        ),
        metadata=data["metadata"],
        schema_version=data["schema_version"],
        plan_version=data["plan_version"],
    )


def _deserialize_date(value: object, name: str) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidCarePlanError(f"{name} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as err:
        raise InvalidCarePlanError(f"{name} must be an ISO date") from err


class MemoryCarePlanPersistence:
    """In-memory persistence adapter for domain tests and development."""

    def __init__(self, care_plans: tuple[CarePlan, ...] = ()) -> None:
        """Initialize with an immutable CarePlan collection."""
        self.care_plans = tuple(care_plans)

    async def async_load(self) -> tuple[CarePlan, ...]:
        """Return the current in-memory collection."""
        return self.care_plans

    async def async_save(self, care_plans: tuple[CarePlan, ...]) -> None:
        """Replace the in-memory collection."""
        self.care_plans = tuple(care_plans)
