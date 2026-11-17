"""Contract rules 9 (an update never blanks a field it has no content for)
and 10 (note type moves are followed, merge leftovers cleaned up).

Each test builds its own tiny author/user collections with Anki's API (no
sleeping: note modification times are set with SQL, note type ids are made
distinct by adding note types in a fixed order)."""

from __future__ import annotations

import os
import re
import time

import pytest
from anki.collection import (
    Collection,
    ExportAnkiPackageOptions,
    ImportAnkiPackageOptions,
    ImportAnkiPackageRequest,
)

from special_fields_by_ankoma.engine import run_import
from special_fields_by_ankoma.model import UNDO_LABEL, FieldChoice, Settings

from .conftest import NT_A, _note_by_guid


def S(keep=(), take=(), protected=(), update_note_types=True):
    fields = tuple(FieldChoice(n, True) for n in keep) + tuple(FieldChoice(n, False) for n in take)
    return Settings(fields=fields, protected_tags=tuple(protected), update_note_types=update_note_types)


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


def fields_of(col, guid):
    n = g(col, guid)
    return dict(zip(n.keys(), n.fields))


# ---------------------------------------------------------------------------
# Rule 9 on the shared world (tests/engine/conftest.py)


def _add_user_field(col, nt_name, field, values):
    nt = col.models.by_name(nt_name)
    col.models.add_field(nt, col.models.new_field(field))
    col.models.update_dict(nt)
    col.models._clear_cache()
    notes = []
    for guid, value in values.items():
        n = g(col, guid)
        n[field] = value
        notes.append(n)
    col.update_notes(notes)


@pytest.mark.parametrize("update_note_types", [True, False])
def test_rule9_user_added_field_survives_when_unlisted(user_col, world, update_note_types):
    """The user added "My Mnemonic" to note type A and filled it on A1 and
    A3. It is not in the settings and the update has no such field: every
    updated note keeps its value."""
    col = user_col
    _add_user_field(col, NT_A, "My Mnemonic", {"A1": "MINE m1", "A3": "MINE m3"})
    res = run_import(col, world["paths"]["v2"],
                     S(keep=("Personal Notes",), take=("Text", "Header", "Extra"),
                       update_note_types=update_note_types))
    assert g(col, "A1")["My Mnemonic"] == "MINE m1"
    assert g(col, "A3")["My Mnemonic"] == "MINE m3"
    assert g(col, "A2")["My Mnemonic"] == ""
    assert g(col, "A5")["My Mnemonic"] == ""  # new note: nothing to restore
    assert g(col, "A1")["Text"].startswith("A1 {{c1::v2}}")  # the rest still updates
    # PN on A1 and B1 (kept) + My Mnemonic on A1 and A3 (rule 9)
    assert res.fields_kept == 4
    assert res.notes_with_fields_kept == 3  # A1, A3, B1


def test_rule9_unlisted_field_with_update_content_takes_the_update(user_col, world):
    """Extra is not listed; the update has content for it: the user's
    edit on B1 is replaced like any other content."""
    col = user_col
    res = run_import(col, world["paths"]["v2"], S(keep=("Personal Notes",)))
    assert g(col, "B1")["Extra"] == "E1 v2"
    assert g(col, "A1")["Extra"] == "E1 v2"
    assert res.fields_kept == 2  # Personal Notes on A1 and B1 only


def test_rule9_listed_take_field_is_blanked_when_update_is_empty(user_col, world):
    """Personal Notes listed as "Take the update's": the update's empty
    value wins, even though the update has no content for it anywhere."""
    col = user_col
    _add_user_field(col, NT_A, "My Mnemonic", {"A1": "MINE m1"})
    res = run_import(col, world["paths"]["v2"], S(take=("Personal Notes", "my mnemonic")))
    assert g(col, "A1")["Personal Notes"] == "" and g(col, "B1")["Personal Notes"] == ""
    assert g(col, "A1")["My Mnemonic"] == ""
    assert res.fields_kept == 0 and res.notes_with_fields_kept == 0


