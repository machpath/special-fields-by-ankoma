"""Contract rule 12 (prove the result or refuse), the C1 restore of notes
the import did not update (cloned note types sharing field ids), and rule
13 (a rollback that cannot be done raises RollbackFailedError).

Each refusal test asserts: MergeRepairError naming the invariant, every
table unchanged, the user's own undo step on top, nothing to redo."""

from __future__ import annotations

import os
import time

import pytest
from anki.collection import Collection

from special_fields_by_ankoma import engine
from special_fields_by_ankoma.engine import MergeRepairError, RollbackFailedError, run_import
from special_fields_by_ankoma.model import UNDO_LABEL

from .test_rules_9_10 import S, _add, _export, _move, _review_everything, _stock_import, dump, g


def _nt(col, name, fields, tmpls, cloze=False):
    mm = col.models
    m = mm.new(name)
    if cloze:
        m["type"] = 1
    for f in fields:
        mm.add_field(m, mm.new_field(f))
    for tname, qfmt, afmt in tmpls:
        t = mm.new_template(tname)
        t["qfmt"] = qfmt
        t["afmt"] = afmt
        mm.add_template(m, t)
    mm.add(m)
    time.sleep(0.003)
    return mm.by_name(name)


def _clone(col, src, name, fields=None):
    """Like Manage Note Types > Add > Clone: field and template ids copied."""
    m = col.models.copy(col.models.by_name(src), add=False)
    m["name"] = name
    if fields is not None:
        by = {f["name"]: f for f in m["flds"]}
        m["flds"] = [by[f] for f in fields]
        for i, f in enumerate(m["flds"]):
            f["ord"] = i
    col.models.add(m)
    time.sleep(0.003)
    return col.models.by_name(name)


def _world(tmp, build_types, notes, moves, own, damage=None):
    """Author builds note types and `notes` [(guid, type)], exports v1; the
    user imports it, adds `own` [(guid, type, values)], fills Personal
    Notes, reviews everything; the author applies `moves` [(guid, type)],
    edits every note and exports v2."""
    os.makedirs(tmp, exist_ok=True)
    a = Collection(os.path.join(tmp, "author.anki2"))
    build_types(a)
    for guid, nt in notes:
        cloze = a.models.by_name(nt)["type"] == 1
        front = ("{{c1::F %s}}" if cloze else "F %s") % guid
        _add(a, nt, "Rel", guid, {"Front": front, "Back": "B " + guid}, ["v1"])
    a.db.execute("update notes set mod=1000000")
    v1 = _export(a, os.path.join(tmp, "v1.apkg"))
    time.sleep(0.01)
    u = Collection(os.path.join(tmp, "user.anki2"))
    _stock_import(u, v1)
    for guid, nt, values in own:
        _add(u, nt, "Mine", guid, values, ["mine"])
    for nid in u.find_notes(""):
        n = u.get_note(nid)
        n["Personal Notes"] = "PN " + n.guid
        u.update_note(n)
    _review_everything(u)
    u.db.execute("update notes set mod=3000000")
    if damage:
        damage(u)
    for guid, to in moves:
        _move(a, guid, to)
    for nid in a.find_notes(""):
        n = a.get_note(nid)
        n["Back"] = n["Back"] + " v2"
        a.update_note(n)
    a.db.execute("update notes set mod=2000000")
    v2 = _export(a, os.path.join(tmp, "v2.apkg"))
    a.close()
    return u, v2


def _user_step(col, guid):
    n = g(col, guid)
    n["Extra"] = "my last edit"
    col.update_note(n)


def _refused(col, v2, invariant, settings=None):
    prior = col.undo_status()
    before = dump(col)
    with pytest.raises(MergeRepairError) as err:
        run_import(col, v2, settings or S(keep=("Personal Notes",)))
    assert invariant in err.value.reason, err.value.reason
    assert dump(col) == before
    status = col.undo_status()
    assert status.undo == prior.undo and status.redo == ""
    return err.value


F4 = ["Front", "Back", "Extra", "Personal Notes"]


