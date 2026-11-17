"""The two import switches: "Import learning progress" (`import_scheduling`
-> Anki's `with_scheduling`) and "Import deck presets"
(`import_deck_presets` -> `with_deck_configs`), and rule 12 G3 with them.

Each test builds tiny author/user collections with Anki's own API. What
Anki does with these options (found by experiment, identical on 25.02.7 to
26.11b1):

* scheduling: a card that already exists keeps its own scheduling and
  review log, and none of the file's review log rows for it are imported;
  a card new to the collection arrives with the file's scheduling and its
  review log rows. Off: new cards arrive as new, no rows are added.
* deck presets: a preset whose id is already in the collection is never
  changed (the Default preset included); a preset only in the file is
  added; a deck in the file (existing or new) is switched to the preset the
  file gives it, unless that is the Default preset. Off: no preset is added
  and no deck changes its preset.
"""

from __future__ import annotations

import os
import time

import pytest
from anki.collection import (
    Collection,
    DeckIdLimit,
    ExportAnkiPackageOptions,
    ImportAnkiPackageOptions,
    ImportAnkiPackageRequest,
)

from special_fields_by_ankoma import engine
from special_fields_by_ankoma.config import default_settings
from special_fields_by_ankoma.engine import MergeRepairError, run_import
from special_fields_by_ankoma.model import UNDO_LABEL, FieldChoice, Settings

from . import test_rules_9_10 as r910
from .test_rules_9_10 import dump, g

FIELDS = ["Front", "Back", "Personal Notes"]
# every card column but mod/usn
CARD_SCHED = "id, nid, did, ord, type, queue, due, ivl, factor, reps, lapses, left, odue, odid, flags, data"


def S(sched=False, presets=False, keep=("Personal Notes",)):
    return Settings(fields=tuple(FieldChoice(n, True) for n in keep), protected_tags=(),
                    update_note_types=True, import_scheduling=sched, import_deck_presets=presets)


def _review(col, cids=None):
    for cid in sorted(cids if cids is not None else col.db.list("select id from cards")):
        card = col.get_card(cid)
        card.start_timer()
        col.sched.answerCard(card, 3)


def _add(col, deck, guid, front):
    note = col.new_note(col.models.by_name("SW"))
    note["Front"] = front
    note["Back"] = "back " + guid
    note.guid = guid
    col.add_note(note, col.decks.id(deck))
    return note


def _preset(col, name, per_day):
    pid = col.decks.add_config_returning_id(name)
    conf = col.decks.get_config(pid)
    conf["new"]["perDay"] = per_day
    col.decks.update_config(conf)
    return pid


def _use(col, deck, pid):
    d = col.decks.get(col.decks.id(deck))
    d["conf"] = pid
    col.decks.save(d)


def _conf_of(col, deck):
    return col.decks.get(col.decks.id(deck))["conf"]


def _export(col, path, sched):
    col.export_anki_package(
        out_path=path,
        options=ExportAnkiPackageOptions(with_scheduling=sched, with_deck_configs=sched,
                                         with_media=True, legacy=False),
        limit=DeckIdLimit(col.decks.id("Sw")),
    )
    return path


