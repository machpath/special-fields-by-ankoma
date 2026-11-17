#!/usr/bin/env python3
"""Build synthetic Ankoma-like fixtures for the acceptance tests (workstream D).

usage:
    python tools/build_fixtures.py [--size small|full] [--out DIR] [--force]

Everything is made with Anki's own API and exporter, headless (no Qt), so it
must run inside one of the per-version Anki environments. Output goes to
DIR (default /tmp/sfa-d/fixtures/<anki version>-py<X.Y>/<size>), never into
the project tree. A `fixtures.json` manifest in DIR describes what was built;
the acceptance tests read it.

What gets built (see `describe()` / the report for details):

  packages/Ankoma-v1.2.apkg            author's v1.2 release (8 Ankoma note types)
  packages/Ankoma-v1.3.apkg            v1.3: every note edited, tags moved to
                                       ##ANKOMA-v1.3 with some levels reorganized,
                                       new templates + CSS, new notes (one in a
                                       brand-new sub-deck), a new c3 card on
                                       some existing notes
  packages/Ankoma-v1.3-newfield.apkg   v1.3 plus "Board Pearls" appended to
                                       Cloze-Ankoma-AP (filled, used in a template)
  packages/Ankoma-v1.3-moved.apkg      v1.3 with some notes moved by the author to
                                       another existing note type (AP -> AP-
                                       Unrestricted, IOE -> IOE+, whose fields are
                                       in another order)
  packages/Pharm-v1.apkg / -v2.apkg    another author's deck whose note type
                                       has a field ("My Mnemonic") no Ankoma
                                       note type has
  packages/BrandNew.apkg               a deck the user has never imported
  reference/<package>.anki2            each package imported into an empty
                                       collection = "the update's" content
  user/user.anki2 (+ user.media)       the simulated user: v1.2 + Pharm-v1
                                       imported with Anki's stock defaults,
                                       then customised (see simulate_user)

Python 3.9 compatible (runs inside Anki 25.02's environment).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIXTURE_FORMAT = 4  # bump when the fixture layout or content changes

# ---------------------------------------------------------------------------
# Ankoma's note types (exact names and field lists from docs/CONTRACT.md)
# ---------------------------------------------------------------------------

AP_FIELDS = ["Header", "Text", "Extra", "Personal Notes", "Textbook", "Citation"]
AP_MULTI_FIELDS = ["Header", "Text", "Images", "Extra", "Personal Notes", "Textbook", "Citation"]
CP_FIELDS = ["Text", "Extra", "Personal Notes", "Citation"]
IOE_FIELDS = ["ID (hidden)", "Header", "Image", "Question Mask", "Footer", "Remarks",
              "Sources", "Extra 1", "Extra 2", "Answer Mask", "Original Mask"]
IOE_PLUS_FIELDS = ["ID (hidden)", "Header", "Image", "Footer", "Remarks", "Sources",
                   "Extra 1", "Extra 2", "Question Mask", "Answer Mask", "Original Mask"]

# name, is_cloze, fields, branch ("AP"/"CP"), full-size note count
NOTE_TYPES: List[Tuple[str, bool, List[str], str, int]] = [
    ("Cloze-Ankoma-AP", True, AP_FIELDS, "AP", 7000),
    ("Cloze-Ankoma-AP-Unrestricted", True, AP_FIELDS, "AP", 2000),
    ("Cloze-Ankoma-AP - multiple images", True, AP_MULTI_FIELDS, "AP", 1000),
    ("Cloze-Ankoma-CP", True, CP_FIELDS, "CP", 4000),
    ("Cloze-Ankoma-CP-Unrestricted", True, CP_FIELDS, "CP", 1200),
    ("Cloze-Ankoma-CP-Unrestricted+", True, CP_FIELDS, "CP", 800),
    ("Image Occlusion Enhanced", False, IOE_FIELDS, "AP", 1300),
    ("Image Occlusion Enhanced+", False, IOE_PLUS_FIELDS, "AP", 1300),
]
# full size: 18,600 notes; 16,000 cloze of which 5,700 have c1+c2 -> 24,300 cards

SMALL_COUNTS = {
    "Cloze-Ankoma-AP": 30,
    "Cloze-Ankoma-AP-Unrestricted": 20,
    "Cloze-Ankoma-AP - multiple images": 20,
    "Cloze-Ankoma-CP": 20,
    "Cloze-Ankoma-CP-Unrestricted": 20,
    "Cloze-Ankoma-CP-Unrestricted+": 20,
    "Image Occlusion Enhanced": 20,
    "Image Occlusion Enhanced+": 20,
}

AP_TOPICS = ["Breast", "Cardiac", "Pulmonary", "Renal", "GI", "Neuro"]
CP_TOPICS = ["Hematology", "Microbiology", "Chemistry", "Transfusion"]
ROOT_DECK = "Ankoma"
AP_DECK = "Ankoma::Ankoma - AP"
CP_DECK = "Ankoma::Ankoma - CP"
NEW_SUBDECK = "Ankoma::Ankoma - AP::Endocrine"  # first appears in v1.3

# v1.2 -> v1.3 tag reorganisation (below the version root)
TAG_REORG = {
    "AP::Breast": "AP::chest::breast",
    "AP::Cardiac": "AP::chest::cardiac",
    "CP::Transfusion": "CP::Hematology::Transfusion",
}

NEWFIELD_NOTETYPE = "Cloze-Ankoma-AP"
NEWFIELD_NAME = "Board Pearls"

# A field the simulated user added to one Ankoma note type themselves (not in
# any release), filled in on some notes (contract rule 9).
USER_FIELD_NOTETYPE = "Cloze-Ankoma-CP"
USER_FIELD_NAME = "My Mnemonic (mine)"

# Notes the author moves to another note type in v1.3-moved (rule 10):
# (from, to); every note of `from` whose position i has i % 9 == 4.
MOVES = (
    ("Cloze-Ankoma-AP", "Cloze-Ankoma-AP-Unrestricted"),
    ("Image Occlusion Enhanced", "Image Occlusion Enhanced+"),
)

PHARM_NOTETYPE = "Pharm-Basic"
PHARM_FIELDS = ["Front", "Back", "My Mnemonic"]
PHARM_DECK = "Pharm Deck"
BRANDNEW_NOTETYPE = "BrandNew-Basic"
BRANDNEW_FIELDS = ["Front", "Back", "Personal Notes"]
BRANDNEW_DECK = "Brand New Deck::Neuro"

USER_DECK = "My Deck"
USER_SPLIT_DECK = "My Deck::Split"

MEDIA_FILES = (
    ["ankoma_img_%d.png" % i for i in range(5)]
    + ["io_base_%d.png" % i for i in range(5)]
    + ["io_mask_%d.svg" % i for i in range(5)]
)


def anki_version() -> str:
    from anki.buildinfo import version

    return version


def builder_hash() -> str:
    with open(os.path.abspath(__file__), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16]


def default_out_dir(size: str) -> str:
    return os.path.join(
        "/tmp/sfa-d/fixtures",
        "%s-py%d.%d" % (anki_version(), sys.version_info[0], sys.version_info[1]),
        size,
    )


def _counts(size: str) -> Dict[str, int]:
    if size == "full":
        return {name: n for name, _, _, _, n in NOTE_TYPES}
    if size == "small":
        return dict(SMALL_COUNTS)
    raise ValueError("size must be 'small' or 'full', not %r" % size)


# ---------------------------------------------------------------------------
# Anki helpers
# ---------------------------------------------------------------------------


def _conditions():
    from anki.import_export_pb2 import ImportAnkiPackageUpdateCondition as C

    return (
        C.IMPORT_ANKI_PACKAGE_UPDATE_CONDITION_IF_NEWER,
        C.IMPORT_ANKI_PACKAGE_UPDATE_CONDITION_ALWAYS,
        C.IMPORT_ANKI_PACKAGE_UPDATE_CONDITION_NEVER,
    )


def stock_import(col, path: str):
    """What Anki's import screen does with its default options."""
    from anki.collection import ImportAnkiPackageOptions, ImportAnkiPackageRequest

    if_newer, _, _ = _conditions()
    return col.import_anki_package(ImportAnkiPackageRequest(
        package_path=path,
        options=ImportAnkiPackageOptions(
            merge_notetypes=False, update_notes=if_newer, update_notetypes=if_newer,
            with_scheduling=False, with_deck_configs=False)))


