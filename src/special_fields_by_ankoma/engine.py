"""Import engine for Special Fields by Ankoma (workstream B).

`run_import` imports an .apkg with Anki's own importer, forced to update every
note, then puts back what the user chose to keep:

1. open one custom undo entry (`UNDO_LABEL`);
2. snapshot, in one SQL pass over the user's own notes, every note's note
   type, field values and tags (contract rules 9 and 10 need all of them,
   whatever the settings), plus every note type's field and template ids
   and the ids of existing cards;
3. run the native importer (`update_notes=ALWAYS`, `merge_notetypes=True`,
   `update_notetypes=ALWAYS/NEVER`);
4. clear pylib's note-type cache (a backend import does not invalidate it);
5. restore, on the notes the importer reports as updated, kept fields,
   fields the update has no content for (rule 9) and protected tags (one
   batched `update_notes`); a note whose note type changed ("moved", rule
   10a) is restored by field name on its new note type;
6. clean up what Anki's forced note type merge leaves behind (rule 10b, see
   `_clean_merge_leftovers`);
7. when the user keeps their card styling, make sure templates and CSS of
   existing note types are exactly as before;
8. merge every undo entry made since step 1 into one, and return the result.

Runs headless and inside aqt's `CollectionOp` background thread: it imports
nothing from `aqt`. Python 3.9 compatible.
"""

from __future__ import annotations

import copy
import os
import re
import shutil
import tempfile
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

# Pre-import fields of one note type, by position: (field config id or None,
# normalized name).
_FieldInfo = List[Tuple[Optional[int], str]]


class MergeRepairError(Exception):
    """Contract rule 10g: Anki's forced note type merge left a note type in a
    state the engine cannot repair safely (blank and duplicate cards would
    remain). Raised after the whole import has been rolled back, so the
    collection is exactly as it was. `notetype` names the note type."""

    def __init__(self, notetype: str, reason: str) -> None:
        self.notetype = notetype
        self.reason = reason
        super().__init__(
            "Nothing was imported: the update moves notes to note type %r, and "
            "Anki's note type merge could not be repaired safely (%s)." % (notetype, reason)
        )


class _Snapshot:
    """The user's collection before the import: every note's
    (note type id, raw fields, raw tags), every note type's fields and
    template ids, and the ids of all cards."""

    __slots__ = ("notes", "fields", "templates", "card_ids")

    def __init__(
        self,
        notes: Dict[int, Tuple[int, str, str]],
        fields: Dict[int, _FieldInfo],
        templates: Dict[int, Set[Any]],
        card_ids: Set[int],
    ) -> None:
        self.notes = notes
        self.fields = fields
        self.templates = templates
        self.card_ids = card_ids


def run_import(col: Collection, path: str, settings: Settings) -> ImportResult:
    """Import `path` into `col` with the user's Special Fields choices.

    One undo step labelled `UNDO_LABEL`. If anything raises, the exception
    propagates and the collection is left as it was before the call.
    """
    res = ImportResult()
    t_start = time.perf_counter()
    prior = col.undo_status()
    undo_pos = col.add_custom_undo_entry(UNDO_LABEL)
    try:
        _run(col, path, settings, res, undo_pos)
    except BaseException:
        _roll_back(col, undo_pos, prior)
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
    snap = _snapshot(col)
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
    updated_ids = [int(entry.id.nid) for entry in log.updated]
    added_ids = [int(entry.id.nid) for entry in log.new]
    _restore_notes(col, snap, settings, updated_ids, added_ids, res)
    if res.notes_updated:
        _clean_merge_leftovers(col, snap, set(updated_ids).union(added_ids))
    if styling is not None:
        _restore_styling(col, styling)
    _restore_import_prefs(col, prefs)
    res.note_types_changed = col.db.scalar("select scm from col") != scm_before
    res.changes = col.merge_undo_entries(undo_pos)
    res.seconds["restore"] = time.perf_counter() - t2


# --- snapshot ---------------------------------------------------------------------


def _notetype_fields(col: Collection) -> Dict[int, _FieldInfo]:
    """note type id -> [(field config id, normalized name)] by position."""
    out: Dict[int, _FieldInfo] = {}
    for nt in col.models.all():
        out[int(nt["id"])] = [(fld.get("id") or None, norm_field(fld["name"])) for fld in nt["flds"]]
    return out


