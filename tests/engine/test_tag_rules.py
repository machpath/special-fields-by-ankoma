"""Contract rule 14: a field table per protected tag.

Shared world (tests/engine/conftest.py), release v2: A1 carries "#Edited"
and "#Edited::Images" (and "personal"; "#edited2" is not a sub-tag), A3
carries "#Edited" (and the update adds "#EDITED" to it), B1 carries
"#Edited::sub"; A2 has a Text fix and no personal tag. The update changes
Header, Text and Extra of A1-A4, B1, B2 and leaves Personal Notes empty
everywhere.

A note carrying protected tags follows the union of their tables, NOT the
main list; other notes follow the main list. A table is frozen: changing
the main list later changes no tag. Legacy entries (a plain string of beta
7; beta 8's {"tag", "keep_fields"}) keep the meaning they had there until
the settings window freezes them."""

from __future__ import annotations

import dataclasses
import shutil

import pytest
from anki.collection import Collection

from special_fields_by_ankoma.config import settings_from_config, settings_to_config
from special_fields_by_ankoma.engine import _tag_rule_lookup, run_import
from special_fields_by_ankoma.model import UNDO_LABEL, FieldChoice, Settings, TagRule

from .conftest import USER_MOD, _note_by_guid
from .test_rules_9_10 import _build, _plus_fields, fields_of

ALL = ("Header", "Text", "Extra", "Personal Notes")


def T(tag, fields=(), every=False):
    """A frozen table: the tag keeps exactly `fields`."""
    return TagRule(tag, (), every, tuple(fields))


def S(keep=(), take=(), protected=(), tables=(), update_note_types=True):
    """`tables`: TagRule objects (frozen with `T`, or legacy beta 8)."""
    fields = tuple(FieldChoice(n, True) for n in keep) + tuple(FieldChoice(n, False) for n in take)
    return Settings(fields=fields, protected_tags=tuple(protected), update_note_types=update_note_types,
                    tag_rules=tuple(tables))


def dump(col: Collection):
    col.models._clear_cache()
    out = {}
    for table in ("notes", "cards", "revlog", "notetypes", "fields", "templates",
                  "decks", "deck_config", "tags", "graves"):
        out[table] = col.db.all("select * from %s order by 1, 2" % table)
    out["config"] = col.db.all("select KEY, val from config order by KEY")
    out["scm"] = col.db.scalar("select scm from col")
    return out


def g(col, guid):
    return _note_by_guid(col, guid)


def content(col):
    """guid -> (fields, sorted tags): what the import decides."""
    return {guid: (flds, sorted(tags.split()))
            for guid, flds, tags in col.db.all("select guid, flds, tags from notes")}


def run_on_copy(world, tmp_path, name, settings, key="v2"):
    """Import into a fresh copy of the user's collection; (content, result)."""
    path = str(tmp_path / ("%s.anki2" % name))
    shutil.copy(world["user_base"], path)
    col = Collection(path)
    try:
        res = run_import(col, world["paths"][key], settings)
        return content(col), (res.fields_kept, res.notes_with_fields_kept,
                              res.protected_tags_kept, res.notes_with_tags_kept)
    finally:
        col.close()


def give_a2_personal_notes(col):
    a2 = g(col, "A2")
    a2["Personal Notes"] = "mine A2"
    col.update_note(a2)
    col.db.execute("update notes set mod=? where guid='A2'", USER_MOD)


A1_V1 = "A1 {{c1::v1}} {{c2::two}}"
A3_V1 = "A3 {{c1::v1}} {{c2::two}}"