def _world(tmp):
    """Author: note type "SW", decks Sw::One (preset SharedP), Sw::Two
    (Default), notes n1-n3; v1 exported with presets but no scheduling.
    The user imports v1 with presets, edits SharedP (55 new cards a day),
    moves Sw::Two to an own preset MineP and Sw::One to MineP too, fills
    Personal Notes and reviews n1 twice (its own history). The author then
    adds AuthorP for Sw::One, changes Default, adds n4, reviews every card
    and exports v2 with scheduling and presets."""
    os.makedirs(tmp, exist_ok=True)
    a = Collection(os.path.join(tmp, "author.anki2"))
    mm = a.models
    m = mm.new("SW")
    for f in FIELDS:
        mm.add_field(m, mm.new_field(f))
    t = mm.new_template("Card 1")
    t["qfmt"] = "{{Front}}"
    t["afmt"] = "{{FrontSide}}<hr id=answer>{{Back}}"
    mm.add_template(m, t)
    mm.add(m)
    shared = _preset(a, "SharedP", 44)
    _use(a, "Sw::One", shared)
    a.decks.id("Sw::Two")
    for i, deck in ((1, "Sw::One"), (2, "Sw::One"), (3, "Sw::Two")):
        _add(a, deck, "n%d" % i, "front n%d" % i)
    a.db.execute("update notes set mod=1000000")
    v1 = os.path.join(tmp, "v1.apkg")
    a.export_anki_package(out_path=v1, options=ExportAnkiPackageOptions(
        with_scheduling=False, with_deck_configs=True, with_media=True, legacy=False),
        limit=DeckIdLimit(a.decks.id("Sw")))
    time.sleep(0.01)

    u = Collection(os.path.join(tmp, "user.anki2"))
    u.import_anki_package(ImportAnkiPackageRequest(
        package_path=v1, options=ImportAnkiPackageOptions(with_deck_configs=True)))
    conf = u.decks.get_config(shared)
    conf["new"]["perDay"] = 55
    u.decks.update_config(conf)
    mine = _preset(u, "MineP", 12)
    _use(u, "Sw::One", mine)
    _use(u, "Sw::Two", mine)
    for nid in u.find_notes(""):
        n = u.get_note(nid)
        n["Personal Notes"] = "MINE " + n.guid
        u.update_note(n)
    n1_cards = list(g(u, "n1").card_ids())
    _review(u, n1_cards)
    _review(u, n1_cards)
    u.db.execute("update notes set mod=3000000")

    author_p = _preset(a, "AuthorP", 33)
    _use(a, "Sw::One", author_p)
    default = a.decks.get_config(1)
    default["new"]["perDay"] = 77
    a.decks.update_config(default)
    _add(a, "Sw::Two", "n4", "front n4")
    for nid in a.find_notes(""):
        n = a.get_note(nid)
        n["Back"] = n["Back"] + " v2"
        a.update_note(n)
    a.db.execute("update notes set mod=2000000")
    _review(a)
    v2 = _export(a, os.path.join(tmp, "v2.apkg"), sched=True)
    author_rows = {g(a, "n%d" % i).guid: a.db.scalar(
        "select count() from revlog where cid in (select id from cards where nid=?)", g(a, "n%d" % i).id)
        for i in (1, 2, 3, 4)}
    a.close()
    # the user's own last step, which must stay under ours
    n = g(u, "n2")
    n["Back"] = "my last edit"
    u.update_note(n)
    return u, v2, {"shared": shared, "author_p": author_p, "mine": mine, "author_rows": author_rows}


@pytest.fixture
def sworld(tmp_path):
    u, v2, info = _world(str(tmp_path))
    yield u, v2, info
    u.close()


def _presets(col):
    return {c["id"]: (c["name"], c["new"]["perDay"]) for c in col.decks.all_config()}


# ---------------------------------------------------------------------------
# defaults


def test_both_switches_off_by_default():
    d = default_settings()
    assert d.import_scheduling is False and d.import_deck_presets is False
    assert Settings().import_scheduling is False and Settings().import_deck_presets is False


def test_switches_passed_to_anki(sworld, monkeypatch):
    u, v2, _info = sworld
    seen = []
    real = u.import_anki_package

    def spy(req):
        seen.append((req.options.with_scheduling, req.options.with_deck_configs))
        return real(req)

    monkeypatch.setattr(u, "import_anki_package", spy)
    for sched, presets in ((False, False), (True, False), (False, True), (True, True)):
        run_import(u, v2, S(sched, presets))
        u.undo()
    assert seen == [(False, False), (True, False), (False, True), (True, True)]


# ---------------------------------------------------------------------------
# learning progress