def test_rule9_counts_with_nothing_listed(user_col, world):
    col = user_col
    res = run_import(col, world["paths"]["v2"], S())
    # Personal Notes: no content in the update for A or B -> A1, B1 put back
    assert g(col, "A1")["Personal Notes"] == "mine A1"
    assert g(col, "B1")["Personal Notes"] == "mine B1"
    # Header/Text/Extra have update content -> the user's edits are replaced
    assert g(col, "A1")["Header"] == "H1 v2" and g(col, "B1")["Text"] == "B1 v2"
    assert res.fields_kept == 2 and res.notes_with_fields_kept == 2


# ---------------------------------------------------------------------------
# Small worlds built per test


def _new_nt(col, name, fields, cloze=False, css=None):
    mm = col.models
    nt = mm.new(name)
    if cloze:
        nt["type"] = 1
    for f in fields:
        mm.add_field(nt, mm.new_field(f))
    t = mm.new_template("Cloze" if cloze else "Card 1")
    if cloze:
        t["qfmt"] = "{{cloze:%s}}" % fields[1]
        t["afmt"] = "{{cloze:%s}}<br>{{%s}}" % (fields[1], fields[-1])
    else:
        t["qfmt"] = "{{%s}}<br>{{%s}}" % (fields[0], fields[1])
        t["afmt"] = "{{FrontSide}}<hr id=answer>{{%s}}" % fields[-1]
    mm.add_template(nt, t)
    nt["css"] = css or ".card { color: black; } /* %s */" % name
    mm.add(nt)
    time.sleep(0.002)  # distinct note type ids
    return mm.by_name(name)


def _add(col, nt_name, deck, guid, values, tags=()):
    note = col.new_note(col.models.by_name(nt_name))
    for k, v in values.items():
        note[k] = v
    note.tags = list(tags)
    note.guid = guid
    col.add_note(note, col.decks.id(deck))
    return note


def _export(col, path):
    col.export_anki_package(
        out_path=path,
        options=ExportAnkiPackageOptions(with_scheduling=False, with_deck_configs=False,
                                         with_media=True, legacy=False),
        limit=None,
    )
    return path


def _stock_import(col, path):
    col.import_anki_package(ImportAnkiPackageRequest(package_path=path, options=ImportAnkiPackageOptions()))


def _review_everything(col):
    for cid in sorted(col.db.list("select id from cards")):
        card = col.get_card(cid)
        card.start_timer()
        col.sched.answerCard(card, 3)


def _move(col, guid, to_name):
    note = g(col, guid)
    info = col.models.change_notetype_info(old_notetype_id=note.mid,
                                           new_notetype_id=col.models.by_name(to_name)["id"])
    req = info.input
    req.note_ids.extend([note.id])
    col.models.change_notetype_of_notes(req)
    col.models._clear_cache()


AP = ["Header", "Text", "Extra", "Personal Notes"]
MI = ["Header", "Text", "Images", "Extra", "Personal Notes"]
NEW = ["Header", "Text", "Images", "Extra", "Personal Notes", "Pearls"]
MINE = ["Header", "Text", "Extra", "Personal Notes", "Own"]

# scheduling columns of a card (everything but mod/usn, which a note type
# change always bumps)
CARD_SCHED = "id, nid, did, ord, type, queue, due, ivl, factor, reps, lapses, left, odue, odid, flags, data"


