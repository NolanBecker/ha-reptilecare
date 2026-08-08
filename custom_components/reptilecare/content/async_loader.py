"""Home Assistant async adapter for built-in content loading."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from .loader import BuiltinContentLoadResult, load_builtin_content


async def async_load_builtin_content(
    hass: HomeAssistant,
) -> BuiltinContentLoadResult:
    """Load built-in content through Home Assistant's executor pool."""
    return await hass.async_add_executor_job(load_builtin_content)
