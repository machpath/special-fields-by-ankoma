"""Checks 4-5: tags (contract rules 3-4)."""

from __future__ import annotations

import pytest

import sfa_acc_helpers as H
from sfa_acc_helpers import settings
from special_fields_by_ankoma.model import is_protected_tag, norm_tag


def _run(fx, col, run_import, key, s):
    res = run_import(col, fx.package(key), s)
    return res, H.notes_by_guid(col)


def _notes_with(fx, protected):
    upd = fx.update("v1.3")
    return [n for g, n in fx.before.items()
            if g in upd and any(is_protected_tag(t, protected) for t in n.tags)]


# ---- check 4: protected tags and sub-tags --------------------------------

@pytest.mark.parametrize("protected", [("#edited",), ("#EDITED ",)], ids=["exact", "case+space"])
def test_check04_protected_tag_and_subtags_stay_rest_updates(fx, user_col, run_import, protected):
    """No fields kept, '#edited' protected: every #edited / #edited::* stays; all else updates."""
    s = settings(protected=protected)
    _, after = _run(fx, user_col, run_import, "v1.3", s)
    problems = H.check_import_outcome(fx.before, fx.update("v1.3"), after, s)
    assert not problems, H.fail_msg(problems, "protected %r, no fields kept" % (protected,))
    had = _notes_with(fx, ("#edited",))
    subs = {norm_tag(t) for n in had for t in n.tags if norm_tag(t).startswith("#edited::")}
    assert "#edited::images" in subs, "fixture should have #edited::images notes"
    for old in had:
        got = after[old.guid]
        for t in old.tags:
            if is_protected_tag(t, ("#edited",)):
                assert t in got.tags, "nid=%s: protected tag %r should stay; tags now %s" % (
                    old.nid, t, got.tags)
        assert not any(norm_tag(t) in ("#edited2", "mytag", "mytag::exam") for t in got.tags), (
            "nid=%s: unprotected personal tags should be gone: %s" % (old.nid, got.tags))
        assert not any(t.startswith("##ANKOMA-v1.2") for t in got.tags), (
            "nid=%s: the rest of the tags should update (v1.2 tags left): %s" % (old.nid, got.tags))
        pn = got.field("Personal Notes")
        assert pn is None or not pn.startswith("MY NOTE"), (
            "nid=%s: no fields kept, so Personal Notes should take the update's" % old.nid)
    lookalike = [n for n in fx.before.values() if any(norm_tag(t) == "#edited2" for t in n.tags)]
    assert lookalike
    for old in lookalike:
        if old.guid in fx.update("v1.3"):
            assert not any(norm_tag(t) == "#edited2" for t in after[old.guid].tags), (
                "nid=%s: '#edited2' is not a sub-tag of '#edited' and must be removed" % old.nid)


def test_check04_protect_only_subtag(fx, user_col, run_import):
    """Protecting '#edited::images' keeps that sub-tag but not its parent '#edited'."""
    s = settings(protected=["#edited::images"])
    _, after = _run(fx, user_col, run_import, "v1.3", s)
    problems = H.check_import_outcome(fx.before, fx.update("v1.3"), after, s)
    assert not problems, H.fail_msg(problems, "protect #edited::images only")


def test_check04_protected_tags_with_kept_fields(fx, user_col, run_import):
    s = settings(keep=["Personal Notes", "Remarks"], protected=["#edited", "mytag::exam"])
    _, after = _run(fx, user_col, run_import, "v1.3", s)
    problems = H.check_import_outcome(fx.before, fx.update("v1.3"), after, s)
    assert not problems, H.fail_msg(problems, "kept fields + protected tags")


def test_check04_protecting_an_old_author_tag_keeps_it_with_subtags(fx, user_col, run_import):
    """Protecting '##ANKOMA-v1.2::AP::Breast' keeps those v1.2 tags beside the new v1.3 ones."""
    p = "##ANKOMA-v1.2::AP::Breast"
    s = settings(protected=[p])
    _, after = _run(fx, user_col, run_import, "v1.3", s)
    problems = H.check_import_outcome(fx.before, fx.update("v1.3"), after, s)
    assert not problems, H.fail_msg(problems, "protect %s" % p)
    had = _notes_with(fx, (p,))
    assert had
    for old in had:
        got = after[old.guid]
        assert any(t.startswith(p) for t in got.tags) and any(
            "##ANKOMA-v1.3::AP::chest::breast" in t for t in got.tags), (
            "nid=%s: should keep %s* and get the v1.3 tag: %s" % (old.nid, p, got.tags))


# ---- check 5: all other tags are replaced --------------------------------

def test_check05_tags_replaced_with_the_updates(fx, user_col, run_import):
    s = settings(keep=["Personal Notes"])
    _, after = _run(fx, user_col, run_import, "v1.3", s)
    upd = fx.update("v1.3")
    problems = H.check_import_outcome(fx.before, upd, after, s)
    assert not problems, H.fail_msg(problems, "no protected tags: tags = the update's")
    ankoma = [g for g in upd]
    leftover_v12 = [after[g].nid for g in ankoma if any(t.startswith("##ANKOMA-v1.2") for t in after[g].tags)]
    assert not leftover_v12, "%d notes still have ##ANKOMA-v1.2 tags" % len(leftover_v12)
    personal = [after[g].nid for g in ankoma if any(
        norm_tag(t).split("::")[0] in ("#edited", "#edited2", "mytag") for t in after[g].tags)]
    assert not personal, "%d notes kept unprotected personal tags" % len(personal)
    breast = [g for g in ankoma if g in fx.before and any("::AP::Breast" in t for t in fx.before[g].tags)]
    assert breast
    for g in breast:
        assert any("##ANKOMA-v1.3::AP::chest::breast" in t for t in after[g].tags), (
            "nid=%s: reorganised level AP::Breast -> AP::chest::breast missing: %s"
            % (after[g].nid, after[g].tags))
        assert not any("::AP::Breast" in t for t in after[g].tags)