# ---------------------------------------------------------------------------
# C1: cloned note types share field ids; Anki rewrites the user's own notes
# of the target type by the old type's positions. They are put back.


def _cloned_cloze(a):
    _nt(a, "AP", ["Header", "Front", "Back", "Extra", "Personal Notes"],
        [("Cloze", "{{cloze:Front}}", "{{cloze:Front}}<br>{{Extra}}")], cloze=True)
    mi = _clone(a, "AP", "AP - multiple images")
    a.models.add_field(mi, a.models.new_field("Images"))
    a.models.reposition_field(mi, mi["flds"][-1], 2)
    a.models.update_dict(mi)


def _cloned_standard(a):
    _nt(a, "IOE", ["Front", "Header", "Back", "Extra", "Personal Notes"],
        [("IO Card", "{{Front}}", "{{Back}}")])
    _clone(a, "IOE", "IOE+", ["Header", "Front", "Extra", "Back", "Personal Notes"])


@pytest.mark.parametrize("kind", ["cloze", "standard"])
def test_c1_cloned_note_types_user_notes_restored(tmp_path, kind):
    if kind == "cloze":
        build, src, dst = _cloned_cloze, "AP", "AP - multiple images"
        own = [("own_dst", dst, {"Header": "my H", "Front": "{{c1::mine}}", "Images": "<img src=m.png>",
                                 "Back": "my B", "Extra": "my X"}),
               ("own_src", src, {"Header": "my AP H", "Front": "{{c1::my ap}}", "Extra": "my AP X"})]
        notes = [("s1", src), ("s2", src), ("d1", dst)]
    else:
        build, src, dst = _cloned_standard, "IOE", "IOE+"
        own = [("own_dst", dst, {"Header": "my H", "Front": "my F", "Back": "my B", "Extra": "my X"}),
               ("own_src", src, {"Header": "my IOE H", "Front": "my IOE F", "Extra": "my IOE X"})]
        notes = [("s1", src), ("s2", src), ("d1", dst)]
    u, v2 = _world(str(tmp_path), build, notes, [("s1", dst)], own)
    try:
        _user_step(u, "own_dst")
        before = {x: (dict(g(u, x).items()), sorted(g(u, x).tags)) for x in ("own_dst", "own_src")}
        cards_before = u.db.all("select * from cards where nid in (?, ?) order by id",
                                g(u, "own_dst").id, g(u, "own_src").id)
        state0 = dump(u)
        prior = u.undo_status()
        res = run_import(u, v2, S(keep=("Personal Notes",)))
        u.models._clear_cache()
        for x in ("own_dst", "own_src"):
            assert (dict(g(u, x).items()), sorted(g(u, x).tags)) == before[x], x
        assert u.db.all("select * from cards where nid in (?, ?) order by id",
                        g(u, "own_dst").id, g(u, "own_src").id) == cards_before
        s1 = g(u, "s1")
        assert s1.note_type()["name"] == dst
        assert s1["Personal Notes"] == "PN s1" and s1["Back"] == "B s1 v2"
        assert res.notes_updated == 3
        assert not any(f["name"].endswith("+") for nt in u.models.all() for f in nt["flds"])
        assert u.undo_status().undo == UNDO_LABEL
        u.undo()
        assert dump(u) == state0
        assert u.undo_status().undo == prior.undo
    finally:
        u.close()


# ---------------------------------------------------------------------------
# The gate refuses, each invariant constructed for real where possible


def test_gate_g1_untouched_note_cannot_be_restored(tmp_path):
    """Real: the cloned-cloze move rewrites the user's own note of the target
    type; that note was damaged before (one stray value more than its note
    type has fields), so it cannot be put back exactly -> G1."""
    def damage(u):
        u.db.execute("update notes set flds = flds || char(31) || 'stray' where guid='own_dst'")

    own = [("own_dst", "AP - multiple images", {"Header": "my H", "Front": "{{c1::mine}}", "Back": "my B"})]
    u, v2 = _world(str(tmp_path), _cloned_cloze, [("s1", "AP"), ("s2", "AP"), ("d1", "AP - multiple images")],
                   [("s1", "AP - multiple images")], own, damage=damage)
    try:
        _refused(u, v2, "G1")
    finally:
        u.close()


