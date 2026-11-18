"""Helpers for the acceptance tests (workstream D).

Expectations are derived from docs/CONTRACT.md only:
  * "the update's" content of a note = that note as it appears after
    importing the package into an EMPTY collection (a reference collection
    the fixture builder makes with Anki's own importer);
  * "mine" = the note in the simulated user's collection before the import.

Nothing here reads or imitates engine.py.
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from special_fields_by_ankoma import config as sfa_config
from special_fields_by_ankoma.model import FieldChoice, Settings, TagRule, norm_field, norm_tag

MAX_SHOWN = 12

# Ankoma's defaults: the 7 cloze fields, only Personal Notes kept, no
# protected tags, templates/styling updated.
DEFAULTS = sfa_config.default_settings()


def settings(keep=(), take=(), protected=(), update_note_types=True, rules=()) -> Settings:
    """`keep` names are "Keep mine", `take` names are "Take the update's".
    `rules`: (tag, field names) pairs for protected tags that also keep
    fields (contract rule 14); field names == "all" means every field."""
    return Settings(
        fields=tuple(FieldChoice(n, True) for n in keep) + tuple(FieldChoice(n, False) for n in take),
        protected_tags=tuple(protected),
        update_note_types=update_note_types,
        tag_rules=tuple(TagRule(t, (), True) if f == "all" else TagRule(t, tuple(f), False)
                        for t, f in rules),
    )


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------


def copy_collection(src: str, dst_dir: str, name: str = "user") -> str:
    """Copy a closed collection (and its media folder) into dst_dir."""
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, name + ".anki2")
    shutil.copy2(src, dst)
    smedia = src[: -len(".anki2")] + ".media"
    if os.path.isdir(smedia):
        shutil.copytree(smedia, dst[: -len(".anki2")] + ".media", dirs_exist_ok=True)
    return dst


def open_collection(path: str):
    from anki.collection import Collection

    return Collection(path)


def fresh_notetypes(col) -> List[dict]:
    """All note types, bypassing pylib's Python-side cache.

    The cache is not invalidated by a backend import (spike gotcha G1); the
    test must see what is really stored, whatever the engine did.
    """
    clear = getattr(col.models, "_clear_cache", None)
    if clear:
        clear()
    return col.models.all()


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------


@dataclass
class NoteSnap:
    nid: int
    guid: str
    notetype: str
    fields: Dict[str, str]  # field name (as stored) -> value
    tags: List[str]
    mod: int

    def field(self, name: str) -> Optional[str]:
        key = norm_field(name)
        for k, v in self.fields.items():
            if norm_field(k) == key:
                return v
        return None

    def has_field(self, name: str) -> bool:
        return self.field(name) is not None


def notes_by_guid(col) -> Dict[str, NoteSnap]:
    """guid -> NoteSnap, straight from SQL (no caches)."""
    names = dict(col.db.all("select id, name from notetypes"))
    fnames: Dict[int, List[str]] = {}
    for ntid, _ord, name in col.db.all("select ntid, ord, name from fields order by ntid, ord"):
        fnames.setdefault(ntid, []).append(name)
    out: Dict[str, NoteSnap] = {}
    for nid, guid, mid, mod, tags, flds in col.db.execute(
            "select id, guid, mid, mod, tags, flds from notes"):
        vals = flds.split("\x1f")
        fl = fnames.get(mid, [])
        out[guid] = NoteSnap(nid=nid, guid=guid, notetype=names.get(mid, "?%s" % mid),
                             fields=dict(zip(fl, vals)), tags=tags.split(), mod=mod)
    return out


def card_rows(col, cids: Optional[Iterable[int]] = None) -> Dict[int, tuple]:
    rows = col.db.all("select * from cards")
    out = {r[0]: tuple(r) for r in rows}
    if cids is not None:
        keep = set(cids)
        out = {k: v for k, v in out.items() if k in keep}
    return out


def revlog_rows(col, cids: Optional[Iterable[int]] = None) -> List[tuple]:
    rows = [tuple(r) for r in col.db.all("select * from revlog order by id")]
    if cids is not None:
        keep = set(cids)
        rows = [r for r in rows if r[1] in keep]
    return rows


def deck_name_by_id(col) -> Dict[int, str]:
    return {d.id: d.name for d in col.decks.all_names_and_ids()}


def card_decks_by_note_ord(col) -> Dict[Tuple[str, int], str]:
    """(note guid, card ord) -> deck name."""
    names = deck_name_by_id(col)
    out = {}
    for guid, ord_, did in col.db.all(
            "select n.guid, c.ord, c.did from cards c join notes n on n.id = c.nid"):
        out[(guid, ord_)] = names.get(did, "?%s" % did)
    return out


TEMPLATE_KEYS = ("name", "qfmt", "afmt", "bqfmt", "bafmt")


def notetype_looks(col) -> Dict[str, Dict[str, Any]]:
    """note type name -> {"css": ..., "tmpls": [(name, qfmt, afmt, bqfmt, bafmt)], "fields": [...]}"""
    out = {}
    for nt in fresh_notetypes(col):
        out[nt["name"]] = {
            "css": nt["css"],
            "tmpls": [tuple(t.get(k, "") for k in TEMPLATE_KEYS) for t in nt["tmpls"]],
            "fields": [f["name"] for f in nt["flds"]],
        }
    return out


UNDO_TABLES = ("notes", "cards", "revlog", "notetypes", "fields", "templates",
               "decks", "deck_config", "tags", "graves", "config")


def db_state(col, tables: Iterable[str] = UNDO_TABLES) -> Dict[str, List[tuple]]:
    out = {}
    for t in tables:
        out[t] = sorted((tuple(r) for r in col.db.all("select * from %s" % t)), key=repr)
    out["col.scm"] = [(col.db.scalar("select scm from col"),)]
    return out


def diff_db_state(a: Dict[str, List[tuple]], b: Dict[str, List[tuple]]) -> List[str]:
    msgs = []
    for t in a:
        if a[t] != b.get(t):
            sa, sb = set(a[t]), set(b.get(t, []))
            only_a = sorted(sa - sb, key=repr)[:3]
            only_b = sorted(sb - sa, key=repr)[:3]
            msgs.append("table %s differs: %d rows before vs %d after; only before (first 3): %s; "
                        "only after (first 3): %s" % (t, len(a[t]), len(b.get(t, [])),
                                                      _short(only_a), _short(only_b)))
    return msgs


def _short(x: Any, n: int = 400) -> str:
    s = repr(x)
    return s if len(s) <= n else s[:n] + "...(truncated)"


# ---------------------------------------------------------------------------
# Expected outcome (contract rules 2-4, 9 and 10)
# ---------------------------------------------------------------------------


def norm_tags(tags: Iterable[str]) -> Set[str]:
    return {norm_tag(t) for t in tags}


def listed_field_names(settings: Settings) -> Set[str]:
    """Normalized names of every field listed in the settings (either side)."""
    return {norm_field(f.name) for f in settings.fields}


def type_fields(before: Dict[str, NoteSnap], update: Dict[str, NoteSnap]) -> Dict[str, List[str]]:
    """note type name -> the field names it must have after the import:
    the update's fields, plus every field the user's note type already had
    (rule 2: nothing is dropped; rule 10: no "<name>+" leftovers). Names are
    as stored, deduplicated by normalized name, update's spelling first."""
    out: Dict[str, List[str]] = {}
    seen: Dict[str, Set[str]] = {}
    for src in (update, before):
        for n in src.values():
            names = out.setdefault(n.notetype, [])
            keys = seen.setdefault(n.notetype, set())
            for name in n.fields:
                if norm_field(name) not in keys:
                    keys.add(norm_field(name))
                    names.append(name)
    return out