def reference_import(col, path: str):
    """Import into an EMPTY collection: gives the update's content as is."""
    from anki.collection import ImportAnkiPackageOptions, ImportAnkiPackageRequest

    _, always, _ = _conditions()
    return col.import_anki_package(ImportAnkiPackageRequest(
        package_path=path,
        options=ImportAnkiPackageOptions(
            merge_notetypes=True, update_notes=always, update_notetypes=always,
            with_scheduling=False, with_deck_configs=False)))


def export_deck(col, deck_name: str, out_path: str) -> int:
    from anki.collection import DeckIdLimit, ExportAnkiPackageOptions

    opts = ExportAnkiPackageOptions(with_scheduling=False, with_deck_configs=False,
                                    with_media=True, legacy=False)
    if os.path.exists(out_path):
        os.remove(out_path)
    return col.export_anki_package(out_path=out_path, options=opts,
                                   limit=DeckIdLimit(col.decks.id(deck_name)))


def add_notetype(col, name: str, fields: Sequence[str], cloze: bool,
                 qfmt: str, afmt: str, css: str) -> dict:
    mm = col.models
    nt = mm.new(name)
    if cloze:
        nt["type"] = 1  # MODEL_CLOZE
    for f in fields:
        mm.add_field(nt, mm.new_field(f))
    t = mm.new_template("Cloze" if cloze else "Card 1")
    t["qfmt"] = qfmt
    t["afmt"] = afmt
    mm.add_template(nt, t)
    nt["css"] = css
    mm.add(nt)
    return mm.by_name(name)


