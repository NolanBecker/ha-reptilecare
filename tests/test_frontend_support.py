"""Unit tests for bundled frontend asset registration."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from custom_components.reptilecare.const import (
    FRONTEND_MODULE_URL,
    FRONTEND_STATIC_PATH,
)
from custom_components.reptilecare.frontend_support import (
    async_register_frontend_assets,
    async_unregister_frontend_assets,
)
from custom_components.reptilecare.manifest import INTEGRATION_VERSION


def test_frontend_assets_register_once_and_unregister(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bundled frontend resources use one static path and removable module URLs."""

    async def _run() -> None:
        static_calls: list[object] = []
        added_urls: list[str] = []
        removed_urls: list[str] = []

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

    asyncio.run(_run())


def test_frontend_assets_noop_without_frontend_component(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Frontend registration is skipped when the HA frontend is unavailable."""

    async def _run() -> None:
        static_calls: list[object] = []
        added_urls: list[str] = []

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

        await async_register_frontend_assets(hass)
        async_unregister_frontend_assets(hass)

        assert static_calls == []
        assert added_urls == []

    asyncio.run(_run())
