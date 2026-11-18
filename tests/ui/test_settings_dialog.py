"""Offscreen tests that drive the settings window like a user would."""

from __future__ import annotations

import dataclasses

import pytest

from PyQt6.QtTest import QTest

from aqt.qt import QDialog, QPalette, QColor, QApplication, QWidget, QPushButton, Qt

from special_fields_by_ankoma.config import (
    DEFAULT_FIELDS, default_settings, settings_from_config, settings_to_config)
from special_fields_by_ankoma.model import ACCENT_COLOR, FieldChoice, Settings, TagRule
from special_fields_by_ankoma.settings_dialog import (
    KEEP_LABEL,
    PRESETS_HEADING,
    PRESETS_INFO,
    SCHEDULING_HEADING,
    SCHEDULING_INFO,
    STYLING_INFO,
    TAGS_INFO,
    TAKE_LABEL,
    WINDOW_TITLE,
    FieldRow,
    SettingsDialog,
    filter_fields,
    filter_tags,
)

from conftest import ALL_TAGS

ACCENT = ACCENT_COLOR.lower()


def has_accent(button) -> bool:
    css = button.styleSheet().lower()
    return ACCENT in css and "#ffffff" in css


def type_into(widget, text):
    widget.setFocus()
    QTest.keyClicks(widget, text)


def click_item(lst, text, double=False):
    item = lst.findItems(text, Qt.MatchFlag.MatchExactly)[0]
    lst.scrollToItem(item)
    pos = lst.visualItemRect(item).center()
    if double:
        # A real double-click: press/release, then the double-click event.
        QTest.mouseClick(lst.viewport(), Qt.MouseButton.LeftButton, pos=pos)
        QTest.mouseDClick(lst.viewport(), Qt.MouseButton.LeftButton, pos=pos)
    else:
        QTest.mouseClick(lst.viewport(), Qt.MouseButton.LeftButton, pos=pos)


def list_texts(lst):
    return [lst.item(i).text() for i in range(lst.count())]


# --------------------------------------------------------------------------
# Window basics


def test_title_and_default_rows(make_dialog):
    dlg = make_dialog()
    assert dlg.windowTitle() == WINDOW_TITLE == "Special Fields by Ankoma: Settings"
    assert [r.name for r in dlg.field_rows()] == [n for n, _ in DEFAULT_FIELDS]
    assert [r.toggle.keep() for r in dlg.field_rows()] == [k for _, k in DEFAULT_FIELDS]
    assert dlg.info_buttons["tags"].info_text() == TAGS_INFO
    assert dlg.result_settings() == default_settings()


def test_selected_side_carries_accent(make_dialog):
    dlg = make_dialog()
    for row in dlg.field_rows():
        t = row.toggle
        assert t.keep_button.text() == KEEP_LABEL
        assert t.take_button.text() == TAKE_LABEL
        sel, other = (t.keep_button, t.take_button) if t.keep() else (t.take_button, t.keep_button)
        assert has_accent(sel), row.name
        assert ACCENT not in other.styleSheet().lower(), row.name
        assert sel.isChecked() and not other.isChecked()


def test_toggle_field_moves_accent_and_changes_result(make_dialog):
    dlg = make_dialog()
    t = dlg.row_for("Text").toggle
    assert has_accent(t.take_button) and not has_accent(t.keep_button)

    QTest.mouseClick(t.keep_button, Qt.MouseButton.LeftButton)
    assert t.keep()
    assert has_accent(t.keep_button) and not has_accent(t.take_button)
    assert dlg.result_settings().keeps_field("Text")

    # Keyboard: Space on the focused side selects it.
    t.take_button.setFocus()
    QTest.keyClick(t.take_button, Qt.Key.Key_Space)
    assert not t.keep()
    assert has_accent(t.take_button) and not has_accent(t.keep_button)
    assert not dlg.result_settings().keeps_field("Text")

    # Personal Notes (kept by default) can be switched to the update's.
    pn = dlg.row_for("personal notes").toggle
    QTest.mouseClick(pn.take_button, Qt.MouseButton.LeftButton)
    assert dlg.result_settings().kept_field_names() == frozenset()


def test_default_rows_are_removable(make_dialog):
    dlg = make_dialog()
    assert not dlg.no_fields_label.isVisible()
    for row in dlg.field_rows():
        assert row.remove_button is not None
    QTest.mouseClick(dlg.row_for("Header").remove_button, Qt.MouseButton.LeftButton)
    assert dlg.row_for("Header") is None
    assert [f.name for f in dlg.result_settings().fields] == [
        "Text", "Extra", "Personal Notes", "Textbook", "Citation"]
    assert dlg.result_settings().kept_field_names() == frozenset({"personal notes"})
    # A removed default can be added back like any other field.
    dlg.open_field_picker()
    assert "Header" in list_texts(dlg.field_matches)
    assert dlg.add_field("Header") is True
    assert dlg.row_for("Header").toggle.keep() is False


def test_every_row_can_be_removed_and_it_round_trips(make_dialog):
    dlg = make_dialog()
    for name, _keep in DEFAULT_FIELDS:
        assert dlg.remove_field(name) is True
    assert dlg.field_rows() == []
    assert not dlg.field_rows_frame.isVisible()
    assert dlg.no_fields_label.isVisible()
    got = dlg.result_settings()
    assert got.fields == ()
    # Saved and read back, the list stays empty: defaults do not creep back.
    assert settings_from_config(settings_to_config(got)).fields == ()
    dlg2 = make_dialog(settings=got)
    assert dlg2.field_rows() == [] and dlg2.no_fields_label.isVisible()
    QTest.mouseClick(dlg2.restore_button, Qt.MouseButton.LeftButton)
    assert dlg2.result_settings() == default_settings()
    assert dlg2.field_rows_frame.isVisible() and not dlg2.no_fields_label.isVisible()


