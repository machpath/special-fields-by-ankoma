"""The question and summary dialogs on their own (plain data, no `mw`)."""

from __future__ import annotations

import pytest
from PyQt6.QtTest import QTest

from aqt.qt import QDialog, QLabel, QPushButton, QTextDocument, QWidget, Qt

from special_fields_by_ankoma import import_flow as flow
from special_fields_by_ankoma.config import default_settings
from special_fields_by_ankoma.model import ACCENT_COLOR, ImportResult, UNDO_LABEL
from special_fields_by_ankoma.settings_dialog import choices_summary

ROWS = choices_summary(default_settings())


def _texts(widget: QWidget, name: str):
    return [w.text() for w in widget.findChildren(QLabel, name)]


def _shown_tooltip(text: str) -> str:
    """What Qt displays for a tooltip: rich text if Qt guesses so, else plain."""
    if Qt.mightBeRichText(text):
        doc = QTextDocument()
        doc.setHtml(text)
        return doc.toPlainText()
    return text


def _tab_chain(dlg: QDialog):
    chain = []
    w = dlg.nextInFocusChain()
    while w is not dlg and len(chain) < 200:
        chain.append(w)
        w = w.nextInFocusChain()
    return [x for x in chain if x.focusPolicy() & Qt.FocusPolicy.TabFocus and x.isVisible()]


@pytest.fixture
def question(qapp):
    made = []

    def make(file_name="updated 2026.apkg", rows=ROWS, change=None):
        dlg = flow.QuestionDialog(None, file_name, rows, change)
        made.append(dlg)
        dlg.show()
        qapp.processEvents()
        return dlg

    yield make
    for d in made:
        d.close()
        d.deleteLater()
    qapp.processEvents()


@pytest.fixture
def summary(qapp):
    made = []

    def make(result, file_name="updated 2026.apkg"):
        dlg = flow.SummaryDialog(None, result, file_name)
        made.append(dlg)
        dlg.show()
        qapp.processEvents()
        return dlg

    yield make
    for d in made:
        d.close()
        d.deleteLater()
    qapp.processEvents()


# --------------------------------------------------------------------------
# Question dialog


def test_question_texts(question):
    dlg = question()
    assert dlg.windowTitle() == "Special Fields by Ankoma"
    assert dlg.findChild(QLabel, "question_heading").text() == (
        "Would you like to update with Special Fields by Ankoma?"
    )
    assert dlg.findChild(QLabel, "file_label").text() == "File: updated 2026.apkg"
    assert dlg.findChild(QLabel, "keep_note").text() == (
        "Your review history, and any cards you moved to other decks, are always kept."
    )
    assert dlg.findChild(QLabel, "sync_note").text() == (
        "If you've studied on another device, sync this computer before you update."
    )
    assert dlg.findChild(QLabel, "choices_title").text() == "Your saved choices"
    assert dlg.rows() == ROWS
    assert _texts(dlg, "choice_label") == [r[0] for r in ROWS]
    assert _texts(dlg, "choice_value") == [r[1] for r in ROWS]
    assert dlg.import_button.text() == "Import with my choices"
    assert dlg.change_button.text() == "Change choices…"
    assert dlg.standard_button.text() == "Use Anki's standard import"


def test_question_primary_button(question):
    dlg = question()
    assert dlg.import_button.isDefault()
    assert not dlg.change_button.isDefault() and not dlg.change_button.autoDefault()
    assert not dlg.standard_button.isDefault() and not dlg.standard_button.autoDefault()
    css = dlg.styleSheet()
    assert ACCENT_COLOR in css and "QPushButton#import_button" in css
    # The accent is used only for the primary button(s).
    assert css.count(ACCENT_COLOR) == 2  # background + border of import/done rule
    assert dlg.focusWidget() is dlg.import_button


@pytest.mark.parametrize(
    "button, expected",
    [("import_button", flow.CHOICE_IMPORT), ("standard_button", flow.CHOICE_STANDARD)],
)
def test_question_buttons_set_choice(question, button, expected):
    dlg = question()
    QTest.mouseClick(getattr(dlg, button), Qt.MouseButton.LeftButton)
    assert dlg.choice() == expected
    assert dlg.result() == QDialog.DialogCode.Accepted
    assert not dlg.isVisible()


