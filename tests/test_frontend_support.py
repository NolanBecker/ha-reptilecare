"""Unit tests for bundled frontend asset registration."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from custom_components.reptilecare.const import (
    FRONTEND_MODULE_URL,
    FRONTEND_PANEL_COMPONENT,
    FRONTEND_PANEL_URL_PATH,
    FRONTEND_STATIC_PATH,
)
from custom_components.reptilecare.frontend_support import (
    async_register_frontend_assets,
    async_unregister_frontend_assets,
)
from custom_components.reptilecare.version import INTEGRATION_VERSION


def test_frontend_assets_register_once_and_unregister(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bundled frontend resources use one static path and removable module URLs."""

    async def _run() -> None:
        static_calls: list[object] = []
        added_urls: list[str] = []
        removed_urls: list[str] = []
        registered_panels: list[dict[str, object]] = []
        removed_panels: list[str] = []

        async def _register_static_paths(configs) -> None:
            static_calls.append(configs)

        hass = SimpleNamespace(
            config=SimpleNamespace(components={"frontend"}),
            data={},
            http=SimpleNamespace(async_register_static_paths=_register_static_paths),
        )

        monkeypatch.setattr(
            "custom_components.reptilecare.frontend_support.frontend.add_extra_js_url",
            lambda hass, url: added_urls.append(url),
        )
        monkeypatch.setattr(
            "custom_components.reptilecare.frontend_support.frontend.remove_extra_js_url",
            lambda hass, url: removed_urls.append(url),
        )
        monkeypatch.setattr(
            "custom_components.reptilecare.frontend_support.frontend.async_register_built_in_panel",
            lambda hass, component_name, **kwargs: registered_panels.append(
                {"component_name": component_name, **kwargs}
            ),
        )
        monkeypatch.setattr(
            "custom_components.reptilecare.frontend_support.frontend.async_panel_exists",
            lambda hass, url_path: url_path == FRONTEND_PANEL_URL_PATH,
        )
        monkeypatch.setattr(
            "custom_components.reptilecare.frontend_support.frontend.async_remove_panel",
            lambda hass, url_path: removed_panels.append(url_path),
        )

        await async_register_frontend_assets(hass)
        await async_register_frontend_assets(hass)
        async_unregister_frontend_assets(hass)

        assert len(static_calls) == 1
        static_path = tuple(static_calls[0])[0]
        assert static_path.url_path == FRONTEND_STATIC_PATH
        assert static_path.cache_headers is True
        assert added_urls == [
            f"{FRONTEND_MODULE_URL}?v={INTEGRATION_VERSION}",
            f"{FRONTEND_MODULE_URL}?v={INTEGRATION_VERSION}",
        ]
        assert removed_urls == [f"{FRONTEND_MODULE_URL}?v={INTEGRATION_VERSION}"]
        assert registered_panels == [
            {
                "component_name": FRONTEND_PANEL_COMPONENT,
                "sidebar_title": "Today's Care",
                "sidebar_icon": "mdi:lizard",
                "frontend_url_path": FRONTEND_PANEL_URL_PATH,
                "config_panel_domain": "reptilecare",
                "update": True,
            },
            {
                "component_name": FRONTEND_PANEL_COMPONENT,
                "sidebar_title": "Today's Care",
                "sidebar_icon": "mdi:lizard",
                "frontend_url_path": FRONTEND_PANEL_URL_PATH,
                "config_panel_domain": "reptilecare",
                "update": True,
            },
        ]
        assert removed_panels == [FRONTEND_PANEL_URL_PATH]

    asyncio.run(_run())


def test_frontend_assets_noop_without_frontend_component(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Frontend registration is skipped when the HA frontend is unavailable."""

    async def _run() -> None:
        static_calls: list[object] = []
        added_urls: list[str] = []
        registered_panels: list[object] = []

        async def _register_static_paths(configs) -> None:
            static_calls.append(configs)

        hass = SimpleNamespace(
            config=SimpleNamespace(components=set()),
            data={},
            http=SimpleNamespace(async_register_static_paths=_register_static_paths),
        )

        monkeypatch.setattr(
            "custom_components.reptilecare.frontend_support.frontend.add_extra_js_url",
            lambda hass, url: added_urls.append(url),
        )
        monkeypatch.setattr(
            "custom_components.reptilecare.frontend_support.frontend.async_register_built_in_panel",
            lambda hass, component_name, **kwargs: registered_panels.append(
                (component_name, kwargs)
            ),
        )

        await async_register_frontend_assets(hass)
        async_unregister_frontend_assets(hass)

        assert static_calls == []
        assert added_urls == []
        assert registered_panels == []

    asyncio.run(_run())
