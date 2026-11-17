"""Ankoma Special Fields - add-on entry point (spike skeleton).

Integration strategy: we do NOT hook the stock import dialog (it is a Svelte
page that calls the backend directly over mediasrv, with no Python hook).
Instead we wrap `ApkgImporter.do_import`, which every .apkg import path goes
through (File>Import, drag-and-drop, double-click / open-with):
  aqt/main.py: dropEvent -> import_file, handleImport -> import_file,
               onImport -> prompt_for_file_then_import -> import_file
  aqt/import_export/importing.py: import_file -> IMPORTERS[...].do_import
For Ankoma packages we run our own CollectionOp; anything else falls through
to the original (stock dialog), so other decks are unaffected.
"""

from __future__ import annotations

import os
import re

from aqt import mw
from aqt.qt import QAction
from aqt.utils import askUser, getFile, showInfo, tooltip

from . import ankoma_core as core

_ADDON = __name__


def _config() -> dict:
    return mw.addonManager.getConfig(_ADDON) or {}


def _settings(cfg: dict) -> core.Settings:
    return core.Settings(
        protected_fields=set(cfg.get("protected_fields", [])),
        tag_mode=cfg.get("tag_mode", "overwrite"),
        author_tag_re=cfg.get("author_tag_regex", core.DEFAULT_AUTHOR_TAG_RE),
        update_notetypes=bool(cfg.get("update_notetypes", True)),
        merge_notetypes=bool(cfg.get("merge_notetypes", True)),
    )


def run_ankoma_import(path: str) -> None:
    from aqt.import_export.importing import import_progress_update
    from aqt.operations import CollectionOp

    settings = _settings(_config())
    box: dict = {}

    def op(col):
        box["res"] = core.import_ankoma_package(col, path, settings)
        return box["res"].changes  # OpChanges -> aqt refreshes UI, clears caches

    def on_success(_changes) -> None:
        r = box["res"]
        showInfo(
            f"Ankoma update imported.\n\nNotes in package: {r.found}\n"
            f"New: {r.new}\nUpdated: {r.updated}\n"
            f"Protected values restored: {r.restored_fields} fields on "
            f"{r.restored_notes} notes\n"
            f"Skipped (note type conflict): {r.conflicting}\n\n"
            f"Undo with Edit > Undo '{core.UNDO_LABEL}'."
        )

    (
        CollectionOp(parent=mw, op=op)
        .success(on_success)
        .with_backend_progress(import_progress_update)
        .run_in_background()
    )


def _wrap_apkg_importer() -> None:
    from aqt.import_export import importing

    original = importing.ApkgImporter.do_import  # staticmethod -> plain function

    def do_import(mw_, path: str) -> None:
        cfg = _config()
        name = os.path.basename(path)
        if cfg.get("enabled", True) and re.search(cfg.get("filename_pattern", "(?i)ankoma"), name):
            if not cfg.get("ask_before_import", True) or askUser(
                f"'{name}' looks like an Ankoma update.\n\n"
                "Import it with Ankoma Special Fields (protected fields, your "
                "deck placement and scheduling are kept)?\n\n"
                "Choose No to use Anki's standard importer."
            ):
                run_ankoma_import(path)
                return
        original(mw_, path)

    importing.ApkgImporter.do_import = staticmethod(do_import)


def _add_menu() -> None:
    def on_trigger() -> None:
        path = getFile(mw, "Import Ankoma update", None, filter="Anki deck package (*.apkg)", key="import")
        if path:
            run_ankoma_import(str(path))

    action = QAction("Import Ankoma update...", mw)
    action.triggered.connect(on_trigger)
    mw.form.menuTools.addAction(action)


if mw is not None:  # not when imported by headless tests
    _wrap_apkg_importer()
    _add_menu()