def test_question_enter_imports(question):
    dlg = question()
    QTest.keyClick(dlg, Qt.Key.Key_Return)
    assert dlg.choice() == flow.CHOICE_IMPORT


def test_question_escape_and_close_cancel(question):
    dlg = question()
    QTest.keyClick(dlg, Qt.Key.Key_Escape)
    assert dlg.choice() == flow.CHOICE_CANCEL
    assert dlg.result() == QDialog.DialogCode.Rejected
    dlg2 = question()
    dlg2.close()
    assert dlg2.choice() == flow.CHOICE_CANCEL


def test_question_change_refreshes_rows_and_stays_open(question):
    calls = []
    new_rows = [("Fields you keep", "Personal Notes, Extra"), ("Protected tags", "#edited")]

    def change():
        calls.append(1)
        return new_rows

    dlg = question(change=change)
    QTest.mouseClick(dlg.change_button, Qt.MouseButton.LeftButton)
    assert calls == [1]
    assert dlg.isVisible()
    assert dlg.choice() == flow.CHOICE_CANCEL  # nothing chosen yet
    assert dlg.rows() == new_rows
    assert _texts(dlg, "choice_value") == ["Personal Notes, Extra", "#edited"]
    assert dlg.focusWidget() is dlg.import_button


def test_question_change_returning_none_keeps_rows(question):
    dlg = question(change=lambda: None)
    QTest.mouseClick(dlg.change_button, Qt.MouseButton.LeftButton)
    assert dlg.rows() == ROWS


def test_question_tab_chain(question):
    dlg = question()
    chain = _tab_chain(dlg)
    assert chain == [dlg.import_button, dlg.change_button, dlg.standard_button]
    # Labels never take focus.
    for lab in dlg.findChildren(QLabel):
        assert not (lab.focusPolicy() & Qt.FocusPolicy.TabFocus)


def test_question_object_and_accessible_names(question):
    dlg = question()
    assert dlg.objectName() == "special_fields_question"
    for name in ("question_heading", "file_label", "keep_note", "sync_note", "choices_title"):
        assert dlg.findChild(QLabel, name) is not None, name
    for name in ("import_button", "change_button", "standard_button"):
        b = dlg.findChild(QPushButton, name)
        assert b is not None and b.accessibleName(), name
    rows = dlg.findChildren(QWidget, "choice_row")
    assert [r.property("label") for r in rows] == [r[0] for r in ROWS]
    assert rows[0].accessibleName() == "%s: %s" % ROWS[0]


@pytest.mark.parametrize(
    "name",
    [
        "updated 2026.apkg",
        "Ankoma-v1.3.apkg",
        "my deck <b>bold</b> & co.apkg",
        "日本語デッキ.apkg",
        "x" * 200 + ".apkg",
    ],
)
def test_question_shows_any_file_name(question, name):
    dlg = question(file_name=name)
    lab = dlg.findChild(QLabel, "file_label")
    assert lab.textFormat() == Qt.TextFormat.PlainText
    # Tooltips are escaped rich text, so markup in a file name shows literally.
    assert _shown_tooltip(lab.toolTip()) == name
    assert lab.accessibleName() == "File: " + name
    if len(name) < 60:
        assert lab.text() == "File: " + name
    else:
        assert lab.text().startswith("File: x") and "…" in lab.text()
        assert lab.width() <= dlg.width()


# --------------------------------------------------------------------------
# Summary rows (pure)


def _result(**kw):
    base = dict(notes_in_file=10, notes_added=2, notes_updated=6, fields_kept=4,
                notes_with_fields_kept=3, protected_tags_kept=1, notes_with_tags_kept=1)
    base.update(kw)
    return ImportResult(**base)


FIXED = [("Tags", "Replaced with the update's"), ("Your existing cards: review history and decks", "Unchanged")]
COUNTS = [("Notes updated", "6"), ("New notes added", "2"),
          ("Fields kept from your version", "4"), ("Protected tags kept", "1")]


def test_summary_rows_no_skips():
    assert flow.summary_rows(_result()) == COUNTS + FIXED