def _ankoma_templates(name: str, fields: Sequence[str], cloze: bool, version: str,
                      extra_field: Optional[str] = None) -> Tuple[str, str, str]:
    marker = "<!-- ankoma %s -->" % version
    if cloze:
        q = ("<div class=header>{{Header}}</div>" if "Header" in fields else "") + "{{cloze:Text}}"
        a = "{{cloze:Text}}<hr id=answer>{{Extra}}"
        if "Images" in fields:
            a += "<div class=images>{{Images}}</div>"
        a += "<div class=pn>{{Personal Notes}}</div>"
        if "Textbook" in fields:
            a += "<div class=tb>{{Textbook}}</div>"
        a += "<div class=cite>{{Citation}}</div>"
    else:
        q = "{{#Image}}<div class=header>{{Header}}</div>{{Image}}{{Question Mask}}{{/Image}}"
        a = ("{{Image}}{{Answer Mask}}<div class=remarks>{{Remarks}}</div>"
             "{{Sources}}{{Extra 1}}{{Extra 2}}<div class=footer>{{Footer}}</div>")
    if extra_field:
        a += "<div class=pearls>{{%s}}</div>" % extra_field
    a += marker
    css = (".card { font-family: %s; } /* %s author css for %s */"
           % ("arial" if version == "v1.2" else "helvetica", version, name))
    return q, a, css


def _two_clozes(k: int) -> bool:
    # exactly 57 of every 160 cloze notes get a c2 (5,700 of 16,000)
    return k % 160 < 57


def _field_value(field: str, nt_short: str, i: int, version: str, two: bool) -> str:
    if field == "Header":
        return "%s header %d %s" % (nt_short, i, version)
    if field == "Text":
        return ("%s fact %d %s: {{c1::alpha %d}}" % (nt_short, i, version, i)
                + (" {{c2::beta %d}}" % i if two else ""))
    if field == "Images":
        return '<img src="ankoma_img_%d.png"> (%s)' % (i % 5, version)
    if field == "Extra":
        return "extra %s %s %d" % (nt_short, version, i)
    if field == "Personal Notes":
        return ""  # the author leaves Personal Notes empty
    if field == "Textbook":
        return "Robbins ch.%d (%s)" % (i % 30, version)
    if field == "Citation":
        return "PMID %d (%s)" % (100000 + i, version)
    if field == "ID (hidden)":
        return "io-%s-%d" % (nt_short, i)
    if field == "Image":
        return '<img src="io_base_%d.png">' % (i % 5)
    if field in ("Question Mask", "Answer Mask", "Original Mask"):
        return '<img src="io_mask_%d.svg">' % (i % 5)
    if field in ("Footer", "Remarks", "Sources", "Extra 1", "Extra 2"):
        return "%s %s %d %s" % (field.lower(), nt_short, i, version)
    raise KeyError(field)


def _short(nt_name: str) -> str:
    return (nt_name.replace("Cloze-Ankoma-", "").replace("Image Occlusion Enhanced", "IOE")
            .replace(" - multiple images", "-multi").replace(" ", ""))


def _topic(branch: str, i: int) -> str:
    topics = AP_TOPICS if branch == "AP" else CP_TOPICS
    return topics[i % len(topics)]


def _deck_for(branch: str, topic: str) -> str:
    return "%s::%s" % (AP_DECK if branch == "AP" else CP_DECK, topic)


def _tags(branch: str, topic: str, i: int, version: str, io: bool) -> List[str]:
    path = "%s::%s" % (branch, topic)
    if version != "v1.2":
        path = TAG_REORG.get(path, path)
    root = "##ANKOMA-%s" % version
    tags = ["%s::%s" % (root, path) + ("::IO" if io else "::Sub%d" % (i % 4))]
    if i % 5 == 0:
        tags.append("%s::HighYield" % root)
    return tags