def _snapshot(col: Collection) -> _Snapshot:
    """One SQL pass over every note: note type id, fields and tags as stored.

    Everything is needed whatever the settings: rule 10 follows notes the
    update moves to another note type, and rule 9 may put back any field
    that is not listed in the settings. Strings are kept raw and split only
    for the notes the import updates. Card ids (one more cheap query) let
    the merge clean-up tell cards this import created from the user's."""
    notes: Dict[int, Tuple[int, str, str]] = {}
    for nid, mid, flds, tags in col.db.execute("select id, mid, flds, tags from notes"):
        notes[nid] = (mid, flds, tags)
    templates: Dict[int, Set[Any]] = {}
    for nt in col.models.all():
        templates[int(nt["id"])] = {t.get("id") for t in nt["tmpls"] if t.get("id")}
    card_ids = set(col.db.list("select id from cards"))
    return _Snapshot(notes, _notetype_fields(col), templates, card_ids)


def _snapshot_styling(col: Collection) -> Dict[int, Tuple[str, List[Dict[str, Any]]]]:
    """note type id -> (css, [template subset]) for every note type."""
    out: Dict[int, Tuple[str, List[Dict[str, Any]]]] = {}
    for nt in col.models.all():
        tmpls = [{k: t.get(k) for k in TEMPLATE_KEYS + ("id", "ord")} for t in nt["tmpls"]]
        out[int(nt["id"])] = (nt.get("css", ""), tmpls)
    return out


# --- restore ------------------------------------------------------------------------


def _positions(fields: _FieldInfo) -> Tuple[Dict[int, int], Dict[str, int]]:
    """(field config id -> position, normalized name -> position)."""
    by_id: Dict[int, int] = {}
    by_name: Dict[str, int] = {}
    for i, (fid, name) in enumerate(fields):
        if fid:
            by_id.setdefault(fid, i)
        by_name.setdefault(name, i)
    return by_id, by_name


def _follow(fid: Optional[int], name: str, by_id: Dict[int, int], by_name: Dict[str, int]) -> Optional[int]:
    """Position of a field in another version of its note type: field config
    id first, then normalized name (as Anki's own merge matches fields)."""
    if fid:
        idx = by_id.get(fid)
        if idx is not None:
            return idx
    return by_name.get(name)


def _field_map(old_fields: _FieldInfo, new_fields: _FieldInfo, moved: bool) -> List[Optional[int]]:
    """For each old field position, its position on the (new) note type.

    Same note type: field config id first, then normalized name (as Anki's
    own merge matches fields; follows an author's rename). Moved note: by
    normalized name first, so a value goes to the properly named field and
    never to a "<name>+" duplicate; an old field with no same-named field
    is followed by id, i.e. to the field Anki carried it over as."""
    by_id, by_name = _positions(new_fields)
    out: List[Optional[int]] = []
    taken: Set[int] = set()
    for fid, name in old_fields:
        if moved:
            idx = by_name.get(name)
            if idx is None and fid:
                idx = by_id.get(fid)
        else:
            idx = _follow(fid, name, by_id, by_name)
        if idx is not None and idx in taken:
            idx = None  # never two old fields into one
        if idx is not None:
            taken.add(idx)
        out.append(idx)
    return out


