"""Checks 1-3: field toggles (contract rule 2)."""

from __future__ import annotations

import pytest

import sfa_acc_helpers as H
from sfa_acc_helpers import DEFAULTS, settings

ALL_FIELD_NAMES = sorted({
    "Header", "Text", "Images", "Extra", "Personal Notes", "Textbook", "Citation",
    "ID (hidden)", "Image", "Question Mask", "Footer", "Remarks", "Sources",
    "Extra 1", "Extra 2", "Answer Mask", "Original Mask",
})


def _run(fx, col, run_import, key, s):
    res = run_import(col, fx.package(key), s)
    return res, H.notes_by_guid(col)


# ---- check 1: each toggle keeps or overwrites exactly that field ----------

@pytest.mark.parametrize("field", ALL_FIELD_NAMES)
def test_check01_keep_only_this_field(fx, user_col, run_import, field):
    """Keeping one field keeps exactly that field; every other field takes the update."""
    s = settings(keep=[field])
    _, after = _run(fx, user_col, run_import, "v1.3", s)
    upd = fx.update("v1.3")
    problems = H.check_import_outcome(fx.before, upd, after, s)
    assert not problems, H.fail_msg(problems, "keep only %r, import v1.3" % field)
    # the toggle mattered: some note kept a value that differs from the update's
    kept = [g for g, old in fx.before.items() if g in upd and old.has_field(field)
            and old.field(field) != upd[g].field(field)]
    assert kept, "fixture should have notes whose %r differs from the update's" % field
    for g in kept:
        assert after[g].field(field) == fx.before[g].field(field), (
            "nid=%s: %r should be kept as %r, is %r"
            % (after[g].nid, field, fx.before[g].field(field), after[g].field(field)))


def test_check01_take_update_for_every_field(fx, user_col, run_import):
    """All toggles on "Take the update's": every field, Personal Notes included, is the update's."""
    s = settings(take=ALL_FIELD_NAMES)
    _, after = _run(fx, user_col, run_import, "v1.3", s)
    upd = fx.update("v1.3")
    problems = H.check_import_outcome(fx.before, upd, after, s)
    assert not problems, H.fail_msg(problems, "take the update's for every field")
    pn_left = [after[g].nid for g in upd if (after[g].field("Personal Notes") or "").startswith("MY NOTE")]
    assert not pn_left, "Personal Notes set to Take the update's should be overwritten; %d kept" % len(pn_left)


def test_check01_keep_every_field(fx, user_col, run_import):
    """All toggles on "Keep mine": every existing note keeps all its field values."""
    s = settings(keep=ALL_FIELD_NAMES)
    _, after = _run(fx, user_col, run_import, "v1.3", s)
    problems = H.check_import_outcome(fx.before, fx.update("v1.3"), after, s)
    assert not problems, H.fail_msg(problems, "keep every field")


def test_check01_defaults_keep_only_personal_notes(fx, user_col, run_import):
    """The shipped defaults: Personal Notes kept, Text/Extra/... take the update's."""
    _, after = _run(fx, user_col, run_import, "v1.3", DEFAULTS)
    problems = H.check_import_outcome(fx.before, fx.update("v1.3"), after, DEFAULTS)
    assert not problems, H.fail_msg(problems, "default settings")
    by_nid = fx.before_by_nid()
    for nid in fx.m["user"]["roles"]["text_extra"]:
        g = by_nid[nid].guid
        if after[g].has_field("Text"):
            assert "user typo fix" not in after[g].field("Text"), (
                "nid=%s: Text is Take the update's, the user's edit should be gone" % nid)


def test_check01_field_names_match_ignoring_case_and_spaces(fx, user_col, run_import):
    """'  personal NOTES ' and 'EXTRA' in the settings match the note types' fields."""
    s = settings(keep=["  personal NOTES ", "EXTRA"], take=["text"])
    _, after = _run(fx, user_col, run_import, "v1.3", s)
    problems = H.check_import_outcome(fx.before, fx.update("v1.3"), after, s)
    assert not problems, H.fail_msg(problems, "case/space-insensitive field names")
    kept = [g for g, n in fx.before.items() if (n.field("Personal Notes") or "").startswith("MY NOTE")]
    assert kept and all(after[g].field("Personal Notes") == fx.before[g].field("Personal Notes")
                        for g in kept), "Personal Notes should be kept via '  personal NOTES '"


