"""Settings window: fields kept per protected tag (contract rule 14)."""

from __future__ import annotations

import dataclasses
from types import SimpleNamespace

from PyQt6.QtTest import QTest

from aqt.qt import QAbstractButton, QApplication, QLabel, QLineEdit, QListWidget, Qt, QWidget

from special_fields_by_ankoma import settings_dialog as sd
from special_fields_by_ankoma.config import default_config, default_settings, settings_to_config
from special_fields_by_ankoma.model import FieldChoice, Settings, TagRule
from special_fields_by_ankoma.settings_dialog import (
    EVERY_FIELD_LABEL,
    TAG_KEEP_TEXT,
    TAG_ONLY_TEXT,
    choices_summary,
)

LONG_TAG = "#ANKOMA::CP::Immunology::Autoimmunity::AutoImmuneDiseases::FamilialMediterraneanFever::Extra"


def type_into(widget, text):
    widget.setFocus()
    QTest.keyClicks(widget, text)


def list_texts(lst):
    return [lst.item(i).text() for i in range(lst.count())]


def click_item(lst, text):
    item = lst.findItems(text, Qt.MatchFlag.MatchExactly)[0]
    lst.scrollToItem(item)
    QTest.mouseClick(lst.viewport(), Qt.MouseButton.LeftButton, pos=lst.visualItemRect(item).center())


def chip_names(block):
    return [c.name for c in block.chips()]


def with_tags(*tags, rules=()):
    return dataclasses.replace(default_settings(), protected_tags=tuple(tags), tag_rules=tuple(rules))


def test_new_tag_is_tag_only(make_dialog):
    dlg = make_dialog()
    type_into(dlg.tag_input, "#edited")
    QTest.keyClick(dlg.tag_input, Qt.Key.Key_Return)
    block = dlg.tag_block("#edited")
    assert block is not None and dlg.tag_chips() == [block]
    assert block.keep_label.text() == TAG_ONLY_TEXT
    assert block.chips() == [] and block.add_button.isVisible()
    assert block.add_button.text() == "+ Add field"
    assert dlg.result_settings().tag_rules == ()
    assert dlg.result_settings().protected_tags == ("#edited",)


def test_add_fields_by_enter_and_click_without_message(make_dialog):
    dlg = make_dialog(settings=with_tags("#edited"))
    block = dlg.tag_block("#edited")
    QTest.mouseClick(block.add_button, Qt.MouseButton.LeftButton)
    assert block.picker.isVisible() and not block.add_button.isVisible()
    assert dlg.focusWidget() is block.search
    assert list_texts(block.match_list)[0] == EVERY_FIELD_LABEL
    # nothing highlighted before typing: Enter alone adds nothing
    QTest.keyClick(block.search, Qt.Key.Key_Return)
    assert dlg.tag_rule("#edited") == ([], False)
    type_into(block.search, "tex")
    assert list_texts(block.match_list)[0] == "Text"
    assert block.match_list.currentItem().isSelected()  # first match highlighted
    QTest.keyClick(block.search, Qt.Key.Key_Return)
    assert chip_names(block) == ["Text"] and block.search.text() == ""
    assert not block.hint.isVisible()  # no message after adding
    assert "Text" not in list_texts(block.match_list)
    click_item(block.match_list, "Extra")  # one click adds, highlighted or not
    assert chip_names(block) == ["Text", "Extra"]
    assert block.keep_label.text() == TAG_KEEP_TEXT
    assert dlg.result_settings().tag_rules == (TagRule("#edited", ("Text", "Extra"), False),)
    # Esc clears the search first, then closes the picker
    type_into(block.search, "Hea")
    QTest.keyClick(block.search, Qt.Key.Key_Escape)
    assert block.search.text() == "" and block.picker.isVisible()
    QTest.keyClick(block.search, Qt.Key.Key_Escape)
    assert not block.picker.isVisible() and block.add_button.isVisible()
    assert dlg.focusWidget() is block.add_button
    assert dlg.isVisible()