def _restore_notes(
    col: Collection,
    snap: _Snapshot,
    settings: Settings,
    updated_ids: Sequence[int],
    added_ids: Sequence[int],
    res: ImportResult,
) -> None:
    """Kept fields, rule 9 and protected tags on the updated notes.

    A note whose note type id changed in the import ("moved", rule 10a) is
    restored by field NAME on its new note type, so a value never lands in
    a "<name>+" duplicate made by Anki's merge; an old field with no
    same-named field there is followed by field config id (the field Anki
    carried it over as)."""
    updated: Set[int] = {nid for nid in updated_ids if nid in snap.notes}
    if not updated:
        return
    touched: Set[int] = updated.union(added_ids)
    kept = settings.kept_field_names()
    listed = frozenset(norm_field(f.name) for f in settings.fields)
    protects = settings.protects_tag
    want_tags = any(norm_tag(t) for t in settings.protected_tags)

    # One pass over the post-import state of the notes this import touched.
    post: Dict[int, Tuple[int, List[str], str]] = {}
    for nid, mid, flds, tags in col.db.execute("select id, mid, flds, tags from notes"):
        if nid in touched:
            post[nid] = (mid, flds.split("\x1f"), tags)

    post_fields = _notetype_fields(col)

    # Rule 9: per note type, the unlisted fields that are empty on every note
    # of that type this import added or updated.
    has_content: Dict[int, List[bool]] = {}
    for mid, vals, _tags in post.values():
        flags = has_content.get(mid)
        if flags is None:
            flags = has_content[mid] = [False] * len(post_fields.get(mid, ()))
        for i in range(min(len(flags), len(vals))):
            if not flags[i] and vals[i].strip():
                flags[i] = True
    no_content: Dict[int, List[int]] = {}
    for mid, flags in has_content.items():
        fields = post_fields.get(mid, [])
        no_content[mid] = [i for i, flag in enumerate(flags) if not flag and fields[i][1] not in listed]

    # (old note type id, new note type id) -> old field position -> new position
    maps: Dict[Tuple[int, int], List[Optional[int]]] = {}
    plans: Dict[int, Tuple[Dict[int, str], List[str]]] = {}
    for nid in updated:
        mid, vals, tags = post[nid]
        old_mid, old_flds, old_tags = snap.notes[nid]
        old_fields = snap.fields.get(old_mid, [])
        writes: Dict[int, str] = {}
        candidates = no_content.get(mid, ())
        if (kept or candidates) and old_fields:
            key = (old_mid, mid)
            fmap = maps.get(key)
            if fmap is None:
                fmap = maps[key] = _field_map(old_fields, post_fields.get(mid, []), moved=old_mid != mid)
            old_vals = old_flds.split("\x1f")
            # "Keep mine": each kept pre-import field, followed to where it is now.
            if kept:
                for i, (_fid, name) in enumerate(old_fields):
                    idx = fmap[i]
                    if name not in kept or idx is None or i >= len(old_vals) or idx >= len(vals):
                        continue
                    if vals[idx] != old_vals[i]:
                        writes[idx] = old_vals[i]
            # Rule 9: a field the update has no content for gets its pre-import
            # value back (a field that did not exist before has none).
            if candidates:
                source = {idx: i for i, idx in enumerate(fmap) if idx is not None}
                for idx in candidates:
                    i = source.get(idx)
                    if idx in writes or i is None or idx >= len(vals) or i >= len(old_vals):
                        continue
                    if vals[idx] != old_vals[i]:
                        writes[idx] = old_vals[i]
        tag_adds: List[str] = []
        if want_tags and old_tags:
            ptags = [t for t in old_tags.split() if protects(t)]
            if ptags:
                current = {norm_tag(t) for t in tags.split()}
                for tag in ptags:
                    key = norm_tag(tag)
                    if key not in current:
                        tag_adds.append(tag)
                        current.add(key)
        if writes or tag_adds:
            plans[nid] = (writes, tag_adds)

    to_save = []
    for nid in sorted(plans):
        writes, tag_adds = plans[nid]
        note = col.get_note(nid)
        for idx, value in writes.items():
            note.fields[idx] = value
        if tag_adds:
            note.tags = list(note.tags) + tag_adds
        to_save.append(note)
        if writes:
            res.fields_kept += len(writes)
            res.notes_with_fields_kept += 1
        if tag_adds:
            res.protected_tags_kept += len(tag_adds)
            res.notes_with_tags_kept += 1
    if to_save:
        col.update_notes(to_save)


# --- note type merge clean-up (rule 10b) --------------------------------------------

# A field reference in a template: {{Name}}, {{#Name}}, {{/Name}}, {{^Name}},
# {{filter:Name}}, {{cloze:Name}}, {{type:cloze:Name}}...
_FIELD_REF = re.compile(r"\{\{([#/^]?)([^{}]*)\}\}")


def _rename_refs(text: str, renames: Dict[str, str]) -> str:
    """Point every template reference to a field named in `renames` (exact
    stored name) at the new name; everything else is left untouched."""
    if not text or not renames:
        return text

    def sub(m: "re.Match[str]") -> str:
        prefix, body = m.group(1), m.group(2)
        head, sep, last = body.rpartition(":")
        name = last.strip()
        if name in renames:
            return "{{%s%s%s%s}}" % (prefix, head, sep, last.replace(name, renames[name]))
        return m.group(0)

    return _FIELD_REF.sub(sub, text)


