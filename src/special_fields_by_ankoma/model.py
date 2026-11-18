"""Shared data model for Special Fields by Ankoma.

This file is the contract between the engine (no GUI) and the screens.
It must import nothing from `anki` or `aqt`, and must run on Python 3.9
through 3.13: no `match`, no PEP 604 unions at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
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
    """The field table of one protected tag (contract rule 14).

    `fields` is the tag's own, complete, frozen list of kept fields (field
    names as the user picked them; empty = keeps no fields). It never
    follows later changes to the main list. `keep_all` keeps every field
    the note had before the import.

    `fields` is None for an entry saved by beta 8 (`{"tag", "keep_fields"}`)
    that has not been frozen yet: its table is the main list's kept fields
    plus `keep_fields`, worked out at import time, as in beta 8. A protected
    tag with no TagRule at all (a plain string, beta 7 and earlier) follows
    the main list."""

    tag: str
    keep_fields: Tuple[str, ...] = ()  # beta 8 only: kept on top of the main list
    keep_all: bool = False
    fields: Optional[Tuple[str, ...]] = None  # the frozen table; None = not frozen yet

    def is_frozen(self) -> bool:
        return self.fields is not None

    def kept_names(self, main_kept: FrozenSet[str]) -> FrozenSet[str]:
        """Normalized names of the fields this tag keeps (without
        `keep_all`). `main_kept` is the main list's, used only by an entry
        that is not frozen yet."""
        if self.fields is not None:
            return frozenset(norm_field(f) for f in self.fields if norm_field(f))
        return main_kept.union(norm_field(f) for f in self.keep_fields if norm_field(f))

    def keeps_any(self) -> bool:
        """True if this entry keeps a field whatever the main list says
        (beta 8's meaning, kept for old call sites)."""
        names = self.fields if self.fields is not None else self.keep_fields
        return self.keep_all or any(norm_field(f) for f in names)


@dataclass(frozen=True)
class Settings:
    """The user's saved choices. One set, used for every import."""

    fields: Tuple[FieldChoice, ...] = ()
    protected_tags: Tuple[str, ...] = ()
    update_note_types: bool = True  # card templates and styling
    import_scheduling: bool = False  # Anki's "Import any learning progress"
    import_deck_presets: bool = False  # Anki's "Import any deck presets"
    # The field table of each protected tag (rule 14). `protected_tags`
    # stays the list of tag names; a rule whose tag is not in it is ignored,
    # and a protected tag without a rule follows the main list (beta 7).
    tag_rules: Tuple[TagRule, ...] = ()

    def kept_field_names(self) -> FrozenSet[str]:
        """Normalized names of the fields whose local value is kept."""
        return frozenset(norm_field(f.name) for f in self.fields if f.keep)

    def keeps_field(self, name: str) -> bool:
        return norm_field(name) in self.kept_field_names()

    def protects_tag(self, tag: str) -> bool:
        return is_protected_tag(tag, self.protected_tags)

    def rule_for(self, tag: str) -> Optional[TagRule]:
        """The TagRule of protected tag `tag` (matched with `norm_tag`), or
        None when the tag is not protected or has no rule (it follows the
        main list)."""
        key = norm_tag(tag)
        if not any(norm_tag(t) == key for t in self.protected_tags):
            return None
        for rule in self.tag_rules:
            if norm_tag(rule.tag) == key:
                return rule
        return None

    def active_tag_rules(self) -> Tuple[TagRule, ...]:
        """The rule of every protected tag that has one, in the order of
        `protected_tags`."""
        out: List[TagRule] = []
        for tag in self.protected_tags:
            rule = self.rule_for(tag)
            if rule is not None and rule not in out:
                out.append(rule)
        return tuple(out)

    def tag_table(self, tag: str) -> Tuple[FrozenSet[str], bool]:
        """What protected tag `tag` keeps: (normalized field names, keep
        every field). A tag without a frozen table is worked out from the
        main list, as the betas that saved it did."""
        rule = self.rule_for(tag)
        main = self.kept_field_names()
        if rule is None:
            return main, False
        return rule.kept_names(main), rule.keep_all

    def fields_kept_for(self, tags: Iterable[str]) -> Tuple[FrozenSet[str], bool]:
        """For a note whose tags (before the import) are `tags`: the
        normalized names of every field kept on it, and whether every field
        is kept. A note that carries protected tags (sub-tags included)
        follows the union of their tables and NOT the main list; any other
        note follows the main list."""
        names: set = set()
        every = False
        carried = False
        tags = list(tags)
        for ptag in self.protected_tags:
            if norm_tag(ptag) and any(is_protected_tag(t, (ptag,)) for t in tags):
                carried = True
                kept, all_ = self.tag_table(ptag)
                names |= kept
                every = every or all_
        if not carried:
            return self.kept_field_names(), False
        return frozenset(names), every

    def with_frozen_tags(self) -> "Settings":
        """The same choices with every protected tag given its own frozen
        table: what each tag keeps today, spelled as in the main list where
        it can be. The settings window shows and saves this form."""
        spelled = {norm_field(f.name): f.name for f in self.fields}
        rules: List[TagRule] = []
        seen = set()
        for tag in self.protected_tags:
            key = norm_tag(tag)
            if not key or key in seen:
                continue
            seen.add(key)
            rule = self.rule_for(tag)
            if rule is not None and rule.is_frozen():
                rules.append(rule)
                continue
            names: List[str] = [f.name for f in self.fields if f.keep]
            have = {norm_field(n) for n in names}
            for extra in (rule.keep_fields if rule is not None else ()):
                k = norm_field(extra)
                if k and k not in have:
                    have.add(k)
                    names.append(spelled.get(k, extra))
            rules.append(TagRule(tag, (), bool(rule and rule.keep_all), tuple(names)))
        return replace(self, tag_rules=tuple(rules))


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
