# Design: fields kept per protected tag

Status: **approved by the author on 17 Nov 2026, not yet built.** When it is built, fold this into `docs/CONTRACT.md` (as rule 14 and in the settings window section) and delete this file.

## The author's request

> "protected tags should protect the cards with specific rules. not just protecting the tag. the tag itself will also be protected. for example, if i am protecting tag #edited, every single card with #edited will be protected with its own set of rules. If i want to protect personal notes on all cards, but on those tagged #edited i want to protect text, extra, and personal notes, i want a way to do that."

## Behaviour

1. A protected tag keeps doing what it does today (contract rule 4): an update never removes it from a note.
2. Each protected tag can also carry a list of field names to keep on the notes that have the tag, and a "keep every field" option. A tag added in the settings window starts with neither ("Tag only"), which is exactly today's behaviour.
3. Tag rules only ADD to the main field list; they never remove protection. For an updated note, the kept fields are: every field set to "Keep mine" in the main list, plus the fields of every protected tag the note carries.
4. A note "carries" a protected tag by the same test as tag protection today (`model.is_protected_tag`): the tag itself or any sub-tag (`#edited::images` carries `#edited`), compared case-insensitively.
5. What counts is the note's tags BEFORE the import (the user's tags), not the update's tags.
6. A note with several protected tags keeps the union of their fields. If any of them has "keep every field", every field is kept.
7. Field names are matched by normalized name within the note's note type, like the main list (`model.norm_field`). A listed field the note type does not have is skipped for that note.
8. "Keep every field" means: every field the note had before the import keeps the user's value. A field that is new to the note (the update's note type has a field the note did not have) takes the update's value.
9. Notes the update moves to another note type: tag rules are applied by field name on the new note type, exactly like kept fields under contract rule 10a.
10. The other tags on those notes are still replaced with the update's (rule 3). Scheduling, decks, review history: unchanged as always.
11. Contract rule 9 (never blank an unlisted field the update leaves empty everywhere) is unaffected. A field listed only in a tag rule counts as "listed" for rule 9 purposes ONLY on notes that carry that tag; on all other notes it is handled as today.
12. Values kept through a tag rule count in `fields_kept` / `notes_with_fields_kept`.

Worked example (the author's): main list has Personal Notes = Keep mine, everything else Take the update's; `#edited` lists Text and Extra. A note tagged `#edited` keeps Text, Extra and Personal Notes and takes the update's Header, Textbook, Citation and tags (keeping `#edited`). Every other note keeps only Personal Notes.

## Settings window

In the "Protected tags" section each protected tag becomes a small block instead of a chip:

```
#edited                                                     ✕
On cards with this tag, also keep   [Text ✕] [Extra ✕]   + Add field

#eevee                                                      ✕
Tag only                                                    + Add field
```

- "+ Add field" on a tag opens the same kind of type-ahead picker as the main "+ Add field" (fields from the user's note types; first match highlighted; Enter or one click adds; no Select button; no message after adding). Its first entry is "Every field"; choosing it replaces the tag's field chips with a single "Every field ✕" chip.
- Fields already kept everywhere by the main list may still be added to a tag (harmless), but the picker lists them last.
- Removing the tag removes its fields with it.
- Section help text: "An update never removes these tags. You can also keep extra fields on the cards that have a tag."
- "Restore defaults" clears protected tags and their fields (as today).
- The "Discard your changes?" question covers these changes too.
- `choices_summary()` "Protected tags" row: `#edited (keeps Text, Extra), #eevee`; with every field: `#edited (keeps every field)`.

## Config

Backward compatible. `protected_tags` in `config.json` may hold, per entry, either a plain string (today's format: tag only) or an object:

```json
{"protected_tags": ["#eevee", {"tag": "#edited", "keep_fields": ["Text", "Extra"], "keep_all_fields": false}]}
```

Configs saved by earlier betas (plain strings) must load unchanged. Reading stays tolerant (unknown keys ignored, wrong types fall back to "tag only"). Saving writes a plain string for a tag with no fields, so untouched configs stay readable by older betas.

In `model.py`, keep `Settings.protected_tags` as the tuple of tag names (many call sites use it) and add the per-tag data beside it (for example `Settings.tag_rules: Tuple[TagRule, ...]` with `TagRule(tag, keep_fields, keep_all)`), with one helper that answers "which normalized field names are kept for a note with these tags, and is it all fields?".

## Tests to add

- Engine: the worked example; union of two tags; sub-tag carries the parent's rule; case-insensitive tag and field names; pre-import tags decide (the update's tags do not); "every field"; a field missing on the note type is skipped; a note moved to another note type; rule 9 interplay; counts in the summary; one undo restores everything; gate still passes; old config loads.
- Acceptance oracle (`tests/acceptance/sfa_acc_helpers.py`): teach it tag rules and add scenarios to the matrix.
- Window: add/remove fields on a tag, "Every field", persistence, restore defaults, summary text, Tab order, discard question.
- Real data: `/tmp/sfa-real/scr/practice.py` (if the workspace still has it) with `#edited` keeping Text and Extra on the author's two files.
