"""End-to-end headless test of the Ankoma import strategy.

usage: python test_import.py WORKDIR [N_CLOZE N_IO]
Builds an author collection, exports v1.2 + v1.3 (+ a v1.3 with an added
field), simulates a user, and checks the requirements.
"""

from __future__ import annotations

import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from anki.buildinfo import version as ANKI_VERSION
from anki.collection import (
    AddNoteRequest,
    Collection,
    DeckIdLimit,
    ExportAnkiPackageOptions,
    ImportAnkiPackageOptions,
    ImportAnkiPackageRequest,
)

import ankoma_core as core

CLOZE_FIELDS = ["Header", "Text", "Images", "Extra", "Personal Notes", "Textbook", "Citation"]
IO_FIELDS = ["ID (hidden)", "Header", "Image", "Question Mask", "Footer", "Remarks",
             "Sources", "Extra 1", "Extra 2", "Answer Mask", "Original Mask"]

checks = []


def check(name, ok, detail=""):
    checks.append((name, bool(ok)))
    print(f"  [{'PASS' if ok else 'FAIL'}] {name} {detail}")


def make_notetypes(col):
    mm = col.models
    cz = mm.new("Ankoma Cloze")
    cz["type"] = 1  # MODEL_CLOZE
    for f in CLOZE_FIELDS:
        mm.add_field(cz, mm.new_field(f))
    t = mm.new_template("Cloze")
    t["qfmt"] = "{{Header}}<br>{{cloze:Text}}"
    t["afmt"] = "{{cloze:Text}}<br>{{Extra}}<br>{{Personal Notes}}<br>{{Images}}"
    mm.add_template(cz, t)
    cz["css"] = ".card{font-family:arial} /* author v1.2 */"
    mm.add(cz)
    io = mm.new("Image Occlusion Enhanced+")
    for f in IO_FIELDS:
        mm.add_field(io, mm.new_field(f))
    t = mm.new_template("IO Card")
    t["qfmt"] = "{{#Image}}{{Image}}{{/Image}}{{Question Mask}}"
    t["afmt"] = "{{Image}}{{Answer Mask}}<br>{{Remarks}}"
    mm.add_template(io, t)
    mm.add(io)
    return mm.by_name("Ankoma Cloze"), mm.by_name("Image Occlusion Enhanced+")


def build_author(path, n_cloze, n_io):
    col = Collection(path)
    cz, io = make_notetypes(col)
    did = col.decks.id("Ankoma::Cardiology")
    did2 = col.decks.id("Ankoma::IO")
    with open(os.path.join(col.media.dir(), "heart.png"), "wb") as f:
        f.write(b"\x89PNG fake v1.2")
    reqs = []
    for i in range(n_cloze):
        n = col.new_note(cz)
        two = i % 16000 < 5700  # -> ~24.3k cards at full scale
        n["Header"] = f"Header {i}"
        n["Text"] = f"Fact {i}: {{{{c1::alpha}}}}" + (" {{c2::beta}}" if two else "")
        n["Images"] = '<img src="heart.png">' if i % 100 == 0 else ""
        n["Extra"] = f"extra v1.2 {i}"
        n["Textbook"] = "Robbins ch.1"
        n["Citation"] = "PMID 1"
        n.tags = [f"##ANKOMA-v1.2::Cardio::Topic{i % 20}"]
        reqs.append(AddNoteRequest(note=n, deck_id=did))
    for i in range(n_io):
        n = col.new_note(io)
        n["ID (hidden)"] = f"io-{i}"
        n["Header"] = f"IO header {i}"
        n["Image"] = '<img src="heart.png">'
        n["Question Mask"] = "<svg>q</svg>"
        n["Remarks"] = f"remarks v1.2 {i}"
        n.tags = ["##ANKOMA-v1.2::IO"]
        reqs.append(AddNoteRequest(note=n, deck_id=did2))
    t = time.time()
    col.add_notes(reqs)
    print(f"  author: {col.note_count()} notes, {col.card_count()} cards ({time.time()-t:.1f}s)")
    return col