def update_has_no_content(update: Dict[str, NoteSnap], imported: Iterable[str],
                          fields_by_type: Dict[str, List[str]]) -> Set[Tuple[str, str]]:
    """(note type, normalized field) pairs that are empty (after strip()) on
    every note of that type the import added or updated (contract rule 9).
    A field the update's note type does not have at all counts as empty."""
    content: Set[Tuple[str, str]] = set()
    types: Set[str] = set()
    for g in imported:
        n = update[g]
        types.add(n.notetype)
        for name, val in n.fields.items():
            if val.strip():
                content.add((n.notetype, norm_field(name)))
    return {(t, norm_field(f)) for t in types for f in fields_by_type.get(t, [])
            if (t, norm_field(f)) not in content}


def kept_on_note(before: Optional[NoteSnap], settings: Settings) -> Tuple[Set[str], bool]:
    """Contract rule 14, read from the contract: the normalized names of the
    fields kept on a note (the "Keep mine" fields plus the fields of every
    protected tag the note carried BEFORE the import, a sub-tag carrying
    its parent's rule, case-insensitive), and whether every field is kept.
    A rule counts only for a tag that is protected."""
    kept = {norm_field(f.name) for f in settings.fields if f.keep}
    every = False
    if before is None:
        return kept, every
    protected = {norm_tag(t) for t in settings.protected_tags if norm_tag(t)}
    mine = [norm_tag(t) for t in before.tags]
    for rule in settings.tag_rules:
        rt = norm_tag(rule.tag)
        if rt not in protected:
            continue
        if any(t == rt or t.startswith(rt + "::") for t in mine):
            every = every or rule.keep_all
            kept |= {norm_field(f) for f in rule.keep_fields if norm_field(f)}
    return kept, every


