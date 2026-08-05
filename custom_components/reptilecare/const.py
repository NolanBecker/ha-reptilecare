"""Constants for ReptileCare."""

from typing import Final

DOMAIN: Final = "reptilecare"
INTEGRATION_NAME: Final = "ReptileCare"
EVENT_REPTILECARE_UPDATED: Final = f"{DOMAIN}_updated"
MANUFACTURER: Final = "ReptileCare"
SIGNAL_RUNTIME_UPDATED: Final = f"{DOMAIN}_runtime_updated"
FRONTEND_STATIC_PATH: Final = f"/{DOMAIN}-frontend"
FRONTEND_MODULE_URL: Final = f"{FRONTEND_STATIC_PATH}/reptilecare.js"
