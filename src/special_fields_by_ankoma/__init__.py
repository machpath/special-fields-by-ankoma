"""Special Fields by Ankoma: add-on entry point.

Anki imports this file at startup. Headless tests import the package too,
so nothing here may require a running Anki window.
"""

from __future__ import annotations

try:
    from aqt import mw
except Exception:  # running in a headless test without aqt
    mw = None

if mw is not None:
    from . import import_flow  # noqa: F401  (workstream E registers the hooks)
