"""Contract rule 14: a field table per protected tag.

The simulated user (tools/build_fixtures.py) tags notes "#edited" (all
fields edited, or Text and Extra edited), "#edited::images" (Personal
Notes filled), "mytag::exam" (Personal Notes filled) and "#edited2",
"mytag". The oracle (sfa_acc_helpers.kept_on_note / expected_fields)
decides, for every note and every field, what rule 14 expects: a note that
carried protected tags follows the union of their tables, not the main
list."""

from __future__ import annotations

import dataclasses

import pytest

import sfa_acc_helpers as H
from sfa_acc_helpers import DEFAULTS, settings
from special_fields_by_ankoma.model import UNDO_LABEL, FieldChoice, is_protected_tag

DEFAULT_KEEP = [f.name for f in DEFAULTS.fields if f.keep]
DEFAULT_TAKE = [f.name for f in DEFAULTS.fields if not f.keep]

CASES = {
    # the author's example: Personal Notes kept in the main list; "#edited"
    # keeps Text and Extra and switches Personal Notes off
    "switch-off": settings(keep=DEFAULT_KEEP, take=DEFAULT_TAKE, protected=["#edited"],
                           rules=[("#edited", ["Text", "Extra"])]),
    "tag-keeps-main-too": settings(keep=DEFAULT_KEEP, take=DEFAULT_TAKE, protected=["#edited"],
                                   rules=[("#edited", ["Text", "Extra", "Personal Notes"])]),
    "union": settings(keep=["Personal Notes"], protected=["#edited", "mytag"],
                      rules=[("#edited", ["Text"]), ("mytag", ["Extra", "Header", "Remarks"])]),
    "every-field": settings(keep=DEFAULT_KEEP, take=DEFAULT_TAKE, protected=["#EDITED", "mytag::exam"],
                            rules=[("#EDITED", "all"), ("mytag::exam", ["text"])]),
    "subtag-table": settings(take=DEFAULT_TAKE + ["Personal Notes"], protected=["#edited::images"],
                             rules=[("#edited::images", ["Personal Notes", "Images"])]),
    "nothing-listed": settings(protected=["#edited"], rules=[("#edited", ["Extra", "Extra 1"])]),
    "keeps-no-fields": settings(keep=DEFAULT_KEEP, take=DEFAULT_TAKE, protected=["#edited", "mytag"],
                                rules=[("#edited", []), ("mytag", ["Header"])]),
    # frozen at Personal Notes; the main list later switched it off
    "main-changed-later": settings(take=DEFAULT_TAKE + DEFAULT_KEEP, protected=["#edited"],
                                   rules=[("#edited", ["Personal Notes"])]),
    # earlier betas' entries, not frozen yet
    "legacy-plain": settings(keep=DEFAULT_KEEP, take=DEFAULT_TAKE, protected=["#edited", "mytag"]),
    "legacy-beta8": settings(keep=DEFAULT_KEEP, take=DEFAULT_TAKE, protected=["#edited", "mytag"],
                             legacy=[("#edited", ["Text", "Extra"]), ("mytag", "all")]),
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


def test_rule14_the_tables_really_decide(fx, user_col, run_import):
    """Guard against a vacuous oracle. With "#edited" keeping Text and
    Extra only: some tagged notes keep a Text the update changed, some
    untagged notes take the update's Text, some tagged notes LOSE a Personal
    Notes the main list keeps (the update's differs), and some untagged
    notes keep theirs."""
    s = CASES["switch-off"]
    run_import(user_col, fx.package("v1.3"), s)
    after = H.notes_by_guid(user_col)
    upd = fx.update("v1.3")
    n = {"text kept": 0, "text taken": 0, "pn lost": 0, "pn kept": 0}
    for g, old in fx.before.items():
        if g not in upd:
            continue
        tagged = any(is_protected_tag(t, ("#edited",)) for t in old.tags)
        if old.has_field("Text") and old.field("Text") != upd[g].field("Text"):
            if tagged:
                assert after[g].field("Text") == old.field("Text"), old.nid
                n["text kept"] += 1
            else:
                assert after[g].field("Text") == upd[g].field("Text"), old.nid
                n["text taken"] += 1
        if old.has_field("Personal Notes") and old.field("Personal Notes") != (upd[g].field("Personal Notes") or ""):
            if tagged:
                assert after[g].field("Personal Notes") == (upd[g].field("Personal Notes") or ""), old.nid
                n["pn lost"] += 1
            else:
                assert after[g].field("Personal Notes") == old.field("Personal Notes"), old.nid
                n["pn kept"] += 1
    assert all(n.values()), n


def _content(col):
    return {g: (n.notetype, n.fields, sorted(n.tags)) for g, n in H.notes_by_guid(col).items()}


@pytest.mark.parametrize("case", ["legacy-plain", "legacy-beta8"])
def test_rule14_legacy_entries_same_before_and_after_freezing(fx, user_col, run_import, tmp_path, case):
    """Beta 7's plain strings and beta 8's objects give exactly the same
    notes before and after the settings window freezes them."""
    s = CASES[case]
    run_import(user_col, fx.package("v1.3"), s)
    legacy = _content(user_col)
    other = H.open_collection(H.copy_collection(fx.m["user_collection"], str(tmp_path / "again")))
    try:
        frozen = s.with_frozen_tags()
        assert all(r.fields is not None for r in frozen.tag_rules)
        run_import(other, fx.package("v1.3"), frozen)
        again = _content(other)
    finally:
        other.close()
    assert again == legacy


def test_rule14_plain_tags_equal_todays_result(fx, user_col, run_import, tmp_path):
    """Plain protected tags (beta 7): exactly the main list's result."""
    s = CASES["legacy-plain"]
    run_import(user_col, fx.package("v1.3"), s)
    plain = _content(user_col)
    other = H.open_collection(H.copy_collection(fx.m["user_collection"], str(tmp_path / "again")))
    try:
        # tables equal to the main list, and a table for a tag that is not protected (ignored)
        s2 = settings(keep=DEFAULT_KEEP, take=DEFAULT_TAKE, protected=["#edited", "mytag"],
                      rules=[("#edited", DEFAULT_KEEP), ("mytag", DEFAULT_KEEP), ("not-protected", "all")])
        run_import(other, fx.package("v1.3"), s2)
        again = _content(other)
    finally:
        other.close()
    assert again == plain


def test_rule14_main_list_change_leaves_tables_alone(fx, user_col, run_import, tmp_path):
    """The same frozen table with two different main lists: the notes that
    carry the tag come out identical."""
    a = CASES["main-changed-later"]
    b = dataclasses.replace(a, fields=tuple(FieldChoice(f.name, True) for f in a.fields))
    run_import(user_col, fx.package("v1.3"), a)
    first = _content(user_col)
    other = H.open_collection(H.copy_collection(fx.m["user_collection"], str(tmp_path / "again")))
    try:
        run_import(other, fx.package("v1.3"), b)
        second = _content(other)
    finally:
        other.close()
    tagged = [g for g, n in fx.before.items() if H.carried_tags(n, a)]
    assert tagged and all(first[g] == second[g] for g in tagged)
    assert any(first[g] != second[g] for g in first if g not in tagged)


@pytest.mark.parametrize("key", ["v1.3", "v1.3-moved"])
def test_rule14_one_undo_restores_exactly(fx, user_col, run_import, key):
    state0 = H.db_state(user_col)
    run_import(user_col, fx.package(key), CASES["every-field"])
    assert user_col.undo_status().undo == UNDO_LABEL
    user_col.undo()
    assert user_col.undo_status().undo == ""
    diffs = H.diff_db_state(state0, H.db_state(user_col))
    assert not diffs, "undo should restore the collection exactly:\n  " + "\n  ".join(diffs)
