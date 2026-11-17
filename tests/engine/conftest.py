"""Tiny synthetic decks for the engine tests.

An "author" collection is built once per session and exported as several
.apkg releases; a "user" collection imports release v1 the stock way and is
then customised. Each test gets a fresh copy of the user collection.

Note and note-type modification times are set explicitly with SQL instead of
sleeping, so the tests are fast and deterministic:
  v1 notes: mod 1_000_000; v2 notes: 2_000_000; v2-newfield/-rename notes:
  2_500_000; notes the user edited: 3_000_000 (later than the author).

Generated files go under /tmp/sfa-b/ (never into the project tree).
"""

from __future__ import annotations

import os
import shutil
import sys
from typing import Dict

import pytest
from anki.buildinfo import version as ANKI_VERSION
from anki.collection import (
    Collection,
    DeckIdLimit,
    ExportAnkiPackageOptions,
    ImportAnkiPackageOptions,
    ImportAnkiPackageRequest,
)

SCRATCH_ROOT = "/tmp/sfa-b/pytest"

# Note type A: "Header" present, "Text" second.  Note type B: no "Header",
# "Text" first.  Different field orders on purpose.
NT_A = "SF Cloze A"
NT_A_FIELDS = ["Header", "Text", "Extra", "Personal Notes"]
NT_B = "SF Basic B"
NT_B_FIELDS = ["Text", "Extra", "Personal Notes"]
NT_C = "SF Fresh C"

V1_MOD = 1_000_000
V2_MOD = 2_000_000
V25_MOD = 2_500_000
USER_MOD = 3_000_000


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config):
    if not config.option.basetemp:
        tag = "anki%s-py%d%d" % (ANKI_VERSION, sys.version_info[0], sys.version_info[1])
        os.makedirs(SCRATCH_ROOT, exist_ok=True)
        config.option.basetemp = os.path.join(SCRATCH_ROOT, tag)


# --- author side ----------------------------------------------------------------


def _export(col: Collection, root_deck: str, out: str, scheduling: bool = False) -> None:
    col.export_anki_package(
        out_path=out,
        options=ExportAnkiPackageOptions(
            with_scheduling=scheduling,
            with_deck_configs=scheduling,
            with_media=True,
            legacy=False,
        ),
        limit=DeckIdLimit(col.decks.id(root_deck)),
    )


def _set_mod(col: Collection, guids, mod: int) -> None:
    col.db.execute(
        "update notes set mod=? where guid in (%s)" % ",".join("'%s'" % g for g in guids), mod
    )


def _set_nt_mtime(col: Collection, mtime: int) -> None:
    col.db.execute("update notetypes set mtime_secs=? where name in (?, ?)", mtime, NT_A, NT_B)
    col.models._clear_cache()


def _add(col, nt_name, deck, guid, values, tags):
    note = col.new_note(col.models.by_name(nt_name))
    for k, v in values.items():
        note[k] = v
    note.tags = list(tags)
    note.guid = guid
    col.add_note(note, col.decks.id(deck))
    return note


def _note_by_guid(col, guid):
    return col.get_note(col.db.scalar("select id from notes where guid=?", guid))