def test_scheduling_off_new_card_is_new_no_review_rows(sworld):
    u, v2, info = sworld
    before = dump(u)
    res = run_import(u, v2, S())
    assert res.learning_progress_imported is False and res.cards_with_progress == 0
    n4 = g(u, "n4")
    assert [(c.type, c.queue, c.ivl, c.reps) for c in n4.cards()] == [(0, 0, 0, 0)]
    assert u.db.all("select * from revlog order by id") == before["revlog"]
    # every existing card untouched
    now = [tuple(r) for r in u.db.all("select %s from cards where nid != ? order by id" % CARD_SCHED, n4.id)]
    assert now == [r for r in _cards_before(before) if r[1] != n4.id]
    assert u.db.all("select * from deck_config order by id") == before["deck_config"]


def _cards_before(before):
    # CARD_SCHED columns from a dump()'s full cards rows (schema order:
    # id nid did ord mod usn type queue due ivl factor reps lapses left odue odid flags data)
    return sorted((r[0], r[1], r[2], r[3], r[6], r[7], r[8], r[9], r[10], r[11], r[12], r[13], r[14], r[15],
                   r[16], r[17]) for r in before["cards"])


def test_scheduling_on_existing_cards_keep_own_progress_new_card_arrives_with_it(sworld):
    u, v2, info = sworld
    before = dump(u)
    old_cards = {r[0]: r for r in _cards_before(before)}
    res = run_import(u, v2, S(sched=True))
    assert res.learning_progress_imported is True
    # existing cards: same scheduling, same review log (the author reviewed
    # n1-n3 too; none of those rows came in)
    now = {r[0]: tuple(r) for r in u.db.all("select %s from cards" % CARD_SCHED)}
    for cid, row in old_cards.items():
        assert now[cid] == row, cid
    old_ids = {r[0] for r in before["revlog"]}
    rows = u.db.all("select * from revlog order by id")
    assert [r for r in rows if r[0] in old_ids] == before["revlog"]
    added = [r for r in rows if r[0] not in old_ids]
    # n4 is new to the collection: it arrives reviewed, with its history
    n4 = g(u, "n4")
    (card,) = n4.cards()
    assert card.type != 0 and card.queue != 0 and card.reps == 1  # learning, as the author left it
    assert added and {r[1] for r in added} == {card.id}
    assert len(added) == info["author_rows"]["n4"]
    assert res.cards_with_progress == 1
    # the other switch is off: presets untouched
    assert u.db.all("select * from deck_config order by id") == before["deck_config"]
    # kept field still kept
    assert g(u, "n1")["Personal Notes"] == "MINE n1" and g(u, "n1")["Back"] == "back n1 v2"


def test_scheduling_on_file_without_progress_new_cards_new(tmp_path):
    """A file exported without scheduling: nothing to import, the count is 0."""
    u, _v2, _info = _world(str(tmp_path))
    try:
        a = Collection(os.path.join(str(tmp_path), "author.anki2"))
        v2n = _export(a, os.path.join(str(tmp_path), "v2n.apkg"), sched=False)
        a.close()
        revlog = u.db.all("select * from revlog order by id")
        res = run_import(u, v2n, S(sched=True))
        assert res.learning_progress_imported is True and res.cards_with_progress == 0
        assert [c.type for c in g(u, "n4").cards()] == [0]
        assert u.db.all("select * from revlog order by id") == revlog
    finally:
        u.close()


# ---------------------------------------------------------------------------
# deck presets


def test_presets_off_nothing_changes(sworld):
    u, v2, info = sworld
    before = dump(u)
    run_import(u, v2, S(sched=True))
    assert u.db.all("select * from deck_config order by id") == before["deck_config"]
    assert _conf_of(u, "Sw::One") == info["mine"] and _conf_of(u, "Sw::Two") == info["mine"]
    assert _conf_of(u, "Sw") == 1


