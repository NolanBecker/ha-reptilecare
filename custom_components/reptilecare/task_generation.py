"""Pure schedule calculation and CareTask generation services."""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256
from types import MappingProxyType
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from .domain.care_plan import (
    CarePlan,
    CarePlanRepository,
    CarePlanScheduleUnit,
    IntervalSchedule,
)
from .domain.care_task import (
    CareTask,
    CareTaskGenerationReason,
    CareTaskRepository,
)
from .domain.reptile import Reptile, ReptileNotFoundError, ReptileRepository
from .domain.task_template import TaskTemplateNotFoundError, TaskTemplateRegistry
from .domain.workflow import WorkflowNotFoundError, WorkflowRegistry

DEFAULT_TASK_GENERATION_LOOK_AHEAD = timedelta(days=7)
DEFAULT_TASK_GENERATION_LOOK_BACK = timedelta(days=30)
DEFAULT_OVERDUE_GRACE = timedelta()
UTC_TIMEZONE = ZoneInfo("UTC")


@dataclass(frozen=True, slots=True)
class TaskGenerationResult:
    """Structured result for one generation pass."""

    created_task_ids: tuple[str, ...] = ()
    existing_task_ids: tuple[str, ...] = ()
    skipped_plan_ids: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    errors: Mapping[str, str] = field(default_factory=dict)


class ScheduleCalculator:
    """Pure schedule calculator for supported CarePlan interval schedules."""

    def __init__(self, schedule_timezone: ZoneInfo = UTC_TIMEZONE) -> None:
        """Initialize the calculator with one local scheduling timezone."""
        self._schedule_timezone = schedule_timezone

    @property
    def schedule_timezone(self) -> ZoneInfo:
        """Return the configured schedule timezone."""
        return self._schedule_timezone

    def first_occurrence(self, care_plan: CarePlan) -> datetime:
        """Return the first scheduled occurrence for one CarePlan."""
        self._validate_schedule(care_plan.schedule)
        return self._local_date_to_utc(care_plan.effective_date)

    def next_occurrence(self, care_plan: CarePlan, occurrence: datetime) -> datetime:
        """Return the next scheduled occurrence after a prior occurrence."""
        current = self._aware_utc(occurrence, "occurrence")
        schedule = care_plan.schedule
        if schedule.unit is CarePlanScheduleUnit.HOURS:
            return current + timedelta(hours=schedule.every)

        local_time = current.astimezone(self._schedule_timezone)
        if schedule.unit is CarePlanScheduleUnit.DAYS:
            return (local_time + timedelta(days=schedule.every)).astimezone(UTC)
        if schedule.unit is CarePlanScheduleUnit.WEEKS:
            return (local_time + timedelta(weeks=schedule.every)).astimezone(UTC)

        next_date = self._add_months(local_time.date(), schedule.every)
        next_local = datetime.combine(
            next_date,
            local_time.timetz().replace(tzinfo=None),
            tzinfo=self._schedule_timezone,
        )
        return next_local.astimezone(UTC)

    def occurrences_between(
        self,
        care_plan: CarePlan,
        *,
        start: datetime,
        end: datetime,
    ) -> tuple[datetime, ...]:
        """Return scheduled occurrences in the inclusive bounded UTC interval."""
        start_time = self._aware_utc(start, "start")
        end_time = self._aware_utc(end, "end")
        if start_time > end_time:
            raise ValueError("start must not be after end")

        first = self.first_occurrence(care_plan)
        latest_date = care_plan.optional_end_date
        occurrence = first

        while occurrence < start_time:
            next_occurrence = self.next_occurrence(care_plan, occurrence)
            if next_occurrence <= occurrence:
                raise ValueError("schedule must advance occurrences")
            occurrence = next_occurrence
            if (
                latest_date is not None
                and occurrence.astimezone(self._schedule_timezone).date() > latest_date
            ):
                return ()

        results: list[datetime] = []
        while occurrence <= end_time:
            local_date = occurrence.astimezone(self._schedule_timezone).date()
            if latest_date is not None and local_date > latest_date:
                break
            if occurrence >= start_time:
                results.append(occurrence)
            next_occurrence = self.next_occurrence(care_plan, occurrence)
            if next_occurrence <= occurrence:
                raise ValueError("schedule must advance occurrences")
            occurrence = next_occurrence
        return tuple(results)

    def _local_date_to_utc(self, value: date) -> datetime:
        local_start = datetime.combine(value, time.min, tzinfo=self._schedule_timezone)
        return local_start.astimezone(UTC)

    @staticmethod
    def _validate_schedule(schedule: IntervalSchedule) -> None:
        if not isinstance(schedule, IntervalSchedule):
            raise ValueError("schedule must be an IntervalSchedule")

    @staticmethod
    def _aware_utc(value: datetime, name: str) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{name} must be timezone-aware")
        return value.astimezone(UTC)

    @staticmethod
    def _add_months(value: date, months: int) -> date:
        absolute_month = (value.year * 12 + value.month - 1) + months
        year, month_index = divmod(absolute_month, 12)
        month = month_index + 1
        day = min(value.day, monthrange(year, month)[1])
        return date(year, month, day)