def test_gate_g2_two_note_types_into_one(tmp_path):
    """Real (second verifier's C2): notes from two standard note types are
    moved into a third in one release; Anki's merge deletes reviewed cards
    -> G2, nothing imported."""
    def build(a):
        _nt(a, "A", ["Front", "Back", "Personal Notes", "Extra"], [("Card", "{{Front}}", "{{Back}}")])
        _nt(a, "B", ["Front", "Extra", "Back", "Personal Notes"], [("Card", "{{Front}}?", "{{Back}}")])
        _nt(a, "C", F4, [("Card", "{{Front}}!", "{{Back}}")])

    notes = [("%s%d" % (t.lower(), i), t) for t in "ABC" for i in range(2)]
    u, v2 = _world(str(tmp_path), build, notes, [("a0", "C"), ("b0", "C")],
                   [("own_c", "C", {"Front": "own"})])
    try:
        _user_step(u, "own_c")
        _refused(u, v2, "G2")
    finally:
        u.close()


def test_gate_g2_non_clashing_template_name(tmp_path):
    """Real (second verifier's C3): the old type's template has another name
    than the target's, so Anki leaves the existing cards on the copied
    template -> G2."""
    def build(a):
        _nt(a, "A", F4, [("Front", "{{Front}}", "{{Back}}")])
        _nt(a, "C", F4, [("Card 1", "{{Front}}!", "{{Back}}")])

    notes = [("a0", "A"), ("a1", "A"), ("c0", "C"), ("c1", "C")]
    u, v2 = _world(str(tmp_path), build, notes, [("a0", "C")], [("own_c", "C", {"Front": "own"})])
    try:
        _user_step(u, "own_c")
        _refused(u, v2, "G2")
    finally:
        u.close()


def test_gate_g4_template_copied_from_old_note_type(tmp_path):
    """Real (point 4 of the last round): the old type has a second template
    the target lacks; Anki copies it over and every note of the target
    type gets a new card for it, including the user's own note -> G4."""
    def build(a):
        _nt(a, "A", F4, [("Card 1", "{{Front}}", "{{Back}}"), ("Card 2", "{{Back}}", "{{Front}}")])
        _nt(a, "C", F4, [("Card 1", "{{Front}}!", "{{Back}}")])

    notes = [("a0", "A"), ("a1", "A"), ("c0", "C")]
    u, v2 = _world(str(tmp_path), build, notes, [("a0", "C")],
                   [("own_c", "C", {"Front": "own", "Back": "own back"})])
    try:
        _user_step(u, "own_c")
        _refused(u, v2, "G4")
    finally:
        u.close()


def test_gate_g3_review_log(tmp_path, monkeypatch):
    """Monkeypatched: with with_scheduling=False Anki's importer never writes
    to the review log, so there is no honest way to change it during an
    import. The second review-log aggregate (after the import) is made to
    differ."""
    def build(a):
        _nt(a, "C", F4, [("Card 1", "{{Front}}", "{{Back}}")])

    u, v2 = _world(str(tmp_path), build, [("c0", "C"), ("c1", "C")], [], [("own_c", "C", {"Front": "own"})])
    calls = []
    real = engine._revlog_sum

    def revlog_sum(col):
        calls.append(1)
        out = real(col)
        return out if len(calls) == 1 else out[:-1] + (out[-1] + 1,)

    monkeypatch.setattr(engine, "_revlog_sum", revlog_sum)
    try:
        _user_step(u, "own_c")
        _refused(u, v2, "G3")
    finally:
        u.close()


def test_gate_g2_scheduling_changed(tmp_path, monkeypatch):
    """Monkeypatched: Anki's importer never changes an existing card's
    scheduling; a card's due is changed (through Anki's own API, inside the
    undo step) right after the native import."""
    def build(a):
        _nt(a, "C", F4, [("Card 1", "{{Front}}", "{{Back}}")])

    u, v2 = _world(str(tmp_path), build, [("c0", "C"), ("c1", "C")], [], [])
    real = u.import_anki_package

    def import_then_reschedule(req):
        out = real(req)
        cid = u.db.scalar("select id from cards order by id limit 1")
        u.sched.set_due_date([cid], "30")
        return out

    monkeypatch.setattr(u, "import_anki_package", import_then_reschedule)
    try:
        _user_step(u, "c1")
        _refused(u, v2, "G2")
    finally:
        u.close()


