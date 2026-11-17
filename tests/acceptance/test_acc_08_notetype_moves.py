"""Contract rule 10: notes the author moved to another note type are
followed onto it, and Anki's merge leftovers are cleaned up.

Package v1.3-moved: v1.3 with some Cloze-Ankoma-AP notes moved to
Cloze-Ankoma-AP-Unrestricted (cloze) and some Image Occlusion Enhanced notes
moved to Image Occlusion Enhanced+ (standard note type, fields in another
order). The oracle (sfa_acc_helpers.check_import_outcome) checks every field
of every note: the moved notes end on the file's note type, kept fields hold
the user's value in the properly named field, no note type gains a field the
update and the user's note type did not have, other notes stay as they were."""

from __future__ import annotations

import pytest

import sfa_acc_helpers as H
from sfa_acc_helpers import DEFAULTS, settings
from special_fields_by_ankoma.model import UNDO_LABEL

KEY = "v1.3-moved"
CASES = {
    "defaults": DEFAULTS,
    "nothing-listed": settings(protected=["#edited"]),
    "keep-header-remarks": settings(keep=["Personal Notes", "Header", "Remarks"], protected=["#edited"]),
}
# card columns that hold scheduling, history and deck (mod/usn change with
# any note type change)
SCHED_COLS = ("id", "nid", "did", "ord", "type", "queue", "due", "ivl", "factor", "reps",
              "lapses", "left", "odue", "odid", "flags", "data")


def _cards(col):
    return {r[0]: tuple(r) for r in col.db.all("select %s from cards" % ", ".join(SCHED_COLS))}


def test_fixture_has_moves(fx):
    # (some moved notes are new in v1.3; the ones the user already has matter)
    moved = [m for m in fx.m["v13"]["moved_notes"] if m["guid"] in fx.before]
    assert {m["to"] for m in moved} == {"Cloze-Ankoma-AP-Unrestricted", "Image Occlusion Enhanced+"}
    upd = fx.update(KEY)
    for m in moved:
        assert fx.before[m["guid"]].notetype == m["from"]
        assert upd[m["guid"]].notetype == m["to"]


@pytest.mark.parametrize("update_note_types", [True, False], ids=["styling-update", "styling-keep"])
@pytest.mark.parametrize("case", sorted(CASES))
def test_rule10_moved_notes_followed_and_cleaned(fx, user_col, run_import, case, update_note_types):
    s = H.settings(keep=[f.name for f in CASES[case].fields if f.keep],
                   take=[f.name for f in CASES[case].fields if not f.keep],
                   protected=CASES[case].protected_tags, update_note_types=update_note_types)
    state0 = H.db_state(user_col)
    cards0 = _cards(user_col)
    looks0 = H.notetype_looks(user_col)
    res = run_import(user_col, fx.package(KEY), s)
    after = H.notes_by_guid(user_col)
    upd = fx.update(KEY)
    problems = H.check_import_outcome(fx.before, upd, after, s)
    assert not problems, H.fail_msg(problems, "%s, import v1.3-moved" % case)
    # no merge leftovers on any note type
    looks = H.notetype_looks(user_col)
    ref = fx.update_looks(KEY)
    for name, look in looks.items():
        allowed = set(looks0.get(name, {}).get("fields", [])) | set(ref.get(name, {}).get("fields", []))
        leftover = [f for f in look["fields"] if f not in allowed]
        assert not leftover, "%s gained fields %s (merge leftovers)" % (name, leftover)
    # counters
    exp = H.expected_counters(fx.before, upd, s)
    got = {k: getattr(res, k) for k in exp}
    assert got == exp, "counters {name: (expected, got)}: %s" % {
        k: (exp[k], got[k]) for k in exp if exp[k] != got[k]}
    # every existing card keeps its id, scheduling, history and deck; the
    # moved notes get no duplicate cards
    cards = _cards(user_col)
    lost = sorted(set(cards0) - set(cards))
    assert not lost, "existing cards disappeared: %s" % lost[:10]
    changed = [cid for cid in cards0 if cards[cid] != cards0[cid]]
    assert not changed, "scheduling/deck/ord of existing cards changed, e.g. %r -> %r" % (
        cards0[changed[0]], cards[changed[0]])
    assert sorted(H.revlog_rows(user_col)) == sorted(state0["revlog"]), "review log changed"
    moved = {m["guid"] for m in fx.m["v13"]["moved_notes"] if m["guid"] in fx.before}
    for g in moved:
        nid = after[g].nid
        before_n = user_col.db.scalar("select count() from cards where nid=? and id in (%s)"
                                      % ",".join(str(c) for c in cards0), nid)
        total = user_col.db.scalar("select count() from cards where nid=?", nid)
        assert total == before_n, "moved note %s: %d cards now, %d before" % (g, total, before_n)
    # styling switch off: every note type the user had keeps templates and CSS
    if not update_note_types:
        for name, look in looks0.items():
            assert looks[name]["css"] == look["css"], name
            assert looks[name]["tmpls"] == look["tmpls"], name
    # one undo puts everything back
    assert user_col.undo_status().undo == UNDO_LABEL
    user_col.undo()
    diffs = H.diff_db_state(state0, H.db_state(user_col))
    assert not diffs, "undo should restore the collection exactly:\n  " + "\n  ".join(diffs)