def test_presets_on_adds_missing_switches_decks_never_changes_existing(sworld):
    u, v2, info = sworld
    before = _presets(u)
    before_rows = {r[0]: r for r in dump(u)["deck_config"]}
    run_import(u, v2, S(presets=True))
    after = _presets(u)
    # existing presets never change: the user's SharedP (55, the file has
    # 44), Default (the file has 77) and MineP
    after_rows = {r[0]: r for r in dump(u)["deck_config"]}
    for pid, row in before_rows.items():
        assert after_rows[pid] == row, pid
    assert after[info["shared"]] == ("SharedP", 55) and after[1][1] == before[1][1] != 77
    # the preset only the file has is added, with the file's values and id
    assert set(after) - set(before) == {info["author_p"]}
    assert after[info["author_p"]] == ("AuthorP", 33)
    # a deck the file gives a non-default preset is switched to it, even
    # one the user had moved to their own preset; a deck the file has on
    # Default keeps the user's preset
    assert _conf_of(u, "Sw::One") == info["author_p"]
    assert _conf_of(u, "Sw::Two") == info["mine"]
    assert _conf_of(u, "Sw") == 1
    # scheduling switch off: no review rows added
    assert [c.type for c in g(u, "n4").cards()] == [0]


# ---------------------------------------------------------------------------
# one undo step, Anki's own import preferences, rollback


def test_one_undo_restores_everything_with_both_on(sworld):
    u, v2, info = sworld
    prior = u.undo_status()
    before = dump(u)
    res = run_import(u, v2, S(sched=True, presets=True))
    assert res.cards_with_progress == 1 and _conf_of(u, "Sw::One") == info["author_p"]
    assert u.undo_status().undo == UNDO_LABEL
    u.undo()
    assert dump(u) == before  # presets, decks, review log, cards, config
    assert u.undo_status().undo == prior.undo


@pytest.mark.parametrize("saved", [None, (False, False), (True, True)], ids=["missing", "off", "on"])
def test_anki_import_preferences_put_back_with_switches_on(sworld, saved):
    u, v2, _info = sworld
    if saved is not None:
        u.set_config("withScheduling", saved[0])
        u.set_config("withDeckConfigs", saved[1])
    else:
        for key in ("withScheduling", "withDeckConfigs"):
            u.remove_config(key)
    prefs = {k: u.get_config(k, "MISSING") for k in engine.IMPORT_PREF_KEYS}
    for sched, presets in ((True, True), (True, False), (False, True)):
        run_import(u, v2, S(sched, presets))
        assert {k: u.get_config(k, "MISSING") for k in engine.IMPORT_PREF_KEYS} == prefs
        u.undo()


def test_failure_after_import_rolls_back_presets_and_progress(sworld, monkeypatch):
    u, v2, _info = sworld
    prior = u.undo_status()
    before = dump(u)

    def boom(*_a, **_k):
        raise RuntimeError("late failure")

    monkeypatch.setattr(engine, "_restore_untouched", boom)
    with pytest.raises(RuntimeError):
        run_import(u, v2, S(sched=True, presets=True))
    assert dump(u) == before
    status = u.undo_status()
    assert status.undo == prior.undo and status.redo == ""


# ---------------------------------------------------------------------------
# G3 with scheduling


def _gate_world(tmp_path):
    col = Collection(str(tmp_path / "g3.anki2"))
    m = col.models.by_name("Basic")
    for i in range(3):
        n = col.new_note(m)
        n["Front"] = "q%d" % i
        col.add_note(n, 1)
    cids = sorted(col.db.list("select id from cards"))
    _review(col, cids[:2])
    # history of a card that was deleted later (Anki keeps it)
    orphan = 1_500_000_000_000
    col.db.execute("insert into revlog values (?, ?, -1, 3, 4, 1, 2500, 5000, 1)", 1_600_000_000_001, orphan)
    return col, cids, orphan


def _new_card(col):
    n = col.new_note(col.models.by_name("Basic"))
    n["Front"] = "brand new"
    col.add_note(n, 1)
    return n.card_ids()[0]


def _row(col, rid, cid):
    col.db.execute("insert into revlog values (?, ?, -1, 3, 9, 1, 2500, 6000, 1)", rid, cid)


