"""Checks 9-10: scheduling and review log; one undo step (contract rules 6-7)."""

from __future__ import annotations

import pytest

import sfa_acc_helpers as H
from sfa_acc_helpers import settings
from special_fields_by_ankoma.model import UNDO_LABEL

BUSY = settings(keep=["Personal Notes", "Header", "Remarks"], protected=["#edited", "mytag"])


# ---- check 9 ---------------------------------------------------------------

@pytest.mark.parametrize("key", ["v1.3", "v1.3-newfield"])
@pytest.mark.parametrize("update_note_types", [True, False])
def test_check09_scheduling_and_revlog_identical(fx, user_col, run_import, key, update_note_types):
    s = settings(keep=["Personal Notes", "Header"], protected=["#edited"],
                 update_note_types=update_note_types)
    before_cards = H.card_rows(user_col)
    before_revlog = H.revlog_rows(user_col)
    reviewed = set(fx.m["user"]["reviewed_card_ids"])
    assert reviewed and {r[1] for r in before_revlog} >= reviewed, "fixture should have review history"
    run_import(user_col, fx.package(key), s)
    after_cards = H.card_rows(user_col, before_cards)
    missing = sorted(set(before_cards) - set(after_cards))
    assert not missing, "existing cards disappeared: %s" % missing[:10]
    changed = [(cid, before_cards[cid], after_cards[cid]) for cid in before_cards
               if before_cards[cid] != after_cards[cid]]
    assert not changed, (
        "%d existing cards changed (all columns of `cards` must be identical). First: id=%s\n before %r\n after  %r"
        % (len(changed), changed[0][0], changed[0][1], changed[0][2]))
    after_revlog = H.revlog_rows(user_col, before_cards)
    assert after_revlog == before_revlog, (
        "review log of existing cards must be identical: %d rows before, %d after"
        % (len(before_revlog), len(after_revlog)))


# ---- check 10 ----------------------------------------------------------------

@pytest.mark.parametrize("key", ["v1.3", "v1.3-newfield", "brandnew"])
def test_check10_one_undo_step_restores_exactly(fx, user_col, run_import, key):
    assert user_col.undo_status().undo == "", "precondition: freshly opened collection has no undo history"
    state0 = H.db_state(user_col)
    run_import(user_col, fx.package(key), BUSY)
    st = user_col.undo_status()
    assert st.undo == UNDO_LABEL, "undo menu should offer %r, offers %r" % (UNDO_LABEL, st.undo)
    user_col.undo()
    st = user_col.undo_status()
    assert st.undo == "", (
        "after ONE undo there should be nothing left to undo (the import must be a single step); "
        "next undo step is %r" % st.undo)
    diffs = H.diff_db_state(state0, H.db_state(user_col))
    assert not diffs, "undo should restore the collection exactly:\n  " + "\n  ".join(diffs)


def test_check10_undo_after_prior_user_action_leaves_that_action(fx, user_col, run_import):
    """The user's own earlier step stays below ours, untouched."""
    nid = fx.m["user"]["roles"]["untouched"][0]
    n = user_col.get_note(nid)
    n.tags.append("before-import")
    user_col.update_note(n)
    prior = user_col.undo_status().undo
    assert prior, "precondition: the user's edit is undoable"
    state0 = H.db_state(user_col)
    run_import(user_col, fx.package("v1.3"), BUSY)
    assert user_col.undo_status().undo == UNDO_LABEL
    user_col.undo()
    assert user_col.undo_status().undo == prior, (
        "after undoing the import, the next step should be the user's %r, is %r"
        % (prior, user_col.undo_status().undo))
    diffs = H.diff_db_state(state0, H.db_state(user_col))
    assert not diffs, "undo should restore the collection exactly:\n  " + "\n  ".join(diffs)
