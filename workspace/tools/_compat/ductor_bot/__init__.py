"""Compatibility shim for the sandbox container.

The real ``ductor_bot`` package is installed on the host, not inside
``ductor-sandbox``. Framework tool scripts import their helpers through
``ductor_bot._home_defaults.workspace.tools._tool_shared``, which fails here.

Patching those tool scripts does not survive — the framework restores them
from its own defaults. So instead this shim provides the import path and
forwards to the workspace copy of ``_tool_shared``.

Activated via ``PYTHONPATH`` in ``~/.ductor/.env``.
"""
