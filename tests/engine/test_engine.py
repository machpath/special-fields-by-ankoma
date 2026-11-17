"""Engine tests: run_import on tiny synthetic decks (see conftest.py)."""

from __future__ import annotations

import pytest
from anki.collection import Collection, OpChanges

from special_fields_by_ankoma import engine
from special_fields_by_ankoma.engine import run_import
from special_fields_by_ankoma.model import UNDO_LABEL, FieldChoice, Settings

from .conftest import NT_A, NT_B, NT_C, _note_by_guid

KEEP_PN = FieldChoice("Personal Notes", True)


def S(keep=(), take=(), protected=(), update_note_types=True):
    fields = tuple(FieldChoice(n, True) for n in keep) + tuple(FieldChoice(n, False) for n in take)
    return Settings(fields=fields, protected_tags=tuple(protected), update_note_types=update_note_types)


def dump(col: Collection):
    """Everything an import could touch, row by row (ordered)."""
    out = {}
    for table in ("notes", "cards", "revlog", "notetypes", "fields", "templates",
                  "decks", "deck_config", "tags", "graves"):
        out[table] = col.db.all("select * from %s order by 1, 2" % table)
    out["config"] = col.db.all("select KEY, val from config order by KEY")
    out["scm"] = col.db.scalar("select scm from col")
    return out


def styling_rows(col: Collection, nt_name: str):
    nt = col.models.by_name(nt_name)
    rows = col.db.all("select ntid, ord, name, mtime_secs, usn, config from templates where ntid=? order by ord",
                      nt["id"])
    return nt["css"], rows


def g(col, guid):
    return _note_by_guid(col, guid)


# --- fields -------------------------------------------------------------------------------


def test_kept_fields_by_name_across_note_types(user_col, world):
    """Text is 2nd in A and 1st in B; Header exists only in A. Matching is by
    normalized name; Extra is not listed, so it takes the update."""
    col = user_col
    settings = S(keep=("  personal NOTES ", "text", "Header"), take=("Extra",))
    res = run_import(col, world["paths"]["v2"], settings)

    a1, a2, a3, b1, b2 = (g(col, x) for x in ("A1", "A2", "A3", "B1", "B2"))
    # A1: Header + Personal Notes edited by the user -> kept; Text kept (pre-import v1 value)
    assert a1["Header"] == "my header A1"
    assert a1["Personal Notes"] == "mine A1"
    assert a1["Text"] == "A1 {{c1::v1}} {{c2::two}}"
    assert a1["Extra"] == "E1 v2"
    # A2: user's Text fix kept, Header kept at v1, Extra updated
    assert a2["Text"] == "A2 {{c1::v1}} {{c2::two}} (my fix A2)"
    assert a2["Header"] == "H2 v1"
    assert a2["Extra"] == "E2 v2"
    # B1 (Text first, no Header): Text and Personal Notes kept, Extra takes update
    assert b1["Text"] == "my text B1"
    assert b1["Personal Notes"] == "mine B1"
    assert b1["Extra"] == "E1 v2"
    assert b2["Text"] == "B2 v1" and b2["Extra"] == "E2 v2"
    # Values written back: A1..A4 Header+Text (8) + A1 PN (1) + B1 Text + PN (2) + B2 Text (1)
    # (A3/A4 had Header/Text changed by the update too; PN unchanged elsewhere: "" == "")
    assert res.fields_kept == 12
    assert res.notes_with_fields_kept == 6
    assert res.notes_updated == 6


def test_take_update_overwrites_all_fields(user_col, world):
    col = user_col
    res = run_import(col, world["paths"]["v2"], S(take=("Personal Notes", "Text", "Header")))
    a1, b1 = g(col, "A1"), g(col, "B1")
    assert a1["Personal Notes"] == "" and a1["Header"] == "H1 v2" and a1["Text"].startswith("A1 {{c1::v2}}")
    assert b1["Personal Notes"] == "" and b1["Text"] == "B1 v2" and b1["Extra"] == "E1 v2"
    assert res.fields_kept == 0 and res.notes_with_fields_kept == 0


