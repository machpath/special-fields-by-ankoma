"""Contract rule 14: fields kept per protected tag.

Shared world (tests/engine/conftest.py), release v2: A1 carries "#Edited"
and "#Edited::Images" (and "personal"), A3 carries "#Edited" (and the update
adds "#EDITED" to it), B1 carries "#Edited::sub"; A2 has a Text fix and no
personal tag. The update changes Header, Text and Extra of A1-A4, B1, B2 and
leaves Personal Notes empty everywhere."""

from __future__ import annotations

import pytest
from anki.collection import Collection

from special_fields_by_ankoma.config import settings_from_config, settings_to_config
from special_fields_by_ankoma.engine import run_import
from special_fields_by_ankoma.model import UNDO_LABEL, FieldChoice, Settings, TagRule

from .conftest import USER_MOD, _note_by_guid
from .test_rules_9_10 import _build, _plus_fields, fields_of

ALL = ("Header", "Text", "Extra", "Personal Notes")


def S(keep=(), take=(), protected=(), rules=(), update_note_types=True):
    """`rules`: (tag, fields) pairs; fields == "all" means "every field"."""
    fields = tuple(FieldChoice(n, True) for n in keep) + tuple(FieldChoice(n, False) for n in take)
    tag_rules = tuple(TagRule(t, (), True) if f == "all" else TagRule(t, tuple(f), False) for t, f in rules)
    return Settings(fields=fields, protected_tags=tuple(protected), update_note_types=update_note_types,
                    tag_rules=tag_rules)


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


A1_V1 = "A1 {{c1::v1}} {{c2::two}}"
A3_V1 = "A3 {{c1::v1}} {{c2::two}}"


def test_worked_example(user_col, world):
    """The author's example: Personal Notes kept everywhere, "#edited" also
    keeps Text and Extra. Notes with #edited (or a sub-tag) keep Text, Extra
    and Personal Notes and take the update's Header and tags (keeping
    #edited); every other note keeps only Personal Notes."""
    col = user_col
    prior = col.undo_status()
    before = dump(col)
    s = S(keep=("Personal Notes",), take=("Header", "Text", "Extra"), protected=("#edited",),
          rules=(("#edited", ("Text", "Extra")),))
    res = run_import(col, world["paths"]["v2"], s)
    a1, a2, a3, a4, b1, b2 = (g(col, x) for x in ("A1", "A2", "A3", "A4", "B1", "B2"))
    assert (a1["Header"], a1["Text"], a1["Extra"], a1["Personal Notes"]) == ("H1 v2", A1_V1, "E1 v1", "mine A1")
    assert sorted(a1.tags) == sorted(["##REL-v2::a::t1", "#Edited", "#Edited::Images"])
    assert (a3["Header"], a3["Text"], a3["Extra"]) == ("H3 v2", A3_V1, "E3 v1")
    # B1 carries the sub-tag "#Edited::sub": the parent's rule applies
    assert (b1["Text"], b1["Extra"], b1["Personal Notes"]) == ("my text B1", "my extra B1", "mine B1")
    # no tag: only Personal Notes is kept, the user's Text fix is replaced
    assert a2["Text"] == "A2 {{c1::v2}} {{c2::two}}" and a2["Extra"] == "E2 v2"
    assert a4["Text"] == "A4 {{c1::v2}} {{c2::two}}" and b2["Extra"] == "E2 v2"
    # A1: Text, Extra, PN; A3: Text, Extra; B1: Text, Extra, PN
    assert res.fields_kept == 8 and res.notes_with_fields_kept == 3
    assert res.protected_tags_kept == 3 and res.notes_with_tags_kept == 2
    assert res.notes_updated == 6 and "gate" in res.seconds  # the rule 12 gate ran and passed
    # one undo puts everything back
    assert col.undo_status().undo == UNDO_LABEL
    col.undo()
    assert dump(col) == before
    assert col.undo_status().undo == prior.undo


def test_union_of_two_tags(user_col, world):
    """A1 carries "#Edited" (keeps Text) and "personal" (keeps Header): it
    keeps both. A3 only has #Edited."""
    col = user_col
    s = S(take=ALL, protected=("#edited", "personal"),
          rules=(("#edited", ("Text",)), ("personal", ("Header",))))
    res = run_import(col, world["paths"]["v2"], s)
    a1, a3 = g(col, "A1"), g(col, "A3")
    assert (a1["Header"], a1["Text"], a1["Extra"]) == ("my header A1", A1_V1, "E1 v2")
    assert a1["Personal Notes"] == ""  # listed as "Take the update's"
    assert (a3["Header"], a3["Text"]) == ("H3 v2", A3_V1)
    assert "personal" in a1.tags
    # A1 Header + Text, A3 Text, B1 Text
    assert res.fields_kept == 4 and res.notes_with_fields_kept == 3


