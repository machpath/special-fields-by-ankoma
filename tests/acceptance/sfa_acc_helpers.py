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
from special_fields_by_ankoma.model import FieldChoice, Settings, norm_field, norm_tag

MAX_SHOWN = 12

# Ankoma's defaults: the 7 cloze fields, only Personal Notes kept, no
# protected tags, templates/styling updated.
DEFAULTS = sfa_config.default_settings()


def settings(keep=(), take=(), protected=(), update_note_types=True) -> Settings:
    """`keep` names are "Keep mine", `take` names are "Take the update's"."""
    return Settings(
        fields=tuple(FieldChoice(n, True) for n in keep) + tuple(FieldChoice(n, False) for n in take),
        protected_tags=tuple(protected),
        update_note_types=update_note_types,
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
# Expected outcome (contract rules 2-4)
# ---------------------------------------------------------------------------


def norm_tags(tags: Iterable[str]) -> Set[str]:
    return {norm_tag(t) for t in tags}


def expected_fields(before: Optional[NoteSnap], update: NoteSnap, settings: Settings) -> Dict[str, str]:
    """Field name -> expected value for a note that is in the file."""
    exp = {}
    for name, val in update.fields.items():
        if before is not None and settings.keeps_field(name) and before.has_field(name):
            exp[name] = before.field(name)  # "Keep mine"
        else:
            exp[name] = val  # "Take the update's" (or field new to this note)
    return exp


def expected_tags(before: Optional[NoteSnap], update: NoteSnap, settings: Settings) -> Set[str]:
    exp = norm_tags(update.tags)
    if before is not None:
        exp |= {norm_tag(t) for t in before.tags if settings.protects_tag(t)}
    return exp


def check_import_outcome(before: Dict[str, NoteSnap], update: Dict[str, NoteSnap],
                         after: Dict[str, NoteSnap], settings: Settings,
                         label: str = "") -> List[str]:
    """Every rule about note content and tags, for every note.

    Returns human-readable mismatch descriptions (empty = all as expected).
    """
    problems: List[str] = []

    def bad(msg: str) -> None:
        problems.append(msg)

    for guid, upd in update.items():
        got = after.get(guid)
        old = before.get(guid)
        kind = "updated" if old is not None else "new"
        if got is None:
            bad("%s note %s (%s) from the file is missing after import" % (kind, guid, upd.notetype))
            continue
        for name, exp in expected_fields(old, upd, settings).items():
            actual = got.field(name)
            if actual is None:
                bad("%s note nid=%s (%s): field %r missing after import" % (kind, got.nid, got.notetype, name))
            elif actual != exp:
                rule = ("Keep mine" if (old is not None and settings.keeps_field(name)
                                        and old.has_field(name)) else "Take the update's")
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
    added = [g for g in update if g not in before]
    existing = [g for g in update if g in before]
    fields_kept = notes_fk = tags_kept = notes_tk = 0
    for g in existing:
        old, upd = before[g], update[g]
        n_f = 0
        for name, val in upd.fields.items():
            if settings.keeps_field(name) and old.has_field(name) and old.field(name) != val:
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