def _write_media(col, version: str) -> None:
    d = col.media.dir()
    for name in MEDIA_FILES:
        with open(os.path.join(d, name), "wb") as f:
            # identical content in every release, so the importer never renames
            f.write(("fixture media %s" % name).encode())


# ---------------------------------------------------------------------------
# Author side
# ---------------------------------------------------------------------------


def build_author_v12(col, counts: Dict[str, int]) -> Dict[str, List[int]]:
    from anki.collection import AddNoteRequest

    _write_media(col, "v1.2")
    by_type: Dict[str, List[int]] = {}
    reqs = []
    k = 0  # running cloze index
    meta = []
    for name, cloze, fields, branch, _ in NOTE_TYPES:
        q, a, css = _ankoma_templates(name, fields, cloze, "v1.2")
        nt = add_notetype(col, name, fields, cloze, q, a, css)
        short = _short(name)
        for i in range(counts[name]):
            topic = _topic(branch, i)
            n = col.new_note(nt)
            two = cloze and _two_clozes(k)
            if cloze:
                k += 1
            for f in fields:
                n[f] = _field_value(f, short, i, "v1.2", two)
            n.tags = _tags(branch, topic, i, "v1.2", not cloze)
            reqs.append(AddNoteRequest(note=n, deck_id=col.decks.id(_deck_for(branch, topic))))
            meta.append(name)
    col.add_notes(reqs)
    for name in counts:
        by_type[name] = sorted(col.find_notes('"note:%s"' % name))
    return by_type