def test_only_personal_notes_kept_default_style(user_col, world):
    col = user_col
    res = run_import(col, world["paths"]["v2"], S(keep=("Personal Notes",), take=("Text", "Extra", "Header")))
    a1, a2, b1 = g(col, "A1"), g(col, "A2"), g(col, "B1")
    assert a1["Personal Notes"] == "mine A1" and a1["Header"] == "H1 v2"
    assert a2["Text"] == "A2 {{c1::v2}} {{c2::two}}"  # user's fix replaced
    assert b1["Personal Notes"] == "mine B1" and b1["Text"] == "B1 v2"
    assert res.fields_kept == 2 and res.notes_with_fields_kept == 2


def test_kept_field_followed_across_rename_by_field_id(user_col, world):
    """The author renames B's "Extra" to "Extra Info"; the user keeps "Extra".
    The value follows the field (by field config id), as Anki's merge does."""
    col = user_col
    res = run_import(col, world["paths"]["v2rename"], S(keep=("Extra",)))
    nt = col.models.by_name(NT_B)
    assert [f["name"] for f in nt["flds"]] == ["Text", "Extra Info", "Personal Notes"]
    b1, b2 = g(col, "B1"), g(col, "B2")
    assert b1["Extra Info"] == "my extra B1"
    assert b2["Extra Info"] == "E2 v1"
    assert b1["Text"] == "B1 v2"
    assert res.fields_kept >= 2


# --- tags ---------------------------------------------------------------------------------


def test_protected_tags_kept_other_tags_replaced(user_col, world):
    """No fields listed, "#edited" protected: every #edited (and sub-tag)
    stays, every other tag is replaced by the update's, fields take the
    update's content. (Rule 9: Personal Notes is not listed and the update
    has no content for it on any note, so the user's values come back.)"""
    col = user_col
    res = run_import(col, world["paths"]["v2"], S(protected=("#edited",)))
    a1, a3, b1, a2 = g(col, "A1"), g(col, "A3"), g(col, "B1"), g(col, "A2")

    # The user's spelling ("#Edited") is put back although "#edited" is protected.
    assert sorted(a1.tags) == sorted(["##REL-v2::a::t1", "#Edited", "#Edited::Images"])
    assert "personal" not in a1.tags and "#edited2" not in a1.tags
    # A3: the update already carries "#EDITED" -> nothing re-added, no duplicate
    assert len([t for t in a3.tags if t.lower() == "#edited"]) == 1
    assert sorted(b1.tags) == sorted(["##REL-v2::b", "#Edited::sub"])
    assert a2.tags == ["##REL-v2::a::t2"]
    # fields took the update's content; the field it has none for is put back
    assert a1["Header"] == "H1 v2" and b1["Text"] == "B1 v2"
    assert a1["Personal Notes"] == "mine A1" and b1["Personal Notes"] == "mine B1"
    assert res.protected_tags_kept == 3  # A1: 2, B1: 1
    assert res.notes_with_tags_kept == 2
    assert res.fields_kept == 2 and res.notes_with_fields_kept == 2  # rule 9: A1, B1


def test_protecting_a_sub_tag_only(user_col, world):
    col = user_col
    res = run_import(col, world["paths"]["v2"], S(protected=("#EDITED::images",)))
    a1, b1 = g(col, "A1"), g(col, "B1")
    assert sorted(a1.tags) == sorted(["##REL-v2::a::t1", "#Edited::Images"])
    assert b1.tags == ["##REL-v2::b"]
    assert res.protected_tags_kept == 1 and res.notes_with_tags_kept == 1


# --- note types ------------------------------------------------------------------------------


def test_update_note_types_true_replaces_templates_and_css(user_col, world):
    col = user_col
    res = run_import(col, world["paths"]["v2"], S(keep=("Personal Notes",), update_note_types=True))
    for name in (NT_A, NT_B):
        nt = col.models.by_name(name)
        assert "author v2" in nt["css"] and "USER" not in nt["css"]
        assert "<!-- author v2 -->" in nt["tmpls"][0]["qfmt"]
        assert "<!-- USER -->" not in nt["tmpls"][0]["afmt"]
    assert res.note_types_changed is False