# ---------------------------------------------------------------------------
# The gate does not fire on correct imports


def test_gate_allows_a_template_the_author_added(tmp_path):
    """The author adds a card template to a standard note type: Anki gives
    every note of that type a card for it, also the user's own note that is
    not in the file. That is a correct update and is not refused."""
    tmp = str(tmp_path)

    def build(a):
        _nt(a, "C", F4, [("Card 1", "{{Front}}", "{{Back}}")])

    u, v2 = _world(tmp, build, [("c0", "C"), ("c1", "C")], [], [("own_c", "C", {"Front": "own", "Back": "ob"})])
    a = Collection(os.path.join(tmp, "author.anki2"))
    nt = a.models.by_name("C")
    t = a.models.new_template("Card 2")
    t["qfmt"] = "{{Back}}"
    t["afmt"] = "{{Front}}"
    a.models.add_template(nt, t)
    a.models.update_dict(nt)
    a.db.execute("update notes set mod=2500000")
    v3 = _export(a, os.path.join(tmp, "v3.apkg"))
    a.close()
    try:
        res = run_import(u, v3, S(keep=("Personal Notes",)))
        assert res.notes_updated == 2
        assert sorted(c.ord for c in g(u, "own_c").cards()) == [0, 1]
    finally:
        u.close()


# ---------------------------------------------------------------------------
# Rule 13: a rollback that cannot be done


def test_rollback_failed_when_anki_discards_undo(tmp_path, monkeypatch):
    """Real backend failure after the native import: the engine's scratch
    check is bypassed (monkeypatched), so Anki itself refuses the repaired
    note type on the user's collection ("front side is identical"), which
    empties Anki's undo queue. The engine cannot roll back and says so."""
    def build(a):
        _nt(a, "AP", F4, [("Card 1", "{{Back}}", "{{Extra}}"), ("Card 2", "{{Front}}<br>{{Back}}", "{{Extra}}")])
        _nt(a, "MI", F4 + ["Images"], [("Card 1", "{{Front}}<br>{{Back}}", "{{Extra}}")])

    u, v2 = _world(str(tmp_path), build, [("aaa", "AP"), ("bbb", "AP"), ("ccc", "MI")], [("aaa", "MI")],
                   [("ddd", "MI", {"Front": "my own", "Back": "ddd"})])
    monkeypatch.setattr(engine._Validator, "check", lambda self, nt: None)
    try:
        _user_step(u, "ddd")
        with pytest.raises(RollbackFailedError) as err:
            run_import(u, v2, S(keep=("Personal Notes",)))
        assert isinstance(err.value.__cause__, MergeRepairError)
        assert "identical" in str(err.value.__cause__)
        assert u.undo_status().undo == ""  # Anki discarded the history
    finally:
        u.close()


def test_native_import_failure_is_not_a_failed_rollback(user_col, tmp_path):
    """A failure inside the native import changes nothing (one backend
    transaction): the original error propagates, not RollbackFailedError."""
    bad = str(tmp_path / "bad.apkg")
    with open(bad, "wb") as f:
        f.write(b"PK\x03\x04 not a package")
    with pytest.raises(Exception) as err:
        run_import(user_col, bad, S(keep=("Personal Notes",)))
    assert not isinstance(err.value, RollbackFailedError)


def test_roll_back_reports_whether_it_undid(user_col):
    col = user_col
    pos = col.add_custom_undo_entry(UNDO_LABEL)
    assert engine._roll_back(col, pos, None) is True
    col.db.execute("update col set mod=mod")  # raw write: Anki empties the undo queue
    pos = col.add_custom_undo_entry(UNDO_LABEL)
    col.db.execute("update col set mod=mod")
    assert engine._roll_back(col, pos, None) is False