def test_g3_with_scheduling_rows_for_new_cards_allowed(tmp_path):
    col, cids, orphan = _gate_world(tmp_path)
    try:
        snap = engine._snapshot(col, True)
        snap_off = engine._snapshot(col, False)
        assert snap.orphan_revlog == {orphan: [1_600_000_000_001]}
        assert snap_off.orphan_revlog is None
        assert engine._revlog_kept(col, snap, []) and engine._revlog_kept(col, snap_off, [])
        new = _new_card(col)
        _row(col, 1_600_000_000_100, new)
        _row(col, 1_600_000_000_101, new)
        assert engine._revlog_kept(col, snap, [new])
        # without the file's scheduling the same added rows are a failure
        assert not engine._revlog_kept(col, snap_off, [new])
    finally:
        col.close()


@pytest.mark.parametrize("damage", ["altered", "added_to_existing", "removed", "orphan_altered", "orphan_removed"])
def test_g3_with_scheduling_detects_damage(tmp_path, damage):
    col, cids, orphan = _gate_world(tmp_path)
    try:
        snap = engine._snapshot(col, True)
        new = _new_card(col)
        _row(col, 1_600_000_000_100, new)  # allowed
        rid = col.db.scalar("select id from revlog where cid=? order by id limit 1", cids[0])
        if damage == "altered":
            col.db.execute("update revlog set ease=1 where id=?", rid)
        elif damage == "added_to_existing":
            _row(col, 1_600_000_000_200, cids[2])  # a card that existed before
        elif damage == "removed":
            col.db.execute("delete from revlog where id=?", rid)
        elif damage == "orphan_altered":
            col.db.execute("update revlog set ivl=99 where cid=?", orphan)
        else:
            col.db.execute("delete from revlog where cid=?", orphan)
        assert not engine._revlog_kept(col, snap, [new])
    finally:
        col.close()


def test_g3_new_card_reusing_a_deleted_cards_id(tmp_path):
    """A card new to the collection may get back the id of a deleted card
    whose history Anki kept: its new rows are allowed, the old rows must
    stay as they were."""
    col, cids, orphan = _gate_world(tmp_path)
    try:
        snap = engine._snapshot(col, True)
        new = _new_card(col)
        col.db.execute("update cards set id=? where id=?", orphan, new)
        _row(col, 1_600_000_000_300, orphan)
        assert engine._revlog_kept(col, snap, [orphan])
        col.db.execute("update revlog set ease=2 where id=?", 1_600_000_000_001)
        assert not engine._revlog_kept(col, snap, [orphan])
    finally:
        col.close()


@pytest.mark.parametrize("where", ["whole log", "rows of new cards"])
def test_g3_refusal_in_run_import_with_scheduling(sworld, monkeypatch, where):
    """Monkeypatched: Anki's importer never alters a review log row or adds
    one to a card that already exists, and a raw SQL write would empty
    Anki's undo history. So the review log aggregate the gate reads after
    the import is made to differ (the detection itself is tested on real
    rows above). The import is refused and everything is rolled back,
    presets and imported progress included."""
    u, v2, _info = sworld
    prior = u.undo_status()
    before = dump(u)
    real = engine._revlog_sum
    calls = []

    def revlog_sum(col, clause=""):
        out = real(col, clause)
        calls.append(clause)
        hit = (not clause and len(calls) > 1) if where == "whole log" else "cid in" in clause
        return out[:-1] + (out[-1] + 1,) if hit else out

    monkeypatch.setattr(engine, "_revlog_sum", revlog_sum)
    with pytest.raises(MergeRepairError) as err:
        run_import(u, v2, S(sched=True, presets=True))
    assert "G3" in err.value.reason
    assert dump(u) == before
    status = u.undo_status()
    assert status.undo == prior.undo and status.redo == ""