def test_update_note_types_false_keeps_styling_byte_identical(user_col, world):
    col = user_col
    before = {n: styling_rows(col, n) for n in (NT_A, NT_B)}
    res = run_import(col, world["paths"]["v2"], S(keep=("Personal Notes",), update_note_types=False))
    assert {n: styling_rows(col, n) for n in (NT_A, NT_B)} == before
    # note content still updates
    assert g(col, "A1")["Extra"] == "E1 v2" and g(col, "A1")["Personal Notes"] == "mine A1"
    assert res.notes_updated == 6


def test_update_note_types_false_with_added_field(user_col, world):
    col = user_col
    before = {n: styling_rows(col, n) for n in (NT_A, NT_B)}
    scm = col.db.scalar("select scm from col")
    res = run_import(col, world["paths"]["v2newfield"], S(keep=("Personal Notes",), update_note_types=False))
    assert {n: styling_rows(col, n) for n in (NT_A, NT_B)} == before
    nt = col.models.by_name(NT_A)
    assert [f["name"] for f in nt["flds"]] == ["Header", "Text", "Extra", "Personal Notes", "Mnemonic"]
    a1 = g(col, "A1")
    assert a1["Mnemonic"] == "mnemonic A1"
    assert a1["Personal Notes"] == "mine A1" and a1["Extra"] == "E1 v2"
    assert g(col, "A5")["Mnemonic"] == "mnemonic A5"
    assert res.note_types_changed is True
    assert col.db.scalar("select scm from col") != scm


def test_update_note_types_true_with_added_field(user_col, world):
    col = user_col
    res = run_import(col, world["paths"]["v2newfield"], S(keep=("Personal Notes", "Header"), update_note_types=True))
    nt = col.models.by_name(NT_A)
    assert "author v2" in nt["css"] and "USER" not in nt["css"]
    a1 = g(col, "A1")
    assert a1["Mnemonic"] == "mnemonic A1"
    assert a1["Personal Notes"] == "mine A1" and a1["Header"] == "my header A1"
    assert res.note_types_changed is True


def test_styling_guard_restores_css_and_templates(user_col):
    """The guard used when update_note_types is False puts back CSS and
    template text if anything changed them (NEVER alone already does, so the
    guard is exercised directly here)."""
    col = user_col
    snap = engine._snapshot_styling(col)
    before = styling_rows(col, NT_A)
    nt = col.models.by_name(NT_A)
    nt["css"] = "changed"
    nt["tmpls"][0]["qfmt"] = "{{cloze:Text}} changed"
    col.models.update_dict(nt)
    assert engine._restore_styling(col, snap) == 1
    css, rows = styling_rows(col, NT_A)
    assert css == before[0]
    assert [(r[0], r[1], r[2], r[5]) for r in rows] == [(r[0], r[1], r[2], r[5]) for r in before[1]]
    assert engine._restore_styling(col, snap) == 0


# --- forced update, cards, decks ------------------------------------------------------------


def test_notes_edited_later_than_author_still_updated(user_col, world):
    col = user_col
    assert g(col, "B1").mod > 2_000_000  # user edit is "newer" than the release
    res = run_import(col, world["paths"]["v2"], S())
    assert g(col, "B1")["Extra"] == "E1 v2" and g(col, "B1")["Text"] == "B1 v2"
    assert g(col, "A2")["Text"] == "A2 {{c1::v2}} {{c2::two}}"
    assert res.notes_updated == 6


def test_existing_cards_deck_and_scheduling_untouched(user_col, world):
    """Imported with the author's scheduling and deck options in the file:
    existing cards, the review log and the user's deck options stay
    byte-identical; moved cards stay put; new cards land in the release deck."""
    col = user_col
    cards_before = col.db.all("select * from cards order by id")
    revlog_before = col.db.all("select * from revlog order by id")
    dconf_before = col.db.all("select * from deck_config order by id")
    assert revlog_before, "fixture should have review history"
    res = run_import(col, world["paths"]["v2sched"], S(keep=("Personal Notes",), protected=("#edited",)))
    old_ids = {r[0] for r in cards_before}
    assert [r for r in col.db.all("select * from cards order by id") if r[0] in old_ids] == cards_before
    assert col.db.all("select * from revlog order by id") == revlog_before
    assert col.db.all("select * from deck_config order by id") == dconf_before
    for cid in world["moved"]:
        assert col.get_card(cid).did == world["my_deck"]
    a5 = g(col, "A5")
    new_cards = [col.get_card(c) for c in col.card_ids_of_note(a5.id)]
    assert new_cards and all(col.decks.name(c.did) == "Rel::A" for c in new_cards)
    assert all(c.type == 0 for c in new_cards)  # new, no author scheduling
    assert res.notes_added == 1


