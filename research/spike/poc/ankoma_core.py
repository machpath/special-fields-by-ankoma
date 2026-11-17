"""Ankoma Special Fields - GUI-independent core (spike PoC).

Architecture (A) "snapshot -> native import -> restore", but the snapshot is
taken from the *user's* collection, and the restore set is the list of note
ids that the native importer reports as `updated`.  We therefore never need to
read the (zstd-compressed) package ourselves.

Must stay importable on Anki 25.02 (Python 3.9) .. 26.x (Python 3.13):
no `match`, no PEP 604 unions at runtime, only public `anki` APIs.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from anki.collection import (
    Collection,
    ImportAnkiPackageOptions,
    ImportAnkiPackageRequest,
)
from anki.import_export_pb2 import ImportAnkiPackageUpdateCondition

ALWAYS = ImportAnkiPackageUpdateCondition.IMPORT_ANKI_PACKAGE_UPDATE_CONDITION_ALWAYS
IF_NEWER = ImportAnkiPackageUpdateCondition.IMPORT_ANKI_PACKAGE_UPDATE_CONDITION_IF_NEWER
NEVER = ImportAnkiPackageUpdateCondition.IMPORT_ANKI_PACKAGE_UPDATE_CONDITION_NEVER

UNDO_LABEL = "Import Ankoma update"

# Tags under e.g. "##ANKOMA-v1.2" or "##ANKOMA-v1.2::Cardio::HF" are author tags.
DEFAULT_AUTHOR_TAG_RE = r"^##ANKOMA-v[0-9][0-9.]*(::|$)"


@dataclass
class Settings:
    # field names whose LOCAL value is kept (matched by name, across notetypes)
    protected_fields: Set[str] = field(default_factory=lambda: {"Personal Notes"})
    # "overwrite" (default: incoming tags win), "preserve" (local tags win),
    # "merge" (incoming author tags + user's non-author tags)
    tag_mode: str = "overwrite"
    author_tag_re: str = DEFAULT_AUTHOR_TAG_RE
    # True = also take the author's templates/CSS; False = keep local ones
    update_notetypes: bool = True
    # merge_notetypes=True is required for author schema changes (added/
    # reordered fields) to update notes at all; it can force a full sync.
    merge_notetypes: bool = True


@dataclass
class _Snap:
    mid: int
    # field key -> value; key is ("id", field_config_id) or ("name", name)
    fields: Dict[Tuple[str, object], str]
    tags: List[str]


@dataclass
class Result:
    found: int = 0
    new: int = 0
    updated: int = 0
    duplicate: int = 0
    conflicting: int = 0
    restored_notes: int = 0
    restored_fields: int = 0
    seconds: Dict[str, float] = field(default_factory=dict)
    changes: object = None  # OpChanges for CollectionOp


def _field_key(fld: dict) -> Tuple[str, object]:
    # Field config ids exist on notetypes created/updated by 2.1.5x+; the
    # importer itself matches fields by id first, then by name (merge.rs).
    fid = fld.get("id")
    if fid:
        return ("id", fid)
    return ("name", fld["name"])


def _protected_keys(col: Collection, settings: Settings) -> Dict[int, Dict[int, Tuple[str, object]]]:
    """notetype id -> {field index -> key} for protected fields."""
    out: Dict[int, Dict[int, Tuple[str, object]]] = {}
    for nt in col.models.all():
        idx = {}
        for i, fld in enumerate(nt["flds"]):
            if fld["name"] in settings.protected_fields:
                idx[i] = _field_key(fld)
        if idx:
            out[nt["id"]] = idx
    return out


def snapshot(col: Collection, settings: Settings) -> Dict[int, _Snap]:
    """Snapshot protected fields + tags of every note whose notetype has at
    least one protected field (or all notes if tags need preserving).
    One SQL pass; ~18k notes is a few MB and well under a second."""
    keys = _protected_keys(col, settings)
    need_tags = settings.tag_mode != "overwrite"
    snap: Dict[int, _Snap] = {}
    for nid, mid, flds, tags in col.db.execute("select id, mid, flds, tags from notes"):
        idx = keys.get(mid)
        if not idx and not need_tags:
            continue
        vals = flds.split("\x1f")
        fields = {k: vals[i] for i, k in (idx or {}).items() if i < len(vals)}
        snap[nid] = _Snap(mid=mid, fields=fields, tags=tags.split())
    return snap


def _merge_tags(local: Sequence[str], incoming: Sequence[str], mode: str, author_re: "re.Pattern[str]") -> List[str]:
    if mode == "preserve":
        return list(local)
    if mode == "merge":
        personal = [t for t in local if not author_re.search(t)]
        seen = {t.lower() for t in incoming}
        return list(incoming) + [t for t in personal if t.lower() not in seen]
    return list(incoming)


def _clear_notetype_cache(col: Collection) -> None:
    clear = getattr(col.models, "_clear_cache", None)
    if clear:
        clear()


def import_ankoma_package(col: Collection, path: str, settings: Settings) -> Result:
    """Run in a background thread (CollectionOp). Produces ONE undo step."""
    res = Result()
    t0 = time.time()
    undo_pos = col.add_custom_undo_entry(UNDO_LABEL)
    snap = snapshot(col, settings)
    res.seconds["snapshot"] = time.time() - t0

    t1 = time.time()
    req = ImportAnkiPackageRequest(
        package_path=path,
        options=ImportAnkiPackageOptions(
            merge_notetypes=settings.merge_notetypes,
            # ALWAYS, not IF_NEWER: a user's local edit makes the local note
            # "newer" and IF_NEWER would silently skip the author's update.
            update_notes=ALWAYS,
            # NEVER still lets merge_notetypes add the author's new fields
            update_notetypes=ALWAYS if settings.update_notetypes else NEVER,
            # existing cards are never touched by the importer; these only
            # affect brand-new cards / deck presets coming from the author
            with_scheduling=False,
            with_deck_configs=False,
        ),
    )
    out = col.import_anki_package(req)
    # GOTCHA: pylib's ModelManager keeps a Python-side notetype cache that a
    # backend import does not invalidate (aqt only clears it on the main
    # thread *after* the op, aqt/main.py on_operation_did_execute). Without
    # this, post-import lookups see the pre-import field list/CSS.
    _clear_notetype_cache(col)
    log = out.log
    res.found = log.found_notes
    res.new, res.updated = len(log.new), len(log.updated)
    res.duplicate, res.conflicting = len(log.duplicate), len(log.conflicting)
    res.seconds["native_import"] = time.time() - t1

    t2 = time.time()
    author_re = re.compile(settings.author_tag_re)
    to_save = []
    nt_cache: Dict[int, Dict[Tuple[str, object], int]] = {}
    for logged in log.updated:
        nid = logged.id.nid
        old = snap.get(nid)
        if old is None:
            continue
        note = col.get_note(nid)
        if note.mid not in nt_cache:
            nt = col.models.get(note.mid)
            nt_cache[note.mid] = {_field_key(f): i for i, f in enumerate(nt["flds"])}
            # fall back to name lookup for keys that were id-based pre-import
            for i, f in enumerate(nt["flds"]):
                nt_cache[note.mid].setdefault(("name", f["name"]), i)
        pos = nt_cache[note.mid]
        changed = False
        for key, value in old.fields.items():
            i = pos.get(key)
            if i is not None and note.fields[i] != value:
                note.fields[i] = value
                res.restored_fields += 1
                changed = True
        new_tags = _merge_tags(old.tags, note.tags, settings.tag_mode, author_re)
        if new_tags != note.tags:
            note.tags = new_tags
            changed = True
        if changed:
            to_save.append(note)
    if to_save:
        col.update_notes(to_save)
    res.restored_notes = len(to_save)
    res.changes = col.merge_undo_entries(undo_pos)
    res.seconds["restore"] = time.time() - t2
    return res