def export(col, out):
    opts = ExportAnkiPackageOptions(with_scheduling=False, with_deck_configs=False,
                                    with_media=True, legacy=False)
    n = col.export_anki_package(out_path=out, options=opts,
                                limit=DeckIdLimit(col.decks.id("Ankoma")))
    import zipfile
    print(f"  exported {n} notes -> {os.path.basename(out)} {zipfile.ZipFile(out).namelist()[:4]}")


def author_release_13(col, add_field=False):
    """Author edits Text/Extra on every note, retags v1.2 -> v1.3, changes CSS."""
    mm = col.models
    cz = mm.by_name("Ankoma Cloze")
    cz["css"] = ".card{font-family:helvetica} /* author v1.3 */"
    if add_field:
        mm.add_field(cz, mm.new_field("Mnemonic"))
    mm.update_dict(cz)
    with open(os.path.join(col.media.dir(), "heart.png"), "wb") as f:
        f.write(b"\x89PNG fake v1.3 changed")
    notes = []
    for nid in col.find_notes(""):
        n = col.get_note(nid)
        if "Text" in n:
            n["Text"] = n["Text"].replace("Fact", "Fact(v1.3)")
            n["Extra"] = n["Extra"].replace("v1.2", "v1.3")
        else:
            n["Remarks"] = n["Remarks"].replace("v1.2", "v1.3")
        n.tags = [t.replace("##ANKOMA-v1.2", "##ANKOMA-v1.3") for t in n.tags]
        notes.append(n)
    col.update_notes(notes)


def native_default_import(col, path):
    """What the stock dialog does with its default options."""
    return col.import_anki_package(ImportAnkiPackageRequest(
        package_path=path,
        options=ImportAnkiPackageOptions(merge_notetypes=False, update_notes=core.IF_NEWER,
                                         update_notetypes=core.IF_NEWER,
                                         with_scheduling=False, with_deck_configs=False)))