def test_saved_custom_rows_are_removable(make_dialog):
    s = dataclasses.replace(
        default_settings(),
        fields=default_settings().fields + (FieldChoice("Remarks", True),),
    )
    dlg = make_dialog(settings=s)
    row = dlg.row_for("Remarks")
    assert row.remove_button is not None and row.toggle.keep()
    QTest.mouseClick(row.remove_button, Qt.MouseButton.LeftButton)
    assert dlg.row_for("Remarks") is None
    assert dlg.result_settings() == default_settings()


# --------------------------------------------------------------------------
# + Add field


def test_add_field_by_typing_and_enter_then_remove(make_dialog):
    dlg = make_dialog()
    assert not dlg.field_picker.isVisible()
    QTest.mouseClick(dlg.add_field_button, Qt.MouseButton.LeftButton)
    assert dlg.field_picker.isVisible()

    # Empty query lists every field that isn't already a row.
    shown = list_texts(dlg.field_matches)
    assert "Text" not in shown and "Personal Notes" not in shown
    assert set(shown) == {"Images", "Remarks", "Sources", "Footer", "Extra 1", "Extra 2",
                          "Back Extra", "Lecture Notes", "Missed Questions"}

    type_into(dlg.field_search, "lect")
    assert list_texts(dlg.field_matches) == ["Lecture Notes"]
    QTest.keyClick(dlg.field_search, Qt.Key.Key_Return)
    row = dlg.row_for("Lecture Notes")
    assert row is not None
    assert row.toggle.keep() is False  # new rows start as "Take the update's"
    assert has_accent(row.toggle.take_button)
    assert dlg.field_search.text() == ""
    assert "Lecture Notes" not in list_texts(dlg.field_matches)
    assert dlg.isVisible()  # Enter did not press Save

    QTest.mouseClick(row.remove_button, Qt.MouseButton.LeftButton)
    assert dlg.row_for("Lecture Notes") is None
    assert "Lecture Notes" in list_texts(dlg.field_matches)
    assert dlg.result_settings() == default_settings()


def test_add_field_by_clicking_list_narrowing(make_dialog):
    dlg = make_dialog()
    dlg.open_field_picker()
    type_into(dlg.field_search, "ex")
    # Prefix matches first; "Extra" is already a row so it isn't offered.
    assert list_texts(dlg.field_matches) == ["Extra 1", "Extra 2", "Back Extra"]
    type_into(dlg.field_search, "tra 2")
    assert list_texts(dlg.field_matches) == ["Extra 2"]
    dlg.field_search.clear()
    type_into(dlg.field_search, "EX")  # case-insensitive
    assert list_texts(dlg.field_matches) == ["Extra 1", "Extra 2", "Back Extra"]
    click_item(dlg.field_matches, "Back Extra")
    assert dlg.row_for("Back Extra") is not None
    assert [r.name for r in dlg.field_rows()][-1] == "Back Extra"


def test_add_field_with_arrow_keys(make_dialog):
    dlg = make_dialog()
    dlg.open_field_picker()
    type_into(dlg.field_search, "extra")
    assert list_texts(dlg.field_matches) == ["Extra 1", "Extra 2", "Back Extra"]
    QTest.keyClick(dlg.field_search, Qt.Key.Key_Down)
    QTest.keyClick(dlg.field_search, Qt.Key.Key_Down)
    QTest.keyClick(dlg.field_search, Qt.Key.Key_Return)
    assert dlg.row_for("Extra 2") is not None
    assert dlg.row_for("Extra 1") is None


def test_unknown_field_cannot_be_added(make_dialog):
    dlg = make_dialog()
    dlg.open_field_picker()
    type_into(dlg.field_search, "Bogus Field")
    assert dlg.field_matches.count() == 0
    QTest.keyClick(dlg.field_search, Qt.Key.Key_Return)
    assert dlg.row_for("Bogus Field") is None
    assert "only fields from your note types" in dlg.field_hint.text().lower()
    assert dlg.add_field("Bogus Field") is False
    assert dlg.add_field("Text") is False  # already a row
    assert len(dlg.field_rows()) == len(DEFAULT_FIELDS)


def test_field_picker_escape_then_done(make_dialog):
    dlg = make_dialog()
    dlg.open_field_picker()
    type_into(dlg.field_search, "rem")
    QTest.keyClick(dlg.field_search, Qt.Key.Key_Escape)
    assert dlg.field_search.text() == "" and dlg.field_picker.isVisible()
    QTest.keyClick(dlg.field_search, Qt.Key.Key_Escape)
    assert not dlg.field_picker.isVisible()
    assert dlg.isVisible()
    dlg.open_field_picker()
    QTest.mouseClick(dlg.field_done_button, Qt.MouseButton.LeftButton)
    assert not dlg.field_picker.isVisible() and dlg.add_field_button.isVisible()


# --------------------------------------------------------------------------
# Protected tags picker