def test_brand_new_deck_into_existing_collection(user_col, world):
    col = user_col
    before_notes = col.db.all("select * from notes order by id")
    res = run_import(col, world["paths"]["fresh"], S(keep=("Personal Notes",), protected=("#edited",)))
    assert res.notes_in_file == 2 and res.notes_added == 2
    assert res.notes_updated == 0 and res.notes_skipped == 0
    assert res.fields_kept == 0 and res.protected_tags_kept == 0
    assert col.models.by_name(NT_C) is not None
    nids = col.find_notes('"deck:Fresh::Deck"')
    assert len(nids) == 2
    assert col.get_note(nids[0])["Personal Notes"] == "author pn"
    old_ids = {r[0] for r in before_notes}
    assert [r for r in col.db.all("select * from notes order by id") if r[0] in old_ids] == before_notes


def test_brand_new_deck_into_empty_collection(empty_col, world):
    col = empty_col
    res = run_import(col, world["paths"]["v1"], S(keep=("Personal Notes",)))
    assert res.notes_in_file == 7 and res.notes_added == 7 and res.notes_updated == 0
    assert col.note_count() == 7
    assert col.undo_status().undo == UNDO_LABEL


# --- nothing to restore -------------------------------------------------------------------


def test_nothing_to_restore_still_forces_import(user_col, world, monkeypatch):
    """Nothing kept, nothing protected, and the update has content for every
    field it does not list (Header, Extra): nothing is written back, but the
    forced import still runs. (Rules 9 and 10 need the snapshot whatever the
    settings, so the restore pass always runs; it just writes nothing.)"""
    col = user_col
    settings = S(take=("Personal Notes", "Text"), protected=("  ",))
    saved = []
    real_update = col.update_notes
    monkeypatch.setattr(col, "update_notes", lambda notes: saved.append(list(notes)) or real_update(notes))
    res = run_import(col, world["paths"]["v2"], settings)
    assert saved == []
    assert res.notes_updated == 6 and res.fields_kept == 0 and res.protected_tags_kept == 0
    assert g(col, "A1")["Personal Notes"] == "" and g(col, "B1")["Extra"] == "E1 v2"


def test_snapshot_holds_every_note_as_stored(user_col):
    """Rules 9 and 10 need every field value and note type of every note,
    whatever the settings: the snapshot is one pass over the notes table
    (contract: "the snapshot must now hold every field value of every
    existing note"), plus note type field/template ids and card ids."""
    col = user_col
    snap = engine._snapshot(col)
    rows = col.db.all("select id, mid, flds, tags from notes")
    assert snap.notes == {nid: (mid, flds, tags) for nid, mid, flds, tags in rows}
    assert snap.card_ids == set(col.db.list("select id from cards"))
    nt = col.models.by_name(NT_A)
    assert [n for _fid, n in snap.fields[nt["id"]]] == ["header", "text", "extra", "personal notes"]
    assert snap.templates[nt["id"]] == {t["id"] for t in nt["tmpls"]}


# --- undo ----------------------------------------------------------------------------------


def test_one_undo_step_restores_everything(user_col, world):
    col = user_col
    b2 = g(col, "B2")
    b2["Personal Notes"] = "last user action"
    col.update_note(b2)
    prior = col.undo_status().undo
    before = dump(col)
    res = run_import(col, world["paths"]["v2newfield"],
                     S(keep=("Personal Notes", "Header"), protected=("#edited",), update_note_types=False))
    assert res.fields_kept > 0 and res.protected_tags_kept > 0 and res.notes_added == 1
    status = col.undo_status()
    assert status.undo == UNDO_LABEL
    col.undo()
    col.models._clear_cache()
    assert col.undo_status().undo == prior  # the user's own action is next
    assert dump(col) == before


def test_changes_is_opchanges(user_col, world):
    res = run_import(user_col, world["paths"]["v2"], S(keep=("Personal Notes",)))
    assert isinstance(res.changes, OpChanges)
    # the import changed notes and added cards (A5 is new), and aqt refreshes
    # the browser and the study screen from these flags
    assert res.changes.note is True and res.changes.card is True
    assert res.changes.browser_table is True