def _build_author(work: str) -> Dict[str, str]:
    paths = {}
    col = Collection(os.path.join(work, "author.anki2"))
    mm = col.models
    a = mm.new(NT_A)
    a["type"] = 1  # cloze
    for f in NT_A_FIELDS:
        mm.add_field(a, mm.new_field(f))
    t = mm.new_template("Cloze")
    t["qfmt"] = "{{Header}}<br>{{cloze:Text}}"
    t["afmt"] = "{{cloze:Text}}<br>{{Extra}}<br>{{Personal Notes}}"
    mm.add_template(a, t)
    a["css"] = ".card { color: black; } /* author v1 */"
    mm.add(a)
    b = mm.new(NT_B)
    for f in NT_B_FIELDS:
        mm.add_field(b, mm.new_field(f))
    t = mm.new_template("Card 1")
    t["qfmt"] = "{{Text}}"
    t["afmt"] = "{{Text}}<hr id=answer>{{Extra}}<br>{{Personal Notes}}"
    mm.add_template(b, t)
    b["css"] = ".card { color: navy; } /* author v1 */"
    mm.add(b)

    for i in (1, 2, 3, 4):
        _add(col, NT_A, "Rel::A", "A%d" % i,
             {"Header": "H%d v1" % i, "Text": "A%d {{c1::v1}} {{c2::two}}" % i, "Extra": "E%d v1" % i},
             ["##REL-v1::a::t%d" % i])
    for i in (1, 2, 3):
        _add(col, NT_B, "Rel::B", "B%d" % i,
             {"Text": "B%d v1" % i, "Extra": "E%d v1" % i}, ["##REL-v1::b"])
    _set_mod(col, ["A1", "A2", "A3", "A4", "B1", "B2", "B3"], V1_MOD)
    _set_nt_mtime(col, V1_MOD)
    paths["v1"] = os.path.join(work, "rel-v1.apkg")
    _export(col, "Rel", paths["v1"])

    # --- v2: content, tags, templates and CSS change; one new note; B3 unchanged
    for nt_name in (NT_A, NT_B):
        nt = mm.by_name(nt_name)
        nt["css"] = nt["css"].replace("author v1", "author v2")
        nt["tmpls"][0]["qfmt"] += "<!-- author v2 -->"
        mm.update_dict(nt)
    notes = []
    for guid in ("A1", "A2", "A3", "A4", "B1", "B2"):
        n = _note_by_guid(col, guid)
        for k in ("Header", "Text", "Extra"):
            if k in n:
                n[k] = n[k].replace("v1", "v2")
        n.tags = [t.replace("##REL-v1", "##REL-v2") for t in n.tags]
        if guid == "A3":
            n.tags.append("#EDITED")  # the update itself carries a protected tag
        notes.append(n)
    col.update_notes(notes)
    _add(col, NT_A, "Rel::A", "A5", {"Header": "H5 v2", "Text": "A5 {{c1::new}}"}, ["##REL-v2::a::t5"])
    _set_mod(col, ["A1", "A2", "A3", "A4", "B1", "B2", "A5"], V2_MOD)
    _set_nt_mtime(col, V2_MOD)
    paths["v2"] = os.path.join(work, "rel-v2.apkg")
    _export(col, "Rel", paths["v2"])

    # v2 exported with the author's scheduling and deck options.
    conf = col.decks.get_config(1)
    conf["new"]["perDay"] = 77
    col.decks.update_config(conf)
    cids = sorted(col.find_cards("deck:Rel::A"))
    col.sched.set_due_date(cids, "3")
    paths["v2sched"] = os.path.join(work, "rel-v2-sched.apkg")
    _export(col, "Rel", paths["v2sched"], scheduling=True)
    col.close()

    # v2-newfield: v2 plus a field appended to note type A (schema change).
    shutil.copy(os.path.join(work, "author.anki2"), os.path.join(work, "author-nf.anki2"))
    col = Collection(os.path.join(work, "author-nf.anki2"))
    nt = col.models.by_name(NT_A)
    col.models.add_field(nt, col.models.new_field("Mnemonic"))
    col.models.update_dict(nt)
    notes = []
    for guid in ("A1", "A2", "A3", "A4", "A5"):
        n = _note_by_guid(col, guid)
        n["Mnemonic"] = "mnemonic " + guid
        notes.append(n)
    col.update_notes(notes)
    _set_mod(col, ["A1", "A2", "A3", "A4", "A5"], V25_MOD)
    _set_nt_mtime(col, V25_MOD)
    paths["v2newfield"] = os.path.join(work, "rel-v2-newfield.apkg")
    _export(col, "Rel", paths["v2newfield"])
    col.close()

    # v2-rename: v2 with field "Extra" of note type B renamed to "Extra Info".
    shutil.copy(os.path.join(work, "author.anki2"), os.path.join(work, "author-rn.anki2"))
    col = Collection(os.path.join(work, "author-rn.anki2"))
    nt = col.models.by_name(NT_B)
    col.models.rename_field(nt, nt["flds"][1], "Extra Info")
    nt["tmpls"][0]["afmt"] = nt["tmpls"][0]["afmt"].replace("{{Extra}}", "{{Extra Info}}")
    col.models.update_dict(nt)
    _set_mod(col, ["B1", "B2"], V25_MOD)
    _set_nt_mtime(col, V25_MOD)
    paths["v2rename"] = os.path.join(work, "rel-v2-rename.apkg")
    _export(col, "Rel", paths["v2rename"])
    col.close()

    # A separate release with its own note type and deck.
    col = Collection(os.path.join(work, "fresh-author.anki2"))
    mm = col.models
    c = mm.new(NT_C)
    for f in ("Text", "Personal Notes"):
        mm.add_field(c, mm.new_field(f))
    t = mm.new_template("Card 1")
    t["qfmt"] = "{{Text}}"
    t["afmt"] = "{{Text}}"
    mm.add_template(c, t)
    mm.add(c)
    for i in (1, 2):
        _add(col, NT_C, "Fresh::Deck", "C%d" % i, {"Text": "C%d" % i, "Personal Notes": "author pn"}, ["#edited"])
    paths["fresh"] = os.path.join(work, "fresh.apkg")
    _export(col, "Fresh", paths["fresh"])
    col.close()
    return paths