def test_case_insensitive_tag_and_field_names(user_col, world):
    col = user_col
    run_import(col, world["paths"]["v2"],
               S(take=ALL, protected=("#EDITED ",), rules=(("#EDITED ", (" text ", "EXTRA")),)))
    a1, b1, a2 = g(col, "A1"), g(col, "B1"), g(col, "A2")
    assert (a1["Text"], a1["Extra"], a1["Header"]) == (A1_V1, "E1 v1", "H1 v2")
    assert (b1["Text"], b1["Extra"]) == ("my text B1", "my extra B1")
    assert a2["Text"] == "A2 {{c1::v2}} {{c2::two}}"


def test_sub_tag_rule_does_not_reach_the_parent(user_col, world):
    """A rule on "#edited::images" applies to A1 (which has it), not to A3
    or B1 (which only have the parent or another sub-tag)."""
    col = user_col
    run_import(col, world["paths"]["v2"],
               S(take=ALL, protected=("#edited::images",), rules=(("#edited::images", ("Text",)),)))
    assert g(col, "A1")["Text"] == A1_V1
    assert g(col, "A3")["Text"] == "A3 {{c1::v2}} {{c2::two}}"
    assert g(col, "B1")["Text"] == "B1 v2"


def test_pre_import_tags_decide(user_col, world):
    """The update adds "#EDITED" to A3. With the user's own #Edited removed
    before the import, A3 did not carry the tag: its Text takes the update.
    A1 loses #Edited in the update's tags but carried it: kept."""
    col = user_col
    a3 = g(col, "A3")
    a3["Text"] = a3["Text"] + " (my fix A3)"
    a3.tags = [t for t in a3.tags if t.lower() != "#edited"]
    col.update_note(a3)
    col.db.execute("update notes set mod=? where guid='A3'", USER_MOD)
    run_import(col, world["paths"]["v2"], S(take=ALL, protected=("#edited",), rules=(("#edited", ("Text",)),)))
    a3, a1 = g(col, "A3"), g(col, "A1")
    assert a3["Text"] == "A3 {{c1::v2}} {{c2::two}}"
    # the update's own tag (Anki spells it as the collection already does)
    assert "#edited" in [t.lower() for t in a3.tags]
    assert a1["Text"] == A1_V1


def test_every_field(user_col, world):
    """"Every field": every field the note had keeps the user's value,
    "Take the update's" in the main list notwithstanding."""
    col = user_col
    res = run_import(col, world["paths"]["v2"], S(take=ALL, protected=("#edited",), rules=(("#edited", "all"),)))
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
    run_import(col, world["paths"]["v2newfield"], S(take=ALL, protected=("#edited",), rules=(("#edited", "all"),)))
    a1 = g(col, "A1")
    assert a1["Mnemonic"] == "mnemonic A1"
    assert (a1["Header"], a1["Text"], a1["Extra"]) == ("my header A1", A1_V1, "E1 v1")
    assert g(col, "A2")["Header"] == "H2 v2"


def test_field_missing_on_the_note_type_is_skipped(user_col, world):
    """"Header" is not a field of B; "Mnemonic" exists nowhere."""
    col = user_col
    res = run_import(col, world["paths"]["v2"],
                     S(take=ALL, protected=("#edited",), rules=(("#edited", ("Header", "Mnemonic")),)))
    a1, b1 = g(col, "A1"), g(col, "B1")
    assert a1["Header"] == "my header A1" and a1["Text"].startswith("A1 {{c1::v2}}")
    assert (b1["Text"], b1["Extra"]) == ("B1 v2", "E1 v2")
    assert res.fields_kept == 2  # A1 and A3 Header


def test_rule9_interplay(user_col, world):
    """Personal Notes is listed only in the tag rule. On the other notes it
    is handled as today: unlisted and empty in the whole update, so rule 9
    puts every user's value back (A2 has no tag). Extra, also only in the
    tag rule, has update content: untagged notes take the update's."""
    col = user_col
    a2 = g(col, "A2")
    a2["Personal Notes"] = "mine A2"
    a2["Extra"] = "my extra A2"
    col.update_note(a2)
    col.db.execute("update notes set mod=? where guid='A2'", USER_MOD)
    res = run_import(col, world["paths"]["v2"],
                     S(take=("Header", "Text"), protected=("#edited",),
                       rules=(("#edited", ("Extra", "Personal Notes")),)))
    a1, a2, b1 = g(col, "A1"), g(col, "A2"), g(col, "B1")
    assert a2["Personal Notes"] == "mine A2" and a2["Extra"] == "E2 v2"
    assert a1["Personal Notes"] == "mine A1" and a1["Extra"] == "E1 v1"
    assert b1["Personal Notes"] == "mine B1" and b1["Extra"] == "my extra B1"
    # A1 Extra + PN, A3 Extra, B1 Extra + PN, A2 PN (rule 9)
    assert res.fields_kept == 6 and res.notes_with_fields_kept == 4


