"""Fixtures for the settings-window tests (workstream C).

Run offscreen: QT_QPA_PLATFORM=offscreen (set here if missing).
`src/` is put on sys.path so the tests work with or without PYTHONPATH.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

SRC = Path(__file__).resolve().parents[2] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pytest  # noqa: E402

from aqt.qt import QApplication  # noqa: E402

# A small stand-in for the user's collection.
ALL_FIELDS = [
    "Header", "Text", "Images", "Extra", "Personal Notes", "Textbook", "Citation",
    "Remarks", "Sources", "Footer", "Extra 1", "Extra 2", "Back Extra",
    "Lecture Notes", "Missed Questions",
]
ALL_TAGS = [
    "#edited", "#edited::images", "my-edits", "my-edits::rewritten",
    "board-review", "board-review::missed", "weak-areas", "#image-based",
    "##ANKOMA-v1.2::AP::Breast", "##ANKOMA-v1.2::CP::Coagulation", "Edit-later",
]


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def make_dialog(qapp):
    from special_fields_by_ankoma.config import default_settings
    from special_fields_by_ankoma.settings_dialog import SettingsDialog

    made = []

    def make(settings=None, fields=None, tags=None, show=True):
        dlg = SettingsDialog(
            None,
            settings if settings is not None else default_settings(),
            ALL_FIELDS if fields is None else fields,
            ALL_TAGS if tags is None else tags,
        )
        made.append(dlg)
        if show:
            dlg.show()
            qapp.processEvents()
        return dlg

    yield make
    for dlg in made:
        # done() closes without reject(), so a window left with changes
        # never asks "Discard your changes?" during teardown.
        dlg.done(0)
        dlg.deleteLater()
    qapp.processEvents()