# --- user side ------------------------------------------------------------------------


def _build_user(path: str, v1: str) -> Dict[str, object]:
    col = Collection(path)
    col.import_anki_package(ImportAnkiPackageRequest(package_path=v1, options=ImportAnkiPackageOptions()))
    a1 = _note_by_guid(col, "A1")
    a1["Header"] = "my header A1"
    a1["Personal Notes"] = "mine A1"
    a1.tags += ["#Edited", "#Edited::Images", "#edited2", "personal"]
    a2 = _note_by_guid(col, "A2")
    a2["Text"] = a2["Text"] + " (my fix A2)"
    a3 = _note_by_guid(col, "A3")
    a3.tags += ["#Edited"]
    b1 = _note_by_guid(col, "B1")
    b1["Text"] = "my text B1"
    b1["Extra"] = "my extra B1"
    b1["Personal Notes"] = "mine B1"
    b1.tags += ["#Edited::sub"]
    col.update_notes([a1, a2, a3, b1])
    _set_mod(col, ["A1", "A2", "A3", "B1"], USER_MOD)

    my_deck = col.decks.id("My Deck")
    moved = list(col.card_ids_of_note(a1.id))
    col.set_deck(moved, my_deck)
    rescheduled = list(col.card_ids_of_note(b1.id)) + list(col.card_ids_of_note(_note_by_guid(col, "A4").id))
    col.sched.set_due_date(rescheduled, "7")

    for nt_name in (NT_A, NT_B):
        nt = col.models.by_name(nt_name)
        nt["css"] += "\n/* USER tweak */"
        nt["tmpls"][0]["afmt"] += "<!-- USER -->"
        col.models.update_dict(nt)
    col.close()
    return {"my_deck": my_deck, "moved": moved, "rescheduled": rescheduled}


@pytest.fixture(scope="session")
def world(tmp_path_factory):
    work = str(tmp_path_factory.mktemp("world"))
    paths = _build_author(work)
    user_path = os.path.join(work, "user-base.anki2")
    info = _build_user(user_path, paths["v1"])
    return {"paths": paths, "user_base": user_path, **info}


@pytest.fixture
def user_col(world, tmp_path):
    path = str(tmp_path / "user.anki2")
    shutil.copy(world["user_base"], path)
    col = Collection(path)
    yield col
    col.close()


@pytest.fixture
def empty_col(tmp_path):
    col = Collection(str(tmp_path / "empty.anki2"))
    yield col
    col.close()
