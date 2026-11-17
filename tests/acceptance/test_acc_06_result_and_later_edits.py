"""Checks 11-12: ImportResult counters; locally newer notes still update."""

from __future__ import annotations

import pytest

import sfa_acc_helpers as H
from sfa_acc_helpers import DEFAULTS, settings

COUNTERS = ("notes_in_file", "notes_added", "notes_updated", "notes_skipped", "fields_kept",
            "notes_with_fields_kept", "protected_tags_kept", "notes_with_tags_kept")

CASES = {
    "defaults": DEFAULTS,
    "nothing-kept": settings(),
    "fields+tags": settings(keep=["Personal Notes", "Header", "Remarks", "Extra 1"],
                            protected=["#edited", "mytag::exam"]),
    "tags-only": settings(protected=["#EDITED"]),
}


def _scm(col):
    return col.db.scalar("select scm from col")


# ---- check 11 ----------------------------------------------------------------

@pytest.mark.parametrize("case", sorted(CASES))
@pytest.mark.parametrize("key", ["v1.3", "v1.3-newfield", "pharm-v2", "brandnew"])
def test_check11_counters(fx, user_col, run_import, key, case):
    s = CASES[case]
    scm0 = _scm(user_col)
    res = run_import(user_col, fx.package(key), s)
    exp = H.expected_counters(fx.before, fx.update(key), s)
    got = {k: getattr(res, k) for k in COUNTERS}
    wrong = {k: (exp[k], got[k]) for k in COUNTERS if exp[k] != got[k]}
    assert not wrong, "ImportResult counters for %s / %s, {counter: (expected, got)}: %s" % (key, case, wrong)
    assert sum(v for v in (res.skip_reasons or {}).values()) == 0, (
        "nothing was skipped, skip_reasons should be empty: %r" % res.skip_reasons)
    scm_changed = _scm(user_col) != scm0
    assert res.note_types_changed == scm_changed, (
        "note_types_changed=%r but the schema-modified marker %s"
        % (res.note_types_changed, "changed" if scm_changed else "did not change"))
    assert res.changes is not None, "ImportResult.changes should carry the OpChanges"


def test_check11_note_types_changed_flag_on_schema_change(fx, user_col, run_import):
    res = run_import(user_col, fx.package("v1.3-newfield"), DEFAULTS)
    assert res.note_types_changed is True, (
        "v1.3-newfield adds a field (schema change, next sync is a full sync): "
        "note_types_changed should be True")


def test_check11_no_schema_change_for_v13(fx, user_col, run_import):
    res = run_import(user_col, fx.package("v1.3"), DEFAULTS)
    assert res.note_types_changed is False, (
        "v1.3 changes no field or template structure: note_types_changed should be False")


def test_check11_reimport_partitions_notes_in_file(fx, user_col, run_import):
    """Second import of the same file: every note in it is added, updated or skipped."""
    run_import(user_col, fx.package("v1.3"), DEFAULTS)
    res = run_import(user_col, fx.package("v1.3"), DEFAULTS)
    assert res.notes_in_file == len(fx.update("v1.3"))
    total = res.notes_added + res.notes_updated + res.notes_skipped
    assert total == res.notes_in_file, (
        "notes_added (%d) + notes_updated (%d) + notes_skipped (%d) should equal notes_in_file (%d)"
        % (res.notes_added, res.notes_updated, res.notes_skipped, res.notes_in_file))
    assert sum((res.skip_reasons or {}).values()) == res.notes_skipped, (
        "skip_reasons %r should account for all %d skipped notes" % (res.skip_reasons, res.notes_skipped))


# ---- check 12 ----------------------------------------------------------------

def test_check12_locally_newer_notes_still_get_the_update(fx, user_col, run_import):
    res = run_import(user_col, fx.package("v1.3"), DEFAULTS)
    upd = fx.update("v1.3")
    after = H.notes_by_guid(user_col)
    by_nid = fx.before_by_nid()
    later = [by_nid[n] for n in fx.m["user"]["later_edited_nids"] if by_nid[n].guid in upd]
    assert later
    stale = []
    for old in later:
        u, got = upd[old.guid], after[old.guid]
        for name, val in u.fields.items():
            if not DEFAULTS.keeps_field(name) and got.field(name) != val:
                stale.append((old.nid, name, val, got.field(name)))
    assert not stale, (
        "%d field values on locally newer notes did not take the update; first (nid, field, expected, got): %s"
        % (len(stale), stale[:5]))
    assert res.notes_updated == len([g for g in upd if g in fx.before]), (
        "every existing note in the file should be reported updated, including locally newer ones")
