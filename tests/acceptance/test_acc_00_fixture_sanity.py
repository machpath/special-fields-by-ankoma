"""The fixtures themselves are meaningful (no engine involved).

If one of these fails, the acceptance results below it can't be trusted:
the fixture would not exercise the rule it is meant to test.
"""

from __future__ import annotations

import sfa_acc_helpers as H
from special_fields_by_ankoma.model import norm_tag


def test_fixture_has_all_eight_ankoma_note_types_with_exact_fields(fx):
    ref = fx.update_looks("v1.2")
    for name, fields in fx.m["constants"]["notetypes"].items():
        assert name in ref, "v1.2 package should contain note type %r; has %s" % (name, sorted(ref))
        assert ref[name]["fields"] == fields, (
            "note type %r should have fields %s, has %s" % (name, fields, ref[name]["fields"]))


def test_every_existing_note_is_changed_by_v13(fx):
    upd = fx.update("v1.3")
    v12 = fx.update("v1.2")
    unchanged = [g for g, n in v12.items() if g in upd and upd[g].fields == n.fields]
    assert not unchanged, "v1.3 should edit every v1.2 note; %d unchanged" % len(unchanged)
    assert len(upd) > len(v12), "v1.3 should add new notes (has %d vs %d)" % (len(upd), len(v12))


def test_v13_moves_tags_and_reorganises_levels(fx):
    upd = fx.update("v1.3")
    tags = set(t for n in upd.values() for t in n.tags)
    assert not any(t.startswith("##ANKOMA-v1.2") for t in tags), "v1.3 should carry no v1.2 tags"
    assert any("::AP::chest::breast" in t for t in tags), "v1.3 should have AP::chest::breast"
    before_tags = set(t for n in fx.before.values() for t in n.tags)
    assert any("::AP::Breast" in t for t in before_tags), "user (v1.2) should have AP::Breast tags"


def test_v13_changes_templates_and_css_of_every_ankoma_note_type(fx):
    v12, v13 = fx.update_looks("v1.2"), fx.update_looks("v1.3")
    for name in fx.m["constants"]["notetypes"]:
        assert v12[name]["css"] != v13[name]["css"], "%s: v1.3 CSS should differ" % name
        assert v12[name]["tmpls"] != v13[name]["tmpls"], "%s: v1.3 templates should differ" % name


def test_newfield_package_appends_one_field(fx):
    nt = fx.m["constants"]["newfield_notetype"]
    f = fx.m["constants"]["newfield_name"]
    looks = fx.update_looks("v1.3-newfield")
    assert looks[nt]["fields"] == fx.m["constants"]["notetypes"][nt] + [f]
    filled = [n for n in fx.update("v1.3-newfield").values() if n.notetype == nt and n.field(f)]
    assert filled, "the new field should carry data in v1.3-newfield"


def test_simulated_user_has_every_kind_of_customisation(fx):
    u = fx.m["user"]
    for role, nids in u["roles"].items():
        assert nids, "user role %r is empty" % role
    assert u["moved_card_ids"] and u["split_card_ids"], "user should have moved cards"
    assert u["reviewed_card_ids"], "user should have review history"
    assert u["later_edited_nids"], "user should have later edits"
    looks, ref = fx.before_looks, fx.update_looks("v1.2")
    for name in u["css_tweaked_notetypes"]:
        assert looks[name]["css"] != ref[name]["css"], "%s CSS should be tweaked by the user" % name
    tags = set(norm_tag(t) for n in fx.before.values() for t in n.tags)
    for t in ("#edited", "#edited::images", "#edited2", "mytag::exam"):
        assert t in tags, "user should have tag %r" % t
    pn = [n for n in fx.before.values() if (n.field("Personal Notes") or "").startswith("MY NOTE")]
    assert pn, "user should have Personal Notes filled in"


def test_later_edits_are_newer_than_the_update(fx):
    """Rule 12 precondition: local mtime > incoming mtime for edited notes."""
    upd = fx.update("v1.3")
    by_nid = fx.before_by_nid()
    for nid in fx.m["user"]["later_edited_nids"]:
        old = by_nid[nid]
        if old.guid in upd:
            assert old.mod > upd[old.guid].mod, (
                "note %s: local mtime %s should be after the update's %s"
                % (nid, old.mod, upd[old.guid].mod))


def test_stock_if_newer_import_skips_later_edits(fx, user_col):
    """Shows the trap the add-on exists to avoid: Anki's default skips them."""
    import build_fixtures

    log = build_fixtures.stock_import(user_col, fx.package("v1.3")).log
    # "duplicate" = skipped as not newer. Notes of the note type the user
    # added a field to are "conflicting" instead (schema differs, merge off):
    # also not updated.
    skipped = {x.id.nid for x in log.duplicate} | {x.id.nid for x in log.conflicting}
    later = set(fx.m["user"]["later_edited_nids"]) & {n.nid for g, n in fx.before.items()
                                                      if g in fx.update("v1.3")}
    assert later and later <= skipped, (
        "stock IF_NEWER import should skip every later-edited note; %d of %d skipped"
        % (len(later & skipped), len(later)))