def test_summary_rows_only_unchanged_are_left_out():
    r = _result(notes_skipped=2, skip_reasons={"unchanged": 2})
    assert flow.summary_rows(r) == COUNTS + FIXED
    assert flow.skip_details(r) == []


def test_summary_rows_other_reasons_counted_without_unchanged():
    r = _result(notes_skipped=7, skip_reasons={"unchanged": 4, "note type conflict": 2, "missing deck": 1})
    assert flow.summary_rows(r) == COUNTS + [("Notes skipped", "3")] + FIXED
    assert flow.skip_details(r) == [("note type conflict", 2), ("missing deck", 1)]
    assert flow.skip_details_text(r) == "Note type conflict: 2 · Missing deck: 1"


def test_question_shows_learning_progress_and_preset_rows(question):
    assert [r[0] for r in ROWS][-2:] == ["Learning progress", "Deck options"]
    assert dict(ROWS)["Learning progress"] == "Not imported"
    assert dict(ROWS)["Deck options"] == "Not imported"
    import dataclasses
    on = choices_summary(dataclasses.replace(default_settings(), import_scheduling=True,
                                             import_deck_presets=True))
    dlg = question(rows=on)
    labels = _texts(dlg, "choice_label")
    values = _texts(dlg, "choice_value")
    assert labels[-2:] == ["Learning progress", "Deck options"]
    assert values[-2:] == ["Imported for new cards", "Imported"]
    assert dlg.findChild(QLabel, "keep_note").text() == (
        "Your review history, and any cards you moved to other decks, are always kept."
    )


def test_summary_rows_learning_progress_only_when_imported():
    assert flow.summary_rows(_result(cards_with_progress=0)) == COUNTS + FIXED
    r = _result(learning_progress_imported=True, cards_with_progress=12)
    assert flow.summary_rows(r) == COUNTS + FIXED + [("New cards with learning progress", "12")]
    r = _result(learning_progress_imported=True)
    assert flow.summary_rows(r)[-1] == ("New cards with learning progress", "0")


def test_summary_dialog_learning_progress_row(summary):
    dlg = summary(_result(learning_progress_imported=True, cards_with_progress=5))
    assert _texts(dlg, "row_label")[-2:] == ["Your existing cards: review history and decks", "New cards with learning progress"]
    assert _texts(dlg, "row_value")[-2:] == ["Unchanged", "5"]


def test_summary_rows_zero_reason_ignored():
    r = _result(notes_skipped=0, skip_reasons={"note type conflict": 0})
    assert flow.summary_rows(r) == COUNTS + FIXED


# --------------------------------------------------------------------------
# Summary dialog


def test_summary_dialog_basic(summary):
    dlg = summary(_result())
    assert dlg.windowTitle() == "Special Fields by Ankoma"
    assert dlg.findChild(QLabel, "summary_heading").text() == "Update complete"
    assert _texts(dlg, "row_label") == [r[0] for r in COUNTS + FIXED]
    assert _texts(dlg, "row_value") == [r[1] for r in COUNTS + FIXED]
    assert dlg.findChild(QWidget, "full_sync_notice") is None
    assert dlg.findChild(QLabel, "skip_details") is None
    note = dlg.findChild(QLabel, "undo_note")
    assert "Edit → Undo %s" % UNDO_LABEL in note.text()
    assert "reverses the whole update" in note.text()
    assert dlg.undo_button.text() == "Undo update"
    assert dlg.done_button.text() == "Done"
    assert dlg.done_button.isDefault()
    assert not dlg.undo_button.isDefault() and not dlg.undo_button.autoDefault()
    assert dlg.focusWidget() is dlg.done_button


def test_summary_dialog_skipped_reasons_listed(summary):
    r = _result(notes_skipped=5, skip_reasons={"unchanged": 2, "note type conflict": 3})
    dlg = summary(r)
    labels = _texts(dlg, "row_label")
    assert "Notes skipped" in labels
    assert _texts(dlg, "row_value")[labels.index("Notes skipped")] == "3"
    det = dlg.findChild(QLabel, "skip_details")
    assert det is not None and det.text() == "Note type conflict: 3"
    assert "unchanged" not in det.text().lower()


