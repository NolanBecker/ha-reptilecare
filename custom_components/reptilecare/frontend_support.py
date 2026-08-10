"""Frontend asset registration for bundled ReptileCare modules."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components import frontend
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    FRONTEND_MODULE_URL,
    FRONTEND_PANEL_COMPONENT,
    FRONTEND_PANEL_URL_PATH,
    FRONTEND_STATIC_PATH,
)
from .version import INTEGRATION_VERSION

_DATA_STATIC_REGISTERED = f"{DOMAIN}_frontend_static_registered"
_FRONTEND_DIRECTORY = Path(__file__).parent / "frontend"


async def async_register_frontend_assets(hass: HomeAssistant) -> None:
    """Register bundled frontend modules when the HA frontend is available."""
    if "frontend" not in hass.config.components:
        return

    if not hass.data.get(_DATA_STATIC_REGISTERED):
        await hass.http.async_register_static_paths(
            [StaticPathConfig(FRONTEND_STATIC_PATH, str(_FRONTEND_DIRECTORY))]
        )
        hass.data[_DATA_STATIC_REGISTERED] = True

    frontend.add_extra_js_url(
        hass,
        f"{FRONTEND_MODULE_URL}?v={INTEGRATION_VERSION}",
    )
    frontend.async_register_built_in_panel(
        hass,
        FRONTEND_PANEL_COMPONENT,
        sidebar_title="Today's Care",
        sidebar_icon="mdi:lizard",
        frontend_url_path=FRONTEND_PANEL_URL_PATH,
        config_panel_domain=DOMAIN,
        update=True,
    )


def async_unregister_frontend_assets(hass: HomeAssistant) -> None:
    """Remove the bundled module URL from the active frontend runtime."""
    if "frontend" not in hass.config.components:
        return

    frontend.remove_extra_js_url(
        hass,
        f"{FRONTEND_MODULE_URL}?v={INTEGRATION_VERSION}",
    )
    if frontend.async_panel_exists(hass, FRONTEND_PANEL_URL_PATH):
        frontend.async_remove_panel(hass, FRONTEND_PANEL_URL_PATH)