def _build(tmp, kind, cloze):
    """kind: existing | new | user | samename. Returns (user col, v2 path, info)."""
    os.makedirs(tmp, exist_ok=True)
    a = Collection(os.path.join(tmp, "author.anki2"))
    u = None
    info = {}
    if kind == "samename":
        _new_nt(a, "AP", AP, cloze)
        _add(a, "AP", "Rel", "aaa", {"Header": "H aaa v1", "Text": "{{c1::T aaa}} v1"}, ["rel::v1"])
        a.db.execute("update notes set mod=1000000")
        u = Collection(os.path.join(tmp, "user.anki2"))
        _new_nt(u, "AP", AP, cloze)  # same name, its own id
        _add(u, "AP", "Rel", "aaa", {"Header": "H aaa v1", "Text": "{{c1::T aaa}} v1"}, ["rel::v1"])
        _add(u, "AP", "Mine", "ddd", {"Header": "my own note", "Text": "{{c1::ddd}} text"}, ["mine"])
        info["moved"] = ["aaa"]
        info["target"] = None  # the file's AP, added under another name
        info["others"] = ["ddd"]
    else:
        _new_nt(a, "AP", AP, cloze)
        _new_nt(a, "MI", MI, cloze)
        for guid, nt in (("aaa", "AP"), ("bbb", "AP"), ("ccc", "MI")):
            _add(a, nt, "Rel", guid, {"Header": "H %s v1" % guid, "Text": "{{c1::T %s}} v1" % guid}, ["rel::v1"])
        a.db.execute("update notes set mod=1000000")
        v1 = _export(a, os.path.join(tmp, "v1.apkg"))
        time.sleep(0.01)
        u = Collection(os.path.join(tmp, "user.anki2"))
        _stock_import(u, v1)
        _add(u, "MI", "Mine", "ddd", {"Header": "my own MI note", "Text": "{{c1::ddd}} text"}, ["mine"])
        info["others"] = ["ddd"]
        if kind == "user":
            _new_nt(u, "Mine", MINE, cloze)
            _move(u, "bbb", "Mine")
            _add(u, "Mine", "Mine", "own1", {"Header": "own", "Text": "{{c1::own}}", "Own": "own data"}, ["mine"])
            n = g(u, "bbb")
            n["Own"] = "MY OWN bbb"
            u.update_note(n)
            info["others"].append("own1")
            info["moved"] = ["bbb"]
            info["target"] = "AP"
        else:
            info["moved"] = ["aaa"]
            info["target"] = "NEW" if kind == "new" else "MI"
        # a field the user added themselves whose name really ends with "+"
        # (same base name as a real field, empty everywhere): it existed
        # before the import, so it must survive
        mi = u.models.by_name("MI")
        u.models.add_field(mi, u.models.new_field("Extra+"))
        u.models.update_dict(mi)
        u.models._clear_cache()
    for nid in u.find_notes(""):
        n = u.get_note(nid)
        n["Personal Notes"] = "MINE " + n.guid
        n.tags = list(n.tags) + ["#edited"]
        u.update_note(n)
    _review_everything(u)
    u.db.execute("update notes set mod=3000000")

    # author's v2
    if kind in ("existing", "new"):
        if kind == "new":
            _new_nt(a, "NEW", NEW, cloze)
        _move(a, "aaa", info["target"])
    for nid in a.find_notes(""):
        n = a.get_note(nid)
        n["Text"] = n["Text"].replace("v1", "v2")
        n["Extra"] = "E %s v2" % n.guid
        n.tags = ["rel::v2"]
        a.update_note(n)
    a.db.execute("update notes set mod=2000000")
    v2 = _export(a, os.path.join(tmp, "v2.apkg"))
    a.close()
    return u, v2, info


def _plus_fields(col):
    return {(nt["name"], f["name"]) for nt in col.models.all() for f in nt["flds"] if f["name"].strip().endswith("+")}


def _looks(col):
    out = {}
    for nt in col.models.all():
        out[nt["id"]] = (nt["css"], [(t.get("id"), t["name"], t["qfmt"], t["afmt"]) for t in nt["tmpls"]])
    return out


@pytest.mark.parametrize("cloze", [False, True], ids=["standard", "cloze"])
@pytest.mark.parametrize("kind", ["existing", "new", "user", "samename"])
@pytest.mark.parametrize("update_note_types", [True, False], ids=["styling-update", "styling-keep"])
def test_rule10_note_type_moves_are_followed_and_cleaned(tmp_path, kind, cloze, update_note_types):
    col, v2, info = _build(str(tmp_path), kind, cloze)
    try:
        _check_move(col, v2, info, kind, cloze, update_note_types)
    finally:
        col.close()