def test_tag_table_replaces_the_main_list(user_col, world):
    """Personal Notes kept in the main list; "#edited" keeps Text, Extra
    and Personal Notes. Tagged notes keep those three and take the update's
    Header and tags (keeping #edited); every other note keeps only Personal
    Notes. One undo puts everything back."""
    col = user_col
    prior = col.undo_status()
    before = dump(col)
    s = S(keep=("Personal Notes",), take=("Header", "Text", "Extra"), protected=("#edited",),
          tables=(T("#edited", ("Text", "Extra", "Personal Notes")),))
    res = run_import(col, world["paths"]["v2"], s)
    a1, a2, a3, a4, b1, b2 = (g(col, x) for x in ("A1", "A2", "A3", "A4", "B1", "B2"))
    assert (a1["Header"], a1["Text"], a1["Extra"], a1["Personal Notes"]) == ("H1 v2", A1_V1, "E1 v1", "mine A1")
    assert sorted(a1.tags) == sorted(["##REL-v2::a::t1", "#Edited", "#Edited::Images"])
    assert (a3["Header"], a3["Text"], a3["Extra"]) == ("H3 v2", A3_V1, "E3 v1")
    # B1 carries the sub-tag "#Edited::sub": the parent's table applies
    assert (b1["Text"], b1["Extra"], b1["Personal Notes"]) == ("my text B1", "my extra B1", "mine B1")
    # no tag: only Personal Notes is kept, the user's Text fix is replaced
    assert a2["Text"] == "A2 {{c1::v2}} {{c2::two}}" and a2["Extra"] == "E2 v2"
    assert a4["Text"] == "A4 {{c1::v2}} {{c2::two}}" and b2["Extra"] == "E2 v2"
    # A1: Text, Extra, PN; A3: Text, Extra; B1: Text, Extra, PN
    assert res.fields_kept == 8 and res.notes_with_fields_kept == 3
    assert res.protected_tags_kept == 3 and res.notes_with_tags_kept == 2
    assert res.notes_updated == 6 and "gate" in res.seconds  # the rule 12 gate ran and passed
    assert col.undo_status().undo == UNDO_LABEL
    col.undo()
    assert dump(col) == before
    assert col.undo_status().undo == prior.undo


def test_a_tag_can_switch_off_a_field_the_main_list_keeps(user_col, world):
    """The author: "if a tag does not select personal notes but the overall
    [list] on top does, then [cards with that] tag will not be protected for
    that field". "#edited" keeps Text and Extra only: tagged notes take the
    update's Personal Notes, even though it is empty (it is listed, so rule
    9 does not put it back); A2 (no tag) keeps its Personal Notes."""
    col = user_col
    give_a2_personal_notes(col)
    s = S(keep=("Personal Notes",), take=("Header", "Text", "Extra"), protected=("#edited",),
          tables=(T("#edited", ("Text", "Extra")),))
    res = run_import(col, world["paths"]["v2"], s)
    a1, a2, a3, b1 = (g(col, x) for x in ("A1", "A2", "A3", "B1"))
    assert (a1["Text"], a1["Extra"], a1["Personal Notes"]) == (A1_V1, "E1 v1", "")
    assert (b1["Text"], b1["Extra"], b1["Personal Notes"]) == ("my text B1", "my extra B1", "")
    assert (a3["Text"], a3["Extra"]) == (A3_V1, "E3 v1")
    assert a2["Personal Notes"] == "mine A2" and a2["Text"] == "A2 {{c1::v2}} {{c2::two}}"
    # A1, A3, B1: Text and Extra each; A2: Personal Notes
    assert res.fields_kept == 7 and res.notes_with_fields_kept == 4


def test_a_tag_that_keeps_no_fields(user_col, world):
    """An empty table: tagged notes take the update's everything (except
    the protected tag itself); untagged notes follow the main list."""
    col = user_col
    give_a2_personal_notes(col)
    res = run_import(col, world["paths"]["v2"], S(keep=ALL, protected=("#edited",), tables=(T("#edited"),)))
    a1, a2, b1 = g(col, "A1"), g(col, "A2"), g(col, "B1")
    assert list(a1.fields) == ["H1 v2", "A1 {{c1::v2}} {{c2::two}}", "E1 v2", ""]
    assert list(b1.fields) == ["B1 v2", "E1 v2", ""]
    assert "#Edited" in a1.tags and "#Edited::sub" in b1.tags
    assert list(a2.fields) == ["H2 v1", "A2 {{c1::v1}} {{c2::two}} (my fix A2)", "E2 v1", "mine A2"]
    assert res.protected_tags_kept == 3