def test_summary_dialog_full_sync_notice(summary):
    dlg = summary(_result(note_types_changed=True))
    box = dlg.findChild(QWidget, "full_sync_notice")
    assert box is not None and box.isVisible()
    assert dlg.findChild(QLabel, "full_sync_text").text() == (
        "This update changed a note type, so your next sync will be a one-way full "
        "sync. Choose “Upload to AnkiWeb” so this computer's updated copy is kept. "
        "If you studied on another device and hadn't synced this computer first, "
        "undo this update, sync, then import again."
    )
    assert dlg.findChild(QLabel, "full_sync_text").textFormat() == Qt.TextFormat.PlainText
    assert box.accessibleName()


def test_question_sync_note_is_muted_and_directly_under_keep_note(question):
    dlg = question()
    keep = dlg.findChild(QLabel, "keep_note")
    sync = dlg.findChild(QLabel, "sync_note")
    assert sync.isVisible() and sync.textFormat() == Qt.TextFormat.PlainText
    lay = keep.parentWidget().layout()
    # both sit in the same top block, sync_note right after keep_note
    top = None
    for i in range(lay.count()):
        item = lay.itemAt(i)
        sub = item.layout()
        if sub is not None and sub.indexOf(keep) >= 0:
            top = sub
    assert top is not None
    assert top.indexOf(sync) == top.indexOf(keep) + 1
    assert sync.geometry().top() > keep.geometry().top()
    # muted: same colour rule as the other muted texts, not the plain keep_note
    assert "color:" in sync.styleSheet() and "color:" not in keep.styleSheet()
    assert sync.styleSheet() == dlg.findChild(QLabel, "file_label").styleSheet()


def test_every_dialog_label_is_plain_text_except_the_undo_note(question, summary):
    """Nothing user-supplied (file names, skip reasons, saved choices) can be
    rendered as markup; only the fixed undo hint uses rich text."""
    rows = [("Fields you keep", "<b>Personal</b> Notes"), ("Protected tags", "<i>#edited</i>")]
    q = question(file_name="<b>x</b>.apkg", rows=rows)
    for lab in q.findChildren(QLabel):
        if lab.pixmap() is None or lab.pixmap().isNull():
            assert lab.textFormat() == Qt.TextFormat.PlainText, lab.objectName()
    assert _texts(q, "choice_value") == ["<b>Personal</b> Notes", "<i>#edited</i>"]
    s = summary(_result(note_types_changed=True, notes_skipped=1,
                        skip_reasons={"<b>odd</b>": 1}), file_name="<b>x</b>.apkg")
    for lab in s.findChildren(QLabel):
        if lab.objectName() in ("undo_note", "full_sync_icon"):
            continue
        assert lab.textFormat() == Qt.TextFormat.PlainText, lab.objectName()
    assert s.findChild(QLabel, "skip_details").text() == "<b>odd</b>: 1"


def test_summary_undo_and_done(summary):
    dlg = summary(_result())
    QTest.mouseClick(dlg.undo_button, Qt.MouseButton.LeftButton)
    assert dlg.choice() == flow.CHOICE_UNDO and not dlg.isVisible()
    dlg = summary(_result())
    QTest.mouseClick(dlg.done_button, Qt.MouseButton.LeftButton)
    assert dlg.choice() == flow.CHOICE_DONE and not dlg.isVisible()
    dlg = summary(_result())
    QTest.keyClick(dlg, Qt.Key.Key_Return)
    assert dlg.choice() == flow.CHOICE_DONE
    dlg = summary(_result())
    QTest.keyClick(dlg, Qt.Key.Key_Escape)
    assert dlg.choice() == flow.CHOICE_DONE


def test_summary_tab_chain_and_names(summary):
    dlg = summary(_result(note_types_changed=True, notes_skipped=1, skip_reasons={"missing deck": 1}))
    assert _tab_chain(dlg) == [dlg.undo_button, dlg.done_button]
    assert dlg.objectName() == "special_fields_summary"
    for name in ("summary_heading", "file_label", "undo_note", "full_sync_text", "skip_details"):
        assert dlg.findChild(QLabel, name) is not None, name
    for name in ("undo_button", "done_button"):
        assert dlg.findChild(QPushButton, name).accessibleName()
    rows = dlg.findChildren(QWidget, "summary_row")
    assert all(r.accessibleName() for r in rows)
    assert len(rows) == len(dlg.rows())


