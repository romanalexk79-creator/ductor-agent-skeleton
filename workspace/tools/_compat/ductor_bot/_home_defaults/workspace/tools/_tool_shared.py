"""Forward to the workspace copy of the shared tool helpers."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REAL = Path("/ductor/workspace/tools/_tool_shared.py")

_spec = importlib.util.spec_from_file_location("_ductor_tool_shared_real", _REAL)
if _spec is None or _spec.loader is None:  # pragma: no cover - install error
    raise ImportError(f"cannot load shared tool helpers from {_REAL}")
_module = importlib.util.module_from_spec(_spec)
sys.modules["_ductor_tool_shared_real"] = _module
_spec.loader.exec_module(_module)

available_ids = _module.available_ids
find_by_id = _module.find_by_id
load_collection_or_default = _module.load_collection_or_default
load_collection_strict = _module.load_collection_strict
sanitize_name = _module.sanitize_name
save_collection = _module.save_collection