def test_filter_tags_helper():
    assert filter_tags("", ALL_TAGS) == []
    got = filter_tags("edit", ALL_TAGS)
    # Prefix matches first (case-insensitive), then substring matches.
    assert got[0] == "Edit-later"
    assert set(got) == {"Edit-later", "#edited", "#edited::images", "my-edits", "my-edits::rewritten"}
    assert got.index("Edit-later") < got.index("#edited")
    assert filter_tags("EDIT", ALL_TAGS) == got
    assert filter_tags("edit", ALL_TAGS, exclude=["#EDITED"]) == [t for t in got if t != "#edited"]
    assert filter_fields("", ["A", "b", "a"], exclude=[]) == ["A", "b"]


def test_tag_list_appears_and_narrows_while_typing(make_dialog):
    dlg = make_dialog()
    assert not dlg.tag_list.isVisible()
    type_into(dlg.tag_input, "b")
    assert dlg.tag_list.isVisible()
    first = list_texts(dlg.tag_list)
    # prefix matches ("board-review…") before substring matches ("##ANKOMA…::Breast", "#image-based")
    assert first[:2] == ["board-review", "board-review::missed"]
    assert set(first) >= {"#image-based", "##ANKOMA-v1.2::AP::Breast"}
    type_into(dlg.tag_input, "oard-review::")
    assert list_texts(dlg.tag_list) == ["board-review::missed"]
    dlg.tag_input.clear()
    assert not dlg.tag_list.isVisible()
    type_into(dlg.tag_input, "MY-EDITS")
    assert list_texts(dlg.tag_list) == ["my-edits", "my-edits::rewritten"]


def test_already_protected_tags_not_listed(make_dialog):
    s = dataclasses.replace(default_settings(), protected_tags=("#edited",))
    dlg = make_dialog(settings=s)
    type_into(dlg.tag_input, "#edited")
    assert list_texts(dlg.tag_list) == ["#edited::images"]
    # Typing a tag that is already protected must not add its sub-tag by accident.
    assert dlg.tag_target() is None
    assert "already protected" in dlg.tag_hint.text()
    QTest.keyClick(dlg.tag_input, Qt.Key.Key_Return)
    assert dlg.protected_tags() == ["#edited"]
    assert dlg.add_tag("#EDITED") is False
    # The sub-tag can still be picked deliberately: one click adds it.
    click_item(dlg.tag_list, "#edited::images")
    assert dlg.protected_tags() == ["#edited", "#edited::images"]


def test_enter_adds_exact_match_even_with_other_matches(make_dialog):
    dlg = make_dialog()
    type_into(dlg.tag_input, "#edited")
    assert list_texts(dlg.tag_list)[:2] == ["#edited", "#edited::images"]
    QTest.keyClick(dlg.tag_input, Qt.Key.Key_Return)
    assert dlg.protected_tags() == ["#edited"]
    assert [c.tag for c in dlg.tag_chips()] == ["#edited"]
    assert dlg.tag_input.text() == ""
    assert dlg.isVisible()  # Enter didn't trigger Save


def test_enter_exact_match_is_case_insensitive_and_keeps_collection_spelling(make_dialog):
    dlg = make_dialog()
    type_into(dlg.tag_input, "WEAK-AREAS")
    QTest.keyClick(dlg.tag_input, Qt.Key.Key_Enter)
    assert dlg.protected_tags() == ["weak-areas"]


def test_enter_adds_single_match(make_dialog):
    dlg = make_dialog()
    type_into(dlg.tag_input, "rewrit")
    assert list_texts(dlg.tag_list) == ["my-edits::rewritten"]
    QTest.keyClick(dlg.tag_input, Qt.Key.Key_Return)
    assert dlg.protected_tags() == ["my-edits::rewritten"]


def test_first_match_is_highlighted_and_enter_adds_it(make_dialog):
    dlg = make_dialog()
    type_into(dlg.tag_input, "board")
    assert list_texts(dlg.tag_list) == ["board-review", "board-review::missed"]
    assert dlg.tag_list.currentRow() == 0 and dlg.tag_list.item(0).isSelected()
    assert dlg.tag_target() == "board-review"
    assert dlg.protected_tags() == []  # highlighting alone adds nothing
    QTest.keyClick(dlg.tag_input, Qt.Key.Key_Return)
    assert dlg.protected_tags() == ["board-review"]
    assert dlg.tag_input.text() == ""
    assert dlg.isVisible()  # Enter didn't trigger Save


def test_there_is_no_select_button(make_dialog):
    dlg = make_dialog()
    assert not hasattr(dlg, "tag_select_button")
    assert dlg.findChild(QPushButton, "tag_select_button") is None
    assert not [b for b in dlg.findChildren(QPushButton) if b.text() == "Select"]


def test_one_click_adds_a_tag_that_was_not_highlighted(make_dialog):
    dlg = make_dialog()
    type_into(dlg.tag_input, "board")
    assert dlg.tag_target() == "board-review"  # the first one is highlighted
    click_item(dlg.tag_list, "board-review::missed")
    assert dlg.protected_tags() == ["board-review::missed"]
    assert [c.tag for c in dlg.tag_chips()] == ["board-review::missed"]
    assert dlg.tag_input.text() == ""
    assert not dlg.tag_list.isVisible()


def test_one_click_adds_the_highlighted_tag(make_dialog):
    dlg = make_dialog()
    type_into(dlg.tag_input, "board")
    click_item(dlg.tag_list, "board-review")
    assert dlg.protected_tags() == ["board-review"]


def test_double_click_adds_only_one_tag(make_dialog):
    dlg = make_dialog()
    type_into(dlg.tag_input, "board")
    click_item(dlg.tag_list, "board-review", double=True)
    assert dlg.protected_tags() == ["board-review"]