# --------------------------------------------------------------------------
# After the real-Anki pass (17 Nov 2026)


def test_question_same_size_before_and_after_change_choices(question, qapp):
    """Fix 1: the first layout is the final one: "Change choices…" returning
    the same rows changes neither size nor spacing; with more or fewer rows
    only the height changes, and going back gives the first size again."""
    import dataclasses

    from special_fields_by_ankoma.config import default_settings as ds

    more = ROWS + [("Extra row", "value")]
    answers = [ROWS, more, ROWS]
    dlg = question(change=lambda: answers.pop(0))
    first = dlg.size()
    gap = dlg.sync_note.geometry().top() - dlg.keep_note.geometry().bottom()
    assert first.width() == 540
    # No slack: the height is what the layout needs at this width.
    assert first.height() == dlg.layout().totalHeightForWidth(first.width())
    QTest.mouseClick(dlg.change_button, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert dlg.size() == first
    assert dlg.sync_note.geometry().top() - dlg.keep_note.geometry().bottom() == gap
    QTest.mouseClick(dlg.change_button, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert dlg.width() == first.width() and dlg.height() > first.height()
    assert dlg.sync_note.geometry().top() - dlg.keep_note.geometry().bottom() == gap
    QTest.mouseClick(dlg.change_button, Qt.MouseButton.LeftButton)
    qapp.processEvents()
    assert dlg.size() == first
    # A different saved-choices text (longer values) still fits exactly.
    on = choices_summary(dataclasses.replace(ds(), import_scheduling=True))
    dlg2 = question(rows=on)
    assert dlg2.height() == dlg2.layout().totalHeightForWidth(dlg2.width())


def test_summary_for_new_deck_says_import_complete_without_zero_kept_rows(summary):
    """Fix 5: nothing updated (a deck new to the collection)."""
    r = _result(notes_updated=0, notes_added=5, fields_kept=0, protected_tags_kept=0)
    assert flow.summary_heading(r) == "Import complete"
    assert flow.summary_rows(r) == [("Notes updated", "0"), ("New notes added", "5")] + FIXED
    dlg = summary(r)
    assert dlg.findChild(QLabel, "summary_heading").text() == "Import complete"
    assert "Fields kept from your version" not in _texts(dlg, "row_label")
    assert "Protected tags kept" not in _texts(dlg, "row_label")


def test_summary_keeps_zero_kept_rows_when_notes_were_updated(summary):
    r = _result(notes_updated=3, fields_kept=0, protected_tags_kept=0)
    assert flow.summary_heading(r) == "Update complete"
    labels = [x[0] for x in flow.summary_rows(r)]
    assert "Fields kept from your version" in labels and "Protected tags kept" in labels
    assert summary(r).findChild(QLabel, "summary_heading").text() == "Update complete"


def test_summary_existing_cards_row_renamed():
    assert flow.FIXED_SUMMARY_ROWS[-1] == ("Your existing cards: review history and decks", "Unchanged")
    assert all("deck moves" not in label for label, _v in flow.summary_rows(_result()))


# --------------------------------------------------------------------------
# Fields kept per protected tag (rule 14) and the summary window's size


def test_question_shows_tag_rules_and_long_rows_do_not_widen_it(question, qapp):
    """The "Protected tags" row says what each tag keeps; a long value wraps
    without an empty line under it, and a tag too long for a line is elided
    in the middle (tooltip: the whole value), so the window stays 540 px."""
    import dataclasses

    from special_fields_by_ankoma.model import TagRule

    tags = ("#edited", "#eevee", "my-private-tag", "board-review")
    s = dataclasses.replace(default_settings(), protected_tags=tags, tag_rules=(
        TagRule("#edited", (), False, ("Text", "Extra", "Personal Notes", "Header")),
        TagRule("#eevee", (), False, ()),
        TagRule("board-review", (), True, ())))
    rows = choices_summary(s)
    value = dict(rows)["Protected tags"]
    # my-private-tag: a plain string of an earlier beta, by name only
    assert value == ("#edited (keeps Text, Extra, Personal Notes, Header), #eevee (keeps no fields), "
                     "my-private-tag, board-review (keeps every field)")
    dlg = question(rows=rows)
    assert dlg.width() == 540 and dlg.minimumSizeHint().width() <= 540
    assert dlg.height() == dlg.layout().totalHeightForWidth(dlg.width())
    row = [w for w in dlg.findChildren(QWidget, "choice_row") if w.property("label") == "Protected tags"][0]
    val = row.findChild(QLabel, "choice_value")
    assert val.text() == value and val.wordWrap()
    assert row.height() == val.heightForWidth(val.width())  # no empty line under it
    assert row.height() <= 3 * val.fontMetrics().lineSpacing()
    long_tag = "#ANKOMA::CP::Immunology::Autoimmunity::AutoImmuneDiseases::FamilialMediterraneanFever"
    s2 = dataclasses.replace(default_settings(), protected_tags=(long_tag,),
                             tag_rules=(TagRule(long_tag, (), False, ("Text",)),))
    dlg2 = question(rows=choices_summary(s2))
    assert dlg2.width() == 540 and dlg2.minimumSizeHint().width() <= 540
    val2 = [w for w in dlg2.findChildren(QLabel, "choice_value") if "keeps Text" in w.text()][0]
    assert "…" in val2.text() and val2.text().endswith("(keeps Text)")
    assert _shown_tooltip(val2.toolTip()) == "%s (keeps Text)" % long_tag
    assert dlg2.findChild(QWidget, "choices_box").accessibleDescription().count(long_tag) == 1


def test_question_shows_at_most_three_lines_of_protected_tags(question, qapp):
    """Many protected tags: at most three lines, then "+N more"; the
    tooltip and the row's accessible name have the whole value."""
    import dataclasses

    from special_fields_by_ankoma.model import TagRule
    from special_fields_by_ankoma.settings_dialog import split_tag_summary

    tags = tuple("#tag-number-%d" % i for i in range(12))
    s = dataclasses.replace(default_settings(), protected_tags=tags, tag_rules=tuple(
        TagRule(t, (), False, ("Header", "Personal Notes")) for t in tags))
    rows = choices_summary(s)
    value = dict(rows)["Protected tags"]
    dlg = question(rows=rows)
    assert dlg.width() == 540
    row = [w for w in dlg.findChildren(QWidget, "choice_row") if w.property("label") == "Protected tags"][0]
    val = row.findChild(QLabel, "choice_value")
    shown = val.text()
    assert shown != value and shown.endswith(" more")
    entries = split_tag_summary(value)
    n_shown = len(split_tag_summary(shown.rsplit(", +", 1)[0]))
    assert 0 < n_shown < len(entries)
    assert shown == ", ".join(entries[:n_shown]) + ", +%d more" % (len(entries) - n_shown)
    lines = round(val.heightForWidth(val.width()) / val.fontMetrics().lineSpacing())
    assert lines <= 3, lines
    assert _shown_tooltip(val.toolTip()) == value
    assert row.accessibleName() == "Protected tags: " + value
    # a few tags fit: no "+N more"
    few = dataclasses.replace(s, protected_tags=tags[:2], tag_rules=s.tag_rules[:2])
    dlg2 = question(rows=choices_summary(few))
    val2 = [w for w in dlg2.findChildren(QLabel, "choice_value") if "#tag-number-0" in w.text()][0]
    assert "more" not in val2.text() and val2.toolTip() == ""


@pytest.mark.parametrize("full_sync", [False, True])
def test_summary_fits_its_content(summary, full_sync):
    """The summary window is sized from its layout's height-for-width, so
    there is no gap above the undo note (only the layout's spacing)."""
    r = _result(notes_updated=9190, notes_added=10122, fields_kept=606, protected_tags_kept=1020,
                note_types_changed=full_sync)
    dlg = summary(r)
    assert dlg.width() == 540
    assert dlg.height() == dlg.layout().totalHeightForWidth(540)
    above = dlg.full_sync_notice if full_sync else dlg.rows_frame
    assert dlg.undo_note.geometry().top() - above.geometry().bottom() - 1 == dlg.layout().spacing()
