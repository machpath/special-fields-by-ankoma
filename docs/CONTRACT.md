# Build contract: Special Fields by Ankoma

This is the binding spec for every workstream. If something here conflicts with the prototype in `research/spike/`, this file wins. Product decisions come from the deck author and are not open for redesign.

## What the add-on does

A user opens any `.apkg` in Anki the usual way. The add-on asks one question, "Would you like to update with Special Fields by Ankoma?". If the user says yes, it imports the file with Anki's own importer, forced to update every note, then puts back what the user chose to keep. Two optional switches, off by default, also let it bring in the file's learning progress (for cards new to the collection only) and its deck presets, as Anki's standard import can (rule 6a).

Rules (all decided):

1. **One set of choices, one logic, for every import.** No per-deck profiles, no detection by file name.
2. **Fields.** Each listed field is "Keep mine" or "Take the update's". Matching is by field name within each note type, ignoring case and surrounding spaces (`model.norm_field`). Field order never matters. A field a note type lacks is skipped for that type. Defaults: Ankoma's cloze fields, with only `Personal Notes` kept.
3. **Tags.** No setting. An updated note ends up with exactly the update's tags, plus rule 4.
4. **Protected tags.** An update never removes a protected tag (or a sub-tag of one, `model.is_protected_tag`) from a note. This is tag-level: the rest of the note still updates. Example: no fields kept and `#edited` protected → every `#edited` stays, all other tags are replaced, fields take the update's content.
5. **Card templates and styling.** `Settings.update_note_types`: True lets the update replace templates and CSS; False keeps the user's exactly, even when the update adds a field. Note content updates either way.
6. **Always preserved, no setting:** review history/scheduling of existing cards, and the deck each existing card is in.
6a. **Learning progress and deck presets from the file** (added 2026-11-17 at the author's request: "moving from one device to another and want to keep my progress without ankiweb sync"). Two saved choices, both off by default, passed to Anki unchanged: `Settings.import_scheduling` → `with_scheduling`, `Settings.import_deck_presets` → `with_deck_configs`. What Anki does with them (verified identically on 25.02.7 to 26.11b1):
    - `with_scheduling=True`: a card that already exists is never changed (interval, due date, review log), and the file's review log rows for it are not imported. Only cards new to the collection arrive with the file's scheduling and their review log rows. A new card may get back the id of a card the user deleted earlier; that card's old review rows (Anki keeps them) stay as they were. `False`: new cards arrive as new; no review log rows are added.
    - `with_deck_configs=True`: a preset whose id is already in the collection is never changed (the Default preset included, whatever its modification time); a preset only in the file is added with the file's id and values (a name clash gives two presets with the same name); every deck in the file, existing or new, is switched to the preset the file gives it, unless that is the Default preset (then an existing deck keeps the user's preset). A file exported without presets changes nothing. `False`: no preset is added and no deck changes its preset.
    - Both are inside the one undo step. Anki's other standard-import options stay fixed by design: update notes = always, merge note types = on, update note types = the styling switch.