def _clean_merge_leftovers(col: Collection, snap: _Snapshot, touched: Set[int]) -> int:
    """Rule 10b: undo the damage Anki's forced note type merge does when a
    note in the file has a different note type than the same note in the
    collection (author moved it, user changed its type, same-named note
    type with another id).

    The merge appends the note's old note type's fields and card templates
    to the file's note type, renaming clashes to "<name>+"; it also points
    the existing templates' field references at the "+" fields, moves the
    existing cards of that note type onto the appended "+" template, gives
    every note a new duplicate card on the original template, and moves the
    content of notes of that type which are NOT in the file into the "+"
    fields (verified identically on 25.02.7 to 26.11b1).

    For each note type with leftover fields (did not exist on that note type
    before the import, name ends with "+", the name without the trailing
    "+" matches another field) this, in order: puts back the pre-import
    content of the type's notes the import did not touch; keeps any
    leftover field that then still holds content on some note (it is never
    removed); moves each card on a
    leftover template ("<name>+", new on this note type) back to the
    original template, replacing the duplicate there only if that duplicate
    is a new card this import created with no review history; then repoints
    template references from "<name>+" to "<name>" and removes the leftover
    fields and templates. A leftover field that holds content is kept (not
    a failure). Returns the number of note types cleaned.

    Rule 10g: if the repair cannot be completed safely for a note type,
    raise MergeRepairError; `run_import` then rolls the whole import back
    (every edit made here is an undoable op inside our undo step, and all
    checks run before the first edit of each note type)."""
    cleaned = 0
    validator = _Validator()
    try:
        for nt in col.models.all():
            name = str(nt.get("name", nt["id"]))
            try:
                if _clean_notetype(col, int(nt["id"]), snap, touched, validator):
                    cleaned += 1
            except MergeRepairError:
                raise
            except Exception as exc:
                raise MergeRepairError(name, "the repair failed: %s" % exc) from exc
            finally:
                _clear_notetype_cache(col)
    finally:
        validator.close()
    return cleaned


def _leftover_fields(nt: Dict[str, Any], pre: Optional[_FieldInfo]) -> Dict[int, int]:
    """leftover field position -> position of the field it duplicates."""
    flds = nt["flds"]
    pre_ids = {fid for fid, _n in (pre or []) if fid}
    pre_names = {n for _f, n in (pre or [])}
    names = [norm_field(f["name"]) for f in flds]
    candidates: Dict[int, str] = {}
    for i, f in enumerate(flds):
        fid = f.get("id")
        if (fid and fid in pre_ids) or (not fid and names[i] in pre_names):
            continue  # existed before the import: never removed
        raw = f["name"].strip()
        if not raw.endswith("+"):
            continue
        base = norm_field(raw.rstrip("+"))
        if base:
            candidates[i] = base
    out: Dict[int, int] = {}
    for i, base in candidates.items():
        for j, name in enumerate(names):
            if j != i and j not in candidates and name == base:
                out[i] = j
                break
    return out


def _leftover_templates(nt: Dict[str, Any], pre_ids: Set[Any]) -> Dict[int, int]:
    """leftover template ord -> ord of the template it duplicates (standard
    note types only; Anki does not merge cloze templates)."""
    if nt.get("type") == 1:
        return {}
    tmpls = nt["tmpls"]
    names = [str(t.get("name", "")).strip().casefold() for t in tmpls]
    candidates: Dict[int, str] = {}
    for i, t in enumerate(tmpls):
        tid = t.get("id")
        if tid and tid in pre_ids:
            continue
        raw = str(t.get("name", "")).strip()
        if raw.endswith("+") and raw.rstrip("+").strip():
            candidates[i] = raw.rstrip("+").strip().casefold()
    out: Dict[int, int] = {}
    for i, base in candidates.items():
        for j, name in enumerate(names):
            if j != i and j not in candidates and name == base:
                out[i] = j
                break
    return out