def test_unknown_and_duplicate_field_hints(make_dialog):
    dlg = make_dialog(settings=with_tags("#edited", rules=[TagRule("#edited", ("Text",), False)]))
    block = dlg.tag_block("#edited")
    dlg.open_tag_field_picker("#edited")
    type_into(block.search, "nothing like it")
    assert block.hint.isVisible() and "No other fields" in block.hint.text()
    assert not dlg.add_tag_field("#edited", "nothing like it")
    assert not dlg.add_tag_field("#edited", "text")
    assert "already kept" in block.hint.text()
    assert dlg.tag_rule("#edited") == (["Text"], False)


def test_every_field_replaces_the_chips(make_dialog):
    dlg = make_dialog(settings=with_tags("#edited", rules=[TagRule("#edited", ("Text", "Extra"), False)]))
    block = dlg.tag_block("#edited")
    dlg.open_tag_field_picker("#edited")
    click_item(block.match_list, EVERY_FIELD_LABEL)
    assert chip_names(block) == [EVERY_FIELD_LABEL] and block.every_chip() is not None
    assert not block.picker.isVisible() and not block.add_button.isVisible()
    assert dlg.result_settings().tag_rules == (TagRule("#edited", (), True),)
    # one click on its ✕: back to "Tag only"
    QTest.mouseClick(block.every_chip().remove_button, Qt.MouseButton.LeftButton)
    assert block.chips() == [] and block.keep_label.text() == TAG_ONLY_TEXT
    assert block.add_button.isVisible() and dlg.focusWidget() is block.add_button
    assert dlg.result_settings().tag_rules == ()


def test_every_field_by_typing(make_dialog):
    dlg = make_dialog(settings=with_tags("#edited"))
    block = dlg.tag_block("#edited")
    dlg.open_tag_field_picker("#edited")
    type_into(block.search, "every")
    assert list_texts(block.match_list)[0] == EVERY_FIELD_LABEL
    QTest.keyClick(block.search, Qt.Key.Key_Return)
    assert dlg.tag_rule("#edited") == ([], True)


def test_remove_field_chip_is_one_click(make_dialog):
    dlg = make_dialog(settings=with_tags("#edited", rules=[TagRule("#edited", ("Text", "Extra"), False)]))
    block = dlg.tag_block("#edited")
    QTest.mouseClick(block.chip_for("Text").remove_button, Qt.MouseButton.LeftButton)
    assert chip_names(block) == ["Extra"]
    assert dlg.result_settings().tag_rules == (TagRule("#edited", ("Extra",), False),)


def test_removing_the_tag_removes_its_fields(make_dialog):
    dlg = make_dialog(settings=with_tags("#edited", "weak-areas",
                                         rules=[TagRule("#edited", ("Text",), False)]))
    QTest.mouseClick(dlg.tag_block("#edited").remove_button, Qt.MouseButton.LeftButton)
    assert [b.tag for b in dlg.tag_blocks()] == ["weak-areas"]
    assert dlg.result_settings().tag_rules == ()
    dlg.add_tag("#edited")
    assert dlg.tag_rule("#edited") == ([], False)
    assert dlg.tag_block("#edited").keep_label.text() == TAG_ONLY_TEXT


def test_fields_kept_everywhere_are_listed_last(make_dialog):
    dlg = make_dialog(settings=with_tags("#edited"))
    block = dlg.tag_block("#edited")
    dlg.open_tag_field_picker("#edited")
    names = list_texts(block.match_list)
    assert names[0] == EVERY_FIELD_LABEL and names[-1] == "Personal Notes"  # "Keep mine" in the main list
    dlg.row_for("Text").toggle.set_keep(True)
    dlg._refresh_tag_field_matches("#edited")
    assert list_texts(block.match_list)[-2:] == ["Text", "Personal Notes"]
    assert dlg.add_tag_field("#edited", "Personal Notes")  # allowed (harmless)