def author_release_v13(col, counts: Dict[str, int]) -> Dict[str, Any]:
    """Edit every note, retag, new templates/CSS, new notes, c3 on some notes."""
    from anki.collection import AddNoteRequest

    mm = col.models
    for name, cloze, fields, branch, _ in NOTE_TYPES:
        nt = mm.by_name(name)
        q, a, css = _ankoma_templates(name, fields, cloze, "v1.3")
        nt["tmpls"][0]["qfmt"] = q
        nt["tmpls"][0]["afmt"] = a
        nt["css"] = css
        mm.update_dict(nt)

    c3_notes: List[str] = []
    notes = []
    for name, cloze, fields, branch, _ in NOTE_TYPES:
        short = _short(name)
        nids = sorted(col.find_notes('"note:%s"' % name))
        for i, nid in enumerate(nids):
            n = col.get_note(nid)
            two = "{{c2::" in n["Text"] if cloze else False
            topic = _topic(branch, i)
            for f in fields:
                if f == "Personal Notes":
                    continue
                n[f] = _field_value(f, short, i, "v1.3", two)
            if cloze and not two and i % 13 == 9:
                n["Text"] = n["Text"] + " {{c3::gamma %d}}" % i
                c3_notes.append(n.guid)
            n.tags = _tags(branch, topic, i, "v1.3", not cloze)
            notes.append(n)
    col.update_notes(notes)

    # new notes: ~5% per note type; AP cloze ones partly in a brand-new sub-deck
    reqs = []
    new_meta = []
    for name, cloze, fields, branch, _ in NOTE_TYPES:
        nt = mm.by_name(name)
        short = _short(name)
        base = counts[name]
        for j in range(max(2, counts[name] // 20)):
            i = base + j
            n = col.new_note(nt)
            for f in fields:
                n[f] = _field_value(f, short + "-new", i, "v1.3", False)
            if branch == "AP" and cloze and j % 2 == 0:
                deck = NEW_SUBDECK
                n.tags = ["##ANKOMA-v1.3::AP::Endocrine::Sub%d" % (i % 4)]
            else:
                topic = _topic(branch, i)
                deck = _deck_for(branch, topic)
                n.tags = _tags(branch, topic, i, "v1.3", not cloze)
            reqs.append(AddNoteRequest(note=n, deck_id=col.decks.id(deck)))
            new_meta.append((n, deck))
    col.add_notes(reqs)
    new_notes = [{"guid": n.guid, "deck": deck} for n, deck in new_meta]
    return {"new_notes": new_notes, "c3_note_guids": c3_notes}


def author_add_field(col) -> None:
    mm = col.models
    nt = mm.by_name(NEWFIELD_NOTETYPE)
    mm.add_field(nt, mm.new_field(NEWFIELD_NAME))
    _, a, _ = _ankoma_templates(NEWFIELD_NOTETYPE, AP_FIELDS, True, "v1.3", NEWFIELD_NAME)
    nt["tmpls"][0]["afmt"] = a
    nt["css"] += "\n.pearls { color: teal; } /* v1.3-newfield */"
    mm.update_dict(nt)
    nt = mm.by_name(NEWFIELD_NOTETYPE)
    notes = []
    for i, nid in enumerate(sorted(col.find_notes('"note:%s"' % NEWFIELD_NOTETYPE))):
        n = col.get_note(nid)
        n[NEWFIELD_NAME] = "pearl %d (v1.3-newfield)" % i
        notes.append(n)
    col.update_notes(notes)


def author_move_notes(col) -> List[Dict[str, Any]]:
    """Move some notes to another (existing) note type, the way an author
    would in Anki ("Change Note Type", fields matched by name)."""
    moved: List[Dict[str, Any]] = []
    mm = col.models
    for src, dst in MOVES:
        old = mm.by_name(src)
        new = mm.by_name(dst)
        nids = [nid for i, nid in enumerate(sorted(col.find_notes('"note:%s"' % src))) if i % 9 == 4]
        if not nids:
            continue
        info = mm.change_notetype_info(old_notetype_id=old["id"], new_notetype_id=new["id"])
        req = info.input
        old_names = [f["name"] for f in old["flds"]]
        del req.new_fields[:]
        req.new_fields.extend(old_names.index(f["name"]) if f["name"] in old_names else -1
                              for f in new["flds"])
        req.note_ids.extend(nids)
        mm.change_notetype_of_notes(req)
        for nid in nids:
            moved.append({"guid": col.get_note(nid).guid, "from": src, "to": dst})
    # the author edits the moved notes too
    notes = []
    for m in moved:
        n = col.get_note(col.db.scalar("select id from notes where guid=?", m["guid"]))
        n.fields[0] = n.fields[0] + " (moved)"
        notes.append(n)
    col.update_notes(notes)
    return moved


def build_simple_deck(col, nt_name: str, fields: Sequence[str], deck: str, n: int,
                      version: str, values=None) -> None:
    from anki.collection import AddNoteRequest

    nt = col.models.by_name(nt_name)
    if nt is None:
        nt = add_notetype(col, nt_name, fields, False, "{{Front}}",
                          "{{FrontSide}}<hr id=answer>{{Back}}<br>{{%s}}" % fields[-1],
                          ".card { color: black; } /* %s */" % nt_name)
    did = col.decks.id(deck)
    reqs = []
    for i in range(n):
        note = col.new_note(nt)
        for f in fields:
            note[f] = values(f, i) if values else "%s %d %s" % (f, i, version)
        note.tags = ["%s::%s" % (nt_name, version)]
        reqs.append(AddNoteRequest(note=note, deck_id=did))
    col.add_notes(reqs)


# ---------------------------------------------------------------------------
# User side
# ---------------------------------------------------------------------------


def _bump_mod(col, nids: Sequence[int], seconds: int) -> None:
    if not nids:
        return
    col.db.execute("update notes set mod = mod + ? where id in (%s)"
                   % ",".join(str(int(x)) for x in nids), seconds)


def simulate_user(col, n_reviews: int, n_resched: int) -> Dict[str, Any]:
    """Customise a collection that has v1.2 and Pharm-v1 imported.

    Roles are assigned per note type by the note's position (sorted by id),
    so every note type gets every kind of edit:
      i % 10 == 0  every field edited ("USER <field> ...") + tag #edited
      i % 10 == 1  Personal Notes filled (IO types: Remarks) + tag mytag::exam
      i % 10 == 2  Text and Extra edited (IO: Extra 1 + Footer) + tag #edited
      i % 10 == 3  Personal Notes filled, Images edited if present
                   + tag #edited::images
      i % 10 == 4  Header edited if present + tags #edited2, mytag
      i % 10 == 5  tag "#Edited::Caps" (case variant; Anki may canonicalise it)
      others       untouched
    Every edited note's mtime is then pushed one hour into the future, i.e.
    after the author's v1.3, so Anki's stock "if newer" would skip them.
    """
    roles: Dict[str, List[int]] = {k: [] for k in (
        "all_fields", "personal_notes", "text_extra", "edited_images",
        "header_edit", "unprotected_tags", "case_variant", "untouched")}
    edited: List[int] = []
    notes = []
    for name, cloze, fields, branch, _ in NOTE_TYPES:
        nids = sorted(col.find_notes('"note:%s"' % name))
        for i, nid in enumerate(nids):
            r = i % 10
            if r > 5:
                roles["untouched"].append(nid)
                continue
            n = col.get_note(nid)
            if r == 0:
                for f in fields:
                    n[f] = "USER %s %d" % (f, i)
                n.tags.append("#edited")
                roles["all_fields"].append(nid)
            elif r == 1:
                if "Personal Notes" in fields:
                    n["Personal Notes"] = "MY NOTE %d" % i
                else:
                    n["Remarks"] = "MY REMARK %d" % i
                n.tags.append("mytag::exam")
                roles["personal_notes"].append(nid)
            elif r == 2:
                if cloze:
                    n["Text"] = n["Text"] + " (user typo fix)"
                    n["Extra"] = "USER extra %d" % i
                else:
                    n["Extra 1"] = "USER extra1 %d" % i
                    n["Footer"] = "USER footer %d" % i
                n.tags.append("#edited")
                roles["text_extra"].append(nid)
            elif r == 3:
                if "Personal Notes" in fields:
                    n["Personal Notes"] = "MY NOTE %d" % i
                if "Images" in fields:
                    n["Images"] = '<img src="ankoma_img_0.png"> USER images %d' % i
                n.tags.append("#edited::images")
                roles["edited_images"].append(nid)
            elif r == 4:
                if "Header" in fields:
                    n["Header"] = "USER header %d" % i
                    roles["header_edit"].append(nid)
                n.tags.extend(["#edited2", "mytag"])
                roles["unprotected_tags"].append(nid)
            elif r == 5:
                n.tags.append("#Edited::Caps")
                roles["case_variant"].append(nid)
            notes.append(n)
            edited.append(nid)

    # the other author's deck: user writes their own mnemonic on half the notes
    pharm = sorted(col.find_notes('"note:%s"' % PHARM_NOTETYPE))
    pharm_edited = []
    for i, nid in enumerate(pharm):
        if i % 2 == 0:
            n = col.get_note(nid)
            n["My Mnemonic"] = "MY MNEMONIC %d" % i
            notes.append(n)
            pharm_edited.append(nid)
    col.update_notes(notes)

    # a field of the user's own on one Ankoma note type, filled on the notes
    # that already have other edits (roles 0-2)
    mm = col.models
    nt = mm.by_name(USER_FIELD_NOTETYPE)
    mm.add_field(nt, mm.new_field(USER_FIELD_NAME))
    mm.update_dict(nt)
    user_field_nids = []
    notes = []
    for i, nid in enumerate(sorted(col.find_notes('"note:%s"' % USER_FIELD_NOTETYPE))):
        if i % 10 in (0, 1, 2):
            n = col.get_note(nid)
            n[USER_FIELD_NAME] = "MY OWN MNEMONIC %d" % i
            notes.append(n)
            user_field_nids.append(nid)
    col.update_notes(notes)
    _bump_mod(col, edited + pharm_edited, 3600)

    # move cards: whole notes to "My Deck"; second card of 2-card notes to a sub-deck
    moved: List[int] = []
    split: List[int] = []
    for name, cloze, fields, branch, _ in NOTE_TYPES:
        nids = sorted(col.find_notes('"note:%s"' % name))
        for i, nid in enumerate(nids):
            cids = sorted(col.db.list("select id from cards where nid=? order by ord", nid))
            if i % 7 == 3:
                moved.extend(cids)
            elif i % 7 == 5 and len(cids) > 1:
                split.append(cids[1])
    col.set_deck(moved, col.decks.id(USER_DECK))
    col.set_deck(split, col.decks.id(USER_SPLIT_DECK))

    # review history: study cards from the Ankoma deck with the real scheduler
    root = col.decks.id(ROOT_DECK)
    conf = col.decks.config_dict_for_deck_id(root)
    conf["new"]["perDay"] = 100000
    conf["rev"]["perDay"] = 100000
    col.decks.update_config(conf)
    col.decks.select(root)
    ratings = [3, 1, 4, 3, 2]
    answered = 0
    while answered < n_reviews:
        card = col.sched.getCard()
        if card is None:
            break
        col.sched.answerCard(card, ratings[answered % len(ratings)])
        answered += 1
    # plus "set due date" on another slice (makes them review cards)
    pool = sorted(col.find_cards('"deck:%s" is:new' % ROOT_DECK))
    resched = pool[len(pool) // 3:len(pool) // 3 + n_resched]
    if resched:
        col.sched.set_due_date(resched, "7")
    reviewed = sorted(set(col.db.list("select distinct cid from revlog")))

    # note type tweaks, strictly later than the author's v1.3 (1 s resolution)
    time.sleep(1.1)
    tweaked_css = ["Cloze-Ankoma-AP", "Image Occlusion Enhanced+"]
    for name in tweaked_css:
        nt = col.models.by_name(name)
        nt["css"] += "\n/* USER dark-mode tweak */"
        col.models.update_dict(nt)
    tweaked_tmpl = ["Cloze-Ankoma-CP"]
    for name in tweaked_tmpl:
        nt = col.models.by_name(name)
        nt["tmpls"][0]["afmt"] += "<div class=user-tweak>user template tweak</div>"
        col.models.update_dict(nt)

    return {
        "roles": roles,
        "user_field_nids": user_field_nids,
        "later_edited_nids": sorted(edited + pharm_edited),
        "pharm_edited_nids": pharm_edited,
        "moved_card_ids": sorted(moved),
        "split_card_ids": sorted(split),
        "user_deck": USER_DECK,
        "user_split_deck": USER_SPLIT_DECK,
        "reviewed_card_ids": reviewed,
        "rescheduled_card_ids": sorted(resched),
        "answered_by_scheduler": answered,
        "css_tweaked_notetypes": tweaked_css,
        "template_tweaked_notetypes": tweaked_tmpl,
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _assert_outside_project(path: str) -> None:
    p = os.path.realpath(path)
    root = os.path.realpath(PROJECT_ROOT)
    if p == root or p.startswith(root + os.sep):
        raise SystemExit("refusing to write fixtures inside the project tree: %s" % p)


def build(out_dir: str, size: str = "small", verbose: bool = True) -> Dict[str, Any]:
    from anki.collection import Collection

    _assert_outside_project(out_dir)
    counts = _counts(size)
    log = print if verbose else (lambda *a, **k: None)
    t_start = time.time()
    shutil.rmtree(out_dir, ignore_errors=True)
    pk = os.path.join(out_dir, "packages")
    ref = os.path.join(out_dir, "reference")
    work = os.path.join(out_dir, "work")
    udir = os.path.join(out_dir, "user")
    for d in (pk, ref, work, udir):
        os.makedirs(d)
    pkgs = {
        "v1.2": os.path.join(pk, "Ankoma-v1.2.apkg"),
        "v1.3": os.path.join(pk, "Ankoma-v1.3.apkg"),
        "v1.3-newfield": os.path.join(pk, "Ankoma-v1.3-newfield.apkg"),
        "v1.3-moved": os.path.join(pk, "Ankoma-v1.3-moved.apkg"),
        "pharm-v1": os.path.join(pk, "Pharm-v1.apkg"),
        "pharm-v2": os.path.join(pk, "Pharm-v2.apkg"),
        "brandnew": os.path.join(pk, "BrandNew.apkg"),
    }
    exported: Dict[str, int] = {}
    log("Anki %s, Python %s, size=%s -> %s" % (anki_version(), sys.version.split()[0], size, out_dir))

    # --- Ankoma author -----------------------------------------------------
    a = Collection(os.path.join(work, "author.anki2"))
    build_author_v12(a, counts)
    exported["v1.2"] = export_deck(a, ROOT_DECK, pkgs["v1.2"])
    log("  v1.2: %d notes, %d cards" % (a.note_count(), a.card_count()))
    time.sleep(1.1)  # note/notetype mtimes have 1-second resolution
    v13 = author_release_v13(a, counts)
    exported["v1.3"] = export_deck(a, ROOT_DECK, pkgs["v1.3"])
    log("  v1.3: %d notes, %d cards" % (a.note_count(), a.card_count()))
    a.close()
    shutil.copy(os.path.join(work, "author.anki2"), os.path.join(work, "author-moved.anki2"))
    shutil.copytree(os.path.join(work, "author.media"), os.path.join(work, "author-moved.media"))
    mv = Collection(os.path.join(work, "author-moved.anki2"))
    time.sleep(1.1)
    v13["moved_notes"] = author_move_notes(mv)
    exported["v1.3-moved"] = export_deck(mv, ROOT_DECK, pkgs["v1.3-moved"])
    mv.close()
    a = Collection(os.path.join(work, "author.anki2"))
    time.sleep(1.1)
    author_add_field(a)
    exported["v1.3-newfield"] = export_deck(a, ROOT_DECK, pkgs["v1.3-newfield"])
    a.close()

    # --- other author's deck (Pharm) and a brand-new deck -------------------
    n_other = 10 if size == "small" else 200
    p = Collection(os.path.join(work, "pharm.anki2"))
    build_simple_deck(p, PHARM_NOTETYPE, PHARM_FIELDS, PHARM_DECK, n_other, "v1",
                      values=lambda f, i: "" if f == "My Mnemonic" else "%s %d v1" % (f, i))
    exported["pharm-v1"] = export_deck(p, PHARM_DECK, pkgs["pharm-v1"])
    time.sleep(1.1)
    notes = []
    for i, nid in enumerate(sorted(p.find_notes(""))):
        n = p.get_note(nid)
        n["Front"] = "Front %d v2" % i
        n["Back"] = "Back %d v2" % i
        n["My Mnemonic"] = "author mnemonic %d v2" % i
        n.tags = ["%s::v2" % PHARM_NOTETYPE]
        notes.append(n)
    p.update_notes(notes)
    exported["pharm-v2"] = export_deck(p, PHARM_DECK, pkgs["pharm-v2"])
    p.close()
    b = Collection(os.path.join(work, "brandnew.anki2"))
    build_simple_deck(b, BRANDNEW_NOTETYPE, BRANDNEW_FIELDS, BRANDNEW_DECK, n_other, "v1")
    exported["brandnew"] = export_deck(b, BRANDNEW_DECK, pkgs["brandnew"])
    b.close()

    # --- reference collections: each package imported into an empty one ----
    refs = {}
    for key, path in pkgs.items():
        rp = os.path.join(ref, "%s.anki2" % key)
        r = Collection(rp)
        reference_import(r, path)
        refs[key] = rp
        r.close()

    # --- simulated user -----------------------------------------------------
    time.sleep(1.1)
    upath = os.path.join(udir, "user.anki2")
    u = Collection(upath)
    stock_import(u, pkgs["v1.2"])
    stock_import(u, pkgs["pharm-v1"])
    user = simulate_user(u,
                         n_reviews=40 if size == "small" else 300,
                         n_resched=15 if size == "small" else 300)
    user_counts = {"notes": u.note_count(), "cards": u.card_count(),
                   "revlog": u.db.scalar("select count() from revlog")}
    u.close()
    log("  user: %(notes)d notes, %(cards)d cards, %(revlog)d revlog rows" % user_counts)

    manifest = {
        "fixture_format": FIXTURE_FORMAT,
        "builder_hash": builder_hash(),
        "anki_version": anki_version(),
        "python": sys.version.split()[0],
        "size": size,
        "counts_per_notetype_v12": counts,
        "exported_notes": exported,
        "packages": pkgs,
        "references": refs,
        "user_collection": upath,
        "user_counts": user_counts,
        "user": user,
        "v13": v13,
        "constants": {
            "root_deck": ROOT_DECK, "new_subdeck": NEW_SUBDECK,
            "newfield_notetype": NEWFIELD_NOTETYPE, "newfield_name": NEWFIELD_NAME,
            "user_field_notetype": USER_FIELD_NOTETYPE, "user_field_name": USER_FIELD_NAME,
            "pharm_notetype": PHARM_NOTETYPE, "pharm_deck": PHARM_DECK,
            "brandnew_notetype": BRANDNEW_NOTETYPE, "brandnew_deck": BRANDNEW_DECK,
            "tag_reorg": TAG_REORG,
            "notetypes": {name: list(fields) for name, _, fields, _, _ in NOTE_TYPES},
        },
        "build_seconds": round(time.time() - t_start, 2),
    }
    shutil.rmtree(work, ignore_errors=True)
    with open(os.path.join(out_dir, "fixtures.json"), "w") as f:
        json.dump(manifest, f, indent=1)
    log("  done in %.1fs" % manifest["build_seconds"])
    return manifest


def ensure(out_dir: Optional[str] = None, size: str = "small", verbose: bool = False) -> Dict[str, Any]:
    """Reuse fixtures in out_dir if they were built by this exact builder."""
    out_dir = out_dir or default_out_dir(size)
    mpath = os.path.join(out_dir, "fixtures.json")
    if os.path.exists(mpath):
        try:
            with open(mpath) as f:
                m = json.load(f)
            if (m.get("builder_hash") == builder_hash() and m.get("size") == size
                    and m.get("anki_version") == anki_version()
                    and all(os.path.exists(p) for p in m["packages"].values())
                    and os.path.exists(m["user_collection"])):
                return m
        except Exception:
            pass
    return build(out_dir, size, verbose=verbose)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--size", choices=["small", "full"], default="small")
    ap.add_argument("--out", default=None,
                    help="output directory (default /tmp/sfa-d/fixtures/<anki>-py<X.Y>/<size>)")
    ap.add_argument("--force", action="store_true", help="rebuild even if up to date")
    ap.add_argument("out_pos", nargs="?", help="output directory (same as --out)")
    args = ap.parse_args(argv)
    out = args.out or args.out_pos or default_out_dir(args.size)
    if args.force:
        m = build(out, args.size)
    else:
        m = ensure(out, args.size, verbose=True)
        print("fixtures ready: %s" % os.path.join(out, "fixtures.json"))
    print(json.dumps({"user_counts": m["user_counts"], "exported_notes": m["exported_notes"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
