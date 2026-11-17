"""Fixtures for the import-flow tests (workstream E).

Run offscreen in the Qt environments (QT_QPA_PLATFORM=offscreen is set here
if missing). `src/` is put on sys.path so the tests run with or without
PYTHONPATH. Scratch files go under /tmp/sfa-e/.

The fakes (FakeMW and friends) live in `sfa_flow_helpers.py`, which also
says exactly what is faked. This folder is put on sys.path here, so test
modules import that module by its unique name however pytest is invoked
(`pytest tests/flow`, `pytest tests/flow tests/ui`, `pytest tests`).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

HERE = Path(__file__).resolve().parent
SRC = HERE.parents[1] / "src"
for _p in (str(SRC), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from aqt.qt import QApplication  # noqa: E402

from sfa_flow_helpers import SCRATCH, FakeMW, build_apkg  # noqa: E402


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    if not config.option.basetemp:
        from anki.buildinfo import version

        root = os.path.join(SCRATCH, "pytest")
        os.makedirs(root, exist_ok=True)
        config.option.basetemp = os.path.join(root, "anki" + version)


@pytest.fixture(scope="session")
def qapp():
    # Anki sets the UI language when a profile loads; do it here so aqt's
    # own messages (tr.*) work.
    import anki.lang

    anki.lang.set_lang("en_US")
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def make_col(tmp_path):
    from anki.collection import Collection

    made = []

    def make(name: str = "user") -> Any:
        d = tmp_path / name
        d.mkdir(parents=True, exist_ok=True)
        col = Collection(str(d / "collection.anki2"))
        made.append(col)
        return col

    yield make
    for col in made:
        try:
            col.close()
        except Exception:
            pass


@pytest.fixture
def fake_mw(qapp, make_col, monkeypatch):
    """A FakeMW with a real empty collection, installed as aqt.mw."""
    import aqt

    mw = FakeMW(make_col("user"))
    monkeypatch.setattr(aqt, "mw", mw, raising=False)
    yield mw
    mw.close()
    mw.deleteLater()
    qapp.processEvents()


@pytest.fixture
def pristine_importer():
    """Restore ApkgImporter.do_import, the legacy aqt.importing.importFile
    (where it exists) and the flow's saved original after the test, so every
    test starts from Anki's own importers."""
    from aqt.import_export import importing

    from special_fields_by_ankoma import import_flow

    try:
        import aqt.importing as legacy  # Anki 25.02-26.08 only
    except ImportError:
        legacy = None
    saved = importing.ApkgImporter.__dict__["do_import"]
    saved_legacy = getattr(legacy, "importFile", None)
    saved_original = import_flow._original_do_import
    yield importing
    importing.ApkgImporter.do_import = saved
    if legacy is not None:
        legacy.importFile = saved_legacy
    import_flow._original_do_import = saved_original


@pytest.fixture(scope="session")
def apkg(tmp_path_factory):
    return _session_apkg(tmp_path_factory, "updated 2026.apkg", legacy=False)


@pytest.fixture(scope="session")
def legacy_apkg(tmp_path_factory):
    """Same, in the older package format Anki's legacy importer can read."""
    return _session_apkg(tmp_path_factory, "legacy format.apkg", legacy=True)


def _session_apkg(tmp_path_factory, name, legacy):
    """A tiny Basic deck, built once before any user collection exists.

    Stock note type ids are creation timestamps (ms). An author collection
    created within a few ms of the user's can give the author's "Basic" the
    id of the user's "Cloze", and the forced merge then fails ("Cloze note
    types cannot be merged with regular note types"). Building the package
    first, then waiting, keeps every author id below every user id.
    """
    import time

    from anki.collection import Collection

    d = tmp_path_factory.mktemp("author")
    made = []

    def make(name):
        col = Collection(str(d / (name + ".anki2")))
        made.append(col)
        return col

    path = str(d / name)
    build_apkg(lambda _n: make("a"), path, notes=3, legacy=legacy)
    for col in made:
        col.close()
    time.sleep(0.05)
    return path