def test_check01_unknown_field_name_is_harmless(fx, user_col, run_import):
    s = settings(keep=["Personal Notes", "No Such Field Anywhere"])
    _, after = _run(fx, user_col, run_import, "v1.3", s)
    problems = H.check_import_outcome(fx.before, fx.update("v1.3"), after, s)
    assert not problems, H.fail_msg(problems, "a kept field no note type has")


# ---- check 2: AP and CP in one file, Header kept -------------------------

def test_check02_header_kept_applies_to_ap_and_skips_cp(fx, user_col, run_import):
    s = settings(keep=["Header", "Personal Notes"], take=["Text", "Extra", "Citation"])
    _, after = _run(fx, user_col, run_import, "v1.3", s)
    upd = fx.update("v1.3")
    problems = H.check_import_outcome(fx.before, upd, after, s)
    assert not problems, H.fail_msg(problems, "Header kept, AP + CP in one file")
    by_nid = fx.before_by_nid()
    ap = [by_nid[n] for n in fx.m["user"]["roles"]["header_edit"]
          if by_nid[n].notetype.startswith("Cloze-Ankoma-AP")]
    assert ap, "fixture should have AP notes with a user-edited Header"
    for old in ap:
        assert after[old.guid].field("Header") == old.field("Header"), (
            "AP nid=%s: Header should stay %r, is %r" % (old.nid, old.field("Header"),
                                                          after[old.guid].field("Header")))
    cp = [g for g, n in fx.before.items() if n.notetype.startswith("Cloze-Ankoma-CP") and g in upd]
    assert cp, "fixture should have CP notes in the file"
    for g in cp:
        assert not after[g].has_field("Header"), "CP note types have no Header field"
        assert after[g].field("Text") == upd[g].field("Text"), (
            "CP nid=%s: Text should be the update's %r, is %r"
            % (after[g].nid, upd[g].field("Text"), after[g].field("Text")))


# ---- check 3: kept field that only another deck's note type has ----------

def test_check03_field_only_in_another_decks_notetype_is_kept(fx, user_col, run_import):
    """'My Mnemonic' exists only in the Pharm deck's note type; keeping it is honoured there."""
    s = settings(keep=["Personal Notes", "My Mnemonic"], take=["Text", "Extra"])
    _, after = _run(fx, user_col, run_import, "pharm-v2", s)
    upd = fx.update("pharm-v2")
    problems = H.check_import_outcome(fx.before, upd, after, s)
    assert not problems, H.fail_msg(problems, "keep 'My Mnemonic', import Pharm-v2")
    by_nid = fx.before_by_nid()
    edited = fx.m["user"]["pharm_edited_nids"]
    assert edited
    for nid in edited:
        g = by_nid[nid].guid
        assert after[g].field("My Mnemonic") == by_nid[nid].field("My Mnemonic"), (
            "nid=%s: My Mnemonic should stay %r, is %r"
            % (nid, by_nid[nid].field("My Mnemonic"), after[g].field("My Mnemonic")))
        assert after[g].field("Front") == upd[g].field("Front"), "Front should take the update's"


def test_check03_same_settings_on_ankoma_file(fx, user_col, run_import):
    """The same global settings (with 'My Mnemonic' and IO-only 'Remarks') work on the Ankoma file."""
    s = settings(keep=["Personal Notes", "My Mnemonic", "Remarks"])
    _, after = _run(fx, user_col, run_import, "v1.3", s)
    problems = H.check_import_outcome(fx.before, fx.update("v1.3"), after, s)
    assert not problems, H.fail_msg(problems, "keep My Mnemonic + Remarks, import v1.3")