def expected_fields(before: Optional[NoteSnap], update: NoteSnap, settings: Settings,
                    field_names: Optional[Iterable[str]] = None,
                    no_content: Optional[Set[Tuple[str, str]]] = None) -> Dict[str, Tuple[str, str]]:
    """Field name -> (expected value, rule) for a note that is in the file.

    `field_names`: every field the note's note type has after the import
    (default: the update's fields). Rules: "Keep mine" (rule 2), matched by
    name, also for a note the update moved to another note type (rule 10a);
    a field not listed in the settings that the update has no content for
    on any added/updated note of the type gets the user's value back (rule
    9); otherwise the update's value ("" for a field the update lacks).
    Rule 14: a protected tag the note carried before the import adds its
    fields to "Keep mine" (or keeps every field) for that note only; for
    rule 9 a field listed only in a tag rule is unlisted on other notes."""
    names = list(field_names) if field_names is not None else list(update.fields)
    listed = listed_field_names(settings)
    no_content = no_content or set()
    kept, every = kept_on_note(before, settings)
    exp: Dict[str, Tuple[str, str]] = {}
    for name in names:
        upd_val = update.field(name)
        upd_val = upd_val if upd_val is not None else ""
        key = norm_field(name)
        if before is not None and before.has_field(name):
            # Rule 14: "every field" = every field the note had before; a
            # field new to the note takes the update's.
            if every or key in kept:
                exp[name] = (before.field(name), "Keep mine" if settings.keeps_field(name) else "Keep mine (tag rule)")
                continue
            if key not in listed and (update.notetype, key) in no_content:
                exp[name] = (before.field(name), "rule 9: update has no content")
                continue
        exp[name] = (upd_val, "Take the update's" if key in listed else "update's content")
    return exp


def expected_tags(before: Optional[NoteSnap], update: NoteSnap, settings: Settings) -> Set[str]:
    exp = norm_tags(update.tags)
    if before is not None:
        exp |= {norm_tag(t) for t in before.tags if settings.protects_tag(t)}
    return exp


