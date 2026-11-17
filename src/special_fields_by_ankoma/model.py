"""Shared data model for Special Fields by Ankoma.

This file is the contract between the engine (no GUI) and the screens.
It must import nothing from `anki` or `aqt`, and must run on Python 3.9
through 3.13: no `match`, no PEP 604 unions at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Iterable, List, Tuple

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
class Settings:
    """The user's saved choices. One set, used for every import."""

    fields: Tuple[FieldChoice, ...] = ()
    protected_tags: Tuple[str, ...] = ()
    update_note_types: bool = True  # card templates and styling

    def kept_field_names(self) -> FrozenSet[str]:
        """Normalized names of the fields whose local value is kept."""
        return frozenset(norm_field(f.name) for f in self.fields if f.keep)

    def keeps_field(self, name: str) -> bool:
        return norm_field(name) in self.kept_field_names()

    def protects_tag(self, tag: str) -> bool:
        return is_protected_tag(tag, self.protected_tags)


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
