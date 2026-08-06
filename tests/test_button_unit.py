"""Pure-Python tests for the ReptileCare button platform."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.reptilecare.button import ReptileGenerateTasksButton
from custom_components.reptilecare.task_generation import TaskGenerationResult


def _button(generator_result: TaskGenerationResult) -> ReptileGenerateTasksButton:
    class _FakeGenerator:
        def __init__(self, result: TaskGenerationResult) -> None:
            self._result = result
            self.calls: list[dict[str, object]] = []

        async def async_generate(self, **kwargs):
            self.calls.append(kwargs)
            return self._result

    generator = _FakeGenerator(generator_result)
    runtime = SimpleNamespace(
        coordinator=SimpleNamespace(last_update_success=True),
        care_task_generator=generator,
    )
    entry = SimpleNamespace(runtime_data=runtime)
    button = ReptileGenerateTasksButton(entry, "pixel-id")
    button.hass = SimpleNamespace()
    return button


def test_generate_tasks_button_logs_success(monkeypatch, caplog) -> None:
    """Successful generation logs a concise summary."""
    caplog.set_level("INFO")

    async def _run() -> None:
        button = _button(
            TaskGenerationResult(
                created_task_ids=("task-1",),
                existing_task_ids=("task-2",),
                skipped_plan_ids=("plan-1",),
            )
        )

        await button.async_press()

        assert "created=1 existing=1 skipped=1" in caplog.text

    asyncio.run(_run())


def test_generate_tasks_button_logs_warning_for_partial_errors(
    monkeypatch, caplog
) -> None:
    """Partial generation errors warn without failing the button press."""
    caplog.set_level("WARNING")

    async def _run() -> None:
        button = _button(
            TaskGenerationResult(
                created_task_ids=("task-1",),
                errors={"plan-1": "missing template"},
            )
        )

        await button.async_press()

        assert "completed with warnings" in caplog.text

    asyncio.run(_run())


def test_generate_tasks_button_raises_for_total_failure(monkeypatch, caplog) -> None:
    """Pure generation failures surface a Home Assistant button error."""
    caplog.set_level("ERROR")

    async def _run() -> None:
        button = _button(TaskGenerationResult(errors={"plan-1": "missing template"}))

        with pytest.raises(HomeAssistantError, match="plan-1: missing template"):
            await button.async_press()

        assert "Generate tasks button failed for reptile pixel-id" in caplog.text

    asyncio.run(_run())