def test_union_of_two_tags(user_col, world):
    """A1 carries "#Edited" (keeps Text) and "personal" (keeps Header): it
    keeps both, and neither keeps Personal Notes, so A1 loses it although
    the main list keeps it. A3 only has #Edited."""
    col = user_col
    s = S(keep=("Personal Notes",), take=("Header", "Text", "Extra"), protected=("#edited", "personal"),
          tables=(T("#edited", ("Text",)), T("personal", ("Header",))))
    res = run_import(col, world["paths"]["v2"], s)
    a1, a3 = g(col, "A1"), g(col, "A3")
    assert (a1["Header"], a1["Text"], a1["Extra"], a1["Personal Notes"]) == ("my header A1", A1_V1, "E1 v2", "")
    assert (a3["Header"], a3["Text"]) == ("H3 v2", A3_V1)
    assert "personal" in a1.tags
    # A1 Header + Text, A3 Text, B1 Text
    assert res.fields_kept == 4 and res.notes_with_fields_kept == 3


def test_parent_and_sub_tag_both_protected_are_joined(user_col, world):
    """A1 carries "#Edited::Images", which is protected itself (Header) and
    a sub-tag of protected "#edited" (Text): A1 keeps both; A3 only Text."""
    col = user_col
    run_import(col, world["paths"]["v2"],
               S(take=ALL, protected=("#edited", "#edited::images"),
                 tables=(T("#edited", ("Text",)), T("#edited::images", ("Header",)))))
    a1, a3 = g(col, "A1"), g(col, "A3")
    assert (a1["Header"], a1["Text"]) == ("my header A1", A1_V1)
    assert (a3["Header"], a3["Text"]) == ("H3 v2", A3_V1)


def test_case_insensitive_tag_and_field_names(user_col, world):
    col = user_col
    run_import(col, world["paths"]["v2"],
               S(take=ALL, protected=("#EDITED ",), tables=(T("#EDITED ", (" text ", "EXTRA")),)))
    a1, b1, a2 = g(col, "A1"), g(col, "B1"), g(col, "A2")
    assert (a1["Text"], a1["Extra"], a1["Header"]) == (A1_V1, "E1 v1", "H1 v2")
    assert (b1["Text"], b1["Extra"]) == ("my text B1", "my extra B1")
    assert a2["Text"] == "A2 {{c1::v2}} {{c2::two}}"


def test_sub_tag_table_does_not_reach_the_parent(user_col, world):
    """A table on "#edited::images" applies to A1 (which has it), not to A3
    or B1 (which only have the parent or another sub-tag)."""
    col = user_col
    run_import(col, world["paths"]["v2"],
               S(take=ALL, protected=("#edited::images",), tables=(T("#edited::images", ("Text",)),)))
    assert g(col, "A1")["Text"] == A1_V1
    assert g(col, "A3")["Text"] == "A3 {{c1::v2}} {{c2::two}}"
    assert g(col, "B1")["Text"] == "B1 v2"


def test_pre_import_tags_decide(user_col, world):
    """The update adds "#EDITED" to A3. With the user's own #Edited removed
    before the import, A3 did not carry the tag: it follows the main list
    (its Text takes the update). A1 loses #Edited in the update's tags but
    carried it: its table applies."""
    col = user_col
    a3 = g(col, "A3")
    a3["Text"] = a3["Text"] + " (my fix A3)"
    a3.tags = [t for t in a3.tags if t.lower() != "#edited"]
    col.update_note(a3)
    col.db.execute("update notes set mod=? where guid='A3'", USER_MOD)
    run_import(col, world["paths"]["v2"], S(take=ALL, protected=("#edited",), tables=(T("#edited", ("Text",)),)))
    a3, a1 = g(col, "A3"), g(col, "A1")
    assert a3["Text"] == "A3 {{c1::v2}} {{c2::two}}"
    # the update's own tag (Anki spells it as the collection already does)
    assert "#edited" in [t.lower() for t in a3.tags]
    assert a1["Text"] == A1_V1


