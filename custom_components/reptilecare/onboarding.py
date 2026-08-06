"""Shared onboarding and built-in content installation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import re
from types import MappingProxyType
from typing import Any
from uuid import uuid4

from .application import CareEventRecorded, CarePlanUpdated, ReptileUpdated
from .content.loader import BuiltinContentBundle
from .domain.care_plan import CarePlan, IntervalSchedule
from .domain.reptile import Reptile, ReptileOverrides, ReptileSex
from .domain.task_template import TaskPriority
from .models import CareEvent, CareEventType, ReptileCareRuntimeData

_NON_SLUG = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True, slots=True)
class OnboardingRequest:
    """Serialized onboarding request captured by the config flow."""

    display_name: str
    species_id: str
    selected_care_plan_ids: tuple[str, ...]
    generate_initial_tasks: bool
    nickname: str | None = None
    morph: str | None = None
    sex: str | None = None
    hatch_date: date | None = None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class OnboardingResult:
    """Structured onboarding installation result."""

    reptile: Reptile
    care_plans: tuple[CarePlan, ...]
    generated_task_ids: tuple[str, ...] = ()
    existing_task_ids: tuple[str, ...] = ()
    skipped_plan_ids: tuple[str, ...] = ()


def serialize_request(request: OnboardingRequest) -> dict[str, Any]:
    """Serialize an onboarding request into config-entry-safe data."""
    return {
        "display_name": request.display_name,
        "nickname": request.nickname,
        "species_id": request.species_id,
        "selected_care_plan_ids": list(request.selected_care_plan_ids),
        "generate_initial_tasks": request.generate_initial_tasks,
        "morph": request.morph,
        "sex": request.sex,
        "hatch_date": None
        if request.hatch_date is None
        else request.hatch_date.isoformat(),
        "notes": request.notes,
    }


def deserialize_request(data: dict[str, Any]) -> OnboardingRequest:
    """Deserialize config-entry onboarding data."""
    hatch_date = data.get("hatch_date")
    return OnboardingRequest(
        display_name=str(data["display_name"]),
        nickname=_optional_str(data.get("nickname")),
        species_id=str(data["species_id"]),
        selected_care_plan_ids=tuple(
            str(item) for item in data["selected_care_plan_ids"]
        ),
        generate_initial_tasks=bool(data.get("generate_initial_tasks", False)),
        morph=_optional_str(data.get("morph")),
        sex=_optional_str(data.get("sex")),
        hatch_date=None
        if hatch_date in (None, "")
        else date.fromisoformat(str(hatch_date)),
        notes=_optional_str(data.get("notes")),
    )


async def async_apply_onboarding(
    runtime: ReptileCareRuntimeData,
    request: OnboardingRequest,
    *,
    now: datetime | None = None,
) -> OnboardingResult:
    """Install a reptile and selected built-in care plans."""
    species = runtime.content.species.get(request.species_id)
    reptile = Reptile(
        reptile_id=str(uuid4()),
        display_name=request.display_name.strip(),
        species_profile_id=species.species_id,
        slug=_unique_slug(runtime, request.display_name),
        morph=_optional_str(request.morph),
        sex=None if request.sex is None else ReptileSex(request.sex),
        hatch_date=request.hatch_date,
        notes=_combined_notes(request.nickname, request.notes),
        overrides=ReptileOverrides(MappingProxyType({})),
    )
    await runtime.reptile_repository.async_add(reptile)

    care_plans: list[CarePlan] = []
    for plan_id in request.selected_care_plan_ids:
        template = runtime.content.care_plans.get(plan_id)
        care_plan = CarePlan(
            reptile_id=reptile.reptile_id,
            task_template_id=template.task_template_id,
            workflow_id=template.workflow_id,
            display_name=template.display_name,
            enabled=True,
            priority=TaskPriority(template.priority),
            schedule=IntervalSchedule(every=template.every, unit=template.unit),
            effective_date=(now or datetime.now(UTC)).date(),
            metadata=template.metadata,
        )
        await runtime.care_plan_repository.async_add(care_plan)
        care_plans.append(care_plan)

    events = [
        ReptileUpdated(
            reptile_id=reptile.reptile_id,
            enabled=reptile.enabled,
            slug=reptile.slug,
        ),
        *(
            CarePlanUpdated(
                reptile_id=care_plan.reptile_id,
                care_plan_id=care_plan.care_plan_id,
                enabled=care_plan.enabled,
            )
            for care_plan in care_plans
        ),
    ]
    await runtime.event_publisher.async_publish_many(tuple(events))

    if not request.generate_initial_tasks:
        return OnboardingResult(reptile=reptile, care_plans=tuple(care_plans))

    generation = await runtime.care_task_generator.async_generate(
        now=now or datetime.now(UTC),
        reptile_id=reptile.reptile_id,
    )
    return OnboardingResult(
        reptile=reptile,
        care_plans=tuple(care_plans),
        generated_task_ids=generation.created_task_ids,
        existing_task_ids=generation.existing_task_ids,
        skipped_plan_ids=generation.skipped_plan_ids,
    )


async def async_import_demo_data(
    runtime: ReptileCareRuntimeData,
    *,
    now: datetime | None = None,
) -> OnboardingResult:
    """Install a lightweight optional demo reptile and history."""
    request = OnboardingRequest(
        display_name="Pixel",
        nickname="Pixel",
        species_id="builtin:gargoyle_gecko",
        selected_care_plan_ids=(
            "builtin:feed_fruit_every_2_days",
            "builtin:spot_clean_daily",
            "builtin:change_water_daily",
        ),
        generate_initial_tasks=True,
        notes="Optional demo data installed from the options flow.",
    )
    result = await async_apply_onboarding(runtime, request, now=now)
    event = CareEvent(
        reptile_id=result.reptile.reptile_id,
        event_type=CareEventType.FEEDING,
        timestamp=(now or datetime.now(UTC)) - timedelta(days=3),
        source="reptilecare_demo",
        metadata=MappingProxyType({"demo": True}),
    )
    await runtime.event_store.async_append_event(event)
    await runtime.event_publisher.async_publish(
        CareEventRecorded(
            reptile_id=event.reptile_id,
            event_id=str(event.event_id),
            event_type=event.event_type.value,
            task_id=event.task_id,
            care_plan_id=event.care_plan_id,
        )
    )
    return result


def recommended_care_plan_choices(
    content: BuiltinContentBundle,
    species_id: str,
) -> tuple[tuple[str, str], ...]:
    """Return stable `(value, label)` pairs for one species' recommended plans."""
    species = content.species.get(species_id)
    return tuple(
        (plan_id, content.care_plans.get(plan_id).display_name)
        for plan_id in species.recommended_care_plan_ids
    )


def species_choices(content: BuiltinContentBundle) -> tuple[tuple[str, str], ...]:
    """Return stable `(value, label)` pairs for species selection."""
    return tuple(
        (item.species_id, item.display_name)
        for item in sorted(content.species.all(), key=lambda item: item.display_name)
    )


def _unique_slug(runtime: ReptileCareRuntimeData, display_name: str) -> str | None:
    candidate = _slugify(display_name)
    if candidate is None:
        return None
    if not runtime.reptile_repository.contains_slug(candidate):
        return candidate
    suffix = 2
    while runtime.reptile_repository.contains_slug(f"{candidate}-{suffix}"):
        suffix += 1
    return f"{candidate}-{suffix}"


def _slugify(value: str) -> str | None:
    normalized = _NON_SLUG.sub("-", value.strip().casefold()).strip("-")
    return normalized or None


def _combined_notes(nickname: str | None, notes: str | None) -> str | None:
    parts = []
    if nickname:
        parts.append(f"Nickname: {nickname.strip()}")
    if notes and notes.strip():
        parts.append(notes.strip())
    if not parts:
        return None
    return "\n".join(parts)


def _optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
