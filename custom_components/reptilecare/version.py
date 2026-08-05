"""Manifest-backed integration version helpers."""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path


@lru_cache(maxsize=1)
def _load_manifest_version() -> str:
    manifest_path = Path(__file__).with_name("manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    version = manifest.get("version")
    if not isinstance(version, str) or not version:
        raise RuntimeError("Integration manifest is missing a string version")
    return version


INTEGRATION_VERSION = _load_manifest_version()
