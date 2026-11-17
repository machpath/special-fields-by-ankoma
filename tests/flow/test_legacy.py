"""The legacy import route (`aqt.importing.importFile`), which exists on Anki
25.02 to 26.08 and is gone from 26.09.

On aqt 25 (venv-aqt25) these tests drive the real legacy entry points
(`aqt.importing.onImport` -> `importFile`, and the new importer's
`import_file` handing legacy-only types to `importFile`) with the wrapper
installed. On aqt 26.09 (venv-aqt26) they check that there is nothing to
wrap and that setup is still safe. `mw` is a FakeMW (see sfa_flow_helpers.py).
"""

from __future__ import annotations

import pytest
from PyQt6.QtTest import QTest

from aqt.qt import Qt

from special_fields_by_ankoma import import_flow as flow
from special_fields_by_ankoma.settings_dialog import load_settings

from sfa_flow_helpers import find_top_level, when_shown

try:
    import aqt.importing as legacy
except ImportError:
    legacy = None

needs_legacy = pytest.mark.skipif(legacy is None, reason="this Anki has no legacy importer")


def _click(name):
    return lambda dlg: QTest.mouseClick(getattr(dlg, name), Qt.MouseButton.LeftButton)


# --------------------------------------------------------------------------
# 26.09+: nothing to wrap


@pytest.mark.skipif(legacy is not None, reason="this Anki still has the legacy importer")
def test_no_legacy_module_nothing_to_wrap(fake_mw, pristine_importer):
    from anki.buildinfo import version

    assert tuple(int(x) for x in version.split(".")[:2]) >= (26, 9)
    assert flow.install_legacy_wrapper() is False
    flow.setup(fake_mw)  # must not raise
    with pytest.raises(ImportError):
        import aqt.importing  # noqa: F401
    # the modern wrapper and the menu are still installed
    assert pristine_importer.ApkgImporter.do_import._sfa_original is not None
    assert [a.text() for a in fake_mw.form.menuTools.actions()] == ["Special Fields by Ankoma"]


# --------------------------------------------------------------------------
# pure: which files the legacy wrapper intercepts


@pytest.mark.parametrize(
    "path, expected",
    [
        ("/x/updated 2026.apkg", True),
        ("/x/Ankoma-v1.3.APKG", True),
        ("C:\\Users\\me\\Downloads\\deck.apkg", True),
        ("/x/collection.apkg", False),
        ("/x/backup-2026-11-16-10.00.apkg", False),
        ("/x/backup.colpkg", False),
        ("/x/deck.zip", False),
        ("/x/notes.txt", False),
        ("/x/notes.csv", False),
        ("/x/mnemosyne.db", False),
        ("/x/supermemo.xml", False),
        (None, False),
    ],
)
def test_is_legacy_apkg(path, expected):
    assert flow.is_legacy_apkg(path) is expected


# --------------------------------------------------------------------------
# 25.02-26.08: the legacy route gets the question


@pytest.fixture
def legacy_wired(fake_mw, pristine_importer, monkeypatch):
    """Anki's legacy importFile replaced by a recorder BEFORE our wrapper is
    installed, so 'Use Anki's standard import' is seen handing over to it."""
    calls = []
    monkeypatch.setattr(legacy, "importFile", lambda mw, file: calls.append((mw, file)))
    flow.setup(fake_mw)
    engine_calls = []
    monkeypatch.setattr(flow, "run_import_with_choices",
                        lambda mw, path, settings: engine_calls.append((mw, path, settings)))
    return fake_mw, calls, engine_calls


@needs_legacy
def test_legacy_wrap_installed_once_and_idempotent(fake_mw, pristine_importer):
    stock = legacy.importFile
    assert flow.install_legacy_wrapper() is True
    wrapped = legacy.importFile
    assert wrapped is not stock and wrapped._sfa_original is stock
    assert flow.install_legacy_wrapper() is True
    flow.setup(fake_mw)
    assert legacy.importFile is wrapped


@needs_legacy
def test_legacy_setup_failure_leaves_importer_untouched(fake_mw, pristine_importer, monkeypatch):
    stock = legacy.importFile

    def boom():
        raise RuntimeError("simulated")

    monkeypatch.setattr(flow, "install_legacy_wrapper", boom)
    flow.setup(fake_mw)  # must not raise
    assert legacy.importFile is stock


@needs_legacy
def test_legacy_standard_hands_over_to_anki(legacy_wired):
    mw, calls, engine_calls = legacy_wired
    seen = {}

    def answer(dlg):
        seen["file"] = dlg.file_name
        _click("standard_button")(dlg)

    when_shown("special_fields_question", answer)
    legacy.importFile(mw, "/x/updated 2026.apkg")
    assert seen["file"] == "updated 2026.apkg"
    assert calls == [(mw, "/x/updated 2026.apkg")]
    assert engine_calls == []


