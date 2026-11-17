"""Checks 7-8: brand-new decks, deck placement (contract rule 6)."""

from __future__ import annotations

import sfa_acc_helpers as H
from sfa_acc_helpers import DEFAULTS, settings


# ---- check 7: a brand-new deck imports normally ---------------------------

def test_check07_brand_new_deck_into_users_collection(fx, user_col, run_import):
    before_cards = H.card_rows(user_col)
    res = run_import(user_col, fx.package("brandnew"), DEFAULTS)
    upd = fx.update("brandnew")
    after = H.notes_by_guid(user_col)
    problems = H.check_import_outcome(fx.before, upd, after, DEFAULTS)
    assert not problems, H.fail_msg(problems, "brand-new deck")
    assert res.notes_added == len(upd), "notes_added should be %d, is %d" % (len(upd), res.notes_added)
    assert res.notes_updated == 0, "nothing to update, notes_updated is %d" % res.notes_updated
    decks = H.card_decks_by_note_ord(user_col)
    ref_decks = fx.update_card_decks("brandnew")
    wrong = [(k, ref_decks[k], decks.get(k)) for k in ref_decks if decks.get(k) != ref_decks[k]]
    assert not wrong, "new cards should be in the package's deck; wrong: %s" % wrong[:5]
    after_cards = H.card_rows(user_col, before_cards)
    assert after_cards == before_cards, "existing cards must be untouched by a brand-new deck"


def test_check07_into_an_empty_collection(fx, empty_col, run_import):
    res = run_import(empty_col, fx.package("v1.3"), DEFAULTS)
    upd = fx.update("v1.3")
    after = H.notes_by_guid(empty_col)
    problems = H.check_import_outcome({}, upd, after, DEFAULTS)
    assert not problems, H.fail_msg(problems, "v1.3 into an empty collection")
    assert res.notes_added == len(upd), "notes_added should be %d, is %d" % (len(upd), res.notes_added)
    assert H.card_decks_by_note_ord(empty_col) == fx.update_card_decks("v1.3"), (
        "every card should be in the release's deck")


# ---- check 8: moved cards stay; new notes land in the release's deck ------

def test_check08_moved_cards_stay_new_notes_in_release_deck(fx, user_col, run_import):
    s = settings(keep=["Personal Notes"], protected=["#edited"])
    before_cards = H.card_rows(user_col)
    run_import(user_col, fx.package("v1.3"), s)
    names = H.deck_name_by_id(user_col)
    after_cards = H.card_rows(user_col)
    u = fx.m["user"]
    for cid in u["moved_card_ids"]:
        assert names[after_cards[cid][2]] == u["user_deck"], (
            "card %s was moved to %r by the user; now in %r" % (cid, u["user_deck"], names[after_cards[cid][2]]))
    for cid in u["split_card_ids"]:
        assert names[after_cards[cid][2]] == u["user_split_deck"], (
            "card %s was moved to %r by the user; now in %r"
            % (cid, u["user_split_deck"], names[after_cards[cid][2]]))
    moved_deck = [cid for cid, row in before_cards.items() if after_cards.get(cid, (0, 0, None))[2] != row[2]]
    assert not moved_deck, "%d existing cards changed deck, e.g. %s" % (len(moved_deck), moved_deck[:5])
    decks = H.card_decks_by_note_ord(user_col)
    ref = fx.update_card_decks("v1.3")
    new_guids = {n["guid"] for n in fx.m["v13"]["new_notes"]}
    assert any(n["deck"] == fx.m["constants"]["new_subdeck"] for n in fx.m["v13"]["new_notes"])
    wrong = [(k, ref[k], decks.get(k)) for k in ref if k[0] in new_guids and decks.get(k) != ref[k]]
    assert not wrong, "new notes' cards should be in the release's deck; wrong (key, expected, got): %s" % wrong[:5]


def test_check08_new_card_of_existing_note_goes_to_release_deck(fx, user_col, run_import):
    """HANDOFF assumption: a new card (c3) on an existing note goes to the deck named in the release."""
    run_import(user_col, fx.package("v1.3"), DEFAULTS)
    decks = H.card_decks_by_note_ord(user_col)
    ref = fx.update_card_decks("v1.3")
    guids = fx.m["v13"]["c3_note_guids"]
    assert guids
    for g in guids:
        assert (g, 2) in decks, "note %s should have gained its c3 card (ord 2)" % g
        assert decks[(g, 2)] == ref[(g, 2)], "c3 card of %s should be in %r, is in %r" % (
            g, ref[(g, 2)], decks[(g, 2)])