def test_restore_defaults_clears_tag_rules(make_dialog):
    dlg = make_dialog(settings=with_tags("#edited", rules=[TagRule("#edited", (), True)]))
    QTest.mouseClick(dlg.restore_button, Qt.MouseButton.LeftButton)
    assert dlg.result_settings() == default_settings() and dlg.tag_blocks() == []


def test_discard_question_covers_tag_fields(make_dialog, monkeypatch):
    asked = []
    monkeypatch.setattr(sd, "confirm_discard", lambda parent: asked.append(1) or False)
    dlg = make_dialog(settings=with_tags("#edited"))
    dlg.add_tag_field("#edited", "Text")
    assert dlg.has_changes()
    QTest.keyClick(dlg, Qt.Key.Key_Escape)
    assert asked == [1] and dlg.isVisible()
    dlg.remove_tag_field("#edited", "Text")  # changed back: unchanged
    assert not dlg.has_changes()
    dlg.add_tag_field("#edited", "", every=True)
    assert dlg.has_changes()


def test_persisted_through_the_config(qapp, monkeypatch):
    from conftest import ALL_FIELDS, ALL_TAGS

    def fake_exec(self):
        assert self.add_tag("#edited") and self.add_tag("weak-areas") and self.add_tag("board-review")
        self.open_tag_field_picker("#edited")
        type_into(self.tag_block("#edited").search, "Text")
        QTest.keyClick(self.tag_block("#edited").search, Qt.Key.Key_Return)
        self.add_tag_field("#edited", "Extra")
        self.add_tag_field("weak-areas", "", every=True)
        self.accept()
        return self.result()

    monkeypatch.setattr(sd.SettingsDialog, "exec", fake_exec)
    col = SimpleNamespace(models=SimpleNamespace(all_names_and_ids=lambda: []),
                          tags=SimpleNamespace(all=lambda: list(ALL_TAGS)))
    configs = {}
    am = SimpleNamespace(getConfig=lambda key: dict(configs[key]) if key in configs else None,
                         writeConfig=lambda key, cfg: configs.__setitem__(key, cfg))
    mw = SimpleNamespace(addonManager=am, col=col)
    monkeypatch.setattr(sd, "_collection_field_names", lambda c: list(ALL_FIELDS))
    configs["special_fields_by_ankoma"] = default_config()
    got = sd.open_settings(mw)
    stored = configs["special_fields_by_ankoma"]["protected_tags"]
    assert stored == [
        {"tag": "#edited", "keep_fields": ["Text", "Extra"], "keep_all_fields": False},
        {"tag": "weak-areas", "keep_fields": [], "keep_all_fields": True},
        "board-review",
    ]
    assert sd.load_settings(mw) == got
    # reopened: the blocks show what was saved
    dlg = sd.SettingsDialog(None, sd.load_settings(mw), ALL_FIELDS, ALL_TAGS)
    try:
        assert chip_names(dlg.tag_block("#edited")) == ["Text", "Extra"]
        assert chip_names(dlg.tag_block("weak-areas")) == [EVERY_FIELD_LABEL]
        assert dlg.tag_block("board-review").keep_label.text() == TAG_ONLY_TEXT
        assert not dlg.has_changes()
    finally:
        dlg.deleteLater()


def test_tab_order_through_the_blocks(make_dialog):
    dlg = make_dialog(settings=with_tags("#edited", "weak-areas",
                                         rules=[TagRule("#edited", ("Text", "Extra"), False)]))
    a, b = dlg.tag_block("#edited"), dlg.tag_block("weak-areas")
    order = [a.remove_button, a.chip_for("Text").remove_button, a.chip_for("Extra").remove_button,
             a.add_button, b.remove_button, b.add_button, dlg.tag_input]
    order[0].setFocus()
    QApplication.processEvents()
    for here, there in zip(order, order[1:]):
        assert QApplication.focusWidget() is here, (QApplication.focusWidget(), here)
        QTest.keyClick(here, Qt.Key.Key_Tab)
        QApplication.processEvents()
    assert QApplication.focusWidget() is dlg.tag_input
    # an open picker sits between its block's chips and the next block
    dlg.open_tag_field_picker("#edited")
    assert dlg.focusWidget() is a.search
    QTest.keyClick(a.search, Qt.Key.Key_Tab)
    assert dlg.focusWidget() is a.done_button
    QTest.keyClick(a.done_button, Qt.Key.Key_Tab)
    assert dlg.focusWidget() is a.match_list
    QTest.keyClick(a.match_list, Qt.Key.Key_Tab)
    assert dlg.focusWidget() is b.remove_button