class CareTaskGenerator:
    """Focused application service for deterministic CareTask generation."""

    def __init__(
        self,
        reptile_repository: ReptileRepository,
        care_plan_repository: CarePlanRepository,
        task_templates: TaskTemplateRegistry,
        workflow_graphs: WorkflowRegistry,
        task_repository: CareTaskRepository,
        schedule_calculator: ScheduleCalculator,
        *,
        default_look_ahead: timedelta = DEFAULT_TASK_GENERATION_LOOK_AHEAD,
        default_look_back: timedelta = DEFAULT_TASK_GENERATION_LOOK_BACK,
    ) -> None:
        """Initialize the generator with validated dependencies."""
        for name, value in (
            ("default_look_ahead", default_look_ahead),
            ("default_look_back", default_look_back),
        ):
            if value < timedelta():
                raise ValueError(f"{name} must not be negative")
        self._reptile_repository = reptile_repository
        self._care_plan_repository = care_plan_repository
        self._task_templates = task_templates
        self._workflow_graphs = workflow_graphs
        self._task_repository = task_repository
        self._schedule_calculator = schedule_calculator
        self._default_look_ahead = default_look_ahead
        self._default_look_back = default_look_back

    async def async_generate(
        self,
        *,
        now: datetime,
        look_ahead: timedelta | None = None,
        look_back: timedelta | None = None,
        reptile_id: str | None = None,
        care_plan_id: str | None = None,
    ) -> TaskGenerationResult:
        """Generate missing CareTasks within the bounded window."""
        current_time = self._aware_utc(now, "now")
        look_ahead_window = (
            self._default_look_ahead if look_ahead is None else look_ahead
        )
        look_back_window = self._default_look_back if look_back is None else look_back
        for name, value in (
            ("look_ahead", look_ahead_window),
            ("look_back", look_back_window),
        ):
            if value < timedelta():
                raise ValueError(f"{name} must not be negative")
        window_start = current_time - look_back_window
        window_end = current_time + look_ahead_window

        created: list[str] = []
        existing: list[str] = []
        skipped: list[str] = []
        errors: dict[str, str] = {}

        care_plans = self._care_plan_repository.all(include_disabled=True)
        if care_plan_id is not None:
            care_plans = tuple(
                care_plan
                for care_plan in care_plans
                if care_plan.care_plan_id == care_plan_id
            )
        if reptile_id is not None:
            care_plans = tuple(
                care_plan
                for care_plan in care_plans
                if care_plan.reptile_id == reptile_id
            )

        for care_plan in care_plans:
            if not care_plan.enabled:
                skipped.append(care_plan.care_plan_id)
                continue

            local_today = current_time.astimezone(
                self._schedule_calculator.schedule_timezone
            ).date()
            if (
                care_plan.optional_end_date is not None
                and care_plan.optional_end_date < local_today
            ):
                skipped.append(care_plan.care_plan_id)
                continue

            try:
                reptile = self._reptile_repository.get(care_plan.reptile_id)
                self._task_templates.get(care_plan.task_template_id)
                self._workflow_graphs.get(care_plan.workflow_id)
            except (
                ReptileNotFoundError,
                TaskTemplateNotFoundError,
                WorkflowNotFoundError,
            ) as err:
                errors[care_plan.care_plan_id] = str(err)
                continue

            if not reptile.enabled:
                skipped.append(care_plan.care_plan_id)
                continue

            occurrences = self._schedule_calculator.occurrences_between(
                care_plan,
                start=window_start,
                end=window_end,
            )
            for occurrence in occurrences:
                reason = self._reason_for_occurrence(
                    occurrence=occurrence,
                    now=current_time,
                )
                generation_key = self.build_generation_key(
                    care_plan=care_plan,
                    occurrence=occurrence,
                    generation_reason=reason,
                )
                if self._task_repository.contains_generation_key(generation_key):
                    existing.append(
                        self._task_repository.get_by_generation_key(
                            generation_key
                        ).task_id
                    )
                    continue
                task = self._build_task(
                    reptile=reptile,
                    care_plan=care_plan,
                    occurrence=occurrence,
                    generation_key=generation_key,
                    generation_reason=reason,
                    created_at=current_time,
                )
                await self._task_repository.async_add(task)
                created.append(task.task_id)

        return TaskGenerationResult(
            created_task_ids=tuple(created),
            existing_task_ids=tuple(existing),
            skipped_plan_ids=tuple(sorted(set(skipped))),
            warnings=(),
            errors=MappingProxyType(dict(sorted(errors.items()))),
        )

    def build_generation_key(
        self,
        *,
        care_plan: CarePlan,
        occurrence: datetime,
        generation_reason: CareTaskGenerationReason,
    ) -> str:
        """Build a deterministic idempotency key for one logical occurrence."""
        occurrence_time = self._aware_utc(occurrence, "occurrence")
        seed = "|".join(
            (
                care_plan.care_plan_id,
                str(care_plan.plan_version),
                care_plan.task_template_id,
                care_plan.workflow_id,
                generation_reason.value,
                occurrence_time.isoformat(),
            )
        )
        return sha256(seed.encode("utf-8")).hexdigest()

    def _build_task(
        self,
        *,
        reptile: Reptile,
        care_plan: CarePlan,
        occurrence: datetime,
        generation_key: str,
        generation_reason: CareTaskGenerationReason,
        created_at: datetime,
    ) -> CareTask:
        occurrence_time = self._aware_utc(occurrence, "occurrence")
        workflow = self._workflow_graphs.get(care_plan.workflow_id)
        return CareTask(
            reptile_id=reptile.reptile_id,
            care_plan_id=care_plan.care_plan_id,
            task_template_id=care_plan.task_template_id,
            workflow_id=care_plan.workflow_id,
            due_at=occurrence_time,
            generation_key=generation_key,
            created_at=created_at,
            generated_by=(
                f"care_plan:{care_plan.care_plan_id}:v{care_plan.plan_version}"
            ),
            workflow_chain_id=self._build_workflow_chain_id(care_plan, occurrence_time),
            workflow_node_id=workflow.start_node,
            generation_reason=generation_reason,
        )

    @staticmethod
    def _build_workflow_chain_id(care_plan: CarePlan, occurrence: datetime) -> str:
        seed = (
            f"{care_plan.care_plan_id}|"
            f"{care_plan.task_template_id}|"
            f"{occurrence.isoformat()}"
        )
        return str(uuid5(NAMESPACE_URL, seed))

    @staticmethod
    def _reason_for_occurrence(
        *, occurrence: datetime, now: datetime
    ) -> CareTaskGenerationReason:
        return (
            CareTaskGenerationReason.SYSTEM_RECONCILIATION
            if occurrence < now
            else CareTaskGenerationReason.RECURRING_CARE_PLAN
        )

    @staticmethod
    def _aware_utc(value: datetime, name: str) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{name} must be timezone-aware")
        return value.astimezone(UTC)