def test_no_message_after_adding_or_removing_a_tag(make_dialog):
    dlg = make_dialog()
    type_into(dlg.tag_input, "#edited::im")
    QTest.keyClick(dlg.tag_input, Qt.Key.Key_Return)
    assert dlg.protected_tags() == ["#edited::images"]
    assert dlg.tag_hint.text() == "" and not dlg.tag_hint.isVisible()
    type_into(dlg.tag_input, "board")
    click_item(dlg.tag_list, "board-review")
    assert dlg.tag_hint.text() == "" and not dlg.tag_hint.isVisible()
    dlg.remove_tag("board-review")
    assert dlg.tag_hint.text() == "" and not dlg.tag_hint.isVisible()


def test_no_hint_while_matches_are_listed(make_dialog):
    dlg = make_dialog()
    type_into(dlg.tag_input, "board")
    assert dlg.tag_list.isVisible()
    assert not dlg.tag_hint.isVisible()


def test_up_down_move_through_list_and_enter_adds(make_dialog):
    dlg = make_dialog()
    type_into(dlg.tag_input, "my")
    assert list_texts(dlg.tag_list) == ["my-edits", "my-edits::rewritten"]
    assert dlg.tag_target() == "my-edits"  # first one highlighted from the start
    QTest.keyClick(dlg.tag_input, Qt.Key.Key_Down)
    assert dlg.tag_target() == "my-edits::rewritten"
    QTest.keyClick(dlg.tag_input, Qt.Key.Key_Down)  # stays on the last
    assert dlg.tag_target() == "my-edits::rewritten"
    QTest.keyClick(dlg.tag_input, Qt.Key.Key_Up)
    assert dlg.tag_target() == "my-edits"
    QTest.keyClick(dlg.tag_input, Qt.Key.Key_Up)  # stays on the first
    assert dlg.tag_target() == "my-edits"
    QTest.keyClick(dlg.tag_input, Qt.Key.Key_Down)
    QTest.keyClick(dlg.tag_input, Qt.Key.Key_Return)
    assert dlg.protected_tags() == ["my-edits::rewritten"]


def test_text_matching_no_tag_is_rejected(make_dialog):
    dlg = make_dialog()
    type_into(dlg.tag_input, "not-a-real-tag")
    assert not dlg.tag_list.isVisible()
    assert dlg.tag_target() is None
    assert dlg.tag_hint.isVisible()
    assert "only existing tags can be added" in dlg.tag_hint.text().lower()
    QTest.keyClick(dlg.tag_input, Qt.Key.Key_Return)
    assert dlg.protected_tags() == []
    assert dlg.tag_input.text() == "not-a-real-tag"
    assert dlg.add_tag("not-a-real-tag") is False
    assert dlg.result_settings().protected_tags == ()


def test_escape_clears_tag_text_before_closing(make_dialog):
    dlg = make_dialog()
    type_into(dlg.tag_input, "board")
    QTest.keyClick(dlg.tag_input, Qt.Key.Key_Escape)
    assert dlg.tag_input.text() == ""
    assert dlg.isVisible()
    QTest.keyClick(dlg.tag_input, Qt.Key.Key_Escape)
    assert not dlg.isVisible()
    assert dlg.result() == QDialog.DialogCode.Rejected.value


def test_remove_tag_chip(make_dialog):
    s = dataclasses.replace(default_settings(), protected_tags=("#edited", "weak-areas"))
    dlg = make_dialog(settings=s)
    assert [c.tag for c in dlg.tag_chips()] == ["#edited", "weak-areas"]
    assert dlg.tag_chips_widget.isVisible()
    chip = dlg.tag_chips()[0]
    QTest.mouseClick(chip.remove_button, Qt.MouseButton.LeftButton)
    assert [c.tag for c in dlg.tag_chips()] == ["weak-areas"]
    assert dlg.result_settings().protected_tags == ("weak-areas",)
    # Removed tag can be picked again.
    type_into(dlg.tag_input, "#edited")
    assert "#edited" in list_texts(dlg.tag_list)
    dlg.tag_input.clear()
    dlg.tag_chips()[0].remove_button.click()
    assert dlg.tag_chips() == []
    # no protected tags: the tag box alone, no extra line
    assert not dlg.tag_chips_widget.isVisible()


# --------------------------------------------------------------------------
# Switch, buttons, result


def test_styling_switch(make_dialog):
    dlg = make_dialog()
    sw = dlg.styling_switch
    assert sw.isChecked() and dlg.result_settings().update_note_types is True
    QTest.mouseClick(sw, Qt.MouseButton.LeftButton)
    assert not sw.isChecked() and dlg.result_settings().update_note_types is False
    sw.setFocus()
    QTest.keyClick(sw, Qt.Key.Key_Space)
    assert sw.isChecked() and dlg.result_settings().update_note_types is True
    assert sw.accessibleName() == "Update card templates and styling"


def test_import_switches_default_off(make_dialog):
    dlg = make_dialog()
    for sw in (dlg.scheduling_switch, dlg.presets_switch):
        assert type(sw) is type(dlg.styling_switch)
        assert not sw.isChecked()
    got = dlg.result_settings()
    assert got.import_scheduling is False and got.import_deck_presets is False


