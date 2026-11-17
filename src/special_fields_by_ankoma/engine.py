"""Import engine for Special Fields by Ankoma (workstream B).

`run_import` imports an .apkg with Anki's own importer, forced to update every
note, then puts back what the user chose to keep:

1. open one custom undo entry (`UNDO_LABEL`);
2. snapshot, in one SQL pass over the user's own collection, the values of
   the kept fields and the protected tags (only what the settings need);
3. run the native importer (`update_notes=ALWAYS`, `merge_notetypes=True`,
   `update_notetypes=ALWAYS/NEVER`);
4. clear pylib's note-type cache (a backend import does not invalidate it);
5. restore kept fields and protected tags on the notes the importer reports
   as updated (one batched `update_notes`), and when the user keeps their
   card styling, make sure templates and CSS are exactly as before;
6. merge every undo entry made since step 1 into one, and return the result.

Runs headless and inside aqt's `CollectionOp` background thread: it imports
nothing from `aqt`. Python 3.9 compatible.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from anki.collection import (
    Collection,
    ImportAnkiPackageOptions,
    ImportAnkiPackageRequest,
)
from anki.import_export_pb2 import ImportAnkiPackageUpdateCondition

from .model import UNDO_LABEL, ImportResult, Settings, norm_field, norm_tag

ALWAYS = ImportAnkiPackageUpdateCondition.IMPORT_ANKI_PACKAGE_UPDATE_CONDITION_ALWAYS
NEVER = ImportAnkiPackageUpdateCondition.IMPORT_ANKI_PACKAGE_UPDATE_CONDITION_NEVER

# The native importer saves the options it was called with as the user's
# defaults for Anki's own import screen, under these config keys (verified on
# 25.02.7 and 26.11b1). We put the user's values back afterwards, so a forced
# import does not silently change how Anki's standard import behaves.
IMPORT_PREF_KEYS = (
    "mergeNotetypes",
    "updateNotes",
    "updateNotetypes",
    "withScheduling",
    "withDeckConfigs",
)

# ImportResponse.Log list fields other than `new` / `updated`, i.e. notes in
# the file that were not imported, mapped to the key used in `skip_reasons`.
SKIP_REASON_FIELDS = (
    ("duplicate", "unchanged"),  # with ALWAYS: same modification time as yours
    ("conflicting", "note type conflict"),
    ("first_field_match", "first field match"),
    ("missing_notetype", "missing note type"),
    ("missing_deck", "missing deck"),
    ("empty_first_field", "empty first field"),
)

# Template keys compared/restored when the user keeps their card styling.
TEMPLATE_KEYS = ("name", "qfmt", "afmt", "bqfmt", "bafmt", "bfont", "bsize", "did")

_MISSING = object()

# A kept field: (field config id or None, normalized name, pre-import value)
_KeptValue = Tuple[Optional[int], str, str]


class _NoteSnap:
    __slots__ = ("fields", "tags")

    def __init__(self, fields: List[_KeptValue], tags: List[str]) -> None:
        self.fields = fields
        self.tags = tags  # pre-import protected tags, original spelling


def run_import(col: Collection, path: str, settings: Settings) -> ImportResult:
    """Import `path` into `col` with the user's Special Fields choices.

    One undo step labelled `UNDO_LABEL`. If anything raises, the exception
    propagates and the collection is left as it was before the call.
    """
    res = ImportResult()
    t_start = time.perf_counter()
    undo_pos = col.add_custom_undo_entry(UNDO_LABEL)
    try:
        _run(col, path, settings, res, undo_pos)
    except BaseException:
        _roll_back(col, undo_pos)
        raise
    res.seconds["total"] = time.perf_counter() - t_start
    return res


def _run(col: Collection, path: str, settings: Settings, res: ImportResult, undo_pos: int) -> None:
    # --- snapshot (read-only) -------------------------------------------------
    t0 = time.perf_counter()
    _clear_notetype_cache(col)
    prefs = {key: col.get_config(key, _MISSING) for key in IMPORT_PREF_KEYS}
    scm_before = col.db.scalar("select scm from col")
    styling = None if settings.update_note_types else _snapshot_styling(col)
    snap = _snapshot_notes(col, settings)
    res.seconds["snapshot"] = time.perf_counter() - t0

    # --- native import ----------------------------------------------------------
    t1 = time.perf_counter()
    request = ImportAnkiPackageRequest(
        package_path=path,
        options=ImportAnkiPackageOptions(
            # Required so an author's added field updates notes instead of
            # making every note "conflicting" and duplicating the note type.
            merge_notetypes=True,
            # Never IF_NEWER: any local edit makes the note "newer" and the
            # author's update would be skipped silently.
            update_notes=ALWAYS,
            update_notetypes=ALWAYS if settings.update_note_types else NEVER,
            # The importer never modifies existing cards; these only affect
            # cards/decks new to the collection. False/False never brings in
            # the author's review history or overwrites the user's deck
            # options presets. (Anki's saved import preferences are not
            # exposed by a public Collection API on 25.02-26.11.)
            with_scheduling=False,
            with_deck_configs=False,
        ),
    )
    out = col.import_anki_package(request)
    # pylib caches note types; a backend import does not invalidate the cache
    # (aqt only clears it on the main thread after the op).
    _clear_notetype_cache(col)
    log = out.log
    res.notes_in_file = int(log.found_notes)
    res.notes_added = len(log.new)
    res.notes_updated = len(log.updated)
    skipped = 0
    for attr, reason in SKIP_REASON_FIELDS:
        n = len(getattr(log, attr, ()))
        if n:
            res.skip_reasons[reason] = res.skip_reasons.get(reason, 0) + n
            skipped += n
    res.notes_skipped = skipped
    res.seconds["import"] = time.perf_counter() - t1

    # --- restore ---------------------------------------------------------------
    t2 = time.perf_counter()
    if snap:
        updated_ids = [entry.id.nid for entry in log.updated]
        _restore_notes(col, snap, updated_ids, res)
    if styling is not None:
        _restore_styling(col, styling)
    _restore_import_prefs(col, prefs)
    res.note_types_changed = col.db.scalar("select scm from col") != scm_before
    res.changes = col.merge_undo_entries(undo_pos)
    res.seconds["restore"] = time.perf_counter() - t2


# --- snapshot ---------------------------------------------------------------------


def _kept_fields_by_notetype(col: Collection, settings: Settings) -> Dict[int, List[Tuple[int, Optional[int], str]]]:
    """note type id -> [(field index, field config id, normalized name)]."""
    kept = settings.kept_field_names()
    out: Dict[int, List[Tuple[int, Optional[int], str]]] = {}
    if not kept:
        return out
    for nt in col.models.all():
        entries = []
        for i, fld in enumerate(nt["flds"]):
            name = norm_field(fld["name"])
            if name in kept:
                entries.append((i, fld.get("id") or None, name))
        if entries:
            out[int(nt["id"])] = entries
    return out


def _snapshot_notes(col: Collection, settings: Settings) -> Dict[int, _NoteSnap]:
    """One SQL pass: kept field values and protected tags of every note that
    has any. Empty when the settings keep nothing."""
    plan = _kept_fields_by_notetype(col, settings)
    want_tags = any(norm_tag(t) for t in settings.protected_tags)
    snap: Dict[int, _NoteSnap] = {}
    if not plan and not want_tags:
        return snap
    if want_tags:
        rows = col.db.execute("select id, mid, flds, tags from notes")
    else:
        mids = ",".join(str(int(m)) for m in plan)
        rows = col.db.execute("select id, mid, flds, '' from notes where mid in (%s)" % mids)
    protects = settings.protects_tag
    for nid, mid, flds, tags in rows:
        kept: List[_KeptValue] = []
        entries = plan.get(mid)
        if entries:
            vals = flds.split("\x1f")
            for i, fid, name in entries:
                if i < len(vals):
                    kept.append((fid, name, vals[i]))
        ptags = [t for t in tags.split() if protects(t)] if want_tags and tags else []
        if kept or ptags:
            snap[nid] = _NoteSnap(kept, ptags)
    return snap


def _snapshot_styling(col: Collection) -> Dict[int, Tuple[str, List[Dict[str, Any]]]]:
    """note type id -> (css, [template subset]) for every note type."""
    out: Dict[int, Tuple[str, List[Dict[str, Any]]]] = {}
    for nt in col.models.all():
        tmpls = [{k: t.get(k) for k in TEMPLATE_KEYS + ("id", "ord")} for t in nt["tmpls"]]
        out[int(nt["id"])] = (nt.get("css", ""), tmpls)
    return out


# --- restore ------------------------------------------------------------------------


def _field_positions(col: Collection, mid: int) -> Tuple[Dict[int, int], Dict[str, int]]:
    nt = col.models.get(mid)
    by_id: Dict[int, int] = {}
    by_name: Dict[str, int] = {}
    if nt:
        for i, fld in enumerate(nt["flds"]):
            fid = fld.get("id")
            if fid:
                by_id.setdefault(fid, i)
            by_name.setdefault(norm_field(fld["name"]), i)
    return by_id, by_name


def _restore_notes(col: Collection, snap: Dict[int, _NoteSnap], updated_ids: Sequence[int], res: ImportResult) -> None:
    targets: Set[int] = {int(nid) for nid in updated_ids if int(nid) in snap}
    if not targets:
        return
    positions: Dict[int, Tuple[Dict[int, int], Dict[str, int]]] = {}
    # One pass over the post-import state; Note objects only for notes we write.
    plans: Dict[int, Tuple[List[Tuple[int, str]], List[str]]] = {}
    for nid, mid, flds, tags in col.db.execute("select id, mid, flds, tags from notes"):
        if nid not in targets:
            continue
        old = snap[nid]
        field_writes: List[Tuple[int, str]] = []
        if old.fields:
            if mid not in positions:
                positions[mid] = _field_positions(col, mid)
            by_id, by_name = positions[mid]
            vals = flds.split("\x1f")
            for fid, name, value in old.fields:
                idx = by_id.get(fid) if fid else None
                if idx is None:
                    idx = by_name.get(name)
                if idx is None or idx >= len(vals):
                    continue
                if vals[idx] != value:
                    field_writes.append((idx, value))
        tag_adds: List[str] = []
        if old.tags:
            current = {norm_tag(t) for t in tags.split()}
            for tag in old.tags:
                key = norm_tag(tag)
                if key not in current:
                    tag_adds.append(tag)
                    current.add(key)
        if field_writes or tag_adds:
            plans[nid] = (field_writes, tag_adds)

    to_save = []
    for nid, (field_writes, tag_adds) in plans.items():
        note = col.get_note(nid)
        for idx, value in field_writes:
            note.fields[idx] = value
        if tag_adds:
            note.tags = list(note.tags) + tag_adds
        to_save.append(note)
        if field_writes:
            res.fields_kept += len(field_writes)
            res.notes_with_fields_kept += 1
        if tag_adds:
            res.protected_tags_kept += len(tag_adds)
            res.notes_with_tags_kept += 1
    if to_save:
        col.update_notes(to_save)


def _restore_styling(col: Collection, styling: Dict[int, Tuple[str, List[Dict[str, Any]]]]) -> int:
    """Put back CSS and the pre-existing templates of every note type that the
    import touched. With update_notetypes=NEVER the importer already keeps
    them (verified on 25.02.7 and 26.11b1); this is a guard that writes only
    if something differs. Templates the update added are left in place: they
    may already have cards. Returns the number of note types rewritten."""
    rewritten = 0
    for mid, (css, old_tmpls) in styling.items():
        nt = col.models.get(mid)
        if not nt:
            continue
        changed = False
        if nt.get("css", "") != css:
            nt["css"] = css
            changed = True
        current = nt["tmpls"]
        by_id = {t.get("id"): t for t in current if t.get("id")}
        for old in old_tmpls:
            tmpl = by_id.get(old.get("id")) if old.get("id") else None
            if tmpl is None:
                ord_ = old.get("ord")
                tmpl = current[ord_] if isinstance(ord_, int) and ord_ < len(current) else None
            if tmpl is None:
                continue
            for key in TEMPLATE_KEYS:
                if key in old and tmpl.get(key) != old[key]:
                    tmpl[key] = old[key]
                    changed = True
        if changed:
            col.models.update_dict(nt)
            rewritten += 1
    if rewritten:
        _clear_notetype_cache(col)
    return rewritten


def _restore_import_prefs(col: Collection, prefs: Dict[str, Any]) -> None:
    for key, old in prefs.items():
        now = col.get_config(key, _MISSING)
        if now is _MISSING and old is _MISSING:
            continue
        if old is _MISSING:
            col.remove_config(key)
        elif now is _MISSING or now != old:
            col.set_config(key, old, undoable=True)


# --- helpers -----------------------------------------------------------------------


def _clear_notetype_cache(col: Collection) -> None:
    clear = getattr(col.models, "_clear_cache", None)
    if clear is not None:
        clear()


def _roll_back(col: Collection, undo_pos: int) -> None:
    """Undo everything since `undo_pos` (our custom entry), so a failed
    import leaves the collection as it was. The native import is a single
    transaction, so if it raised it changed nothing; undoing our then-empty
    entry also puts the user's own last action back on top of the undo
    stack. Only undoes if our entry is the one on top."""
    try:
        col.merge_undo_entries(undo_pos)
        status = col.undo_status()
        if status.undo == UNDO_LABEL and status.last_step == undo_pos:
            col.undo()
    except Exception:
        pass
    _clear_notetype_cache(col)
