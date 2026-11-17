"""The wrap, the menu item and the three paths through the flow, driven
through aqt's real `import_file` routing, real modal dialogs (exec()), aqt's
real `CollectionOp` and undo operation, the real settings window and the
real engine on a real collection. `mw` is a `FakeMW` (see sfa_flow_helpers.py)."""

from __future__ import annotations

import pytest
from PyQt6.QtTest import QTest

from aqt.qt import QApplication, QDialog, Qt

from special_fields_by_ankoma import import_flow as flow
from special_fields_by_ankoma.config import default_config
from special_fields_by_ankoma.model import ADDON_NAME, UNDO_LABEL, ImportResult
from special_fields_by_ankoma.settings_dialog import choices_summary, load_settings

from sfa_flow_helpers import FakeMW, build_apkg, find_top_level, when_shown


def _wait(qapp, cond, ms=5000):
    for _ in range(ms // 10):
        if cond():
            return True
        qapp.processEvents()
        QTest.qWait(10)
    return cond()


def _click(name):
    return lambda dlg: QTest.mouseClick(getattr(dlg, name), Qt.MouseButton.LeftButton)


def _record_original(monkeypatch, importing):
    """Replace Anki's ImportDialog (what the original do_import opens) with a
    recorder, so 'the original importer was called with these arguments' is
    observable without a web view."""
    calls = []
    monkeypatch.setattr(importing, "ImportDialog", lambda mw, args: calls.append((mw, args.path)))
    return calls


# --------------------------------------------------------------------------
# Installation


def test_wrap_installed_once_and_idempotent(pristine_importer, fake_mw):
    importing = pristine_importer
    stock = importing.ApkgImporter.__dict__["do_import"].__func__
    assert flow.install_import_wrapper() is True
    wrapped = importing.ApkgImporter.__dict__["do_import"]
    assert isinstance(wrapped, staticmethod)
    assert wrapped.__func__._sfa_original is stock
    assert flow._original_do_import is stock
    # Second (and third) install: nothing changes, no double wrap.
    assert flow.install_import_wrapper() is True
    flow.setup(fake_mw)
    assert importing.ApkgImporter.__dict__["do_import"] is wrapped
    assert flow._original_do_import is stock


def test_menu_item_added_once_and_opens_settings(fake_mw, pristine_importer, monkeypatch):
    flow.setup(fake_mw)
    flow.setup(fake_mw)
    acts = [a for a in fake_mw.form.menuTools.actions() if a.text() == ADDON_NAME]
    assert len(acts) == 1
    assert acts[0].objectName() == flow.MENU_ACTION_NAME
    opened = []
    monkeypatch.setattr(flow, "open_settings", lambda mw, parent=None: opened.append((mw, parent)))
    acts[0].trigger()
    assert opened == [(fake_mw, None)]


def test_setup_never_raises_and_leaves_importer_untouched(fake_mw, pristine_importer, monkeypatch):
    importing = pristine_importer
    before = importing.ApkgImporter.__dict__["do_import"]

    def boom():
        raise RuntimeError("simulated: API differs on this Anki version")

    monkeypatch.setattr(flow, "install_import_wrapper", boom)
    broken_mw = object()  # no .form: the menu step fails too
    flow.setup(broken_mw)  # must not raise
    assert importing.ApkgImporter.__dict__["do_import"] is before


def test_wrap_skipped_when_do_import_missing(pristine_importer, monkeypatch):
    importing = pristine_importer

    class Odd:
        pass

    monkeypatch.setattr(importing, "ApkgImporter", Odd)
    assert flow.install_import_wrapper() is False
    assert not hasattr(Odd, "do_import")


# --------------------------------------------------------------------------
# The three buttons and cancel, through aqt's real import_file routing


@pytest.fixture
def wired(fake_mw, pristine_importer, monkeypatch):
    importing = pristine_importer
    flow.setup(fake_mw)
    original = _record_original(monkeypatch, importing)
    engine_calls = []
    monkeypatch.setattr(flow, "run_import_with_choices",
                        lambda mw, path, settings: engine_calls.append((mw, path, settings)))
    return fake_mw, importing, original, engine_calls


@pytest.mark.parametrize("name", ["updated 2026.apkg", "Ankoma-v1.3.apkg", "random.APKG",
                                  "deck.zip", "nothing to do with ankoma.apkg"])
def test_question_appears_for_any_file_name(wired, qapp, name):
    mw, importing, original, engine_calls = wired
    seen = {}

    def look(dlg):
        seen["file"] = dlg.file_name
        seen["parent"] = dlg.parent()
        seen["rows"] = dlg.rows()
        dlg.reject()

    state = when_shown("special_fields_question", look)
    importing.import_file(mw, "/somewhere/" + name)
    assert state["widget"] is not None
    assert seen["file"] == name
    assert seen["parent"] is mw
    assert seen["rows"] == choices_summary(load_settings(mw))
    assert original == [] and engine_calls == []


def test_standard_import_calls_original_with_same_arguments(wired):
    mw, importing, original, engine_calls = wired
    when_shown("special_fields_question", _click("standard_button"))
    importing.import_file(mw, "/x/deck.apkg")
    assert original == [(mw, "/x/deck.apkg")]
    assert engine_calls == []


def test_import_with_my_choices_calls_engine_path(wired):
    mw, importing, original, engine_calls = wired
    mw.addonManager.config = dict(default_config(), protected_tags=["#edited"])
    when_shown("special_fields_question", _click("import_button"))
    importing.import_file(mw, "/x/deck.apkg")
    assert original == []
    assert len(engine_calls) == 1
    assert engine_calls[0][0] is mw and engine_calls[0][1] == "/x/deck.apkg"
    assert engine_calls[0][2] == load_settings(mw)
    assert engine_calls[0][2].protected_tags == ("#edited",)


@pytest.mark.parametrize("how", ["escape", "close"])
def test_cancel_imports_nothing(wired, how):
    mw, importing, original, engine_calls = wired

    def cancel(dlg):
        if how == "escape":
            QTest.keyClick(dlg, Qt.Key.Key_Escape)
        else:
            dlg.close()

    state = when_shown("special_fields_question", cancel)
    importing.import_file(mw, "/x/deck.apkg")
    assert state["widget"] is not None
    assert original == [] and engine_calls == []


def test_colpkg_routes_are_not_intercepted(wired, monkeypatch):
    """collection.apkg / .colpkg go to Anki's full-restore path first."""
    mw, importing, original, engine_calls = wired
    confirms = []
    monkeypatch.setattr(importing, "askUser", lambda *a, **k: confirms.append(1) and False)
    importing.import_file(mw, "/x/collection.apkg")
    importing.import_file(mw, "/x/backup.colpkg")
    assert confirms == [1, 1]
    assert find_top_level("special_fields_question") is None
    assert original == [] and engine_calls == []


def test_change_choices_opens_real_settings_then_question_again(wired, qapp):
    """"Change choices…" opens the real settings window over the question;
    after Save the question is shown again with refreshed rows; then the
    user imports with the new choices."""
    mw, importing, original, engine_calls = wired
    log = {}

    def in_settings(sdlg):
        log["settings_parent"] = sdlg.parent()
        sdlg.styling_switch.setChecked(False)  # "Card styling: Keep mine"
        sdlg.row_for("Extra").toggle.set_keep(True)
        QTest.mouseClick(sdlg.save_button, Qt.MouseButton.LeftButton)

    def in_question(dlg):
        log["before"] = dlg.rows()
        when_shown("special_fields_settings", in_settings)
        QTest.mouseClick(dlg.change_button, Qt.MouseButton.LeftButton)
        # back from the settings window: the question is still open
        log["visible_after"] = dlg.isVisible()
        log["after"] = dlg.rows()
        QTest.mouseClick(dlg.import_button, Qt.MouseButton.LeftButton)

    when_shown("special_fields_question", in_question)
    importing.import_file(mw, "/x/deck.apkg")
    assert log["settings_parent"].objectName() == "special_fields_question"
    assert dict(log["before"])["Card styling"] == "Update"
    assert log["visible_after"] is True
    after = dict(log["after"])
    assert after["Card styling"] == "Keep mine"
    assert after["Fields you keep"] == "Extra, Personal Notes"
    assert mw.addonManager.writes, "settings were saved through addonManager"
    assert len(engine_calls) == 1
    assert engine_calls[0][2].update_note_types is False
    assert original == []


def test_change_choices_cancel_keeps_rows(wired):
    mw, importing, original, engine_calls = wired
    log = {}

    def in_question(dlg):
        log["before"] = dlg.rows()
        when_shown("special_fields_settings", _click("cancel_button"))
        QTest.mouseClick(dlg.change_button, Qt.MouseButton.LeftButton)
        log["after"] = dlg.rows()
        dlg.reject()

    when_shown("special_fields_question", in_question)
    importing.import_file(mw, "/x/deck.apkg")
    assert log["after"] == log["before"]
    assert mw.addonManager.writes == []
    assert original == [] and engine_calls == []


def test_question_failure_falls_back_to_anki(wired, monkeypatch):
    """A bug in the question dialog must not block importing."""
    mw, importing, original, engine_calls = wired

    def broken(*a, **k):
        raise RuntimeError("simulated bug")

    monkeypatch.setattr(flow, "QuestionDialog", broken)
    importing.import_file(mw, "/x/deck.apkg")
    assert original == [(mw, "/x/deck.apkg")]


# --------------------------------------------------------------------------
# "Import with my choices" end to end: real CollectionOp, real engine


def test_engine_runs_in_collection_op_and_summary_then_done(fake_mw, pristine_importer, apkg, qapp):
    importing = pristine_importer
    mw = fake_mw
    flow.setup(mw)
    seen = {}

    def in_summary(dlg):
        seen["rows"] = dlg.rows()
        seen["parent"] = dlg.parent()
        seen["undo_actions_updated_before_summary"] = mw.undo_action_updates
        QTest.mouseClick(dlg.done_button, Qt.MouseButton.LeftButton)

    when_shown("special_fields_question", _click("import_button"))
    importing.import_file(mw, apkg)
    # The summary appears once aqt has finished the op (next event loop turn).
    when_shown("special_fields_summary", in_summary)
    assert _wait(qapp, lambda: "rows" in seen)
    assert mw.col.note_count() == 3
    assert dict(seen["rows"])["New notes added"] == "3"
    assert seen["parent"] is mw
    # CollectionOp ran with Anki's import progress callback, on the background thread
    assert mw.taskman.progress_updates == [importing.import_progress_update]
    assert mw.background_ops == 0
    # aqt's on_op_finished ran (undo menu refreshed) before the summary
    assert seen["undo_actions_updated_before_summary"] >= 1
    assert mw.col.undo_status().undo == UNDO_LABEL  # Done does not undo


def test_summary_undo_reverts_the_import(fake_mw, pristine_importer, apkg, qapp, monkeypatch):
    importing = pristine_importer
    mw = fake_mw
    flow.setup(mw)
    from aqt import gui_hooks

    undone = []
    gui_hooks.state_did_undo.append(undone.append)
    try:
        when_shown("special_fields_question", _click("import_button"))
        importing.import_file(mw, apkg)
        state = when_shown("special_fields_summary", _click("undo_button"))
        assert _wait(qapp, lambda: state["widget"] is not None)
        assert _wait(qapp, lambda: bool(undone))
    finally:
        gui_hooks.state_did_undo.remove(undone.append)
    assert mw.col.note_count() == 0
    assert undone[0].operation == UNDO_LABEL
    assert mw.col.undo_status().undo != UNDO_LABEL


def test_undo_refused_when_update_is_not_on_top(fake_mw, monkeypatch):
    warned = []
    import aqt.utils

    monkeypatch.setattr(aqt.utils, "showWarning", lambda *a, **k: warned.append(a))
    assert flow.undo_update(fake_mw) is False
    assert warned


def test_engine_failure_shows_anki_error_and_changes_nothing(fake_mw, pristine_importer, tmp_path, monkeypatch):
    importing = pristine_importer
    mw = fake_mw
    flow.setup(mw)
    bad = tmp_path / "broken.apkg"
    bad.write_bytes(b"this is not a zip file")
    errors = []
    import aqt.operations

    monkeypatch.setattr(aqt.operations, "show_exception",
                        lambda *, parent, exception: errors.append((parent, exception)))
    before_undo = mw.col.undo_status().undo
    when_shown("special_fields_question", _click("import_button"))
    importing.import_file(mw, str(bad))
    assert len(errors) == 1 and errors[0][0] is mw
    assert mw.col.note_count() == 0
    assert mw.col.undo_status().undo == before_undo
    assert find_top_level("special_fields_summary") is None
    assert mw.background_ops == 0


def test_op_returns_result_with_changes(fake_mw, apkg, monkeypatch):
    """The CollectionOp's op returns the engine's ImportResult (its .changes
    is what aqt uses to refresh)."""
    import aqt.operations

    captured = {}
    real = aqt.operations.CollectionOp

    class Spy(real):
        def __init__(self, parent, op):
            captured["parent"] = parent
            captured["op"] = op
            super().__init__(parent, op)

    monkeypatch.setattr(aqt.operations, "CollectionOp", Spy)
    monkeypatch.setattr(flow, "_later", lambda mw, f: None)
    flow.run_import_with_choices(fake_mw, apkg, load_settings(fake_mw))
    assert captured["parent"] is fake_mw
    # the op already ran; run a second import directly to look at its return
    res = captured["op"](fake_mw.col)
    assert isinstance(res, ImportResult)
    assert res.changes is not None


# --------------------------------------------------------------------------
# A note type move the engine cannot repair (contract rule 10g)


def _unrepairable_move(make_col, mw, tmp_path):
    """Author's "SFA AP" (templates "{{Text}}" and "{{Header}} {{Text}}")
    and "SFA MI" (template "{{Header}} {{Text}}"); the user has v1 plus an
    own MI note; the author moves one AP note to MI. Repairing Anki's merge
    would leave MI with two identical card fronts, which Anki refuses, so
    the engine raises MergeRepairError (built for real, nothing mocked)."""
    import time

    from anki.collection import (ExportAnkiPackageOptions, ImportAnkiPackageOptions,
                                 ImportAnkiPackageRequest)

    def nt(col, name, fields, fronts):
        mm = col.models
        m = mm.new(name)
        for f in fields:
            mm.add_field(m, mm.new_field(f))
        for i, front in enumerate(fronts):
            t = mm.new_template("Card %d" % (i + 1))
            t["qfmt"] = front
            t["afmt"] = "{{FrontSide}}<hr id=answer>{{Extra}}"
            mm.add_template(m, t)
        mm.add(m)
        time.sleep(0.002)
        return mm.by_name(name)

    def export(col, path):
        col.export_anki_package(out_path=path, options=ExportAnkiPackageOptions(
            with_scheduling=False, with_deck_configs=False, with_media=True, legacy=False), limit=None)
        return path

    author = make_col("unrepairable-author")
    ap = nt(author, "SFA AP", ["Header", "Text", "Extra"], ["{{Text}}", "{{Header}} {{Text}}"])
    mi = nt(author, "SFA MI", ["Header", "Text", "Images", "Extra"], ["{{Header}} {{Text}}"])
    for guid, m in (("u1", ap), ("u2", ap), ("u3", mi)):
        note = author.new_note(m)
        note["Header"] = "H " + guid
        note["Text"] = "T " + guid
        note.guid = guid
        author.add_note(note, author.decks.id("Move Deck"))
    author.db.execute("update notes set mod=1000000")
    v1 = export(author, str(tmp_path / "move-v1.apkg"))
    col = mw.col
    col.import_anki_package(ImportAnkiPackageRequest(package_path=v1, options=ImportAnkiPackageOptions()))
    col.db.execute("update notes set mod=3000000")
    note = col.get_note(col.find_notes("")[0])
    note["Extra"] = "my last edit"
    col.update_note(note)
    info = author.models.change_notetype_info(old_notetype_id=ap["id"], new_notetype_id=mi["id"])
    req = info.input
    req.note_ids.extend([author.db.scalar("select id from notes where guid='u1'")])
    author.models.change_notetype_of_notes(req)
    author.db.execute("update notes set mod=2000000")
    return export(author, str(tmp_path / "move-v2.apkg"))


def test_unrepairable_move_shows_plain_warning_and_imports_nothing(fake_mw, pristine_importer, make_col,
                                                                  tmp_path, qapp, monkeypatch):
    from aqt.qt import QMessageBox, QTimer

    importing = pristine_importer
    mw = fake_mw
    flow.setup(mw)
    path = _unrepairable_move(make_col, mw, tmp_path)
    errors = []
    import aqt.operations

    monkeypatch.setattr(aqt.operations, "show_exception",
                        lambda *, parent, exception: errors.append(exception))
    before = {t: mw.col.db.all("select * from %s order by 1" % t)
              for t in ("notes", "cards", "revlog", "notetypes", "fields", "templates")}
    before_undo = mw.col.undo_status()
    assert before_undo.undo == "Update Note"
    seen = {}

    def poll_box():
        for w in QApplication.topLevelWidgets():
            if isinstance(w, QMessageBox) and w.isVisible():
                seen.update(text=w.text(), fmt=w.textFormat(), icon=w.icon(), title=w.windowTitle(),
                            parent=w.parent())
                w.accept()
                return
        seen["tries"] = seen.get("tries", 0) + 1
        if seen["tries"] < 500:
            QTimer.singleShot(10, poll_box)

    def in_question(dlg):
        poll_box()
        QTest.mouseClick(dlg.import_button, Qt.MouseButton.LeftButton)

    when_shown("special_fields_question", in_question)
    importing.import_file(mw, path)
    assert _wait(qapp, lambda: "text" in seen)
    assert errors == [], "Anki's exception dialog must not be used"
    assert seen["text"] == (
        "Nothing was imported. This file moves some notes to a different note type, and "
        "Special Fields couldn't apply that change safely to your collection. Your collection "
        "is unchanged. You can import this file with Anki's standard import instead, or ask "
        "the deck's author for help."
    )
    assert seen["text"] == flow.MERGE_REPAIR_WARNING
    assert seen["fmt"] == Qt.TextFormat.PlainText
    assert seen["icon"] == QMessageBox.Icon.Warning
    assert seen["title"] == ADDON_NAME
    for _ in range(20):
        qapp.processEvents()
        QTest.qWait(10)
    assert find_top_level("special_fields_summary") is None
    mw.col.models._clear_cache()
    after = {t: mw.col.db.all("select * from %s order by 1" % t) for t in before}
    assert after == before
    status = mw.col.undo_status()
    assert status.undo == before_undo.undo and status.redo == ""
    assert mw.background_ops == 0


def test_other_engine_errors_keep_anki_error_dialog(fake_mw, monkeypatch):
    """Only MergeRepairError gets the plain warning."""
    import aqt.operations
    import aqt.utils

    from special_fields_by_ankoma import engine

    errors, warnings = [], []
    monkeypatch.setattr(aqt.operations, "show_exception",
                        lambda *, parent, exception: errors.append((parent, exception)))
    monkeypatch.setattr(aqt.utils, "showWarning", lambda *a, **k: warnings.append((a, k)))
    monkeypatch.setattr(flow, "_later", lambda mw, f: None)
    boom = RuntimeError("boom")

    def raise_(exc):
        def run(col, path, settings):
            raise exc
        return run

    monkeypatch.setattr(engine, "run_import", raise_(boom))
    flow.run_import_with_choices(fake_mw, "/x/deck.apkg", load_settings(fake_mw))
    assert errors == [(fake_mw, boom)] and warnings == []
    monkeypatch.setattr(engine, "run_import", raise_(engine.MergeRepairError("SFA MI", "test")))
    flow.run_import_with_choices(fake_mw, "/x/deck.apkg", load_settings(fake_mw))
    assert len(errors) == 1 and len(warnings) == 1
    (args, kwargs) = warnings[0]
    assert args[0] == flow.MERGE_REPAIR_WARNING
    assert kwargs.get("textFormat") == "plain" and kwargs.get("title") == ADDON_NAME