def test_import_switches_toggle_and_labels(make_dialog):
    dlg = make_dialog()
    sw = dlg.scheduling_switch
    QTest.mouseClick(sw, Qt.MouseButton.LeftButton)
    assert sw.isChecked() and dlg.result_settings().import_scheduling is True
    assert dlg.result_settings().import_deck_presets is False
    sw = dlg.presets_switch
    sw.setFocus()
    QTest.keyClick(sw, Qt.Key.Key_Space)
    assert sw.isChecked() and dlg.result_settings().import_deck_presets is True
    QTest.mouseClick(dlg.scheduling_switch, Qt.MouseButton.LeftButton)
    assert dlg.result_settings().import_scheduling is False
    assert dlg.scheduling_switch.accessibleName() == SCHEDULING_HEADING == "Import learning progress"
    assert dlg.presets_switch.accessibleName() == PRESETS_HEADING == "Import deck options"
    # Headings shown as plain text; the help is in each one's (i) bubble.
    from aqt.qt import QLabel
    texts = {lab.text(): lab for lab in dlg.findChildren(QLabel)}
    for text in (SCHEDULING_HEADING, PRESETS_HEADING):
        assert text in texts, text
        assert texts[text].textFormat() == Qt.TextFormat.PlainText
    for text in (SCHEDULING_INFO, PRESETS_INFO, STYLING_INFO):
        assert text not in texts, text
    assert dlg.info_buttons["scheduling"].info_text() == SCHEDULING_INFO
    assert dlg.info_buttons["presets"].info_text() == PRESETS_INFO
    assert "Cards you already have always keep your own progress" in SCHEDULING_INFO
    assert "never changed" in PRESETS_INFO


def test_import_switches_come_from_settings_and_save(make_dialog):
    s = dataclasses.replace(default_settings(), import_scheduling=True)
    dlg = make_dialog(settings=s)
    assert dlg.scheduling_switch.isChecked() and not dlg.presets_switch.isChecked()
    QTest.mouseClick(dlg.presets_switch, Qt.MouseButton.LeftButton)
    QTest.mouseClick(dlg.save_button, Qt.MouseButton.LeftButton)
    got = dlg.result_settings()
    assert got == dataclasses.replace(default_settings(), import_scheduling=True, import_deck_presets=True)
    assert settings_from_config(settings_to_config(got)) == got


def test_switch_tab_order(make_dialog):
    """Tab goes styling -> learning progress -> deck presets -> Restore
    defaults, each switch after its (i) bubble."""
    dlg = make_dialog()
    info = dlg.info_buttons
    order = [info["styling"], dlg.styling_switch, info["scheduling"], dlg.scheduling_switch,
             info["presets"], dlg.presets_switch, dlg.restore_button]
    info["styling"].setFocus()
    QApplication.processEvents()
    for here, there in zip(order, order[1:]):
        assert QApplication.focusWidget() is here, QApplication.focusWidget()
        QTest.keyClick(here, Qt.Key.Key_Tab)
        QApplication.processEvents()
        assert QApplication.focusWidget() is there, (here.objectName(), QApplication.focusWidget())


def test_restore_defaults(make_dialog):
    s = Settings(
        fields=(FieldChoice("Text", True), FieldChoice("Remarks", True)),
        protected_tags=("#edited",),
        update_note_types=False,
        import_scheduling=True,
        import_deck_presets=True,
    )
    dlg = make_dialog(settings=s)
    assert dlg.scheduling_switch.isChecked() and dlg.presets_switch.isChecked()
    dlg.open_field_picker()
    type_into(dlg.tag_input, "boa")
    QTest.mouseClick(dlg.restore_button, Qt.MouseButton.LeftButton)
    assert dlg.result_settings() == default_settings()
    assert not dlg.scheduling_switch.isChecked() and not dlg.presets_switch.isChecked()
    assert dlg.tag_chips() == [] and dlg.tag_input.text() == ""
    assert not dlg.field_picker.isVisible()
    assert [r.name for r in dlg.field_rows()] == [n for n, _k in DEFAULT_FIELDS]
    assert dlg.isVisible()  # restore doesn't save or close


def test_save_returns_settings(make_dialog):
    dlg = make_dialog()
    QTest.mouseClick(dlg.row_for("Header").toggle.keep_button, Qt.MouseButton.LeftButton)
    dlg.add_field("Remarks")
    QTest.mouseClick(dlg.row_for("Remarks").toggle.keep_button, Qt.MouseButton.LeftButton)
    dlg.add_tag("#edited")
    QTest.mouseClick(dlg.styling_switch, Qt.MouseButton.LeftButton)
    QTest.mouseClick(dlg.save_button, Qt.MouseButton.LeftButton)
    assert dlg.result() == QDialog.DialogCode.Accepted.value
    got = dlg.result_settings()
    assert got == Settings(
        fields=(
            FieldChoice("Header", True),
            FieldChoice("Text", False),
            FieldChoice("Extra", False),
            FieldChoice("Personal Notes", True),
            FieldChoice("Textbook", False),
            FieldChoice("Citation", False),
            FieldChoice("Remarks", True),
        ),
        protected_tags=("#edited",),
        update_note_types=False,
        # the first tag starts as the main list's kept fields at that moment
        tag_rules=(TagRule("#edited", (), False, ("Header", "Personal Notes", "Remarks")),),
    )
    assert got.kept_field_names() == frozenset({"header", "personal notes", "remarks"})


def test_cancel_rejects(make_dialog):
    dlg = make_dialog()
    QTest.mouseClick(dlg.cancel_button, Qt.MouseButton.LeftButton)
    assert dlg.result() == QDialog.DialogCode.Rejected.value


def test_buttons_and_accent_primary(make_dialog):
    dlg = make_dialog()
    assert dlg.save_button.text() == "Save" and dlg.save_button.isDefault()
    assert dlg.cancel_button.text() == "Cancel"
    assert dlg.restore_button.text() == "Restore defaults"
    assert dlg.add_field_button.text() == "+ Add field"
    assert ACCENT in dlg.styleSheet().lower()