def test_every_field(user_col, world):
    """"Keep every field": every field the note had keeps the user's value,
    whatever the table's rows and the main list say."""
    col = user_col
    res = run_import(col, world["paths"]["v2"],
                     S(take=ALL, protected=("#edited",), tables=(T("#edited", ("Header",), every=True),)))
    a1, a3, b1, a2 = g(col, "A1"), g(col, "A3"), g(col, "B1"), g(col, "A2")
    assert list(a1.fields) == ["my header A1", A1_V1, "E1 v1", "mine A1"]
    assert list(a3.fields) == ["H3 v1", A3_V1, "E3 v1", ""]
    assert list(b1.fields) == ["my text B1", "my extra B1", "mine B1"]
    assert list(a2.fields) == ["H2 v2", "A2 {{c1::v2}} {{c2::two}}", "E2 v2", ""]
    assert sorted(a1.tags) == sorted(["##REL-v2::a::t1", "#Edited", "#Edited::Images"])
    # A1: 4, A3: 3 (PN "" both sides), B1: 3
    assert res.fields_kept == 10 and res.notes_with_fields_kept == 3


def test_every_field_new_field_takes_the_update(user_col, world):
    """v2-newfield appends "Mnemonic" to note type A: it is new to every
    note, so even with "every field" it takes the update's value."""
    col = user_col
    run_import(col, world["paths"]["v2newfield"],
               S(take=ALL, protected=("#edited",), tables=(T("#edited", every=True),)))
    a1 = g(col, "A1")
    assert a1["Mnemonic"] == "mnemonic A1"
    assert (a1["Header"], a1["Text"], a1["Extra"]) == ("my header A1", A1_V1, "E1 v1")
    assert g(col, "A2")["Header"] == "H2 v2"


def test_field_missing_on_the_note_type_is_skipped(user_col, world):
    """"Header" is not a field of B; "Mnemonic" exists nowhere."""
    col = user_col
    res = run_import(col, world["paths"]["v2"],
                     S(take=ALL, protected=("#edited",), tables=(T("#edited", ("Header", "Mnemonic")),)))
    a1, b1 = g(col, "A1"), g(col, "B1")
    assert a1["Header"] == "my header A1" and a1["Text"].startswith("A1 {{c1::v2}}")
    assert (b1["Text"], b1["Extra"]) == ("B1 v2", "E1 v2")
    assert res.fields_kept == 2  # A1 and A3 Header


def test_rule9_interplay(user_col, world):
    """Personal Notes is in no main-list row, only in the tag's table. On
    untagged notes it is unlisted and empty in the whole update, so rule 9
    puts the user's value back (A2). Extra, also only in the table, has
    update content: untagged notes take the update's. On tagged notes the
    table's fields are kept."""
    col = user_col
    a2 = g(col, "A2")
    a2["Personal Notes"] = "mine A2"
    a2["Extra"] = "my extra A2"
    col.update_note(a2)
    col.db.execute("update notes set mod=? where guid='A2'", USER_MOD)
    res = run_import(col, world["paths"]["v2"],
                     S(take=("Header", "Text"), protected=("#edited",),
                       tables=(T("#edited", ("Extra", "Personal Notes")),)))
    a1, a2, b1 = g(col, "A1"), g(col, "A2"), g(col, "B1")
    assert a2["Personal Notes"] == "mine A2" and a2["Extra"] == "E2 v2"
    assert a1["Personal Notes"] == "mine A1" and a1["Extra"] == "E1 v1"
    assert b1["Personal Notes"] == "mine B1" and b1["Extra"] == "my extra B1"
    # A1 Extra + PN, A3 Extra, B1 Extra + PN, A2 PN (rule 9)
    assert res.fields_kept == 6 and res.notes_with_fields_kept == 4