def _repaired(nt: Dict[str, Any], leftovers: Dict[int, int], tmpl_leftovers: Dict[int, int]) -> Dict[str, Any]:
    """`nt` with template references from leftover fields pointed back at the
    fields they duplicate, and the leftover fields and templates removed."""
    renames = {nt["flds"][i]["name"]: nt["flds"][j]["name"] for i, j in leftovers.items()}
    for t in nt["tmpls"]:
        for key in ("qfmt", "afmt", "bqfmt", "bafmt"):
            if t.get(key):
                t[key] = _rename_refs(t[key], renames)
    if tmpl_leftovers:
        nt["tmpls"] = [t for i, t in enumerate(nt["tmpls"]) if i not in tmpl_leftovers]
    nt["flds"] = [f for i, f in enumerate(nt["flds"]) if i not in leftovers]
    return nt


class _Validator:
    """Anki's own note type checks, run on a throwaway collection.

    A backend operation that fails discards Anki's whole undo queue (rslib
    `transact_inner`), so after the native import a failing note type edit
    could no longer be rolled back. The repaired note type is therefore
    first added to an empty scratch collection: if Anki refuses it there,
    nothing in the user's collection has been touched yet."""

    def __init__(self) -> None:
        self._dir: Optional[str] = None
        self._col: Optional[Collection] = None

    def check(self, nt: Dict[str, Any]) -> Optional[str]:
        if self._col is None:
            self._dir = tempfile.mkdtemp(prefix="sfa-validate-")
            self._col = Collection(os.path.join(self._dir, "scratch.anki2"))
        trial = copy.deepcopy(nt)
        trial["id"] = 0
        trial["name"] = str(nt.get("name") or "check")
        try:
            self._col.models.add_dict(trial)
        except Exception as exc:
            return str(exc)
        return None

    def close(self) -> None:
        if self._col is not None:
            try:
                self._col.close(downgrade=False)
            except Exception:
                pass
            self._col = None
        if self._dir:
            shutil.rmtree(self._dir, ignore_errors=True)
            self._dir = None


def _clean_notetype(
    col: Collection, mid: int, snap: _Snapshot, touched: Set[int], validator: "_Validator"
) -> bool:
    nt = col.models.get(mid)
    if not nt:
        return False
    pre_fields = snap.fields.get(mid)
    leftovers = _leftover_fields(nt, pre_fields)
    if not leftovers:
        return False
    tmpl_leftovers = _leftover_templates(nt, snap.templates.get(mid, set()))
    post_fields: _FieldInfo = [(f.get("id") or None, norm_field(f["name"])) for f in nt["flds"]]
    rows = col.db.all("select id, flds from notes where mid = ?", mid)

    # 1. Notes of this type the import did not touch, but whose content the
    #    merge moved: back to exactly their pre-import content.
    fixes: Dict[int, List[str]] = {}
    contents: Dict[int, List[str]] = {}
    for nid, flds in rows:
        vals = flds.split("\x1f")
        old = snap.notes.get(nid)
        if nid not in touched and old is not None and old[0] == mid and pre_fields:
            old_vals = old[1].split("\x1f")
            fmap = _field_map(pre_fields, post_fields, moved=False)
            new_vals = [""] * len(post_fields)
            for i, idx in enumerate(fmap):
                if idx is not None and i < len(old_vals):
                    new_vals[idx] = old_vals[i]
            if len(old_vals) != len(pre_fields) or None in fmap:
                raise MergeRepairError(
                    nt["name"], "a note the file does not contain cannot be put back exactly")
            if new_vals != vals:
                fixes[nid] = new_vals
            vals = new_vals
        contents[nid] = vals

    # 2. A leftover field that holds content on any note is not a leftover
    #    after all (for example the author's own field named "Header+"): it
    #    stays. Only fields empty on every note of the type are removed.
    for vals in contents.values():
        for i in list(leftovers):
            if i < len(vals) and vals[i].strip():
                del leftovers[i]
    if not leftovers:
        return False

    # 3. Cards on leftover templates go back to the original template; the
    #    duplicate there must be a card this import created, never reviewed.
    groups: Dict[Tuple[int, ...], List[int]] = {}
    if tmpl_leftovers:
        nids = [nid for nid, _f in rows]
        cards: Dict[int, Dict[int, int]] = {}
        for cid, nid, ord_ in col.db.all(
            "select id, nid, ord from cards where nid in (select id from notes where mid = ?)", mid
        ):
            cards.setdefault(nid, {})[ord_] = cid
        reviewed = set(
            col.db.list(
                "select distinct cid from revlog where cid in "
                "(select id from cards where nid in (select id from notes where mid = ?))",
                mid,
            )
        )
        for nid in nids:
            by_ord = cards.get(nid, {})
            on_leftover = tuple(sorted(o for o in tmpl_leftovers if o in by_ord))
            if not on_leftover:
                continue
            for o in on_leftover:
                dup = by_ord.get(tmpl_leftovers[o])
                if dup is not None and (dup in snap.card_ids or dup in reviewed):
                    raise MergeRepairError(
                        nt["name"], "a card that would have to be removed existed before the "
                        "import or has review history")
            groups.setdefault(on_leftover, []).append(nid)

    # 4. Anki must accept the repaired note type (checked on a scratch
    #    collection, before anything here is changed).
    problem = validator.check(_repaired(copy.deepcopy(nt), leftovers, tmpl_leftovers))
    if problem:
        raise MergeRepairError(nt["name"], "Anki refused the repaired note type: %s" % problem)

    # --- apply ---------------------------------------------------------------
    if fixes:
        notes = []
        for nid, vals in fixes.items():
            note = col.get_note(nid)
            note.fields = list(vals)
            notes.append(note)
        col.update_notes(notes)
    n_tmpls = len(nt["tmpls"])
    for on_leftover, nids in groups.items():
        new_templates: List[Optional[int]] = list(range(n_tmpls))
        for o in on_leftover:
            new_templates[tmpl_leftovers[o]] = o
            new_templates[o] = None
        info = col.models.change_notetype_info(old_notetype_id=mid, new_notetype_id=mid)
        req = info.input
        req.note_ids.extend(nids)
        del req.new_fields[:]
        req.new_fields.extend(range(len(nt["flds"])))
        del req.new_templates[:]
        req.new_templates.extend(-1 if o is None else o for o in new_templates)
        col.models.change_notetype_of_notes(req)
    _clear_notetype_cache(col)

    # 5. Template references back to the real field names, then remove the
    #    leftover templates (now without cards) and fields (empty).
    nt = col.models.get(mid)
    if nt is None or len(nt["flds"]) != len(post_fields):
        raise MergeRepairError(str(mid), "the note type changed during the repair")
    col.models.update_dict(_repaired(nt, leftovers, tmpl_leftovers))
    return True


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