def test_every_control_reachable_by_tab(make_dialog):
    s = dataclasses.replace(default_settings(), protected_tags=("#edited",))
    dlg = make_dialog(settings=s)
    dlg.add_field("Remarks")
    type_into(dlg.tag_input, "board-review::")  # shows the list
    chain = []
    w = dlg.nextInFocusChain()
    while w is not dlg and len(chain) < 500:
        chain.append(w)
        w = w.nextInFocusChain()
    tabbable = {id(x) for x in chain if x.focusPolicy() & Qt.FocusPolicy.TabFocus}
    wanted = [dlg.add_field_button, dlg.tag_input, dlg.tag_list,
              dlg.styling_switch, dlg.scheduling_switch, dlg.presets_switch, dlg.restore_button, dlg.cancel_button, dlg.save_button,
              dlg.row_for("Remarks").remove_button, dlg.tag_chips()[0].remove_button]
    for row in dlg.field_rows():
        # Each toggle is an exclusive button group: once it has had focus
        # (the first row has it on opening), Qt keeps only its selected side
        # as a Tab stop and Left/Right switch sides, like radio buttons. The
        # selected side is always a Tab stop.
        wanted.append(row.toggle.selected_button())
    for x in wanted:
        assert id(x) in tabbable, x.objectName()
    first = dlg.field_rows()[0].toggle
    first.selected_button().setFocus()
    QTest.keyClick(first.selected_button(), Qt.Key.Key_Left)
    assert dlg.focusWidget() is first.keep_button and first.keep()


def test_colours_follow_dark_palette(qapp):
    """Plain sides use the palette's base colour, not a hard-coded white."""
    old = qapp.palette()
    pal = QPalette()
    for role, col in (
        (QPalette.ColorRole.Window, "#2c2c2c"),
        (QPalette.ColorRole.WindowText, "#eeeeee"),
        (QPalette.ColorRole.Base, "#1e1e1e"),
        (QPalette.ColorRole.Text, "#eeeeee"),
        (QPalette.ColorRole.Button, "#2c2c2c"),
        (QPalette.ColorRole.ButtonText, "#eeeeee"),
    ):
        pal.setColor(role, QColor(col))
    qapp.setPalette(pal)
    try:
        dlg = SettingsDialog(None, default_settings(), [], [])
        plain = dlg.row_for("Text").toggle.keep_button.styleSheet().lower()
        assert "#1e1e1e" in plain
        assert "#ffffff" not in plain
        dlg.deleteLater()
    finally:
        qapp.setPalette(old)


def test_field_rows_are_findable_by_object_name(make_dialog):
    dlg = make_dialog()
    rows = dlg.findChildren(FieldRow, "field_row")
    assert [r.property("field_name") for r in rows] == [n for n, _ in DEFAULT_FIELDS]
    assert dlg.findChild(QWidget, "tag_input") is dlg.tag_input
    assert dlg.findChild(QWidget, "styling_switch") is dlg.styling_switch
    assert dlg.findChild(QWidget, "scheduling_switch") is dlg.scheduling_switch
    assert dlg.findChild(QWidget, "presets_switch") is dlg.presets_switch


# --------------------------------------------------------------------------
# Markup in names is shown literally (field names and tags are user data)


def _shown_tooltip(text):
    from aqt.qt import QTextDocument

    if Qt.mightBeRichText(text):
        doc = QTextDocument()
        doc.setHtml(text)
        return doc.toPlainText()
    return text


def test_markup_in_field_name_and_tag_is_shown_literally(make_dialog):
    from aqt.qt import QLabel

    field = "<b>x</b> & <i>notes</i>"
    tag = "<b>tag</b>::<u>sub</u>"
    settings = Settings(fields=default_settings().fields + (FieldChoice(field, True),),
                        protected_tags=(tag,), update_note_types=True)
    dlg = make_dialog(settings=settings, fields=["Text", field, "<s>other</s>"], tags=[tag, "<s>t</s>"])
    row = dlg.row_for(field)
    assert row is not None
    assert row.label.textFormat() == Qt.TextFormat.PlainText
    assert row.label.text() == field
    assert _shown_tooltip(row.label.toolTip()) == field
    chip = dlg.tag_chips()[0]
    chip_label = chip.findChild(QLabel, "tag_chip_label")
    assert chip_label.textFormat() == Qt.TextFormat.PlainText
    assert chip_label.text() == tag
    assert _shown_tooltip(chip_label.toolTip()) == tag
    # hint lines that echo what the user typed
    type_into(dlg.tag_input, "<b>nope</b>")
    assert dlg.tag_hint.textFormat() == Qt.TextFormat.PlainText
    assert "<b>nope</b>" in dlg.tag_hint.text()
    dlg.open_field_picker()
    type_into(dlg.field_search, "<s>other</s>")
    dlg._field_enter()
    assert dlg.field_hint.textFormat() == Qt.TextFormat.PlainText
    assert dlg.row_for("<s>other</s>").label.text() == "<s>other</s>"
    type_into(dlg.field_search, "<s>other</s>")  # already a row: the hint echoes it
    assert "<s>other</s>" in dlg.field_hint.text()
    # nothing in the window is rich text
    for lab in dlg.findChildren(QLabel):
        assert lab.textFormat() == Qt.TextFormat.PlainText, (lab.objectName(), lab.text())
    # the result keeps the names exactly
    dlg.accept()
    out = dlg.result_settings()
    assert FieldChoice(field, True) in out.fields and tag in out.protected_tags