def _check_move(col, v2, info, kind, cloze, update_note_types):
    col.models._clear_cache()
    # one last undoable user action that must stay on top after an undo
    n = g(col, info["others"][0])
    n["Extra"] = "my last edit"
    col.update_note(n)
    prior = col.undo_status()
    before = dump(col)
    before_looks = _looks(col)
    before_plus = _plus_fields(col)
    before_notes = {guid: (fields_of(col, guid), sorted(g(col, guid).tags)) for guid in
                    [x[0] for x in col.db.all("select guid from notes")]}
    before_cards = {r[0]: r for r in col.db.all("select %s from cards" % CARD_SCHED)}
    before_cards_per_note = dict(col.db.all("select n.guid, count() from cards c join notes n on n.id=c.nid group by n.guid"))
    before_mids = dict(col.db.all("select guid, mid from notes"))

    res = run_import(col, v2, S(keep=("Personal Notes",), take=("Header", "Text"),
                                protected=("#edited",), update_note_types=update_note_types))
    col.models._clear_cache()

    in_file = sorted(g_ for g_ in before_notes if g_ not in info["others"])
    # --- every note of the file: the update's content, user's kept value in
    # the properly named field, on the file's note type
    for guid in in_file:
        f = fields_of(col, guid)
        assert f["Personal Notes"] == "MINE " + guid, (guid, f)
        assert f["Extra"] == "E %s v2" % guid, (guid, f)
        assert f["Text"] == "{{c1::T %s}} v2" % guid, (guid, f)
        assert f["Header"] == "H %s v1" % guid, (guid, f)
        assert "#edited" in g(col, guid).tags and "rel::v2" in g(col, guid).tags
    for guid in info["moved"]:
        nt = g(col, guid).note_type()
        if info["target"]:
            assert nt["name"] == info["target"], guid
        else:  # samename: the file's own note type, not the user's
            assert g(col, guid).mid != before_mids[guid]
            assert nt["name"].startswith("AP")
        if kind == "user":
            assert fields_of(col, guid).get("Own") == "MY OWN bbb"  # carried over, not lost
    # --- no "+" leftovers, a real user "+" field survives
    assert _plus_fields(col) == before_plus
    if kind != "samename":
        assert ("MI", "Extra+") in _plus_fields(col)
    # --- other notes untouched (content and tags)
    for guid in info["others"]:
        assert (fields_of(col, guid), sorted(g(col, guid).tags)) == before_notes[guid], guid
    # --- every existing card still there with its scheduling, history and
    # deck; no extra cards on existing notes
    after_cards = {r[0]: r for r in col.db.all("select %s from cards" % CARD_SCHED)}
    for cid, row in before_cards.items():
        assert cid in after_cards, "card %s lost" % cid
        assert after_cards[cid][2:] == row[2:], (cid, row, after_cards[cid])
    assert col.db.all("select * from revlog order by id") == before["revlog"]
    after_per_note = dict(col.db.all("select n.guid, count() from cards c join notes n on n.id=c.nid group by n.guid"))
    for guid, count in before_cards_per_note.items():
        assert after_per_note[guid] == count, (guid, count, after_per_note[guid])
    # --- templates reference real fields only
    for nt in col.models.all():
        names = {f["name"] for f in nt["flds"]}
        for t in nt["tmpls"]:
            for ref in re.findall(r"\{\{[#/^]?([^{}]*)\}\}", t["qfmt"] + t["afmt"]):
                name = ref.rpartition(":")[2].strip()
                assert name in names or name in ("FrontSide", "Tags", "Deck", "Subdeck", "Card", "Type", "CardFlag"), (
                    nt["name"], t["name"], ref)
    # --- styling switch off: pre-existing note types' templates and CSS identical
    if not update_note_types:
        after_looks = _looks(col)
        for mid, look in before_looks.items():
            if mid in after_looks:
                assert after_looks[mid] == look, mid
    # --- counters
    assert res.notes_updated == len(in_file)
    assert res.notes_added == 0
    # Personal Notes put back on every note of the file
    assert res.fields_kept == len(in_file) + (1 if kind == "user" else 0)
    assert res.notes_with_fields_kept == len(in_file)
    assert res.protected_tags_kept == len(in_file) and res.notes_with_tags_kept == len(in_file)
    # --- one undo restores every table exactly
    assert col.undo_status().undo == UNDO_LABEL
    col.undo()
    assert dump(col) == before
    after_undo = col.undo_status()
    assert after_undo.undo == prior.undo