def test_rule9_still_covers_unlisted_fields_on_tagged_notes(user_col, world):
    """Personal Notes in no row and in no table: unlisted everywhere, so
    rule 9 puts it back on tagged notes too (the update has no content)."""
    col = user_col
    run_import(col, world["paths"]["v2"],
               S(take=("Header", "Text", "Extra"), protected=("#edited",), tables=(T("#edited", ("Text",)),)))
    assert g(col, "A1")["Personal Notes"] == "mine A1" and g(col, "B1")["Personal Notes"] == "mine B1"


def test_main_list_changed_after_the_tag_changes_no_tag(world, tmp_path):
    """Frozen: the tag was set while the main list kept Personal Notes; the
    user then switched Personal Notes to "Take the update's" in the main
    list. Tagged notes still keep it (their table did not change); untagged
    notes lose it. The config keeps the table as it was."""
    table = T("#edited", ("Personal Notes", "Header"))
    first = S(keep=("Personal Notes",), take=("Header", "Text", "Extra"), protected=("#edited",), tables=(table,))
    later = dataclasses.replace(first, fields=tuple(
        FieldChoice(f.name, False) for f in first.fields))
    assert later.rule_for("#edited") == table
    cfg = settings_to_config(later)
    assert cfg["protected_tags"] == [{"tag": "#edited", "fields": ["Personal Notes", "Header"],
                                      "keep_all_fields": False}]
    assert settings_from_config(cfg) == later
    got, _counts = run_on_copy(world, tmp_path, "later", later)
    a1, b1 = got["A1"][0].split("\x1f"), got["B1"][0].split("\x1f")
    assert a1[0] == "my header A1" and a1[3] == "mine A1"
    assert b1[2] == "mine B1"
    # the same as the table on its own, whatever the main list says
    alone, _ = run_on_copy(world, tmp_path, "alone", dataclasses.replace(first, fields=()))
    assert {k: v for k, v in got.items() if k in ("A1", "A3", "B1")} == {
        k: v for k, v in alone.items() if k in ("A1", "A3", "B1")}


def test_plain_string_tags_follow_the_main_list_before_and_after_freezing(world, tmp_path):
    """A beta 7 config (plain-string tags): the result is that of the main
    list alone with the tags kept, and stays exactly the same once the
    settings window has frozen the tags at that main list."""
    cfg = {"fields": [{"name": "Personal Notes", "keep": True}, {"name": "Text", "keep": False}],
           "protected_tags": ["#edited", "personal"]}
    legacy = settings_from_config(cfg)
    assert legacy.tag_rules == ()
    assert _tag_rule_lookup(legacy) is None  # beta 7's exact path
    frozen = legacy.with_frozen_tags()
    assert frozen.rule_for("#edited") == T("#edited", ("Personal Notes",))
    assert _tag_rule_lookup(frozen) is None  # tables equal to the main list: same path
    results = [run_on_copy(world, tmp_path, n, s) for n, s in (("legacy", legacy), ("frozen", frozen))]
    assert results[0] == results[1]
    # and, once frozen, a later main-list change no longer reaches the tags
    later = dataclasses.replace(frozen, fields=(FieldChoice("Personal Notes", False), FieldChoice("Text", False)))
    got, _ = run_on_copy(world, tmp_path, "later", later)
    assert got["A1"][0].split("\x1f")[3] == "mine A1"


