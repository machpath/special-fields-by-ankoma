"""Check 6: card templates and styling (contract rule 5)."""

from __future__ import annotations

import pytest

import sfa_acc_helpers as H
from sfa_acc_helpers import DEFAULTS, settings


def _with(s, update_note_types):
    return settings(keep=[f.name for f in s.fields if f.keep],
                    take=[f.name for f in s.fields if not f.keep],
                    protected=s.protected_tags, update_note_types=update_note_types)


@pytest.mark.parametrize("key", ["v1.3", "v1.3-newfield"])
def test_check06_true_takes_the_updates_templates_and_css(fx, user_col, run_import, key):
    s = _with(DEFAULTS, True)
    run_import(user_col, fx.package(key), s)
    got = H.notetype_looks(user_col)
    ref = fx.update_looks(key)
    for name in fx.m["constants"]["notetypes"]:
        assert got[name]["css"] == ref[name]["css"], (
            "%s [%s, update_note_types=True]: CSS should be the update's.\n expected %r\n got      %r"
            % (name, key, ref[name]["css"], got[name]["css"]))
        assert got[name]["tmpls"] == ref[name]["tmpls"], (
            "%s [%s, update_note_types=True]: templates should be the update's.\n expected %r\n got      %r"
            % (name, key, ref[name]["tmpls"], got[name]["tmpls"]))
    for name in fx.m["user"]["css_tweaked_notetypes"]:
        assert "USER dark-mode tweak" not in got[name]["css"], "%s: user CSS tweak should be replaced" % name


@pytest.mark.parametrize("key", ["v1.3", "v1.3-newfield"])
def test_check06_false_keeps_templates_and_css_byte_identical(fx, user_col, run_import, key):
    s = _with(DEFAULTS, False)
    res = run_import(user_col, fx.package(key), s)
    got = H.notetype_looks(user_col)
    before = fx.before_looks
    for name in fx.m["constants"]["notetypes"]:
        assert got[name]["css"] == before[name]["css"], (
            "%s [%s, update_note_types=False]: CSS must stay byte-identical.\n before %r\n after  %r"
            % (name, key, before[name]["css"], got[name]["css"]))
        assert got[name]["tmpls"] == before[name]["tmpls"], (
            "%s [%s, update_note_types=False]: templates must stay byte-identical.\n before %r\n after  %r"
            % (name, key, before[name]["tmpls"], got[name]["tmpls"]))
    # note content still updates either way
    after = H.notes_by_guid(user_col)
    problems = H.check_import_outcome(fx.before, fx.update(key), after, s)
    assert not problems, H.fail_msg(problems, "%s with update_note_types=False: note content" % key)
    if key == "v1.3-newfield":
        nt = fx.m["constants"]["newfield_notetype"]
        f = fx.m["constants"]["newfield_name"]
        assert f in got[nt]["fields"], (
            "%s: new field %r must exist on the note type even with update_note_types=False; fields %s"
            % (nt, f, got[nt]["fields"]))
        upd = fx.update(key)
        with_data = [g for g, n in upd.items() if n.notetype == nt and n.field(f)]
        assert with_data
        wrong = [(after[g].nid, after[g].field(f)) for g in with_data if after[g].field(f) != upd[g].field(f)]
        assert not wrong, "new field %r should receive the update's data; %d notes wrong, e.g. %s" % (
            f, len(wrong), wrong[:5])
    # the switch changes styling only: which notes were updated, added and
    # how many values were put back is exactly as with the switch on
    exp = H.expected_counters(fx.before, fx.update(key), s)
    got = {k: getattr(res, k) for k in exp}
    assert got == exp, "%s with update_note_types=False, counters {name: (expected, got)}: %s" % (
        key, {k: (exp[k], got[k]) for k in exp if exp[k] != got[k]})
    assert res.note_types_changed is (key == "v1.3-newfield"), (
        "%s: note_types_changed should be %s" % (key, key == "v1.3-newfield"))
