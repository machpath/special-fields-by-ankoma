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


def test_import_switches_default_off_and_old_configs_load():
    assert c.default_settings().import_scheduling is False
    assert c.default_settings().import_deck_presets is False
    cfg = c.default_config()
    assert cfg["import_scheduling"] is False and cfg["import_deck_presets"] is False
    # Saved by an earlier beta: neither key present.
    old = {"config_version": 1, "fields": [{"name": "Text", "keep": True}],
           "protected_tags": ["#edited"], "update_note_types": False}
    s = c.settings_from_config(old)
    assert s.import_scheduling is False and s.import_deck_presets is False
    assert s.update_note_types is False and s.keeps_field("text")


def test_import_switches_read_tolerantly():
    for key in ("import_scheduling", "import_deck_presets"):
        assert getattr(c.settings_from_config({key: "yes"}), key) is True
        assert getattr(c.settings_from_config({key: 1}), key) is True
        assert getattr(c.settings_from_config({key: " Off "}), key) is False
        assert getattr(c.settings_from_config({key: "banana"}), key) is False
        assert getattr(c.settings_from_config({key: None}), key) is False


def test_import_switches_round_trip():
    s = c.Settings(fields=(), import_scheduling=True, import_deck_presets=True)
    cfg = c.settings_to_config(s)
    assert cfg["import_scheduling"] is True and cfg["import_deck_presets"] is True
    assert c.settings_from_config(cfg) == s


def test_shipped_config_json_is_the_default_config():
    import json
    import os

    path = os.path.join(os.path.dirname(c.__file__), "config.json")
    with open(path, encoding="utf-8") as f:
        assert json.load(f) == c.default_config()


def test_tag_rules_read_tolerantly():
    """Rule 14: plain strings (earlier betas) and objects mix; junk falls
    back to "Tag only"; a tag listed twice keeps its first place and the
    fields of both entries; "every field" wins over a field list."""
    s = c.settings_from_config({"protected_tags": [
        "#eevee",
        {"tag": " #edited ", "keep_fields": ["Text", " text ", "", 3, "Extra"], "colour": "red"},
        {"tag": "#bad1", "keep_fields": 5, "keep_all_fields": "maybe"},
        {"tag": "#all", "keep_fields": ["Text"], "keep_all_fields": "yes"},
        {"keep_fields": ["Text"]},
        {"tag": "#EEVEE", "keep_fields": "Header"},
        {"tag": "#edited", "keep_fields": ["Personal Notes"]},
    ]})
    assert s.protected_tags == ("#eevee", "#edited", "#bad1", "#all")
    assert s.tag_rules == (
        c.TagRule("#eevee", ("Header",), False),
        c.TagRule("#edited", ("Text", "Extra", "Personal Notes"), False),
        c.TagRule("#all", (), True),
    )
    assert s.rule_for("#bad1") is None
    # a single object without the list brackets
    one = c.settings_from_config({"protected_tags": {"tag": "#x", "keep_all_fields": True}})
    assert one.protected_tags == ("#x",) and one.rule_for("#X").keep_all


def test_tag_only_saved_as_plain_string():
    s = c.Settings(protected_tags=("#a", "#b"), tag_rules=(c.TagRule("#b", (), False),))
    assert c.settings_to_config(s)["protected_tags"] == ["#a", "#b"]