@needs_legacy
def test_legacy_standard_keyword_arguments(legacy_wired):
    mw, calls, engine_calls = legacy_wired
    when_shown("special_fields_question", _click("standard_button"))
    legacy.importFile(mw=mw, file="/x/deck.apkg")
    assert calls == [(mw, "/x/deck.apkg")]


@needs_legacy
def test_legacy_import_with_my_choices_runs_engine(legacy_wired):
    mw, calls, engine_calls = legacy_wired
    when_shown("special_fields_question", _click("import_button"))
    legacy.importFile(mw, "/x/deck.apkg")
    assert calls == []
    assert len(engine_calls) == 1
    assert engine_calls[0][0] is mw and engine_calls[0][1] == "/x/deck.apkg"
    assert engine_calls[0][2] == load_settings(mw)


@needs_legacy
@pytest.mark.parametrize("how", ["escape", "close"])
def test_legacy_cancel_imports_nothing(legacy_wired, how):
    mw, calls, engine_calls = legacy_wired

    def cancel(dlg):
        if how == "escape":
            QTest.keyClick(dlg, Qt.Key.Key_Escape)
        else:
            dlg.close()

    state = when_shown("special_fields_question", cancel)
    legacy.importFile(mw, "/x/deck.apkg")
    assert state["widget"] is not None
    assert calls == [] and engine_calls == []


@needs_legacy
@pytest.mark.parametrize("name", ["notes.txt", "notes.csv", "deck.zip", "collection.apkg",
                                  "backup-2026-11-16.apkg", "old.colpkg", "export.db"])
def test_legacy_other_types_pass_through_untouched(legacy_wired, name):
    mw, calls, engine_calls = legacy_wired
    legacy.importFile(mw, "/x/" + name)
    assert calls == [(mw, "/x/" + name)]
    assert find_top_level("special_fields_question") is None
    assert engine_calls == []


@needs_legacy
def test_legacy_file_import_menu_route(legacy_wired, monkeypatch):
    """File > Import with the legacy preference: aqt.importing.onImport picks
    a file and calls the module's importFile, which is now ours."""
    mw, calls, engine_calls = legacy_wired
    monkeypatch.setattr(legacy, "getFile", lambda *a, **k: "/x/updated 2026.apkg")
    when_shown("special_fields_question", _click("import_button"))
    legacy.onImport(mw)
    assert [c[1] for c in engine_calls] == ["/x/updated 2026.apkg"]
    assert calls == []


@needs_legacy
def test_legacy_new_import_file_still_one_question(legacy_wired, monkeypatch, pristine_importer):
    """The new importer's import_file sends legacy-only types to importFile
    (no question) and .apkg to ApkgImporter (one question, not two)."""
    mw, calls, engine_calls = legacy_wired
    importing = pristine_importer
    asked = []

    def answer(dlg):
        asked.append(dlg.file_name)
        _click("import_button")(dlg)

    when_shown("special_fields_question", answer)
    importing.import_file(mw, "/x/deck.apkg")
    assert asked == ["deck.apkg"] and len(engine_calls) == 1
    # a legacy-only type (SuperMemo .xml) goes to importFile untouched
    importing.import_file(mw, "/x/supermemo.xml")
    assert calls == [(mw, "/x/supermemo.xml")]
    assert asked == ["deck.apkg"]


@needs_legacy
def test_legacy_standard_runs_real_legacy_importer(legacy_apkg, fake_mw, pristine_importer, monkeypatch):
    """End to end: with our wrapper in place, 'Use Anki's standard import'
    runs Anki's real legacy importer, which adds the notes."""
    mw = fake_mw
    flow.setup(mw)
    path = legacy_apkg
    shown = []
    monkeypatch.setattr(legacy, "showText", lambda *a, **k: shown.append(("text", a)))
    monkeypatch.setattr(legacy, "tooltip", lambda *a, **k: shown.append(("tooltip", a)))
    monkeypatch.setattr(legacy, "showWarning", lambda *a, **k: shown.append(("warning", a)))
    when_shown("special_fields_question", _click("standard_button"))
    legacy.importFile(mw, path)
    assert not any(kind == "warning" for kind, _ in shown), shown
    assert mw.col.note_count() == 3
    assert mw.resets == 1


@needs_legacy
def test_legacy_import_with_my_choices_real_engine(apkg, fake_mw, pristine_importer, qapp):
    """End to end through the legacy entry point with the real engine (which
    uses the backend importer, whatever the legacy preference says)."""
    mw = fake_mw
    flow.setup(mw)
    path = apkg
    seen = {}

    def in_summary(dlg):
        seen["rows"] = dict(dlg.rows())
        _click("done_button")(dlg)

    when_shown("special_fields_question", _click("import_button"))
    legacy.importFile(mw, path)
    when_shown("special_fields_summary", in_summary)
    for _ in range(500):
        if "rows" in seen:
            break
        qapp.processEvents()
        QTest.qWait(10)
    assert seen["rows"]["New notes added"] == "3"
    assert mw.col.note_count() == 3