# --------------------------------------------------------------------------
# After the real-Anki pass (17 Nov 2026)

LONG_TAG = "#ANKOMA::CP::Immunology::Autoimmunity::AutoImmuneDiseases::FamilialMediterraneanFever"


def test_tag_list_has_no_horizontal_scrollbar_and_elides_long_tags(make_dialog, qapp):
    """Fix 2: no horizontal scroll bar; a long tag is elided in the middle
    (start and leaf readable), its tooltip is the full tag, and the tag
    added is the full tag."""
    tags = ["#edit", "#edited", "#edited::images"] + [LONG_TAG + str(i) for i in range(8)]
    dlg = make_dialog(tags=tags)
    type_into(dlg.tag_input, "e")
    qapp.processEvents()
    lst = dlg.tag_list
    assert lst.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert not lst.horizontalScrollBar().isVisible()
    assert lst.textElideMode() == Qt.TextElideMode.ElideMiddle
    vp = lst.viewport().rect()
    # every row is no wider than the list, and the visible ones are whole
    for i in range(lst.count()):
        rect = lst.visualItemRect(lst.item(i))
        assert rect.width() <= vp.width()
    for i in range(min(lst.count(), 8)):
        rect = lst.visualItemRect(lst.item(i))
        assert vp.contains(rect), (i, rect, vp)
    long_items = [lst.item(i) for i in range(lst.count()) if lst.item(i).text().startswith(LONG_TAG)]
    assert long_items
    item = long_items[0]
    assert item.text() == LONG_TAG + item.text()[-1]  # the row's text is the full tag
    assert _shown_tooltip(item.toolTip()) == item.text()
    fm = lst.fontMetrics()
    assert fm.horizontalAdvance(item.text()) > vp.width()  # really needs eliding
    full = item.text()
    click_item(lst, full)
    assert dlg.protected_tags() == [full]


def test_field_list_has_no_horizontal_scrollbar(make_dialog):
    long_field = "A very long field name " * 6
    dlg = make_dialog(fields=["Text", long_field])
    dlg.open_field_picker()
    lst = dlg.field_matches
    assert lst.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    item = lst.findItems(long_field, Qt.MatchFlag.MatchExactly)[0]
    assert lst.visualItemRect(item).width() <= lst.viewport().width()
    assert _shown_tooltip(item.toolTip()) == long_field
    click_item(lst, long_field)
    assert dlg.row_for(long_field) is not None


def test_window_grows_for_the_tag_list_and_shrinks_back(make_dialog, qapp):
    """Fix 3: the list opening grows the window (no scroll bar, heading in
    view, top-left unchanged); closing it shrinks back to the opening size,
    never below it; never above 90% of the screen height. (Two rows, so
    the window starts below the cap on the small offscreen screen.)"""
    few = dataclasses.replace(default_settings(), fields=default_settings().fields[:2])
    dlg = make_dialog(settings=few)
    dlg.move(10, 10)  # room below: the bottom screen edge is a cap too
    qapp.processEvents()
    assert dlg.height() < int(dlg.screen().availableGeometry().height() * 0.9)
    qapp.processEvents()
    pos, h0 = dlg.pos(), dlg.height()
    type_into(dlg.tag_input, "board")
    qapp.processEvents()
    assert dlg.tag_list.isVisible()
    assert dlg.height() > h0
    assert dlg.pos() == pos
    assert dlg.scroll.verticalScrollBar().maximum() == 0
    assert dlg.scroll.verticalScrollBar().value() == 0
    scr = dlg.screen().availableGeometry()
    assert dlg.height() <= int(scr.height() * 0.9)
    dlg.tag_input.clear()
    qapp.processEvents()
    assert not dlg.tag_list.isVisible()
    assert dlg.height() == h0
    # a size the user chose is the new floor
    dlg.resize(dlg.width(), h0 + 120)
    qapp.processEvents()
    dlg.open_field_picker()
    qapp.processEvents()
    dlg.close_field_picker()
    qapp.processEvents()
    assert dlg.height() == h0 + 120


def test_window_never_grows_past_the_screen_bottom(make_dialog, qapp):
    dlg = make_dialog(settings=dataclasses.replace(default_settings(), fields=()))
    scr = dlg.screen().availableGeometry()
    dlg.move(10, scr.bottom() - dlg.frameGeometry().height() - 20)
    qapp.processEvents()
    top = dlg.frameGeometry().top()
    dlg.open_field_picker()
    qapp.processEvents()
    assert dlg.frameGeometry().top() == top
    assert dlg.frameGeometry().bottom() <= scr.bottom()


def test_no_scrollbar_left_after_adding_a_field_and_closing_the_picker(make_dialog, qapp):
    """Seen in the real app: the window was at its cap while the picker was
    open (scroll bar showing); after a field was added and the picker
    closed, the window must fit without a leftover scroll bar."""
    dlg = make_dialog(settings=dataclasses.replace(default_settings(), fields=default_settings().fields[:2]))
    dlg.move(10, 10)
    qapp.processEvents()
    dlg.open_field_picker()
    qapp.processEvents()
    dlg._add_field_from_list("Remarks")
    qapp.processEvents()
    dlg.close_field_picker()
    qapp.processEvents()
    assert dlg.scroll.verticalScrollBar().maximum() == 0