def test_long_tag_does_not_widen_the_window(make_dialog, qapp):
    dlg = make_dialog(settings=with_tags(LONG_TAG, rules=[TagRule(LONG_TAG, ("Text",), False)]),
                      tags=[LONG_TAG])
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
    assert dlg.result_settings().protected_tags == (LONG_TAG,)


def test_tag_picker_list_has_no_horizontal_scrollbar_and_grows_the_window(make_dialog, qapp):
    long_field = "A very long field name " * 6
    few = dataclasses.replace(with_tags("#edited"), fields=default_settings().fields[:1])
    dlg = make_dialog(settings=few, fields=["Text", long_field])
    dlg.move(10, 10)
    qapp.processEvents()
    h0 = dlg.height()
    dlg.open_tag_field_picker("#edited")
    qapp.processEvents()
    lst = dlg.tag_block("#edited").match_list
    assert dlg.height() > h0
    assert dlg.scroll.verticalScrollBar().maximum() == 0
    assert lst.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    item = lst.findItems(long_field, Qt.MatchFlag.MatchExactly)[0]
    assert lst.visualItemRect(item).width() <= lst.viewport().width()
    click_item(lst, long_field)
    assert dlg.tag_rule("#edited") == ([long_field], False)
    dlg.close_tag_field_picker("#edited")
    qapp.processEvents()
    assert dlg.height() == h0 or dlg.scroll.verticalScrollBar().maximum() == 0


def test_only_one_tag_picker_open(make_dialog):
    dlg = make_dialog(settings=with_tags("#edited", "weak-areas"))
    dlg.open_tag_field_picker("#edited")
    dlg.open_tag_field_picker("weak-areas")
    assert not dlg.tag_block("#edited").picker.isVisible()
    assert dlg.tag_block("weak-areas").picker.isVisible()


def test_plain_text_and_accessible_names(make_dialog):
    tag = "<b>tag</b>"
    dlg = make_dialog(settings=with_tags("#edited", tag, rules=[TagRule("#edited", ("<i>f</i>",), False)]),
                      fields=["Text", "<i>f</i>"], tags=["#edited", tag])
    dlg.open_tag_field_picker(tag)
    for lab in dlg.findChildren(QLabel):
        assert lab.textFormat() == Qt.TextFormat.PlainText, (lab.objectName(), lab.text())
    for block in dlg.tag_blocks():
        controls = [block.remove_button, block.add_button, block.search, block.match_list]
        controls += [c.remove_button for c in block.chips()]
        for w in controls:
            assert w.accessibleName(), w.objectName()
        assert block.tag in block.remove_button.accessibleName()
    assert dlg.tag_block(tag).label.text() == tag


def test_choices_summary_protected_tags_row():
    s = Settings(fields=(FieldChoice("Personal Notes", True),), protected_tags=("#edited", "#eevee"),
                 tag_rules=(TagRule("#edited", ("Text", "Extra"), False),))
    assert dict(choices_summary(s))["Protected tags"] == "#edited (keeps Text, Extra), #eevee"
    s2 = dataclasses.replace(s, protected_tags=("#edited",), tag_rules=(TagRule("#edited", (), True),))
    assert dict(choices_summary(s2))["Protected tags"] == "#edited (keeps every field)"
    s3 = dataclasses.replace(s, tag_rules=())
    assert dict(choices_summary(s3))["Protected tags"] == "#edited, #eevee"
    assert [label for label, _ in choices_summary(s)] == [label for label, _ in choices_summary(default_settings())]
    assert settings_to_config(s)["protected_tags"][1] == "#eevee"
