"""Settings window: a field table per protected tag, and the (i) bubbles
(contract rule 14 and the settings-window section, 17 Nov 2026)."""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

import pytest

from PyQt6.QtTest import QTest

from aqt.qt import QApplication, QCheckBox, QFontMetrics, QLabel, QPoint, QPushButton, QToolButton, QToolTip, Qt

from special_fields_by_ankoma import settings_dialog as sd
from special_fields_by_ankoma.config import default_config, default_settings, settings_from_config
from special_fields_by_ankoma.model import FieldChoice, Settings, TagRule
from special_fields_by_ankoma.settings_dialog import (
    FIELDS_INFO,
    INFO_WRAP_WIDTH,
    KEEP_EVERY_FIELD_LABEL,
    PRESETS_INFO,
    SCHEDULING_INFO,
    STYLING_INFO,
    TAGS_INFO,
    choices_summary,
    split_tag_summary,
)

LONG_TAG = "#ANKOMA::CP::Immunology::Autoimmunity::AutoImmuneDiseases::FamilialMediterraneanFever::Extra"
TAGS = ["#edited", "#hard", "#easy", "#text-based", "board-review", "weak-areas", LONG_TAG]


def T(tag, fields=(), every=False):
    return TagRule(tag, (), every, tuple(fields))


def with_tags(*tags, rules=(), fields=None):
    s = dataclasses.replace(default_settings(), protected_tags=tuple(tags), tag_rules=tuple(rules))
    if fields is not None:
        s = dataclasses.replace(s, fields=tuple(fields))
    return s


def kept_rows(block):
    return [r.name for r in block.rows() if r.toggle.keep()]


def click_keep(row, keep):
    QTest.mouseClick(row.toggle.keep_button if keep else row.toggle.take_button, Qt.MouseButton.LeftButton)


@pytest.fixture
def dlg(make_dialog):
    return make_dialog(tags=TAGS)


# ----- the author's worked example ---------------------------------------


def test_worked_example_new_tag_defaults(dlg):
    """Personal Notes kept in the main list. #edited opens with Personal
    Notes; set to Header + Personal Notes. #hard opens with Header +
    Personal Notes (the first closes). #easy opens the same; changed to
    Text + Extra (Personal Notes off). #text-based opens with Text + Extra
    + Personal Notes (back on, because the main list keeps it)."""
    assert dlg.add_tag("#edited")
    a = dlg.tag_block("#edited")
    assert dlg.open_tag() == "#edited" and a.is_expanded()
    assert kept_rows(a) == ["Personal Notes"]
    click_keep(a.row_for("Header"), True)
    assert dlg.tag_rule("#edited") == (["Header", "Personal Notes"], False)

    assert dlg.add_tag("#hard")
    b = dlg.tag_block("#hard")
    assert dlg.open_tag() == "#hard" and not a.is_expanded()
    assert kept_rows(b) == ["Header", "Personal Notes"]

    assert dlg.add_tag("#easy")
    c = dlg.tag_block("#easy")
    assert kept_rows(c) == ["Header", "Personal Notes"]
    click_keep(c.row_for("Header"), False)
    click_keep(c.row_for("Personal Notes"), False)
    click_keep(c.row_for("Text"), True)
    click_keep(c.row_for("Extra"), True)
    assert dlg.tag_rule("#easy") == (["Text", "Extra"], False)

    assert dlg.add_tag("#text-based")
    d = dlg.tag_block("#text-based")
    assert kept_rows(d) == ["Text", "Extra", "Personal Notes"]
    assert [x.is_expanded() for x in (a, b, c, d)] == [False, False, False, True]

    # switching Personal Notes off in the main list changes none of them
    dlg.row_for("Personal Notes").toggle.set_keep(False)
    assert [dlg.tag_rule(t)[0] for t in ("#edited", "#hard", "#easy", "#text-based")] == [
        ["Header", "Personal Notes"], ["Header", "Personal Notes"], ["Text", "Extra"],
        ["Text", "Extra", "Personal Notes"]]
    assert kept_rows(d) == ["Text", "Extra", "Personal Notes"]
    # ... and the next tag starts from the previous one plus the new main list
    assert dlg.add_tag("board-review")
    assert dlg.tag_rule("board-review") == (["Text", "Extra", "Personal Notes"], False)
    got = dlg.result_settings()
    assert got.rule_for("#easy") == T("#easy", ("Text", "Extra"))
    assert got.rule_for("#text-based") == T("#text-based", ("Text", "Extra", "Personal Notes"))