# --- counters ------------------------------------------------------------------------------


def test_every_counter(user_col, world):
    col = user_col
    res = run_import(col, world["paths"]["v2"],
                     S(keep=("Personal Notes", "Header"), take=("Text",), protected=("#edited",)))
    assert res.notes_in_file == 8          # A1-A5, B1-B3
    assert res.notes_added == 1            # A5
    assert res.notes_updated == 6          # A1-A4, B1, B2
    assert res.notes_skipped == 1          # B3: identical modification time
    assert res.skip_reasons == {"unchanged": 1}
    assert res.notes_in_file == res.notes_added + res.notes_updated + res.notes_skipped
    # Header on A1-A4 (4: the update changed each) + Personal Notes on A1, B1 (2)
    assert res.fields_kept == 6
    assert res.notes_with_fields_kept == 5  # A1, A2, A3, A4, B1
    assert res.protected_tags_kept == 3     # A1: #Edited, #Edited::Images; B1: #Edited::sub
    assert res.notes_with_tags_kept == 2
    assert res.note_types_changed is False
    assert set(res.seconds) >= {"snapshot", "import", "restore", "total"}
    assert res.summary_rows()[0] == ("Notes updated", "6")


def test_reimport_same_release_skips_unchanged(user_col, world):
    col = user_col
    run_import(col, world["paths"]["v2"], S(keep=("Personal Notes",)))
    res = run_import(col, world["paths"]["v2"], S(keep=("Personal Notes",)))
    # notes we restored got a new mtime, so they are "updated" again; the rest are unchanged
    assert res.notes_in_file == 8 and res.notes_added == 0
    assert res.notes_updated == 2  # A1, B1 (Personal Notes written back last time)
    assert res.skip_reasons == {"unchanged": 6}
    assert g(col, "A1")["Personal Notes"] == "mine A1"


# --- the user's own import preferences ------------------------------------------------------


def test_anki_import_preferences_unchanged(user_col, empty_col, world):
    for col in (user_col, empty_col):
        before = {k: col.get_config(k, "MISSING") for k in engine.IMPORT_PREF_KEYS}
        run_import(col, world["paths"]["v2"], S(keep=("Personal Notes",)))
        assert {k: col.get_config(k, "MISSING") for k in engine.IMPORT_PREF_KEYS} == before
    assert before == {k: "MISSING" for k in engine.IMPORT_PREF_KEYS}  # empty_col never had them


# --- errors ------------------------------------------------------------------------------------


@pytest.mark.parametrize("kind", ["missing", "corrupt"])
def test_import_raises_collection_unchanged(user_col, tmp_path, kind):
    col = user_col
    b2 = g(col, "B2")
    b2["Personal Notes"] = "last user action"
    col.update_note(b2)
    prior = col.undo_status().undo
    before = dump(col)
    path = str(tmp_path / "bad.apkg")
    if kind == "corrupt":
        with open(path, "wb") as f:
            f.write(b"this is not a zip file")
    with pytest.raises(Exception):
        run_import(col, path, S(keep=("Personal Notes",), protected=("#edited",)))
    assert dump(col) == before
    assert col.undo_status().undo == prior


def test_failure_after_native_import_rolls_back(user_col, world, monkeypatch):
    col = user_col
    before = dump(col)

    def boom(notes):
        raise RuntimeError("restore failed")

    monkeypatch.setattr(col, "update_notes", boom)
    with pytest.raises(RuntimeError, match="restore failed"):
        run_import(col, world["paths"]["v2newfield"], S(keep=("Personal Notes",), update_note_types=False))
    col.models._clear_cache()
    assert dump(col) == before


def test_undo_in_collection_without_saved_import_preferences(empty_col, world):
    """Covers the path where Anki's import-preference keys did not exist before
    (they are removed again) and the whole step is undone."""
    col = empty_col
    before = dump(col)
    run_import(col, world["paths"]["v1"], S(keep=("Personal Notes",), protected=("#edited",)))
    assert col.undo_status().undo == UNDO_LABEL
    col.undo()
    col.models._clear_cache()
    assert dump(col) == before