def test_beta8_entries_keep_their_meaning_before_and_after_freezing(world, tmp_path):
    """A beta 8 object {"tag", "keep_fields"} means "the main list plus
    these" until frozen; frozen, it is that list. Same result either way,
    and the same as beta 8's: Text and Extra plus Personal Notes."""
    cfg = {"fields": [{"name": "Personal Notes", "keep": True}, {"name": "Text", "keep": False}],
           "protected_tags": [{"tag": "#edited", "keep_fields": ["Text", "Extra"], "keep_all_fields": False},
                              "personal"]}
    legacy = settings_from_config(cfg)
    assert legacy.tag_rules == (TagRule("#edited", ("Text", "Extra"), False),)
    assert settings_to_config(legacy)["protected_tags"] == cfg["protected_tags"]  # written back as it came
    frozen = legacy.with_frozen_tags()
    assert frozen.rule_for("#edited") == T("#edited", ("Personal Notes", "Text", "Extra"))
    assert frozen.rule_for("personal") == T("personal", ("Personal Notes",))
    results = [run_on_copy(world, tmp_path, n, s) for n, s in (("legacy", legacy), ("frozen", frozen))]
    assert results[0] == results[1]
    a1 = results[0][0]["A1"][0].split("\x1f")
    assert a1[1:] == [A1_V1, "E1 v1", "mine A1"]
    # beta 8's "every field" object
    every = settings_from_config({"protected_tags": [{"tag": "#edited", "keep_fields": [], "keep_all_fields": True}]})
    assert every.with_frozen_tags().rule_for("#edited").keep_all
    assert run_on_copy(world, tmp_path, "e1", every) == run_on_copy(
        world, tmp_path, "e2", every.with_frozen_tags())


def test_tables_equal_to_the_main_list_take_the_plain_path(world, tmp_path):
    """No measurable cost when every table equals the main list: the engine
    does no per-note lookup (and the result is the main list's)."""
    s = S(keep=("Personal Notes",), take=("Text",), protected=("#edited", "personal"),
          tables=(T("#edited", ("personal notes",)), T("personal", ("Personal Notes",))))
    assert _tag_rule_lookup(s) is None
    plain = dataclasses.replace(s, tag_rules=())
    assert run_on_copy(world, tmp_path, "t", s) == run_on_copy(world, tmp_path, "p", plain)
    # a table that differs, or "every field", needs the lookup
    assert _tag_rule_lookup(dataclasses.replace(s, tag_rules=(T("#edited", ()),))) is not None
    assert _tag_rule_lookup(dataclasses.replace(s, tag_rules=(T("#edited", ("Personal Notes",), True),))) is not None


def test_lookup_is_cached_per_tag_string():
    s = S(keep=("Personal Notes",), protected=("#edited", "b"),
          tables=(T("#edited", ("Text",)), T("b", ("Header",))))
    lookup = _tag_rule_lookup(s)
    assert lookup("x #Edited::Images B") == (frozenset({"text", "header"}), False)
    assert lookup("x #Edited::Images B") is lookup("x #Edited::Images B")
    assert lookup("x y") == (frozenset({"personal notes"}), False)
    assert lookup("") == (frozenset({"personal notes"}), False)
    assert lookup("#edited2") == (frozenset({"personal notes"}), False)


def test_rule_for_a_tag_that_is_not_protected_is_ignored(world, tmp_path):
    s = S(keep=("Personal Notes",), protected=("#edited",), tables=(T("personal", ("Text",)),))
    plain = dataclasses.replace(s, tag_rules=())
    assert run_on_copy(world, tmp_path, "a", s) == run_on_copy(world, tmp_path, "b", plain)


