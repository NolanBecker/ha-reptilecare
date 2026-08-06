"""Built-in content registries for ReptileCare."""

from .loader import (
    BuiltinContentBundle,
    BuiltinContentLoader,
    BuiltinContentLoadResult,
    load_builtin_content,
)
from .models import (
    BuiltinCarePlanTemplate,
    BuiltinSpeciesPackage,
    ContentRegistry,
    EnvironmentalTarget,
)

__all__ = [
    "BuiltinCarePlanTemplate",
    "BuiltinContentBundle",
    "BuiltinContentLoadResult",
    "BuiltinContentLoader",
    "BuiltinSpeciesPackage",
    "ContentRegistry",
    "EnvironmentalTarget",
    "load_builtin_content",
]