def _roll_back(col: Collection, undo_pos: int, prior: Any = None) -> None:
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
            _forget_redo(col, prior)
    except Exception:
        pass
    _clear_notetype_cache(col)


# A config key every collection has; writing its own value back is a no-op
# on disk but runs as a non-undoable backend operation, which empties Anki's
# undo and redo queues (rslib transact_no_undo).
_QUEUE_CLEARING_KEY = "sortType"


def _forget_redo(col: Collection, prior: Any) -> None:
    """After a roll-back our undone step sits on Anki's redo stack, and Redo
    would apply the failed import half-done (for example the native import
    without the user's kept fields put back). Leave nothing to redo, and the
    user's own step on top:

    * the user had steps to undo: a new undo entry empties the redo stack;
      that empty entry is folded into the user's own top step (identified by
      `prior`, the undo status before the import: its id is `last_step`
      when nothing was waiting to be redone);
    * the user had nothing to undo: a no-op, non-undoable backend operation
      (writing a config value back unchanged) empties both queues; nothing
      of the user's is lost because the undo queue was empty anyway;
    * otherwise the empty entry is undone again, so only that empty,
      harmless entry is left to redo."""
    status = col.undo_status()
    if status.redo != UNDO_LABEL:
        return
    if prior is not None and not prior.undo and not status.undo:
        value = col.get_config(_QUEUE_CLEARING_KEY, _MISSING)
        if value is not _MISSING:
            try:
                col.set_config(_QUEUE_CLEARING_KEY, value, undoable=False)
            except Exception:
                pass
            if not col.undo_status().redo:
                return
    pos = col.add_custom_undo_entry(UNDO_LABEL)
    if prior is not None and prior.undo and not prior.redo and prior.undo == status.undo:
        try:
            col.merge_undo_entries(prior.last_step)
        except Exception:
            pass
    if col.undo_status().last_step == pos:
        col.undo()