@pytest.mark.parametrize("every", [False, True], ids=["text", "every-field"])
def test_moved_note_applies_tag_tables_by_name(tmp_path, every):
    """Rule 10a with tag tables: the author moves "aaa" from AP to MI
    (cloze). Every user note carries "#edited" (with Personal Notes "MINE
    <guid>"). The tag's fields are applied by name on the new note type, no
    "+" leftover stays, and one undo restores everything."""
    col, v2, info = _build(str(tmp_path), "existing", True)
    try:
        col.models._clear_cache()
        before_notes = {guid: fields_of(col, guid) for guid in ("aaa", "bbb", "ccc")}
        before_plus = _plus_fields(col)
        before = dump(col)
        table = T("#edited", ("Text", "Personal Notes"), every=every)
        res = run_import(col, v2, S(keep=("Personal Notes",), take=("Header", "Text"),
                                    protected=("#edited",), tables=(table,)))
        col.models._clear_cache()
        for guid in ("aaa", "bbb", "ccc"):
            f = fields_of(col, guid)
            assert f["Text"] == "{{c1::T %s}} v1" % guid, (guid, f)
            assert f["Personal Notes"] == "MINE " + guid
            assert f["Extra"] == ("" if every else "E %s v2" % guid), (guid, f)
        aaa = g(col, "aaa")
        assert aaa.note_type()["name"] == "MI"
        # "Images" is new to the moved note: the update's (empty) value
        assert fields_of(col, "aaa")["Images"] == ""
        assert before_notes["aaa"]["Text"] == "{{c1::T aaa}} v1"
        assert _plus_fields(col) == before_plus
        assert "#edited" in aaa.tags
        assert res.notes_updated == 3
        col.undo()
        assert dump(col) == before
    finally:
        col.close()


def test_new_notes_and_untouched_notes_are_not_affected(user_col, world):
    """A table keeping every field touches only notes the update changes:
    B3 (unchanged in the file) and the new note A5 are as without tables."""
    col = user_col
    b3 = dict(zip(g(col, "B3").keys(), g(col, "B3").fields))
    run_import(col, world["paths"]["v2"], S(protected=("##REL-v1",), tables=(T("##REL-v1", every=True),)))
    assert dict(zip(g(col, "B3").keys(), g(col, "B3").fields)) == b3
    assert g(col, "A5")["Header"] == "H5 v2"
    # every updated note carried ##REL-v1::*: every field kept
    assert g(col, "A2")["Text"] == "A2 {{c1::v1}} {{c2::two}} (my fix A2)"
    assert g(col, "B2")["Extra"] == "E2 v1"


def test_config_round_trip_and_fields_kept_for():
    old = {"fields": [{"name": "Personal Notes", "keep": True}], "protected_tags": ["#edited", "#eevee"]}
    s = settings_from_config(old)
    assert s.protected_tags == ("#edited", "#eevee") and s.tag_rules == ()
    assert s == Settings(fields=(FieldChoice("Personal Notes", True),), protected_tags=("#edited", "#eevee"))
    assert settings_to_config(s)["protected_tags"] == ["#edited", "#eevee"]
    s2 = S(keep=("Personal Notes",), protected=("#eevee", "#edited", "x"),
           tables=(T("#eevee"), T("#edited", ("Text", "Extra")), T("x", ("Header",), every=True)))
    cfg = settings_to_config(s2)
    assert cfg["protected_tags"] == [
        {"tag": "#eevee", "fields": [], "keep_all_fields": False},
        {"tag": "#edited", "fields": ["Text", "Extra"], "keep_all_fields": False},
        {"tag": "x", "fields": ["Header"], "keep_all_fields": True},
    ]
    assert settings_from_config(cfg) == s2
    # a note with protected tags follows their tables, not the main list
    assert s2.fields_kept_for(["#Edited::images", "other"]) == (frozenset({"text", "extra"}), False)
    assert s2.fields_kept_for(["#edited", "#eevee"]) == (frozenset({"text", "extra"}), False)
    assert s2.fields_kept_for(["#eevee"]) == (frozenset(), False)
    assert s2.fields_kept_for(["X"]) == (frozenset({"header"}), True)
    assert s2.fields_kept_for(["other"]) == (frozenset({"personal notes"}), False)
    assert s2.tag_table("#EDITED") == (frozenset({"text", "extra"}), False)
