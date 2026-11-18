"""Shared data model for Special Fields by Ankoma.

This file is the contract between the engine (no GUI) and the screens.
It must import nothing from `anki` or `aqt`, and must run on Python 3.9
through 3.13: no `match`, no PEP 604 unions at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Iterable, List, Optional, Tuple

ADDON_NAME = "Special Fields by Ankoma"
UNDO_LABEL = "Special Fields update"
ACCENT_COLOR = "#7A2E6B"


def norm_field(name: str) -> str:
    """Field names are compared ignoring case and surrounding spaces."""
    return name.strip().casefold()


def norm_tag(tag: str) -> str:
    """Tags are compared ignoring case, as Anki does."""
    return tag.strip().casefold()


def is_protected_tag(tag: str, protected: Iterable[str]) -> bool:
    """True if `tag` is a protected tag or a sub-tag of one.

    Protecting "#edited" also protects "#edited::images" (Anki treats "::"
    as hierarchy), but not "#edited2".
    """
    t = norm_tag(tag)
    for p in protected:
        n = norm_tag(p)
        if not n:
            continue
        if t == n or t.startswith(n + "::"):
            return True
    return False


@dataclass(frozen=True)
class FieldChoice:
    """One row of the settings window: a field name and what to do with it."""

    name: str
    keep: bool  # True = "Keep mine", False = "Take the update's"


@dataclass(frozen=True)
class TagRule:
    """Fields kept on the notes that carry one protected tag (contract rule
    14). `keep_fields` are field names as the user picked them; `keep_all`
    keeps every field the note had before the import. A protected tag with
    neither ("Tag only") needs no TagRule."""

    tag: str
    keep_fields: Tuple[str, ...] = ()
    keep_all: bool = False

    def keeps_any(self) -> bool:
        return self.keep_all or any(norm_field(f) for f in self.keep_fields)


@dataclass(frozen=True)
class Settings:
    """The user's saved choices. One set, used for every import."""

    fields: Tuple[FieldChoice, ...] = ()
    protected_tags: Tuple[str, ...] = ()
    update_note_types: bool = True  # card templates and styling
    import_scheduling: bool = False  # Anki's "Import any learning progress"
    import_deck_presets: bool = False  # Anki's "Import any deck presets"
    # Per protected tag, the fields also kept on the notes that carry it
    # (rule 14). `protected_tags` stays the list of tag names; a rule whose
    # tag is not in it is ignored, and a protected tag without a rule is
    # "Tag only".
    tag_rules: Tuple[TagRule, ...] = ()

    def kept_field_names(self) -> FrozenSet[str]:
        """Normalized names of the fields whose local value is kept."""
        return frozenset(norm_field(f.name) for f in self.fields if f.keep)

    def keeps_field(self, name: str) -> bool:
        return norm_field(name) in self.kept_field_names()

    def protects_tag(self, tag: str) -> bool:
        return is_protected_tag(tag, self.protected_tags)

    def rule_for(self, tag: str) -> Optional[TagRule]:
        """The rule of protected tag `tag` (matched with `norm_tag`), or None
        when it is "Tag only" or not protected."""
        key = norm_tag(tag)
        if not any(norm_tag(t) == key for t in self.protected_tags):
            return None
        for rule in self.tag_rules:
            if norm_tag(rule.tag) == key and rule.keeps_any():
                return rule
        return None

    def active_tag_rules(self) -> Tuple[TagRule, ...]:
        """The rules that keep something, one per protected tag, in the
        order of `protected_tags`."""
        out: List[TagRule] = []
        for tag in self.protected_tags:
            rule = self.rule_for(tag)
            if rule is not None and rule not in out:
                out.append(rule)
        return tuple(out)

    def fields_kept_for(self, tags: Iterable[str]) -> Tuple[FrozenSet[str], bool]:
        """For a note whose tags (before the import) are `tags`: the
        normalized names of every field kept on it (the "Keep mine" fields
        plus those of every protected tag it carries, sub-tags included),
        and whether every field is kept (a carried tag keeps every field)."""
        kept = set(self.kept_field_names())
        every = False
        rules = self.active_tag_rules()
        if rules:
            tags = list(tags)
            for rule in rules:
                if any(is_protected_tag(t, (rule.tag,)) for t in tags):
                    if rule.keep_all:
                        every = True
                    kept.update(norm_field(f) for f in rule.keep_fields if norm_field(f))
        return frozenset(kept), every


@dataclass
class ImportResult:
    """What one import did. Shown in the summary dialog."""

    notes_in_file: int = 0
    notes_added: int = 0  # notes that were not in the collection before
    notes_updated: int = 0  # existing notes the update changed
    notes_skipped: int = 0  # in the file but not imported (see `skip_reasons`)
    fields_kept: int = 0  # field values put back because the update changed them
    notes_with_fields_kept: int = 0
    protected_tags_kept: int = 0  # tag occurrences put back
    notes_with_tags_kept: int = 0
    note_types_changed: bool = False  # True -> the next sync is a full sync
    learning_progress_imported: bool = False  # the file's scheduling was imported
    cards_with_progress: int = 0  # cards new to the collection that arrived not new
    skip_reasons: Dict[str, int] = field(default_factory=dict)
    seconds: Dict[str, float] = field(default_factory=dict)
    changes: object = None  # anki OpChanges, for aqt's CollectionOp

    def summary_rows(self) -> List[Tuple[str, str]]:
        """(label, value) rows for the summary dialog, in display order."""
        rows = [
            ("Notes updated", str(self.notes_updated)),
            ("New notes added", str(self.notes_added)),
            ("Fields kept from your version", str(self.fields_kept)),
            ("Protected tags kept", str(self.protected_tags_kept)),
        ]
        if self.notes_skipped:
            rows.append(("Notes skipped", str(self.notes_skipped)))
        return rows
