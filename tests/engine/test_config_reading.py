"""Hand-edited add-on config must never silently flip a choice."""

from special_fields_by_ankoma import config as c


def test_defaults_round_trip():
    d = c.default_settings()
    assert c.settings_from_config(None) == d
    assert c.settings_from_config(c.default_config()) == d
    assert [f.name for f in d.fields] == ["Header", "Text", "Extra", "Personal Notes", "Textbook", "Citation"]
    assert [f.name for f in d.fields if f.keep] == ["Personal Notes"]


def test_keep_written_as_words_or_numbers():
    s = c.settings_from_config({"fields": [
        {"name": "A", "keep": "false"},
        {"name": "B", "keep": "TRUE"},
        {"name": "C", "keep": "maybe"},
        {"name": "D", "keep": 1},
        {"name": "E", "keep": 7},
        {"name": "F"},
    ]})
    assert [(f.name, f.keep) for f in s.fields] == [
        ("A", False), ("B", True), ("C", False), ("D", True), ("E", False), ("F", False)]


def test_update_note_types_written_as_words():
    assert c.settings_from_config({"update_note_types": "false"}).update_note_types is False
    assert c.settings_from_config({"update_note_types": " No "}).update_note_types is False
    assert c.settings_from_config({"update_note_types": 0}).update_note_types is False
    assert c.settings_from_config({"update_note_types": "true"}).update_note_types is True
    # nonsense falls back to the default (True) rather than guessing
    assert c.settings_from_config({"update_note_types": "banana"}).update_note_types is True
    assert c.settings_from_config({"update_note_types": None}).update_note_types is True


def test_protected_tags_single_string_and_junk():
    assert c.settings_from_config({"protected_tags": "#edited"}).protected_tags == ("#edited",)
    assert c.settings_from_config({"protected_tags": ["a", " A ", 3, ""]}).protected_tags == ("a",)
    assert c.settings_from_config({"protected_tags": {"x": 1}}).protected_tags == ()