def check_import_outcome(before: Dict[str, NoteSnap], update: Dict[str, NoteSnap],
                         after: Dict[str, NoteSnap], settings: Settings,
                         label: str = "") -> List[str]:
    """Every rule about note content and tags, for every note and EVERY
    field of it (not only the fields the update has).

    Returns human-readable mismatch descriptions (empty = all as expected).
    """
    problems: List[str] = []

    def bad(msg: str) -> None:
        problems.append(msg)

    fields_by_type = type_fields(before, update)
    no_content = update_has_no_content(update, update.keys(), fields_by_type)
    for guid, upd in update.items():
        got = after.get(guid)
        old = before.get(guid)
        kind = "updated" if old is not None else "new"
        if got is None:
            bad("%s note %s (%s) from the file is missing after import" % (kind, guid, upd.notetype))
            continue
        if got.notetype != upd.notetype:
            bad("%s note nid=%s is of note type %r, the file has it as %r"
                % (kind, got.nid, got.notetype, upd.notetype))
        want_names = fields_by_type.get(upd.notetype, list(upd.fields))
        extra = [n for n in got.fields if norm_field(n) not in {norm_field(w) for w in want_names}]
        if extra:
            bad("%s note nid=%s (%s) has unexpected fields %r (merge leftovers?)"
                % (kind, got.nid, got.notetype, extra))
        for name, (exp, rule) in expected_fields(old, upd, settings, want_names, no_content).items():
            actual = got.field(name)
            if actual is None:
                bad("%s note nid=%s (%s): field %r missing after import" % (kind, got.nid, got.notetype, name))
            elif actual != exp:
                bad("%s note nid=%s (%s) field %r [%s]: expected %r, got %r"
                    % (kind, got.nid, got.notetype, name, rule, exp, actual))
        exp_t = expected_tags(old, upd, settings)
        got_t = norm_tags(got.tags)
        if got_t != exp_t:
            bad("%s note nid=%s (%s) tags: expected exactly the update's tags%s %s, got %s "
                "(missing %s, unexpected %s)"
                % (kind, got.nid, got.notetype,
                   " + protected" if settings.protected_tags else "",
                   sorted(exp_t), sorted(got_t), sorted(exp_t - got_t), sorted(got_t - exp_t)))
        if old is not None:
            # original spelling of protected tags is kept
            for t in old.tags:
                if settings.protects_tag(t) and norm_tag(t) not in norm_tags(upd.tags):
                    if t not in got.tags:
                        bad("updated note nid=%s: protected tag %r not kept with its original "
                            "spelling (tags now %s)" % (got.nid, t, got.tags))
    for guid, old in before.items():
        if guid in update:
            continue
        got = after.get(guid)
        if got is None:
            bad("note nid=%s not in the file was deleted" % old.nid)
        elif (got.fields, got.tags) != (old.fields, old.tags):
            bad("note nid=%s (%s) is not in the file but changed: fields %r -> %r, tags %r -> %r"
                % (old.nid, old.notetype, old.fields, got.fields, old.tags, got.tags))
    return problems


def fail_msg(problems: List[str], what: str) -> str:
    head = "%s: %d problem(s). First %d:\n  " % (what, len(problems), min(MAX_SHOWN, len(problems)))
    return head + "\n  ".join(problems[:MAX_SHOWN])


# ---------------------------------------------------------------------------
# Expected ImportResult counters (contract section B, model.ImportResult)
# ---------------------------------------------------------------------------


def expected_counters(before: Dict[str, NoteSnap], update: Dict[str, NoteSnap],
                      settings: Settings) -> Dict[str, int]:
    """fields_kept counts values written back: "Keep mine" and rule 9
    values that differ from what the update put there (its value, or "" for
    a field it lacks)."""
    added = [g for g in update if g not in before]
    existing = [g for g in update if g in before]
    fields_by_type = type_fields(before, update)
    no_content = update_has_no_content(update, update.keys(), fields_by_type)
    fields_kept = notes_fk = tags_kept = notes_tk = 0
    for g in existing:
        old, upd = before[g], update[g]
        n_f = 0
        names = fields_by_type.get(upd.notetype, list(upd.fields))
        for name, (exp, rule) in expected_fields(old, upd, settings, names, no_content).items():
            if rule.startswith(("Keep", "rule 9")):
                written_by_update = upd.field(name)
                if exp != (written_by_update if written_by_update is not None else ""):
                    n_f += 1
        upd_t = norm_tags(upd.tags)
        n_t = sum(1 for t in old.tags if settings.protects_tag(t) and norm_tag(t) not in upd_t)
        fields_kept += n_f
        notes_fk += 1 if n_f else 0
        tags_kept += n_t
        notes_tk += 1 if n_t else 0
    return {
        "notes_in_file": len(update),
        "notes_added": len(added),
        "notes_updated": len(existing),
        "notes_skipped": 0,
        "fields_kept": fields_kept,
        "notes_with_fields_kept": notes_fk,
        "protected_tags_kept": tags_kept,
        "notes_with_tags_kept": notes_tk,
    }
