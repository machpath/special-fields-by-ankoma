"""Check 13: full-size run (about 18,600 notes / 24,300 cards). Marked slow.

Run with:  python -m pytest tests/acceptance -m slow -s
Reports wall time, peak RSS during the call (Linux: VmHWM after resetting it
via /proc/self/clear_refs) and peak Python heap (tracemalloc), prints them and
writes them to /tmp/sfa-d/results/fullsize-<anki>-py<X.Y>.json.

The contract's target is "comparable to the prototype (about 1 second)". The
test fails above SFA_FULL_MAX_SECONDS (default 5 s) so a gross regression is
visible; the measured figures are the real result.
"""

from __future__ import annotations

import json
import os
import sys
import time
import tracemalloc

import pytest

import build_fixtures
import sfa_acc_helpers as H
from sfa_acc_helpers import settings


def _vm(key):
    try:
        with open("/proc/self/status") as f:
            for line in f:
                if line.startswith(key + ":"):
                    return int(line.split()[1]) * 1024
    except OSError:
        pass
    return None


def _reset_peak_rss() -> bool:
    try:
        with open("/proc/self/clear_refs", "w") as f:
            f.write("5")
        return True
    except OSError:
        return False


@pytest.mark.slow
@pytest.mark.parametrize("key", ["v1.3", "v1.3-moved"])
def test_check13_full_size_run(tmp_path, run_import, key):
    root = os.environ.get("SFA_FIXTURE_ROOT")
    out = (os.path.join(root, os.path.basename(os.path.dirname(build_fixtures.default_out_dir("full"))), "full")
           if root else build_fixtures.default_out_dir("full"))
    t = time.time()
    m = build_fixtures.ensure(out, "full", verbose=True)
    build_s = time.time() - t
    assert m["user_counts"]["notes"] >= 18600 and m["user_counts"]["cards"] >= 24300, m["user_counts"]

    col = H.open_collection(H.copy_collection(m["user_collection"], str(tmp_path / "col")))
    try:
        before = H.notes_by_guid(col)
        before_cards = H.card_rows(col)
        s = settings(keep=["Personal Notes", "Remarks"], take=["Header", "Text", "Extra"],
                     protected=["#edited"])
        rss0 = _vm("VmRSS")
        reset = _reset_peak_rss()
        tracemalloc.start()
        t0 = time.perf_counter()
        res = run_import(col, m["packages"][key], s)
        secs = time.perf_counter() - t0
        _, py_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        hwm = _vm("VmHWM")

        # correctness at full size
        ref_dir = str(tmp_path / "ref")
        rc = H.open_collection(H.copy_collection(m["references"][key], ref_dir, "ref"))
        try:
            upd = H.notes_by_guid(rc)
        finally:
            rc.close()
        after = H.notes_by_guid(col)
        problems = H.check_import_outcome(before, upd, after, s)
        after_cards = H.card_rows(col, before_cards)
        if key == "v1.3-moved":
            # a note type change bumps mod/usn of the moved notes' cards;
            # compare everything else (all columns but mod and usn)
            def strip(row):
                return None if row is None else row[:4] + row[6:]
            cards_changed = sum(1 for c in before_cards if strip(before_cards[c]) != strip(after_cards.get(c)))
        else:
            cards_changed = sum(1 for c in before_cards if before_cards[c] != after_cards.get(c))
        exp = H.expected_counters(before, upd, s)
    finally:
        col.close()

    report = {
        "anki": build_fixtures.anki_version(), "python": sys.version.split()[0], "package": key,
        "notes_before": m["user_counts"]["notes"], "cards_before": m["user_counts"]["cards"],
        "notes_in_file": len(upd), "run_import_seconds": round(secs, 3),
        "engine_reported_seconds": getattr(res, "seconds", None),
        "rss_before_mb": round(rss0 / 2**20, 1) if rss0 else None,
        "peak_rss_during_call_mb": round(hwm / 2**20, 1) if (hwm and reset) else None,
        "peak_rss_is_process_lifetime": not reset,
        "python_heap_peak_mb": round(py_peak / 2**20, 1),
        "fixture_build_or_load_seconds": round(build_s, 1),
        "counters": {k: getattr(res, k, None) for k in exp}, "expected_counters": exp,
        "content_problems": len(problems), "existing_cards_changed": cards_changed,
    }
    os.makedirs("/tmp/sfa-d/results", exist_ok=True)
    path = "/tmp/sfa-d/results/fullsize-%s-%s-py%d.%d.json" % (key, report["anki"], *sys.version_info[:2])
    with open(path, "w") as f:
        json.dump(report, f, indent=1)
    print("\nFULL-SIZE RESULT " + json.dumps(report))

    assert not problems, H.fail_msg(problems, "full-size %s import" % key)
    assert cards_changed == 0, "%d existing cards changed at full size" % cards_changed
    wrong = {k: (exp[k], report["counters"][k]) for k in exp if exp[k] != report["counters"][k]}
    assert not wrong, "full-size counters {name: (expected, got)}: %s" % wrong
    limit = float(os.environ.get("SFA_FULL_MAX_SECONDS", "5"))
    assert secs <= limit, "run_import took %.2fs at full size (limit %.1fs, target ~1s)" % (secs, limit)