def test_field_picker_grows_the_window(make_dialog, qapp):
    dlg = make_dialog(settings=dataclasses.replace(default_settings(), fields=()))
    dlg.move(10, 10)
    qapp.processEvents()
    h0 = dlg.height()
    dlg.open_field_picker()
    qapp.processEvents()
    assert dlg.height() > h0
    assert dlg.scroll.verticalScrollBar().maximum() == 0


def test_initial_focus_on_first_row_toggle(make_dialog, qapp):
    """Fix 7: focus starts on the first row's toggle (its selected side),
    or on "+ Add field" when there are no rows; never the tag box."""
    dlg = make_dialog()
    qapp.processEvents()
    first = dlg.field_rows()[0].toggle
    assert dlg.focusWidget() is first.selected_button()
    QTest.keyClick(dlg.focusWidget(), Qt.Key.Key_Tab)
    assert dlg.focusWidget() is not dlg.scroll
    empty = make_dialog(settings=dataclasses.replace(default_settings(), fields=()))
    qapp.processEvents()
    assert empty.focusWidget() is empty.add_field_button
    assert empty.focusWidget() is not empty.tag_input


def test_no_message_after_adding_a_field(make_dialog):
    """Fix 9: like the tag picker, nothing is said after a field is added;
    hints that report a problem stay."""
    dlg = make_dialog()
    dlg.open_field_picker()
    type_into(dlg.field_search, "Remarks")
    QTest.keyClick(dlg.field_search, Qt.Key.Key_Return)
    assert dlg.row_for("Remarks") is not None
    assert dlg.field_hint.text() == "" and not dlg.field_hint.isVisible()
    type_into(dlg.field_search, "Remarks")
    assert dlg.field_hint.isVisible() and "already in the list" in dlg.field_hint.text()


# ----- fix 8: "Discard your changes?" ---------------------------------------


@pytest.fixture
def discard_answers(monkeypatch):
    from special_fields_by_ankoma import settings_dialog as sd

    state = {"answer": False, "asked": 0}

    def fake(parent):
        state["asked"] += 1
        return state["answer"]

    monkeypatch.setattr(sd, "confirm_discard", fake)
    return state


def test_unchanged_escape_closes_without_question(make_dialog, discard_answers):
    dlg = make_dialog()
    dlg.row_for("Text").toggle.set_keep(True)
    dlg.row_for("Text").toggle.set_keep(False)  # changed back: unchanged
    QTest.keyClick(dlg, Qt.Key.Key_Escape)
    assert not dlg.isVisible() and discard_answers["asked"] == 0


@pytest.mark.parametrize("how", ["escape", "cancel", "close_box"])
def test_changed_asks_keep_editing_then_discard(make_dialog, discard_answers, how):
    dlg = make_dialog()
    dlg.row_for("Text").toggle.set_keep(True)
    dlg.styling_switch.setChecked(False)
    changed = dlg.result_settings()

    def close():
        if how == "escape":
            QTest.keyClick(dlg, Qt.Key.Key_Escape)
        elif how == "cancel":
            QTest.mouseClick(dlg.cancel_button, Qt.MouseButton.LeftButton)
        else:
            dlg.close()

    discard_answers["answer"] = False  # "Keep editing"
    close()
    assert discard_answers["asked"] == 1
    assert dlg.isVisible() and dlg.result_settings() == changed
    discard_answers["answer"] = True  # "Discard"
    close()
    assert discard_answers["asked"] == 2
    assert not dlg.isVisible()
    assert dlg.result() == QDialog.DialogCode.Rejected.value


def test_save_never_asks(make_dialog, discard_answers):
    dlg = make_dialog()
    dlg.row_for("Text").toggle.set_keep(True)
    QTest.mouseClick(dlg.save_button, Qt.MouseButton.LeftButton)
    assert discard_answers["asked"] == 0
    assert dlg.result() == QDialog.DialogCode.Accepted.value


def test_escape_in_search_box_still_clears_first(make_dialog, discard_answers):
    dlg = make_dialog()
    dlg.row_for("Text").toggle.set_keep(True)
    type_into(dlg.tag_input, "board")
    QTest.keyClick(dlg.tag_input, Qt.Key.Key_Escape)
    assert dlg.tag_input.text() == "" and dlg.isVisible() and discard_answers["asked"] == 0


@pytest.mark.parametrize("button", ["keep_editing_button", "discard_button"])
def test_real_discard_question_box(make_dialog, qapp, button):
    """The real box, answered from a timer: PlainText, title, two buttons,
    "Keep editing" is the default and the Esc button."""
    from aqt.qt import QMessageBox, QTimer

    dlg = make_dialog()
    dlg.row_for("Text").toggle.set_keep(True)
    seen = {}

    def answer():
        box = QApplication.activeModalWidget()
        if not isinstance(box, QMessageBox):
            QTimer.singleShot(10, answer)
            return
        seen.update(title=box.windowTitle(), text=box.text(), fmt=box.textFormat(),
                    buttons=sorted(b.text() for b in box.buttons()),
                    default=box.defaultButton().objectName(),
                    escape=box.escapeButton().objectName(), name=box.objectName())
        QTest.mouseClick(box.findChild(QPushButton, button), Qt.MouseButton.LeftButton)

    QTimer.singleShot(0, answer)
    QTest.keyClick(dlg, Qt.Key.Key_Escape)
    assert seen == dict(title="Special Fields by Ankoma", text="Discard your changes?",
                        fmt=Qt.TextFormat.PlainText, buttons=["Discard", "Keep editing"],
                        default="keep_editing_button", escape="keep_editing_button",
                        name="discard_question")
    assert dlg.isVisible() == (button == "keep_editing_button")
