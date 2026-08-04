"""Shared TaskOutcome value object used by care execution."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import math
import re
from types import MappingProxyType
from typing import Any

_LOCAL_ID = re.compile(r"^[a-z][a-z0-9_]*$")


class InvalidTaskOutcomeError(ValueError):
    """Raised when a TaskOutcome contains invalid data."""


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not (normalized := value.strip()):
        raise InvalidTaskOutcomeError(f"{name} must be a non-empty string")
    return normalized


def _json_value(value: object, name: str) -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InvalidTaskOutcomeError(f"{name} numbers must be finite")
        return value
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise InvalidTaskOutcomeError(f"{name} keys must be strings")
        return MappingProxyType(
            {key: _json_value(item, name) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(_json_value(item, name) for item in value)
    raise InvalidTaskOutcomeError(f"{name} must contain only JSON-compatible values")


def _to_json_compatible(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _to_json_compatible(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_to_json_compatible(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class TaskOutcome:
    """Structured task-resolution outcome scoped to one task template."""

    outcome_id: str
    metadata: Mapping[str, Any] = field(default_factory=lambda: MappingProxyType({}))

    def __post_init__(self) -> None:
        outcome_id = _text(self.outcome_id, "outcome_id")
        if _LOCAL_ID.fullmatch(outcome_id) is None:
            raise InvalidTaskOutcomeError("outcome_id must be a lowercase identifier")
        metadata = _json_value(self.metadata, "outcome metadata")
        if not isinstance(metadata, Mapping):
            raise InvalidTaskOutcomeError("outcome metadata must be an object")
        object.__setattr__(self, "outcome_id", outcome_id)
        object.__setattr__(self, "metadata", metadata)


def task_outcome_to_dict(outcome: TaskOutcome) -> dict[str, Any]:
    """Serialize a TaskOutcome to JSON-compatible values."""
    return {
        "outcome_id": outcome.outcome_id,
        "metadata": _to_json_compatible(outcome.metadata),
    }


def task_outcome_from_dict(value: Mapping[str, Any]) -> TaskOutcome:
    """Deserialize a TaskOutcome from a strict mapping."""
    if set(value) != {"outcome_id", "metadata"}:
        unknown = set(value) - {"outcome_id", "metadata"}
        missing = {"outcome_id", "metadata"} - set(value)
        if missing:
            raise InvalidTaskOutcomeError(
                f"task outcome is missing keys: {', '.join(sorted(missing))}"
            )
        raise InvalidTaskOutcomeError(
            f"task outcome contains unknown keys: {', '.join(sorted(unknown))}"
        )
    metadata = value["metadata"]
    if not isinstance(metadata, Mapping):
        raise InvalidTaskOutcomeError("task outcome metadata must be an object")
    return TaskOutcome(
        outcome_id=value["outcome_id"],
        metadata=metadata,
    )