def simulate_user(col):
    """Returns ids to verify later."""
    cz = col.models.by_name("Ankoma Cloze")
    nids = sorted(col.find_notes('"note:Ankoma Cloze"'))
    q = max(10, len(nids) // 16)  # 1000 at full scale
    personal = nids[:q]
    text_edit = nids[q:q + max(5, q // 20)]
    tagged = nids[0:2 * q:2]
    notes = []
    for nid in set(personal) | set(text_edit) | set(tagged):
        n = col.get_note(nid)
        if nid in personal:
            n["Personal Notes"] = f"MY NOTE {nid}"
        if nid in text_edit:
            n["Text"] = n["Text"] + " (user typo fix)"
        if nid in tagged:
            n.tags.append("mytag::exam")
        notes.append(n)
    col.update_notes(notes)
    # move 500 cards to the user's own deck
    my_deck = col.decks.id("My Deck")
    moved = sorted(col.find_cards('"deck:Ankoma::Cardiology"'))[:min(500, len(nids) // 8)]
    col.set_deck(moved, my_deck)
    # give 300 cards review scheduling
    reviewed = sorted(col.find_cards('"deck:Ankoma::Cardiology"'))[len(nids) // 4:len(nids) // 4 + 300]
    col.sched.set_due_date(reviewed, "7")
    # user tweaks CSS (sleep: notetype/note mtimes have 1-second resolution)
    time.sleep(1.1)
    cz = col.models.by_name("Ankoma Cloze")
    cz["css"] += "\n/* USER dark-mode tweak */"
    col.models.update_dict(cz)
    # simulate that user edits happened *after* the author released v1.3
    col.db.execute("update notes set mod = mod + 3600 where id in " +
                   "(" + ",".join(map(str, set(personal) | set(text_edit) | set(tagged))) + ")")
    sched = {cid: col.db.first("select did, type, queue, due, ivl, factor, reps from cards where id=?", cid)
             for cid in moved + reviewed}
    return dict(personal=personal, text_edit=text_edit, tagged=tagged, moved=moved,
                reviewed=reviewed, my_deck=my_deck, sched=sched)


def copy_col(src_path, dst_path):
    shutil.copy(src_path, dst_path)
    sm = src_path.replace(".anki2", ".media")
    dm = dst_path.replace(".anki2", ".media")
    if os.path.exists(sm):
        shutil.copytree(sm, dm, dirs_exist_ok=True)
    return Collection(dst_path)


def main():
    work = sys.argv[1]
    n_cloze = int(sys.argv[2]) if len(sys.argv) > 2 else 16000
    n_io = int(sys.argv[3]) if len(sys.argv) > 3 else 2600
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    print(f"Anki {ANKI_VERSION}, Python {sys.version.split()[0]}")

    print("1) author builds v1.2")
    a = build_author(os.path.join(work, "author.anki2"), n_cloze, n_io)
    p12 = os.path.join(work, "Ankoma-v1.2.apkg")
    export(a, p12)
    time.sleep(1.1)  # note mtimes have 1s resolution
    print("2) author makes v1.3 (+ v1.3b with added field)")
    author_release_13(a)
    a.db.execute("update notes set mod = mod + 10")  # ensure distinct from v1.2 mtimes
    p13 = os.path.join(work, "Ankoma-v1.3.apkg")
    export(a, p13)
    a.close()
    time.sleep(1.1)
    a = Collection(os.path.join(work, "author.anki2"))
    cz = a.models.by_name("Ankoma Cloze")
    a.models.add_field(cz, a.models.new_field("Mnemonic"))
    a.models.update_dict(cz)
    p13b = os.path.join(work, "Ankoma-v1.3b-newfield.apkg")
    export(a, p13b)
    a.close()

    print("3) user imports v1.2 with stock defaults, then customises")
    upath = os.path.join(work, "user.anki2")
    u = Collection(upath)
    r = native_default_import(u, p12)
    print(f"  user: new={len(r.log.new)} notes, {u.card_count()} cards")
    info = simulate_user(u)
    u.close()
    time.sleep(1.1)

    print("4) BASELINE: stock dialog defaults (IF_NEWER) on v1.3")
    b = copy_col(upath, os.path.join(work, "baseline.anki2"))
    r = native_default_import(b, p13)
    print(f"  updated={len(r.log.updated)} duplicate(skipped)={len(r.log.duplicate)} conflicting={len(r.log.conflicting)}")
    n = b.get_note(info["text_edit"][0])
    check("IF_NEWER trap reproduced: locally-edited notes NOT updated by author",
          "Fact(v1.3)" not in n["Text"], f"(skipped={len(r.log.duplicate)})")
    b.close()

    print("5) OUR STRATEGY on v1.3")
    c = copy_col(upath, os.path.join(work, "ours.anki2"))
    scm0 = c.db.scalar("select scm from col")
    pre_cards = c.card_count()
    pre_revlog = c.db.scalar("select count() from revlog")
    s = core.Settings(protected_fields={"Personal Notes", "Remarks"}, tag_mode="merge")
    res = core.import_ankoma_package(c, p13, s)
    print(f"  {res}")
    n_p = c.get_note(info["personal"][5])
    n_t = c.get_note(info["text_edit"][0])
    check("protected field kept (Personal Notes)", n_p["Personal Notes"].startswith("MY NOTE"))
    check("overwritten field updated (Text) even on locally newer notes", "Fact(v1.3)" in n_t["Text"]
          and "user typo fix" not in n_t["Text"])
    check("overwritten field updated (Extra)", "v1.3" in n_p["Extra"])
    io_n = c.get_note(c.find_notes('"note:Image Occlusion Enhanced+"')[0])
    check("IO 'Remarks' protected -> kept local (author's v1.3 change discarded)", "v1.2" in io_n["Remarks"])
    tagged = c.get_note(info["tagged"][0])
    check("tags merge: author root bumped to v1.3, v1.2 gone, user tag kept",
          any(t.startswith("##ANKOMA-v1.3") for t in tagged.tags)
          and not any(t.startswith("##ANKOMA-v1.2") for t in tagged.tags)
          and "mytag::exam" in tagged.tags, str(tagged.tags))
    after = {cid: c.db.first("select did, type, queue, due, ivl, factor, reps from cards where id=?", cid)
             for cid in info["sched"]}
    check("moved cards stay in user's deck", all(c.get_card(cid).did == info["my_deck"] for cid in info["moved"]))
    check("scheduling of existing cards byte-identical", after == info["sched"])
    check("no cards added/removed", c.card_count() == pre_cards)
    check("revlog untouched", c.db.scalar("select count() from revlog") == pre_revlog)
    check("no schema change -> no forced full sync (same field schema)", c.db.scalar("select scm from col") == scm0)
    css = c.models.by_name("Ankoma Cloze")["css"]
    check("update_notetypes=ALWAYS replaces user CSS with author CSS (expected; product decision)",
          "author v1.3" in css and "USER" not in css)
    st = c.undo_status()
    check("single undo step labelled for us", st.undo == core.UNDO_LABEL, repr(st.undo))
    c.undo()
    n_t = c.get_note(info["text_edit"][0])
    check("undo restores pre-import state", "user typo fix" in n_t["Text"] and "Fact(v1.3)" not in n_t["Text"])
    c.close()

    print("6) schema change by author (added field 'Mnemonic')")
    d = copy_col(upath, os.path.join(work, "schema_nomerge.anki2"))
    r = d.import_anki_package(ImportAnkiPackageRequest(package_path=p13b, options=ImportAnkiPackageOptions(
        merge_notetypes=False, update_notes=core.ALWAYS, update_notetypes=core.ALWAYS)))
    check("merge_notetypes=False: cloze notes NOT updated (conflicting), duplicate notetype created",
          len(r.log.conflicting) == n_cloze and "Ankoma Cloze+" in [x.name for x in d.models.all_names_and_ids()],
          f"(conflicting={len(r.log.conflicting)})")
    d.close()
    d = copy_col(upath, os.path.join(work, "schema_merge_ifnewer.anki2"))
    r = d.import_anki_package(ImportAnkiPackageRequest(package_path=p13b, options=ImportAnkiPackageOptions(
        merge_notetypes=True, update_notes=core.IF_NEWER, update_notetypes=core.IF_NEWER)))
    check("TRAP: merge + IF_NEWER on schema change -> local notes rewritten 'now' first, so NONE of the cloze notes update",
          len(r.log.duplicate) >= n_cloze, f"(updated={len(r.log.updated)}, skipped={len(r.log.duplicate)})")
    d.close()
    e = copy_col(upath, os.path.join(work, "schema_merge.anki2"))
    scm0 = e.db.scalar("select scm from col")
    res = core.import_ankoma_package(e, p13b, s)
    print(f"  {res}")
    n_p = e.get_note(info["personal"][5])
    check("merge_notetypes=True: notes updated + protected kept + new field present",
          "Mnemonic" in n_p and n_p["Personal Notes"].startswith("MY NOTE") and "Fact(v1.3)" in n_p["Text"])
    check("schema change -> scm bumped -> next sync is a one-way FULL sync",
          e.db.scalar("select scm from col") != scm0)
    e.close()

    print(f"\nSUMMARY Anki {ANKI_VERSION}: {sum(ok for _, ok in checks)}/{len(checks)} checks passed")
    return 0 if all(ok for _, ok in checks) else 1


if __name__ == "__main__":
    sys.exit(main())