def test_reimported_deleted_card_gets_its_id_back_old_history_kept(sworld, tmp_path):
    """Real import: the user had n4 (imported with progress), reviewed it and
    deleted the note; Anki keeps the deleted card's review rows. The file
    brings n4 back with one more review by the author. The card gets its old
    id back, the old rows stay as they were, only the new row is added."""
    u, v2, _info = sworld
    u.import_anki_package(ImportAnkiPackageRequest(package_path=v2, options=ImportAnkiPackageOptions(
        merge_notetypes=True, with_scheduling=True)))
    n4 = g(u, "n4")
    (cid,) = n4.card_ids()
    _review(u, [cid])
    u.remove_notes([n4.id])
    old_rows = [tuple(r) for r in u.db.all("select * from revlog where cid=? order by id", cid)]
    assert len(old_rows) == 2 and not u.db.scalar("select count() from cards where id=?", cid)
    a = Collection(os.path.join(str(tmp_path), "author.anki2"))
    _review(a, [a.db.scalar("select id from cards where nid=(select id from notes where guid='n4')")])
    v3 = _export(a, os.path.join(str(tmp_path), "v3.apkg"), sched=True)
    a.close()
    before = dump(u)
    res = run_import(u, v3, S(sched=True))
    assert g(u, "n4").card_ids() == [cid]
    rows = [tuple(r) for r in u.db.all("select * from revlog where cid=? order by id", cid)]
    assert set(old_rows) <= set(rows)
    assert len(rows) == 3
    assert res.cards_with_progress == 1
    u.undo()
    assert dump(u) == before


# ---------------------------------------------------------------------------
# rule 10 note type moves with learning progress and presets on: the
# author's file carries review history for every card


@pytest.mark.parametrize("cloze", [False, True], ids=["standard", "cloze"])
@pytest.mark.parametrize("kind", ["existing", "new", "user", "samename"])
def test_note_type_moves_with_progress_on(tmp_path, monkeypatch, kind, cloze):
    def export_with_progress(col, path):
        _review(col, col.db.list("select id from cards where queue = 0"))
        col.export_anki_package(out_path=path, options=ExportAnkiPackageOptions(
            with_scheduling=True, with_deck_configs=True, with_media=True, legacy=False), limit=None)
        return path

    real_run = r910.run_import

    def run_with_switches(col, path, settings):
        res = real_run(col, path, Settings(
            fields=settings.fields, protected_tags=settings.protected_tags,
            update_note_types=settings.update_note_types, import_scheduling=True, import_deck_presets=True))
        assert res.learning_progress_imported and res.cards_with_progress == 0
        return res

    monkeypatch.setattr(r910, "_export", export_with_progress)
    monkeypatch.setattr(r910, "run_import", run_with_switches)
    col, v2, info = r910._build(str(tmp_path), kind, cloze)
    try:
        # the same checks as with the switches off: user data intact, review
        # log unchanged, one undo step restores every table
        r910._check_move(col, v2, info, kind, cloze, True)
    finally:
        col.close()


def test_refused_move_with_progress_on_leaves_collection_unchanged(tmp_path, monkeypatch):
    """A move the clean-up cannot repair (Anki refuses the repaired note
    type: two identical card fronts) is still refused cleanly with the
    switches on: presets, progress and everything else rolled back."""
    def export_with_progress(col, path):
        _review(col, col.db.list("select id from cards where queue = 0"))
        col.export_anki_package(out_path=path, options=ExportAnkiPackageOptions(
            with_scheduling=True, with_deck_configs=True, with_media=True, legacy=False), limit=None)
        return path

    monkeypatch.setattr(r910, "_export", export_with_progress)
    col, v2 = r910._move_world(str(tmp_path), ap_tmpls=[("Card 1", "{{Text}}"), ("Card 2", "{{Header}} {{Text}}")],
                               mi_tmpls=[("Card 1", "{{Header}} {{Text}}")])
    try:
        n = g(col, "ddd")
        n["Extra"] = "my last edit"
        col.update_note(n)
        prior = col.undo_status()
        before = dump(col)
        with pytest.raises(MergeRepairError) as err:
            run_import(col, v2, S(sched=True, presets=True))
        assert "refused" in err.value.reason
        assert dump(col) == before
        status = col.undo_status()
        assert status.undo == prior.undo and status.redo == ""
    finally:
        col.close()