def test_rule10_plus_field_with_content_is_left_in_place(tmp_path):
    """The author's own note type has a field literally named "Header+" with
    content (new to the user, so it "did not exist before the import" and
    looks like a merge leftover): a field that holds content on any note is
    never removed, and the import still finishes as one undo step."""
    col, v2, info = _build(str(tmp_path), "existing", cloze=False)
    try:
        # rewrite v2 so the moved note's file content has text in a field that
        # will clash: add "Header+" to the author's MI with content
        a = Collection(os.path.join(str(tmp_path), "author.anki2"))
        mi = a.models.by_name("MI")
        a.models.add_field(mi, a.models.new_field("Header+"))
        a.models.update_dict(mi)
        a.models._clear_cache()
        n = g(a, "ccc")
        n["Header+"] = "author content in a plus field"
        a.update_note(n)
        a.db.execute("update notes set mod=2100000")
        v2b = _export(a, os.path.join(str(tmp_path), "v2b.apkg"))
        a.close()
        before = dump(col)
        res = run_import(col, v2b, S(keep=("Personal Notes",)))
        col.models._clear_cache()
        assert g(col, "ccc")["Header+"] == "author content in a plus field"
        # the author's "Header+" and the user's own "Extra+" stay; the empty
        # merge leftovers ("Header++", "Text+", ...) go
        assert [f["name"] for f in col.models.by_name("MI")["flds"]] == MI + ["Extra+", "Header+"]
        assert g(col, "ddd")["Header"] == "my own MI note" and g(col, "ddd")["Personal Notes"] == "MINE ddd"
        assert [c.ord for c in g(col, "aaa").cards()] == [0]
        assert g(col, "aaa").note_type()["name"] == "MI"
        assert g(col, "aaa")["Personal Notes"] == "MINE aaa"
        assert res.notes_updated == 3
        assert col.undo_status().undo == UNDO_LABEL
        col.undo()
        assert dump(col) == before
    finally:
        col.close()


def test_rule10_normal_import_is_unaffected(user_col, world):
    """No note changes note type: nothing is cleaned, every note type keeps
    its fields."""
    col = user_col
    before = {nt["name"]: [f["name"] for f in nt["flds"]] for nt in col.models.all()}
    run_import(col, world["paths"]["v2"], S(keep=("Personal Notes",)))
    col.models._clear_cache()
    after = {nt["name"]: [f["name"] for f in nt["flds"]] for nt in col.models.all()}
    assert after == before
    assert g(col, "A1")["Personal Notes"] == "mine A1"


def test_failed_import_cannot_be_redone(user_col, world, monkeypatch):
    """After a roll-back the undone half-import must not be left on the redo
    stack (Redo would bring back the update without the user's kept
    fields); the user's own last step stays on top."""
    col = user_col
    b2 = g(col, "B2")
    b2["Personal Notes"] = "last user action"
    col.update_note(b2)
    prior = col.undo_status()
    before = dump(col)

    def boom(notes):
        raise RuntimeError("restore failed")

    monkeypatch.setattr(col, "update_notes", boom)
    with pytest.raises(RuntimeError):
        run_import(col, world["paths"]["v2"], S(keep=("Personal Notes",)))
    monkeypatch.undo()
    assert dump(col) == before
    status = col.undo_status()
    assert status.undo == prior.undo and status.redo != UNDO_LABEL
    col.undo()  # the user's own step really is the one on top
    assert g(col, "B2")["Personal Notes"] != "last user action"