def test_listed_take_field_stays_take_on_untagged_notes(user_col, world):
    col = user_col
    a2 = g(col, "A2")
    a2["Personal Notes"] = "mine A2"
    col.update_note(a2)
    run_import(col, world["paths"]["v2"],
               S(take=("Personal Notes",), protected=("#edited",), rules=(("#edited", ("Personal Notes",)),)))
    assert g(col, "A2")["Personal Notes"] == ""
    assert g(col, "A1")["Personal Notes"] == "mine A1"


def test_no_tag_fields_gives_exactly_todays_result(world, tmp_path):
    """Protected tags with no fields, and a rule for a tag that is not
    protected (ignored), give the same notes as plain protected tags."""
    import shutil

    results = []
    for i, extra in enumerate(((), (TagRule("#edited", (), False), TagRule("personal", ("Text",), False)))):
        path = str(tmp_path / ("u%d.anki2" % i))
        shutil.copy(world["user_base"], path)
        col = Collection(path)
        try:
            s = Settings(fields=(FieldChoice("Personal Notes", True),), protected_tags=("#edited",),
                         tag_rules=extra)
            res = run_import(col, world["paths"]["v2"], s)
            results.append((content(col), res.fields_kept, res.notes_with_fields_kept, res.protected_tags_kept))
        finally:
            col.close()
    assert results[0] == results[1]


@pytest.mark.parametrize("every", [False, True], ids=["text", "every-field"])
def test_moved_note_applies_tag_rules_by_name(tmp_path, every):
    """Rule 10a with tag rules: the author moves "aaa" from AP to MI (cloze).
    Every user note carries "#edited" (with Personal Notes "MINE <guid>").
    The tag's fields are applied by name on the new note type, no "+"
    leftover stays, and one undo restores everything."""
    col, v2, info = _build(str(tmp_path), "existing", True)
    try:
        col.models._clear_cache()
        before_notes = {guid: fields_of(col, guid) for guid in ("aaa", "bbb", "ccc")}
        before_plus = _plus_fields(col)
        before = dump(col)
        rule = ("#edited", "all" if every else ("Text",))
        res = run_import(col, v2, S(keep=("Personal Notes",), take=("Header", "Text"),
                                    protected=("#edited",), rules=(rule,)))
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


def test_new_notes_and_untouched_notes_are_not_affected(user_col, world, tmp_path):
    """A rule keeping every field touches only notes the update changes:
    B3 (unchanged in the file) and the new note A5 are as without rules."""
    col = user_col
    b3 = dict(zip(g(col, "B3").keys(), g(col, "B3").fields))
    run_import(col, world["paths"]["v2"], S(protected=("##REL-v1",), rules=(("##REL-v1", "all"),)))
    assert dict(zip(g(col, "B3").keys(), g(col, "B3").fields)) == b3
    assert g(col, "A5")["Header"] == "H5 v2"
    # every updated note carried ##REL-v1::*: every field kept
    assert g(col, "A2")["Text"] == "A2 {{c1::v1}} {{c2::two}} (my fix A2)"
    assert g(col, "B2")["Extra"] == "E2 v1"


def test_old_config_loads_and_rules_round_trip():
    old = {"fields": [{"name": "Personal Notes", "keep": True}], "protected_tags": ["#edited", "#eevee"]}
    s = settings_from_config(old)
    assert s.protected_tags == ("#edited", "#eevee") and s.tag_rules == ()
    assert s == Settings(fields=(FieldChoice("Personal Notes", True),), protected_tags=("#edited", "#eevee"))
    assert settings_to_config(s)["protected_tags"] == ["#edited", "#eevee"]
    s2 = S(keep=("Personal Notes",), protected=("#eevee", "#edited", "x"),
           rules=(("#edited", ("Text", "Extra")), ("x", "all")))
    cfg = settings_to_config(s2)
    assert cfg["protected_tags"] == [
        "#eevee",
        {"tag": "#edited", "keep_fields": ["Text", "Extra"], "keep_all_fields": False},
        {"tag": "x", "keep_fields": [], "keep_all_fields": True},
    ]
    assert settings_from_config(cfg) == s2
    assert s2.fields_kept_for(["#Edited::images", "other"]) == (
        frozenset({"personal notes", "text", "extra"}), False)
    assert s2.fields_kept_for(["X"])[1] is True
    assert s2.fields_kept_for(["#eevee"]) == (frozenset({"personal notes"}), False)