def test_first_tag_starts_as_the_main_list_and_keep_every_field_is_copied(make_dialog):
    s = dataclasses.replace(default_settings(), fields=(
        FieldChoice("Header", True), FieldChoice("Text", False), FieldChoice("Personal Notes", True)))
    dlg = make_dialog(settings=s, tags=TAGS)
    dlg.add_tag("#edited")
    assert dlg.tag_rule("#edited") == (["Header", "Personal Notes"], False)
    block = dlg.tag_block("#edited")
    box = block.keep_all_box
    QTest.mouseClick(box, Qt.MouseButton.LeftButton, pos=QPoint(8, box.height() // 2))
    assert dlg.tag_rule("#edited") == (["Header", "Personal Notes"], True)
    dlg.add_tag("#hard")
    assert dlg.tag_rule("#hard") == (["Header", "Personal Notes"], True)
    assert dlg.tag_block("#hard").keep_all_box.isChecked()


# ----- collapsing ----------------------------------------------------------


def test_collapsed_by_default_and_one_open_at_a_time(make_dialog):
    dlg = make_dialog(settings=with_tags("#edited", "#hard", "#easy",
                                         rules=[T("#edited", ("Text",)), T("#hard"), T("#easy", every=True)]),
                      tags=TAGS)
    blocks = dlg.tag_blocks()
    assert [b.is_expanded() for b in blocks] == [False, False, False] and dlg.open_tag() is None
    assert all(not b.table.isVisible() for b in blocks)
    QTest.mouseClick(blocks[0].expand_button, Qt.MouseButton.LeftButton)
    assert dlg.open_tag() == "#edited" and blocks[0].table.isVisible()
    QTest.mouseClick(blocks[2].expand_button, Qt.MouseButton.LeftButton)
    assert [b.is_expanded() for b in blocks] == [False, False, True]
    QTest.mouseClick(blocks[2].expand_button, Qt.MouseButton.LeftButton)
    assert dlg.open_tag() is None
    # a click on the tag's name opens it too
    QTest.mouseClick(blocks[1].label, Qt.MouseButton.LeftButton)
    assert dlg.open_tag() == "#hard"


def test_arrowhead_is_a_real_button(make_dialog):
    dlg = make_dialog(settings=with_tags("#edited", rules=[T("#edited", ("Text",))]), tags=TAGS)
    block = dlg.tag_block("#edited")
    eb = block.expand_button
    assert isinstance(eb, QToolButton) and eb.focusPolicy() & Qt.FocusPolicy.TabFocus
    assert eb.accessibleName() == "Field choices for #edited, collapsed"
    assert eb.arrowType() == Qt.ArrowType.RightArrow
    eb.setFocus()
    QTest.keyClick(eb, Qt.Key.Key_Space)
    assert block.is_expanded() and eb.accessibleName() == "Field choices for #edited, expanded"
    assert eb.arrowType() == Qt.ArrowType.DownArrow
    QTest.keyClick(eb, Qt.Key.Key_Return)
    assert not block.is_expanded()
    QTest.keyClick(eb, Qt.Key.Key_Enter)
    assert block.is_expanded()
    assert dlg.isVisible() and dlg.result() == 0  # Enter did not press Save


def test_window_grows_when_a_tag_opens_and_shrinks_back(make_dialog, qapp):
    few = with_tags("#edited", rules=[T("#edited")], fields=default_settings().fields[:3])
    dlg = make_dialog(settings=few, tags=TAGS)
    dlg.move(10, 10)
    qapp.processEvents()
    h0 = dlg.height()
    dlg.expand_tag("#edited")
    qapp.processEvents()
    assert dlg.height() > h0 and dlg.scroll.verticalScrollBar().maximum() == 0
    dlg.collapse_tag("#edited")
    qapp.processEvents()
    assert dlg.height() == h0


# ----- the table -----------------------------------------------------------


def test_table_has_the_main_lists_rows_and_nothing_to_add_or_remove(make_dialog):
    dlg = make_dialog(settings=with_tags("#edited", rules=[T("#edited", ("Text",))]), tags=TAGS)
    block = dlg.tag_block("#edited")
    dlg.expand_tag("#edited")
    assert [r.name for r in block.rows()] == [r.name for r in dlg.field_rows()]
    assert kept_rows(block) == ["Text"]
    for w in block.findChildren(QPushButton):
        assert "Add field" not in w.text()
    assert block.findChildren(QToolButton, "remove_field_button") == []
    assert block.findChildren(QToolButton, "remove_tag_field_button") == []
    assert block.keep_all_box.text() == KEEP_EVERY_FIELD_LABEL
    # the same two-sided toggle as the main list, smaller
    main_h = dlg.row_for("Text").toggle.keep_button.sizeHint().height()
    assert block.row_for("Text").toggle.keep_button.sizeHint().height() < main_h
    assert block.row_for("Text").toggle.keep_button.text() == "Keep mine"
    assert block.row_for("Text").toggle.take_button.text() == "Take the update's"


def test_tag_choice_changes_only_that_tag(make_dialog):
    dlg = make_dialog(settings=with_tags("#edited", "#hard", rules=[T("#edited", ("Text",)), T("#hard", ("Text",))]),
                      tags=TAGS)
    main_before = dlg.result_settings().fields
    dlg.expand_tag("#edited")
    click_keep(dlg.tag_block("#edited").row_for("Extra"), True)
    assert dlg.tag_rule("#edited") == (["Text", "Extra"], False)
    assert dlg.tag_rule("#hard") == (["Text"], False)
    assert dlg.result_settings().fields == main_before


def test_main_list_choice_change_leaves_tags_alone(make_dialog):
    dlg = make_dialog(settings=with_tags("#edited", rules=[T("#edited", ("Header",))]), tags=TAGS)
    before = dlg.result_settings().tag_rules
    for row in dlg.field_rows():
        row.toggle.set_keep(not row.toggle.keep())
    assert dlg.result_settings().tag_rules == before
    assert kept_rows(dlg.tag_block("#edited")) == ["Header"]


def test_main_list_rows_added_and_removed_reach_every_tag(make_dialog):
    dlg = make_dialog(settings=with_tags("#edited", "#hard", rules=[T("#edited", ("Text",)), T("#hard", ("Citation",))]),
                      tags=TAGS)
    a, b = dlg.tag_block("#edited"), dlg.tag_block("#hard")
    dlg.add_field("Remarks")
    QTest.mouseClick(dlg.row_for("Remarks").toggle.keep_button, Qt.MouseButton.LeftButton)
    for block in (a, b):
        assert block.rows()[-1].name == "Remarks" and not block.row_for("Remarks").toggle.keep()
    assert dlg.tag_rule("#edited") == (["Text"], False)
    # removing a row: gone from tags that do not keep it, kept (at the end) where it is kept
    dlg.remove_field("Citation")
    assert a.row_for("Citation") is None
    assert b.rows()[-1].name == "Citation" and b.row_for("Citation").toggle.keep()
    assert dlg.tag_rule("#hard") == (["Citation"], False)
    assert b.summary.full_text() == "keeps Citation"
    # switched off there, it leaves that tag's table too
    dlg.expand_tag("#hard")
    click_keep(b.row_for("Citation"), False)
    assert b.row_for("Citation") is None and dlg.tag_rule("#hard") == ([], False)
    assert b.summary.full_text() == "keeps no fields"
    # a removed row comes back on adding it again
    dlg.add_field("Citation")
    assert a.row_for("Citation") is not None and not a.row_for("Citation").toggle.keep()


def test_keep_every_field_shows_rows_kept_and_disabled(make_dialog):
    dlg = make_dialog(settings=with_tags("#edited", rules=[T("#edited", ("Text",))]), tags=TAGS)
    block = dlg.tag_block("#edited")
    dlg.expand_tag("#edited")
    box = block.keep_all_box
    assert isinstance(box, QCheckBox) and not box.isChecked()
    box.setFocus()
    QTest.keyClick(box, Qt.Key.Key_Space)
    assert box.isChecked() and dlg.tag_rule("#edited") == (["Text"], True)
    assert all(r.toggle.keep() and not r.toggle.isEnabled() for r in block.rows())
    assert block.summary.full_text() == "keeps every field"
    QTest.keyClick(box, Qt.Key.Key_Space)
    assert kept_rows(block) == ["Text"] and all(r.toggle.isEnabled() for r in block.rows())
    assert dlg.tag_rule("#edited") == (["Text"], False)


def test_summaries(make_dialog):
    dlg = make_dialog(settings=with_tags("#edited", "#hard", "#easy",
                                         rules=[T("#edited", ("Personal Notes", "Header")), T("#hard"),
                                                T("#easy", ("Text",), every=True)]), tags=TAGS)
    texts = [b.summary.full_text() for b in dlg.tag_blocks()]
    # fields in the main list's order
    assert texts == ["keeps Header, Personal Notes", "keeps no fields", "keeps every field"]
    for b in dlg.tag_blocks():
        assert b.summary.textFormat() == Qt.TextFormat.PlainText
        assert b.summary.full_text() in b.summary.toolTip()


def test_legacy_config_opens_frozen_and_is_not_a_change(make_dialog, monkeypatch):
    """A config of beta 7 or 8 opens with each tag frozen at what it means
    now; opening and closing asks nothing; Save writes the frozen form."""
    asked = []
    monkeypatch.setattr(sd, "confirm_discard", lambda parent: asked.append(1) or True)
    legacy = settings_from_config({
        "fields": [{"name": "Header", "keep": False}, {"name": "Personal Notes", "keep": True}],
        "protected_tags": ["#hard", {"tag": "#edited", "keep_fields": ["Text", "Extra"]}]})
    dlg = make_dialog(settings=legacy, fields=["Header", "Text", "Extra", "Personal Notes"], tags=TAGS)
    assert dlg.tag_rule("#hard") == (["Personal Notes"], False)
    assert dlg.tag_rule("#edited") == (["Personal Notes", "Text", "Extra"], False)
    assert not dlg.has_changes()
    QTest.keyClick(dlg, Qt.Key.Key_Escape)
    assert asked == [] and not dlg.isVisible()
    got = dlg.result_settings()
    assert got.rule_for("#hard") == T("#hard", ("Personal Notes",))
    assert sd.settings_to_config(got)["protected_tags"][1] == {
        "tag": "#edited", "fields": ["Personal Notes", "Text", "Extra"], "keep_all_fields": False}


def test_restore_defaults_clears_tags(make_dialog):
    dlg = make_dialog(settings=with_tags("#edited", rules=[T("#edited", every=True)]), tags=TAGS)
    dlg.expand_tag("#edited")
    QTest.mouseClick(dlg.restore_button, Qt.MouseButton.LeftButton)
    assert dlg.result_settings() == default_settings() and dlg.tag_blocks() == []
    assert dlg.open_tag() is None


def test_discard_question_covers_tag_tables(make_dialog, monkeypatch):
    asked = []
    monkeypatch.setattr(sd, "confirm_discard", lambda parent: asked.append(1) or False)
    dlg = make_dialog(settings=with_tags("#edited", rules=[T("#edited", ("Text",))]), tags=TAGS)
    dlg.expand_tag("#edited")  # opening a table is no change
    assert not dlg.has_changes()
    dlg.set_tag_field("#edited", "Extra", True)
    assert dlg.has_changes()
    QTest.keyClick(dlg, Qt.Key.Key_Escape)
    assert asked == [1] and dlg.isVisible()
    dlg.set_tag_field("#edited", "Extra", False)  # changed back: unchanged
    assert not dlg.has_changes()
    dlg.set_tag_keep_all("#edited", True)
    assert dlg.has_changes()


def test_persisted_through_the_config_and_reopened_collapsed(qapp, monkeypatch):
    from conftest import ALL_FIELDS

    def fake_exec(self):
        assert self.add_tag("#edited") and self.add_tag("weak-areas")
        self.set_tag_field("#edited", "Text", True)
        self.set_tag_field("#edited", "Personal Notes", False)
        self.set_tag_keep_all("weak-areas", True)
        assert self.add_tag("board-review")
        # board-review started from weak-areas: every field; changed
        assert self.tag_rule("board-review") == (["Personal Notes"], True)
        self.set_tag_keep_all("board-review", False)
        self.set_tag_field("board-review", "Text", True)
        self.set_tag_field("board-review", "Personal Notes", False)
        self.accept()
        return self.result()

    monkeypatch.setattr(sd.SettingsDialog, "exec", fake_exec)
    col = SimpleNamespace(models=SimpleNamespace(all_names_and_ids=lambda: []),
                          tags=SimpleNamespace(all=lambda: list(TAGS)))
    configs = {}
    am = SimpleNamespace(getConfig=lambda key: dict(configs[key]) if key in configs else None,
                         writeConfig=lambda key, cfg: configs.__setitem__(key, cfg))
    mw = SimpleNamespace(addonManager=am, col=col)
    monkeypatch.setattr(sd, "_collection_field_names", lambda c: list(ALL_FIELDS))
    configs["special_fields_by_ankoma"] = default_config()
    got = sd.open_settings(mw)
    stored = configs["special_fields_by_ankoma"]["protected_tags"]
    assert stored == [
        {"tag": "#edited", "fields": ["Text"], "keep_all_fields": False},
        {"tag": "weak-areas", "fields": ["Personal Notes"], "keep_all_fields": True},
        {"tag": "board-review", "fields": ["Text"], "keep_all_fields": False},
    ]
    assert sd.load_settings(mw) == got
    dlg = sd.SettingsDialog(None, sd.load_settings(mw), ALL_FIELDS, TAGS)
    try:
        dlg.show()
        qapp.processEvents()
        assert [b.is_expanded() for b in dlg.tag_blocks()] == [False, False, False]
        assert [b.summary.full_text() for b in dlg.tag_blocks()] == [
            "keeps Text", "keeps every field", "keeps Text"]
        assert not dlg.has_changes()
    finally:
        dlg.done(0)
        dlg.deleteLater()


def test_tab_order_through_the_tags(make_dialog):
    dlg = make_dialog(settings=with_tags("#edited", "weak-areas",
                                         rules=[T("#edited", ("Text",)), T("weak-areas")],
                                         fields=default_settings().fields[:2]), tags=TAGS)
    a, b = dlg.tag_block("#edited"), dlg.tag_block("weak-areas")
    order = [dlg.info_buttons["tags"], dlg.tag_input, a.expand_button, a.remove_button,
             b.expand_button, b.remove_button, dlg.info_buttons["styling"], dlg.styling_switch]
    order[0].setFocus()
    QApplication.processEvents()
    for here in order[:-1]:
        assert QApplication.focusWidget() is here, (QApplication.focusWidget().objectName(), here.objectName())
        QTest.keyClick(here, Qt.Key.Key_Tab)
        QApplication.processEvents()
    assert QApplication.focusWidget() is order[-1]
    # an open table sits between its line and the next tag
    dlg.expand_tag("#edited")
    a.remove_button.setFocus()
    QTest.keyClick(a.remove_button, Qt.Key.Key_Tab)
    first = a.rows()[0].toggle
    assert QApplication.focusWidget() in (first.keep_button, first.take_button)
    for _ in range(10):
        if QApplication.focusWidget() is a.keep_all_box:
            break
        QTest.keyClick(QApplication.focusWidget(), Qt.Key.Key_Tab)
    assert QApplication.focusWidget() is a.keep_all_box
    QTest.keyClick(a.keep_all_box, Qt.Key.Key_Tab)
    assert QApplication.focusWidget() is b.expand_button
    # the main list keeps its order: Fields (i), the rows, + Add field
    dlg.info_buttons["fields"].setFocus()
    QTest.keyClick(dlg.info_buttons["fields"], Qt.Key.Key_Tab)
    assert QApplication.focusWidget() is dlg.field_rows()[0].remove_button


def test_long_tag_does_not_widen_the_window(make_dialog, qapp):
    dlg = make_dialog(settings=with_tags(LONG_TAG, "#hard", rules=[T(LONG_TAG, ("Text",)), T("#hard")]), tags=TAGS)
    qapp.processEvents()
    assert dlg.width() == 600
    block = dlg.tag_block(LONG_TAG)
    label = block.label
    assert label.textFormat() == Qt.TextFormat.PlainText
    assert label.text() != LONG_TAG and "…" in label.text()  # elided in the middle
    assert label.text().startswith("#ANKOMA") and label.text().endswith("Extra")
    assert LONG_TAG in label.toolTip() and label.full_text() == LONG_TAG
    assert dlg.scroll.horizontalScrollBar().maximum() == 0
    assert block.width() <= dlg.scroll.viewport().width()
    # the tags line up in one column; the summary starts after it
    short = dlg.tag_block("#hard")
    assert short.label.width() == label.width()
    assert block.summary.geometry().left() >= label.geometry().right()


def test_plain_text_and_accessible_names(make_dialog):
    tag = "<b>tag</b>"
    dlg = make_dialog(settings=with_tags("#edited", tag, rules=[T("#edited", ("<i>f</i>",)), T(tag)],
                                         fields=[FieldChoice("<i>f</i>", True)]),
                      fields=["Text", "<i>f</i>"], tags=["#edited", tag])
    dlg.expand_tag(tag)
    for lab in dlg.findChildren(QLabel):
        assert lab.textFormat() == Qt.TextFormat.PlainText, (lab.objectName(), lab.text())
    for block in dlg.tag_blocks():
        controls = [block.expand_button, block.remove_button, block.keep_all_box]
        for row in block.rows():
            controls += [row.toggle.keep_button, row.toggle.take_button]
        for w in controls:
            assert w.accessibleName(), w.objectName()
            assert block.tag in w.accessibleName(), (w.objectName(), w.accessibleName())
    assert dlg.tag_block(tag).label.text() == tag
    assert dlg.tag_block("#edited").summary.text() == "keeps <i>f</i>"


def test_five_collapsed_tags_are_five_short_lines(make_dialog, qapp):
    """The author's worry: with five tags, all closed, the area is the tag
    box plus five short lines."""
    tags = ["#edited", "#hard", "#easy", "#text-based", "weak-areas"]
    dlg = make_dialog(settings=with_tags(*tags, rules=[T(t, ("Personal Notes",)) for t in tags]), tags=TAGS)
    qapp.processEvents()
    line = dlg.tag_input.sizeHint().height()
    for b in dlg.tag_blocks():
        assert b.height() <= line + 4, b.height()
    assert dlg.tag_chips_widget.height() <= 5 * (line + 4)


# ----- (i) bubbles -----------------------------------------------------------


BUBBLES = {"fields": FIELDS_INFO, "tags": TAGS_INFO, "styling": STYLING_INFO,
           "scheduling": SCHEDULING_INFO, "presets": PRESETS_INFO}


def test_bubble_texts_are_the_approved_ones():
    assert FIELDS_INFO.startswith("Choose what happens to each field when an update changes a card")
    assert FIELDS_INFO.endswith("unless the update leaves that field empty on every card.")
    assert TAGS_INFO.startswith("An update replaces a card's tags with the update's.")
    assert TAGS_INFO.endswith("A card with several protected tags keeps a field if any of them keeps it.")
    assert STYLING_INFO == ("On: an update may replace your card templates and styling with its own. "
                            "Off: yours stay exactly as they are. Card content updates either way.")
    assert SCHEDULING_INFO.endswith("Useful for moving a deck to another computer without syncing.")
    assert PRESETS_INFO.startswith("On: deck options saved in the file (daily limits, learning steps, FSRS settings)")


@pytest.mark.parametrize("name", sorted(BUBBLES))
def test_bubble_hover_click_keyboard_and_description(dlg, qapp, name):
    button = dlg.info_buttons[name]
    text = BUBBLES[name]
    assert button.text() == "i" and button.objectName() == "info_button"
    assert button.accessibleDescription() == text
    assert button.accessibleName().startswith("About ")
    # hover: the tooltip is the text, plain, in short lines
    tip = button.toolTip()
    assert not Qt.mightBeRichText(tip)
    assert " ".join(tip.split()) == text
    fm = QFontMetrics(QToolTip.font())
    assert max(fm.horizontalAdvance(line) for line in tip.split("\n")) <= INFO_WRAP_WIDTH
    assert len(tip.split("\n")) > 1 or fm.horizontalAdvance(text) <= INFO_WRAP_WIDTH
    # click, Space and Enter show it too (without a mouse over it)
    for how in ("click", "space", "enter"):
        QToolTip.hideText()
        qapp.processEvents()
        if how == "click":
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        else:
            button.setFocus()
            QTest.keyClick(button, Qt.Key.Key_Space if how == "space" else Qt.Key.Key_Return)
        qapp.processEvents()
        assert QToolTip.isVisible() and QToolTip.text() == tip, how
    QToolTip.hideText()
    assert dlg.isVisible() and dlg.result() == 0  # Enter did not press Save
    assert button.focusPolicy() & Qt.FocusPolicy.TabFocus


def test_no_grey_paragraphs_left(dlg):
    shown = [lab.text() for lab in dlg.findChildren(QLabel) if lab.isVisible()]
    for text in BUBBLES.values():
        assert text not in shown
    for old in ("Matched by field name", "An update never removes these tags", "Note content updates either way",
                "No protected tags yet."):
        assert not any(old in t for t in shown), old
    assert "Fields" in shown and "Protected tags" in shown
    assert not any(t.startswith("Fields:") for t in shown)


def test_bubbles_do_not_widen_the_window(dlg, qapp):
    qapp.processEvents()
    assert dlg.width() == 600 and dlg.scroll.horizontalScrollBar().maximum() == 0


# ----- the summary -----------------------------------------------------------


def test_choices_summary_protected_tags_row():
    s = Settings(fields=(FieldChoice("Personal Notes", True),), protected_tags=("#edited", "#hard", "#easy", "#old"),
                 tag_rules=(T("#edited", ("Header", "Personal Notes")), T("#hard"), T("#easy", ("Text",), every=True)))
    row = dict(choices_summary(s))["Protected tags"]
    assert row == ("#edited (keeps Header, Personal Notes), #hard (keeps no fields), "
                   "#easy (keeps every field), #old")
    assert split_tag_summary(row) == ["#edited (keeps Header, Personal Notes)", "#hard (keeps no fields)",
                                      "#easy (keeps every field)", "#old"]
    # a legacy entry (plain string, beta 8 object) shows by name only
    legacy = Settings(protected_tags=("#a", "#b"), tag_rules=(TagRule("#b", ("Text",), False),))
    assert dict(choices_summary(legacy))["Protected tags"] == "#a, #b"
    assert dict(choices_summary(default_settings()))["Protected tags"] == "None"
    assert [label for label, _ in choices_summary(s)] == [label for label, _ in choices_summary(default_settings())]


@pytest.mark.parametrize("value", [
    "#a", "#a, #b", "#a (keeps X, Y), #b", "#a(1) (keeps every field), #b,c (keeps A (old))",
    "#x (keeps Personal Notes), #y (keeps no fields), #z",
])
def test_split_tag_summary_round_trips(value):
    parts = split_tag_summary(value)
    assert ", ".join(parts) == value
    assert all(" " not in p.split(" (")[0] for p in parts)
