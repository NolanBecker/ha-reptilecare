"""Shared fixtures for ReptileCare tests."""

import os

import pytest

if os.environ.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD") == "1":
    pytest_plugins: tuple[str, ...] = ()

    @pytest.fixture
    def enable_custom_integrations() -> None:
        """Provide a no-op fallback when plugin autoload is disabled."""
else:
    try:
        import pytest_homeassistant_custom_component  # noqa: F401
    except Exception:  # pragma: no cover - local fallback for non-Linux test hosts
        pytest_plugins = ()

        @pytest.fixture
        def enable_custom_integrations() -> None:
            """Provide a no-op fallback when the HA pytest plugin is unavailable."""
    else:
        pytest_plugins = ("pytest_homeassistant_custom_component",)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
) -> None:
    """Enable loading custom integrations in every test."""