7. **One undo step** for the whole import, labelled `model.UNDO_LABEL`.
8. Notes deleted upstream are out of scope.
9. **An update never blanks a field it has no content for** (added after independent verification). This covers fields the user added to a note type themselves. Precisely: take a note type T and a field F of T whose normalized name is NOT listed in the settings at all. If, after the native import, every note of type T that this import added or updated has an empty F (empty after `strip()`), the update is treated as having no content for F, and every updated note gets its pre-import F back. A field that IS listed as "Take the update's" always takes the update's value, even when that is empty. Values put back this way count in `fields_kept` / `notes_with_fields_kept`.
10. **Note type moves are followed, and the mess Anki's merge leaves is cleaned up** (decided by the author 2026-11-16; replaces an earlier "refuse the import" rule, which would have blocked every user whenever the author moves notes to another note type). Background, verified on Anki 26.09: when an updated note's note type in the file differs from the one the same note has in the collection (the author moved it to another or a brand-new note type, the user changed its type, or the user's copy has same-named note types with different ids), the forced `merge_notetypes=True` import moves the note onto the file's note type and appends the note's OLD note type's fields to that note type, renaming any whose name clashes to `<name>+` ("Header+", "Personal Notes+", …). Those appended fields are empty on every note. The engine must then, inside the same undo step:
    - a. treat every updated note whose note type id changed as "moved". For a moved note, kept fields (rule 2) and rule 9 are applied by field NAME on the note's new note type: the pre-import value of the old field goes to the new note type's field with the same normalized name, never to a `+` duplicate. A pre-import field with no same-named field on the new note type keeps whatever field Anki carried it over as (follow it by field config id) so its content is not lost.
    - b. remove merge leftovers: on any note type, a field that did not exist on that note type before the import, whose name ends with `+`, whose name without the trailing `+` characters matches (normalized) another field of that note type, and that is empty on every note of that note type after step a, is removed from the note type. A field that holds content on any note is never removed. Fields that existed before the import are never removed.
    - c. the import is NOT refused. Moved notes count as updated like any other; there is no new counter and no `NoteTypeMismatchError`.
    - d. `update_note_types=False` protects the templates and CSS of note types that existed before the import (unchanged rule 5). A note the update moves to another note type takes that note type's templates and CSS.
    - e. undo still restores everything exactly (notes, note types, fields, templates).
    - f. what "merge leftovers" really are (found during the fix, identical on every supported version): besides the `+` fields, Anki appends the old note type's card templates (`<name>+` on a clash), repoints the target type's own templates at the empty `+` fields so its cards render blank, moves every existing card of the target type onto the `+` template, creates a duplicate card per note on the original template, and shifts the content of target-type notes that are not in the file into the `+` fields. Step b therefore also restores untouched notes' content, moves cards back, repairs template references and removes the leftover templates.
    - g. if the repair cannot be completed safely for a note type (an untouched note cannot be mapped back exactly, a duplicate card that would have to be removed existed before the import or has review history, or Anki refuses the note type edit), the engine must NOT leave the collection in Anki's half-merged state (blank and duplicate cards). It rolls the whole import back, exactly like any failed import, and raises `engine.MergeRepairError` (an Exception subclass with a clear message). The import flow shows a plain warning instead of Anki's exception dialog: "Nothing was imported. Special Fields couldn't apply this update safely to your collection, so it changed nothing. This usually means the file moves notes to a different note type in a way that can't be followed. You can import this file with Anki's standard import instead, or ask the deck's author for help." A `+` field that merely holds content, or that existed before the import, is not a failure: it is simply kept.

11. **Backup before every "Import with my choices"** (added by the orchestrator after the fix round). Anki discards its whole undo history when one of its own backend operations fails part-way, so undo alone can't guarantee recovery. The import flow asks Anki for a normal backup (`col.create_backup(backup_folder=mw.pm.backupFolder(), force=True, wait_for_completion=True)`) at the start of the background operation. Best effort: a backup that can't be made never blocks the import. Measured 0.06 s on the full-size test collection.

12. **Prove the result or refuse** (added after the second verification, which showed that repairing Anki's cross-note-type merge case by case keeps missing cases). After the restore and any merge clean-up, and before the undo entries are merged, the engine checks these invariants against its pre-import snapshot. If any fails, it rolls the whole import back and raises `MergeRepairError`; it never finishes an import it cannot prove clean.
    - G1. Every note that existed before and that the importer did not report as updated has the same note type id, field values and tags as before.
    - G2. Every card that existed before still exists, on the same note, with the same deck, original deck, due, original due, interval, ease factor, reps, lapses, left, queue, type, flags and `data`. Its template ordinal is also unchanged unless its note was moved to another note type by this import.
    - G3. Every review log row that existed before the import is still there and unchanged. With `import_scheduling` off, no row is added at all. With it on, rows may be added only for cards that did not exist before this import (cards new to the collection, including one that got back the id of a deleted card). Checked with order-independent aggregates: the whole log, the rows of the new cards, and the pre-import rows of deleted cards whose id a new card got back (their ids are snapshotted only when `import_scheduling` is on).
    - G4. No new card was created for a note that existed before and that the importer did not report as updated.
    The check must be cheap (a few SQL passes) and always on, including for imports with no note type moves, where it must never fire on a correct import.
13. **A rollback that cannot be done is said plainly.** If the engine needs to roll back but Anki's undo history is gone (a failing backend operation empties it), the engine raises `engine.RollbackFailedError` instead of claiming the collection is unchanged. The import flow then tells the user: "The update could not be completed and could not be undone automatically. Special Fields asked Anki to save a backup just before the update. To go back to it, choose File → Switch Profile → Open Backup and pick the newest backup." If the pre-import backup was not created, the last two sentences are replaced by: "No backup could be made before the update. Check your cards, and restore one of Anki's automatic backups from File → Switch Profile → Open Backup if anything looks wrong."

## Supported Anki versions

Every desktop release from 2025 on: 25.02, 25.07, 25.09, 26.05, 26.08, 26.09, 26.11 beta. Bundled Python ranges from 3.9 to 3.13, so in all shipped code:

- `from __future__ import annotations` at the top; no `match`, no `X | Y` unions evaluated at runtime, no `dict | dict`, nothing newer than 3.9.
- Only public `anki` / `aqt` APIs where one exists. Qt via `from aqt.qt import *` (PyQt6).
- Relative imports only inside the package (AnkiWeb renames the folder to a number). Config via `mw.addonManager.getConfig(__name__.split(".")[0])`.
- No third-party dependencies.

## Layout and file ownership

Project root: `/mnt/user-data/outputs/project-folder` (mirrored to the author's Desktop folder by the project manager).

| Path | Owner | Notes |
| --- | --- | --- |
| `src/special_fields_by_ankoma/model.py`, `config.py`, `config.json`, `config.md`, `manifest.json`, `__init__.py` | Foundation (PM) | Frozen. Need a change? Report it; don't edit. |
| `src/special_fields_by_ankoma/engine.py`, `tests/engine/` | B: Engine | |
| `src/special_fields_by_ankoma/settings_dialog.py`, `tests/ui/` | C: Settings window | |
| `tests/acceptance/`, `tools/` | D: Test harness | |
| `src/special_fields_by_ankoma/import_flow.py` | E: Import flow (later) | |

Edit only files you own. Put scratch files, collections and generated `.apkg` fixtures under `/tmp/sfa-<your letter>/`, never in the project tree. Do not run git. Do not touch the author's computer, Anki collection or any `mcp__remote-devices__*` tool. Do not publish or upload anything.

Existing Python environments (one Anki version each, headless): `/home/claude/venv-25.2.7`, `venv-py39-25.2.7` (Python 3.9), `venv-25.7.5`, `venv-25.9.5`, `venv-26.9.4`, `venv-26.11b1`; with Qt for offscreen GUI tests (`QT_QPA_PLATFORM=offscreen`): `/home/claude/venv-aqt25`, `/home/claude/venv-aqt26`. Create more with `uv` if needed (26.05 and 26.08 are still missing).

## Shared model (already written)

`model.py`: `Settings(fields: Tuple[FieldChoice,...], protected_tags: Tuple[str,...], update_note_types: bool, import_scheduling: bool = False, import_deck_presets: bool = False)`, `FieldChoice(name, keep)`, `ImportResult`, `norm_field`, `norm_tag`, `is_protected_tag`, `ADDON_NAME`, `UNDO_LABEL`, `ACCENT_COLOR`.
`config.py`: `default_settings()`, `settings_from_config(dict) -> Settings` (tolerant), `settings_to_config(Settings) -> dict`, `default_config()`.

## B: Engine (`engine.py`)

```python
def run_import(col: anki.collection.Collection, path: str, settings: Settings) -> ImportResult
```

- Imports only from `anki` and this package (never `aqt`), so it runs headless and inside aqt's `CollectionOp` background thread.
- Sequence: open one custom undo entry → snapshot from the user's collection → native import → clear the Python note-type cache → restore → merge undo entries → return `ImportResult` with `changes` set to the `OpChanges`.
- Native import options: `update_notes=ALWAYS` (never IF_NEWER, which silently skips notes the user edited), `merge_notetypes=True`, `update_notetypes=ALWAYS if settings.update_note_types else NEVER`. `with_scheduling=settings.import_scheduling`, `with_deck_configs=settings.import_deck_presets` (rule 6a; both off by default). The native importer saves the options it was called with as the user's defaults for Anki's own import screen; the engine puts the user's own values back afterwards (`_restore_import_prefs`), whatever these switches are. `ImportResult.learning_progress_imported` says whether scheduling was imported and `cards_with_progress` counts the cards new to the collection that did not arrive as new cards.
- Restore runs only on notes the importer reports as updated:
  - each kept field gets its pre-import value back when the update changed it. Follow a field across a schema change the way the prototype does (field config id first, then name);
  - each pre-import tag for which `settings.protects_tag(tag)` is true is re-added if the update dropped it (compare with `norm_tag`); original spelling is kept.
- `update_note_types=False` must leave every existing note type's templates and CSS byte-identical, including when the update adds a field (the new field must still exist on the note type and receive data). Verify this on the oldest and newest versions; if `NEVER` alone doesn't guarantee it, snapshot and restore templates and CSS.
- Fill every `ImportResult` counter. `fields_kept` counts field values actually written back; `protected_tags_kept` counts tag occurrences re-added. `note_types_changed` is True when the collection's schema-modified marker changed (next sync will be a full sync). `notes_skipped` and `skip_reasons` cover notes in the file that were not imported.
- No snapshot work beyond what the settings need (no kept fields and no protected tags → nothing to restore, but the forced import still runs).
- Performance target: comparable to the prototype (about 1 second for 18,600 notes / 24,300 cards). One SQL pass for the snapshot; batch the writes.
- If the native import raises, the exception propagates and the collection is left as it was before the call.
- Start from `research/spike/poc/ankoma_core.py` (read `research/spike/SPIKE_REPORT.md` first: it has the verified API facts and gotchas). Drop its tag modes, author-tag regex and file-name logic.
- `tests/engine/`: fast pytest tests on tiny synthetic decks that you build in the test, covering every bullet above. They must pass in every environment listed.

## C: Settings window (`settings_dialog.py`)

Native Qt widgets (no web view). Design reference: the mock at `/mnt/user-data/outputs/artifacts/64de8226-6f20-4c5c-be23-6b1cb453ba01/project/Main.dc.html` (ignore its top navigation bar and explanatory heading; build the dialog inside the white card). Title: "Special Fields by Ankoma: Settings".

```python
class SettingsDialog(QDialog):
    def __init__(self, parent, settings: Settings, all_field_names: Sequence[str], all_tags: Sequence[str]) -> None
    def result_settings(self) -> Settings        # valid after accept()

def open_settings(mw) -> Optional[Settings]      # load config, show dialog, save on Save, return the new Settings (None if cancelled)
def load_settings(mw) -> Settings                # from the add-on config
def save_settings(mw, settings: Settings) -> None
def choices_summary(settings: Settings) -> List[Tuple[str, str]]   # rows for the "Your saved choices" box
```

- The dialog class takes plain data (no `mw`, no collection) so it can be tested offscreen. `open_settings` gathers `all_field_names` from the user's note types and `all_tags` from the collection.
- **Fields section** ("Fields: when an update changes a card…"): one row per field with a two-part toggle, "Keep mine" | "Take the update's". The selected side is filled with `ACCENT_COLOR` and white text whichever side it is; the unselected side is plain. Every row can be removed with its ✕, the default rows included: the defaults are only a starting list, and the add-on must suit any deck. A field that is not listed takes the update's content (rule 9 still applies). With no rows left, a note says so; an empty list is saved as empty and the defaults never come back by themselves (only "Restore defaults" brings them back).
- **"+ Add field"**: opens an inline search that lists field names from the user's note types that are not already rows, narrowing as the user types. A field can only be added from that list. New rows start as "Take the update's". Nothing is said after a field is added (like the tag picker); the hint line under the search shows only problems (no match, already listed, not one of your fields). (17 Nov 2026.)
- **Protected tags section**: current tags as removable chips; a text box whose dropdown list shows only tags that exist in the collection, appears when the user starts typing, and narrows as they type (case-insensitive substring; prefix matches first). The first match in the list is highlighted automatically. A tag is added by (a) pressing Enter, which adds the highlighted tag, or (b) one click on any tag in the list, highlighted or not. There is no Select button and no confirmation step. Up/Down move the highlight; the list scrolls. Exception: when the typed text is itself an already protected tag, nothing is highlighted, so Enter cannot add a sub-tag by accident. Free text that matches no existing tag cannot be added; say so in a hint line. The hint line is shown only when something needs saying (no match, already protected, list cut short); there is no message after a tag is added or removed. Helper text: "An update never removes these tags from your notes, even when tags are replaced. The rest of the note still updates as usual."
- **"Update card templates and styling"** switch (a checkbox styled as a switch is fine).
- Under it, two more switch rows built the same way (rule 6a), both off by default: **"Import learning progress"** (`scheduling_switch`) and **"Import deck options"** (`presets_switch`; Anki's "deck presets", renamed 2026-11-17 because the author found "preset" unclear. The help text: "On: deck options saved in the file (daily limits, learning steps, FSRS settings) come in as new presets, and the file's decks use them. Options you already have are never changed. Off: no deck options are imported."), each with a one-line help text that says what Anki really does (existing cards keep their own progress; existing presets are never changed). "Restore defaults" turns both off. `choices_summary` adds ("Learning progress", "Imported for new cards" / "Not imported") and ("Deck options", "Imported" / "Not imported") after "Card styling". The summary after an import keeps "Your existing cards: review history and decks: Unchanged" (renamed 17 Nov 2026 from "Review history and deck moves") and, only when learning progress was imported, adds ("New cards with learning progress", count).
- There is NO tags-mode section.
- Buttons: "Restore defaults" (resets to `config.default_settings()`), Cancel, Save (accent-filled).
- Must look right in Anki's light and dark themes (don't hard-code light backgrounds; take colours from the palette, use the accent only for selection and the primary button). Keyboard accessible; every control reachable by Tab. (Each field toggle is an exclusive pair: its selected side is the Tab stop and Left/Right switch sides, as Qt does for radio-style groups.)
- Added after the real-Anki pass (17 Nov 2026):
    - The tag list and the "+ Add field" list never show a horizontal scroll bar: every row is as wide as the list, a long name is elided in the middle (the start and the leaf of a hierarchical tag stay readable) and the row's tooltip shows it in full. The row's text, and what gets added, is always the full name. Every visible row is fully visible.
    - When the tag list, its hint or the field picker opens or closes, the window grows or shrinks its height to fit its content, keeping its top-left corner: never above 90% of the screen's available height or past the screen's bottom edge, never below the height it opened with or that the user resized it to. When the content fits, there is no scroll bar and the top heading stays in view.
    - On opening, keyboard focus is on the first field row's toggle (its selected side), or on "+ Add field" when there are no rows; never on the scroll area or the tag box.
    - Closing without saving (Esc, Cancel, the close box; also when opened from "Change choices…") asks first when the choices differ from the ones the window opened with (changed and changed back counts as unchanged): a PlainText box, title "Special Fields by Ankoma", text "Discard your changes?", buttons "Discard" and "Keep editing"; "Keep editing" is the default and the Esc choice. "Discard" closes without saving; "Keep editing" returns with everything as it was. Save never asks. Esc in a non-empty tag or field search box still only clears that box. (`settings_dialog.confirm_discard`, object name `discard_question`.)
- `choices_summary` returns rows such as ("Fields you keep", "Personal Notes"), ("Protected tags", "#edited" or "None"), ("Tags", "Replaced with the update's"), ("Card styling", "Update" or "Keep mine").
- `tests/ui/`: offscreen pytest tests in `venv-aqt25` and `venv-aqt26` that drive the dialog (toggle a field, add and remove a field, the tag picker's filtering and its three ways to add, rejecting an unknown tag, restore defaults, the Settings returned) and the config round trip.

## D: Test harness (`tests/acceptance/`, `tools/`)

Independent acceptance tests written from this contract, not from the engine's code.

- `tools/build_fixtures.py`: builds synthetic Ankoma-like packages with Anki's own exporter: **v1.2**, **v1.3** (content edits on every note; tags moved from `##ANKOMA-v1.2::…` to `##ANKOMA-v1.3::…` with some levels reorganized, e.g. `AP::Breast` → `AP::chest::breast`; changed templates and CSS; some new notes), and **v1.3-newfield** (v1.3 plus one field appended to a note type). Use Ankoma's 8 note types with these exact names and field lists:
  - `Cloze-Ankoma-AP`, `Cloze-Ankoma-AP-Unrestricted`: Header, Text, Extra, Personal Notes, Textbook, Citation
  - `Cloze-Ankoma-AP - multiple images`: Header, Text, Images, Extra, Personal Notes, Textbook, Citation
  - `Cloze-Ankoma-CP`, `Cloze-Ankoma-CP-Unrestricted`, `Cloze-Ankoma-CP-Unrestricted+`: Text, Extra, Personal Notes, Citation
  - `Image Occlusion Enhanced`: ID (hidden), Header, Image, Question Mask, Footer, Remarks, Sources, Extra 1, Extra 2, Answer Mask, Original Mask
  - `Image Occlusion Enhanced+`: ID (hidden), Header, Image, Footer, Remarks, Sources, Extra 1, Extra 2, Question Mask, Answer Mask, Original Mask
  A size parameter: small by default (fast), full size on request (about 18,600 notes / 24,300 cards, decks under `Ankoma::Ankoma - AP::…` and `Ankoma::Ankoma - CP::…`).
- A simulated user on top of v1.2: Personal Notes filled in, edits to Text and Extra, personal tags (including `#edited` and `#edited::images`), cards moved to another deck, review history, a CSS tweak, and edits made after the author's (so "if newer" would skip them).
- `tests/acceptance/`: pytest tests that call `special_fields_by_ankoma.engine.run_import` and check:
  1. each field toggle keeps or overwrites exactly that field, matched by name;
  2. AP and CP notes in one file with Header kept: applied to AP, skipped for CP;
  3. a kept field that only another deck's note type has is honoured;
  4. protected tags (and sub-tags) stay on every note that had them while the rest of the note updates;
  5. all other tags are replaced: v1.2 → v1.3 switch, reorganized levels, unprotected personal tags removed;
  6. `update_note_types` True replaces templates and CSS, False keeps them byte-identical, including with v1.3-newfield;
  7. a brand-new deck imports normally;
  8. cards the user moved stay put; new notes land in the release's deck;
  9. scheduling and review log of existing cards identical before and after;
  10. exactly one undo step, and undo restores the collection exactly;
  11. `ImportResult` counters are correct;
  12. notes edited locally "later" than the author still get the update;
  13. full-size run: time and peak memory reported (marked slow).
- `tools/run_matrix.sh`: runs `tests/engine`, `tests/acceptance` (and `tests/ui` in the Qt environments) on every supported version, creating the missing 26.05 and 26.08 environments, and prints a pass/fail table.
- The engine is being written at the same time by another agent. Don't edit or wait for `engine.py`. To check your own fixtures and tests, you may adapt the prototype (`research/spike/poc/ankoma_core.py`) behind a throwaway shim outside the project tree. When you finish, run against `engine.py` if it exists and report every failure with the evidence, without changing the engine.

## E: Import flow (`import_flow.py`, after B and C)

Wraps `aqt.import_export.importing.ApkgImporter.do_import` (every `.apkg` route goes through it). For every `.apkg`: show the question dialog (title "Special Fields by Ankoma"; heading "Would you like to update with Special Fields by Ankoma?"; the file name; "Your saved choices" box from `choices_summary`; buttons "Import with my choices", "Change choices…", "Use Anki's standard import"). "Import with my choices" runs `run_import` in a `CollectionOp` with Anki's import progress; then a summary dialog from `ImportResult.summary_rows()` with an Undo button, plus a full-sync warning when `note_types_changed`. "Change choices…" opens the settings window and returns to the question. "Use Anki's standard import" calls the original importer untouched. Adds Tools → "Special Fields by Ankoma" for the settings window. Design reference: `Step2-Prompt.dc.html` and `Step4-Report.dc.html` beside the settings mock.

Added after the real-Anki pass (17 Nov 2026):

- The question dialog is sized from its layout's height for its width (540 px unless the user widened it), the same way when first shown and after "Change choices…", so size and spacing never change between the two; only a different number of "Your saved choices" rows changes the height.
- While the update runs, Anki's progress window says "Updating with Special Fields by Ankoma…" with the title "Special Fields by Ankoma": the backend progress callback (Anki's own `import_progress_update`, so Cancel still aborts as in Anki) always sets that label, and `mw.progress.set_title` names the window after `CollectionOp.run_in_background` has opened it. If either API is missing, Anki's default text stays, silently.
- Summary: when the import updated no note (a deck new to the collection) the heading is "Import complete" instead of "Update complete", and "Fields kept from your version" and "Protected tags kept" are left out when they are 0. When notes were updated they are always shown, even at 0.
- Before the backup and the import, `looks_like_apkg` checks cheaply that the file is a readable zip (`zipfile.is_zipfile`) with a `collection.anki21b`, `collection.anki21` or `collection.anki2` entry (only the zip directory is read). If not: no backup, nothing imported, a plain warning "Nothing was imported. This file isn't a valid Anki package, or it is damaged." followed by "File: <name>". If Anki's own importer (`Collection.import_anki_package`, found in the error's traceback) still fails on a file that passed: a plain warning "Nothing was imported. Anki couldn't read this file:" followed by Anki's message, instead of Anki's error dialog. It does not claim the collection is unchanged (the engine does not report whether its rollback ran); rules 12 and 13 are unchanged, and any other error keeps Anki's error dialog.

## What every agent reports at the end

Files written; what was verified, on which Anki versions, with the exact commands and their pass/fail output; anything not verified; any place the contract was ambiguous or could not be met, and what you did about it. Don't claim a test passed unless you ran it and saw it pass.
