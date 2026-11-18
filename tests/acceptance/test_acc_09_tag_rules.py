"""Contract rule 14: fields kept per protected tag.

The simulated user (tools/build_fixtures.py) tags notes "#edited" (all
fields edited, or Text and Extra edited), "#edited::images", "mytag::exam"
(Personal Notes filled) and "#edited2", "mytag". The oracle
(sfa_acc_helpers.kept_on_note / expected_fields) decides, for every note
and every field, what rule 14 expects."""

from __future__ import annotations

import pytest

import sfa_acc_helpers as H
from sfa_acc_helpers import DEFAULTS, settings
from special_fields_by_ankoma.model import UNDO_LABEL, is_protected_tag

DEFAULT_KEEP = [f.name for f in DEFAULTS.fields if f.keep]
DEFAULT_TAKE = [f.name for f in DEFAULTS.fields if not f.keep]

CASES = {
    # the author's example: Personal Notes everywhere, Text and Extra on #edited
    "worked-example": settings(keep=DEFAULT_KEEP, take=DEFAULT_TAKE, protected=["#edited"],
                               rules=[("#edited", ["Text", "Extra"])]),
    "union": settings(keep=["Personal Notes"], protected=["#edited", "mytag"],
                      rules=[("#edited", ["Text"]), ("mytag", ["Extra", "Header", "Remarks"])]),
    "every-field": settings(keep=DEFAULT_KEEP, take=DEFAULT_TAKE, protected=["#EDITED", "mytag::exam"],
                            rules=[("#EDITED", "all"), ("mytag::exam", ["text"])]),
    "subtag-rule": settings(take=DEFAULT_TAKE + ["Personal Notes"], protected=["#edited::images"],
                            rules=[("#edited::images", ["Personal Notes", "Images"])]),
    "nothing-listed": settings(protected=["#edited"], rules=[("#edited", ["Extra", "Extra 1"])]),
}


@pytest.mark.parametrize("key", ["v1.3", "v1.3-newfield", "v1.3-moved"])
@pytest.mark.parametrize("case", sorted(CASES))
def test_rule14_every_field_of_every_note(fx, user_col, run_import, key, case):
    s = CASES[case]
    res = run_import(user_col, fx.package(key), s)
    after = H.notes_by_guid(user_col)
    problems = H.check_import_outcome(fx.before, fx.update(key), after, s)
    assert not problems, H.fail_msg(problems, "%s, import %s" % (case, key))
    exp = H.expected_counters(fx.before, fx.update(key), s)
    got = {k: getattr(res, k) for k in exp}
    wrong = {k: (exp[k], got[k]) for k in exp if exp[k] != got[k]}
    assert not wrong, "ImportResult counters {counter: (expected, got)}: %s" % wrong


def test_rule14_the_rule_really_keeps_something(fx, user_col, run_import):
    """Guard against a vacuous oracle: in the worked example, some notes
    carrying #edited keep a Text the update changed, and some notes without
    it take the update's Text over the user's."""
    s = CASES["worked-example"]
    run_import(user_col, fx.package("v1.3"), s)
    after = H.notes_by_guid(user_col)
    upd = fx.update("v1.3")
    kept = taken = 0
    for g, old in fx.before.items():
        if g not in upd or not old.has_field("Text") or old.field("Text") == upd[g].field("Text"):
            continue
        if any(is_protected_tag(t, ("#edited",)) for t in old.tags):
            assert after[g].field("Text") == old.field("Text"), old.nid
            kept += 1
        else:
            assert after[g].field("Text") == upd[g].field("Text"), old.nid
            taken += 1
    assert kept and taken


def test_rule14_tag_only_equals_todays_result(fx, user_col, run_import, tmp_path):
    """Protected tags with no fields: exactly the plain protected-tag result."""
    s = settings(keep=DEFAULT_KEEP, take=DEFAULT_TAKE, protected=["#edited", "mytag"])
    run_import(user_col, fx.package("v1.3"), s)
    plain = {g: (n.fields, sorted(n.tags)) for g, n in H.notes_by_guid(user_col).items()}
    other = H.open_collection(H.copy_collection(fx.m["user_collection"], str(tmp_path / "again")))
    try:
        s2 = settings(keep=DEFAULT_KEEP, take=DEFAULT_TAKE, protected=["#edited", "mytag"],
                      rules=[("#edited", []), ("not-protected", "all")])
        run_import(other, fx.package("v1.3"), s2)
        again = {g: (n.fields, sorted(n.tags)) for g, n in H.notes_by_guid(other).items()}
    finally:
        other.close()
    assert again == plain


@pytest.mark.parametrize("key", ["v1.3", "v1.3-moved"])
def test_rule14_one_undo_restores_exactly(fx, user_col, run_import, key):
    state0 = H.db_state(user_col)
    run_import(user_col, fx.package(key), CASES["every-field"])
    assert user_col.undo_status().undo == UNDO_LABEL
    user_col.undo()
    assert user_col.undo_status().undo == ""
    diffs = H.diff_db_state(state0, H.db_state(user_col))
    assert not diffs, "undo should restore the collection exactly:\n  " + "\n  ".join(diffs)
