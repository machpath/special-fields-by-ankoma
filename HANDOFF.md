# HANDOFF: how to pick this build up

**To resume in a new chat:** open a chat in the "Special Fields Add on for Ankoma" project and say: *"Continue the Special Fields build from HANDOFF.md in the machpath/special-fields-by-ankoma GitHub repository."* (The same file is in the Desktop folder `Anki Add Ons\Special Fields Add On`.)

This file is updated at every checkpoint. The GitHub repository and this folder are the record between sessions; the cloud workspace a session builds in is temporary.

## What this is

**Special Fields by Ankoma**: an Anki add-on that lets users import an updated deck without losing the fields and tags they chose to protect. Built for the Ankoma deck, works with any deck.

- Plan (decisions, build plan, tests, risks): https://claude.ai/artifact/WRPTYrPKMD8wYQ9e66bSSq
- Mock screens: https://claude.ai/artifact/DTSAP1wSdY24Khwi5vHxCx
- Binding spec for the code: `docs/CONTRACT.md`
- Short decision record: project doc `claude/ankoma-special-fields-spec.md`
- Technical investigation and prototype: `research/spike/`

## How the work is organized

- The chat session is the orchestrator: it owns the contract, hands out work, reviews and integrates.
- Workers are Opus agents on medium effort (Agent tool: `model: "opus"`, `effort: "medium"`), one per workstream, each editing only the files it owns (see the table in `docs/CONTRACT.md`).
- The author approved the plan on 2026-11-16. Nothing is uploaded or published without the author's say-so.

## Status

Last updated: 2026-11-16, evening (Pacific).

| Phase | Status |
| --- | --- |
| 1. Plan approved | Done |
| 2. Foundation (A): layout, `model.py`, `config.py`, `docs/CONTRACT.md` | Done |
| 3. Parallel build: engine (B), settings window (C), test harness (D) | Done and saved. Gate met: the orchestrator ran `bash tools/run_matrix.sh --no-create` and saw `tests/engine` 26/26 and `tests/acceptance` 75/75 pass on 25.02.7 (Py 3.9 and 3.13), 25.07.5, 25.09.5, 26.05, 26.08.1, 26.09.4, 26.11b1, and `tests/ui` 46/46 on aqt 25.02.7 and 26.09.4 |
| 4. Integration: import flow (E) | Done and saved: `import_flow.py` (question on every .apkg, progress, summary with undo, Tools menu item; also wraps the old `aqt.importing.importFile` route as a safety net) + `tests/flow/`. Gate met: orchestrator ran the matrix and saw engine 26/26 and acceptance 75/75 on all 8 headless versions, ui 46/46 and flow 77/60 passed on aqt 25.02.7 / 26.09.4 |
| 5. Independent verification + manual pass in desktop Anki | Two independent verifications done; all Critical/High findings are either fixed or now end in a clean refusal (contract rules 9 to 13). After the last round the orchestrator re-ran the matrix (engine 72, acceptance 87 on all 8 headless versions; ui 47; flow 88 on aqt 25.02.7, 71 on 26.09.4) and the second verifier's 17 scenarios on 25.02.7/py3.9 and 26.11b1: every completed import keeps all user data; every unsafe note type move is refused with the collection unchanged. Beta build made: `special_fields_by_ankoma-0.1.0-beta7.ankiaddon` (in the Desktop folder under `builds/`; loads under a numeric folder name in both Qt environments). NOT yet run in a real Anki: that manual pass is next and needs the author |
| 6. Author beta with a real v1.3 | Not started; needs a v1.3 file from the author |
| 7. Release (F): AnkiWeb upload by the author, ankomapath.com page | Not started |

### What exists in this folder right now

- `src/special_fields_by_ankoma/`: `model.py`, `config.py`, `config.json`, `config.md`, `manifest.json`, `__init__.py` (foundation); `engine.py` (B); `settings_dialog.py` (C).
- `src/special_fields_by_ankoma/import_flow.py` (E).
- `tests/engine/` (26 tests), `tests/ui/` (46), `tests/flow/` (78), `tests/acceptance/` (75 + 1 slow full-size test), `tools/build_fixtures.py`, `tools/run_matrix.sh`, `tools/build_addon.py`.
- `docs/USER_GUIDE.md`, `docs/ANKIWEB_LISTING.md`: drafts for the author.
- `docs/CONTRACT.md`: the spec each workstream builds to.
- `research/spike/`: the investigation report and prototype.

If a file named above or in the status table is missing here, that work had not been reviewed and saved when the session ended: relaunch that workstream from `docs/CONTRACT.md`.

### Verification findings (workstream G, 2026-11-16) and their status

Verdict: safe for the author to trial on a COPY of a profile; not ready for users until the Critical and High items are fixed.

| # | Severity | Finding | Status |
| --- | --- | --- | --- |
| C1 | Critical | Fields not listed in the settings were blanked on every updated note, including fields the user added themselves | Fixed: contract rule 9 (an update never blanks a field it has no content for) |
| H1 | High | When a note's note type differs between the file and the collection, Anki's forced merge made duplicate "+" fields, hid kept values in them, and brought the author's styling even with the switch off | Fixed: contract rule 10 as REVISED by the author: follow the move (restore kept fields by name on the new note type, remove the empty "+" leftover fields). The author rejected "refuse the import" because future releases will move notes between note types |
| M1 | Medium | Hand-edited config: `"keep": "false"` read as true, `"update_note_types": "false"` read as true, a single-string `protected_tags` ignored | Fixed in `config.py` (+ `tests/engine/test_config_reading.py`) |
| M2 | Medium | Full-sync advice could lose reviews from other devices | Fixed in docs and dialogs |
| M3 | Medium | Keeping cloze Text while the update adds a cloze number leaves a blank card | Documented in the user guide |
| M4 | Medium | User guide overclaimed the styling switch | Reworded |
| L1 | Low | Markup in field/tag names rendered as rich text in Settings | Fixed |
| L2 | Low | The question also appears for `.zip` files (Anki's importer accepts them) | Accepted, not documented |
| L3 | Low | Small wording differences from the mocks (summary heading "Update complete") | Accepted |
| L4 | Low | A note whose local and author edit share the same second is skipped as unchanged | Accepted (Anki behaviour) |
| L5 | Low | Acceptance oracle ignored fields absent from the update; two assertions could not fail | Fixed |
| L6 | Low | Deck option presets in a file are not imported | Documented; since 17 Nov 2026 an optional switch ("Import deck presets") |

The verifier's scripts are in `/tmp/sfa-g/` of the session that ran them (not saved). Not checked by anyone yet: a real running Anki, media handling (whether Undo removes imported media), GUI on Python 3.9.

**What the fix agent found about note type moves (important):** on every supported version, Anki's forced merge for a note whose note type differs does far more than add empty "+" fields. It also appends the old type's card templates, points the target type's own templates at the empty "+" fields (cards render blank), moves every existing card of the target type onto a "+" template, creates a duplicate card per note, and shifts untouched notes' content into "+" fields. `engine._clean_merge_leftovers` repairs all of that inside the undo step (16 tests; they all fail with the clean-up disabled). Known limits: a non-clashing extra template from the old type (e.g. "Card 2") is kept; a cloze ↔ standard move still fails with Anki's own error and rolls back; in the same-name/different-id case the note type keeps Anki's "+" name. Rule 9 side effect: if the author empties an unlisted field on every note, users keep their old value.

### Second verification (rules 9 and 10 only, 2026-11-16 late) and its status

Verdict: safe to trial on a COPY; must not go to users until the items below are closed. Normal updates (no note type moves) passed everything again. All findings are in the note-type-move repair, identical on all 8 versions:

| # | Severity | Finding | Status |
| --- | --- | --- | --- |
| V2-C1 | Critical | Note types made with Anki's Clone share field ids. A move between them adds no "+" fields, so the clean-up returned early while Anki had scrambled the fields of the user's OWN notes of the target type. Plain Anki with "merge note types" does the same | Fixed (`_restore_untouched`) and guarded by gate G1 |
| V2-C2 | Critical | Notes arriving in one standard note type from two other types: reviewed cards deleted | Now refused by gate G2 (rule 12); making it succeed is not done |
| V2-C3 | Critical | Old type's template has a non-clashing name: duplicate cards on every target note, cards left on the foreign template | Now refused by gates G2/G4 (rule 12); making it succeed is not done |
| V2-H1 | High | Moves in both directions between two standard types are refused | Still refused (safe) |
| V2-H2 | High | Standard types with identical templates under different names are refused | Still refused (safe) |
| V2-H3 | High | If Anki's backend fails after the import, undo is gone and the user was told "unchanged" | Done: rule 13 |
| V2-M1/M2 | Medium | Extra non-clashing template or empty carried-over fields left on the target type | Open (M1 now refused where it creates cards on untouched notes) |

Design decision after this round: stop patching Anki's merge case by case; the engine now has to PROVE the result is clean (contract rule 12) or roll back. Moves that the repair handles correctly go through (cloze types with independent ids, one direction; standard types with clashing template names, one direction; repeat imports; move-then-move-back). Everything else is refused with a clear message.

**Decision for the author:** whether to invest in making more kinds of note type move succeed (V2-C2, C3, H1, H2), or to avoid moving notes between note types in releases (adding new note types and changing fields/templates of existing ones is safe). Also: run `tools/check_shared_ids.py` on a COPY of the author's collection to see whether Ankoma's note types share ids (were cloned), which decides how much V2-C1 matters. The second verifier's scenario scripts are in `/tmp/sfa-v2/scr/` of that session (copy kept in `/tmp/sfa-pm/v2keep/`; not saved to the repository).

**For the author's beta:** export v1.3 from the same collection as v1.2 so note type ids match; a mismatch no longer blocks the import but makes every note go through the move-and-clean-up path. Orchestrator's experiment script for author-side note type moves: `/tmp/sfa-pm/nt/exp.py` (session-local; result recorded in contract rule 10).

### Author feedback after first trying beta1 (17 Nov 2026)

The author installed beta1 and reported that it looked like it worked (what exactly was tried, and whether on a copy of the profile, is not yet known: ask). Changes requested and made, settings window only (beta2: tag picker; beta3: removable default fields):

- Protected tag picker: no Select button. The first match is highlighted; Enter adds the highlighted tag; one click on any tag in the list adds it. Nothing is highlighted when the typed text is itself an already protected tag.
- No message after a tag is added or removed. The hint line under the box shows only for: no match, already protected, list cut short.

- Every field row can be removed, the six default rows included. The author: the add-on must work with literally any deck, "building for longevity and scale, not a temporary ankoma thing". An empty list is valid and is saved as empty; only "Restore defaults" brings the defaults back. An unlisted field takes the update's content (rule 9 applies).

The "+ Add field" picker showed 'Added "X". It starts as "Take the update\'s".' after adding a field; removed 17 Nov 2026 at the author's request (see below).

**17 Nov 2026: "Import learning progress" and "Import deck presets" switches.** The author asked for the two options of Anki's standard import that the add-on lacked ("moving from one device to another and want to keep my progress without ankiweb sync"). Made (contract rule 6a, G3 of rule 12 rewritten):

- `Settings.import_scheduling` → Anki's `with_scheduling`, `Settings.import_deck_presets` → `with_deck_configs`; both OFF by default; config keys `import_scheduling` / `import_deck_presets` (a config from an earlier beta without them loads as off). The other three standard-import options stay fixed (update notes always, merge note types on, update note types = the styling switch).
- Settings window: two switch rows under "Update card templates and styling" (`scheduling_switch`, `presets_switch`); "Restore defaults" turns them off; `choices_summary` gains "Learning progress" and "Deck options" (the switch was first labelled "Import deck presets"; renamed "Import deck options" the same day because the author asked what a preset is. The config key stays `import_deck_presets`) rows, so the question window shows them. The summary after an import adds "New cards with learning progress: N" only when the switch was on (`ImportResult.learning_progress_imported`, `cards_with_progress`). The window opens about 130 px taller (body 559 → 689 px at 600 px wide).
- What Anki really does, verified identically on 25.02.7 (Py 3.9) to 26.11b1: with scheduling on, existing cards and their review log are never changed and the file's rows for them are not imported; only cards new to the collection arrive with the file's scheduling and review rows. With presets on, a preset already in the collection (same id) is never changed, Default included, even when the file's copy is newer; presets only in the file are added (same id; a name clash gives two presets with one name); every deck in the file, existing ones included, is switched to the file's preset unless the file has it on Default. So a user's own deck-to-preset choice can be changed, but no preset's values; one undo puts it all back (tested).
- Gate G3 now: every pre-import review row still there and unchanged; with scheduling off no row may be added; with it on, rows only for cards new to the collection (a new card that gets back the id of a deleted card is handled: the deleted card's old rows must stay as they were). Extra cost with scheduling on, measured on 24,000 cards / 380,000 review rows: well under 0.1 s.
- Note type moves with both switches on: the engine's 8 move scenarios and the second verifier's 17 scenarios (scratch copy with an author file carrying review history for every card, `SFA_SCHED=1`) end exactly as with the switches off: every completed import keeps all user data, every refused one leaves the collection unchanged. With both switches off nothing changed (same results as before on all 8 versions).
- Known, harmless: if a review row in the file has the same id (millisecond time stamp) as one already in the collection, Anki skips the file's row; the card still arrives with the file's scheduling. Only seen in fast test scripts.
- For the author to know: "Import learning progress" brings progress only for cards the collection does not have yet. A device that already has the cards keeps its own progress; the user guide says to use sync or a `.colpkg` to copy everything.

**17 Nov 2026, after the real-Anki pass** (tester ran Anki 25.02.7 and 26.09.4 on a virtual screen with the author's deck; everything worked; these Low rough edges were fixed, contract sections C and E updated, each confirmed in the real app on both versions):

1. Question window: same size and spacing on first show and after "Change choices…" (sized from the layout's height-for-width; it used to open 542×481 with loose spacing and come back 502×431).
2. Tag list and "+ Add field" list: no horizontal scroll bar, long names elided in the middle with the full name as tooltip; the added text is still the full name.
3. Settings window grows/shrinks to fit when the tag list or field picker opens/closes (top-left fixed; capped at 90% of the screen and the screen's bottom edge; never below its opening or user-resized height), so no stray scroll bar and the heading stays in view.
4. Progress window: "Updating with Special Fields by Ankoma…", titled "Special Fields by Ankoma" (Anki's default if the API differs).
5. Summary: "Import complete" and no zero "kept" rows when no note was updated; row renamed "Your existing cards: review history and decks".
6. Broken or non-package file: checked before the backup; plain "Nothing was imported. This file isn't a valid Anki package, or it is damaged." + file name, no backup. A file that passes but that Anki's importer cannot read: "Nothing was imported. Anki couldn't read this file:" + Anki's message (no "unchanged" claim).
7. Initial focus in the settings window: first row's toggle (or "+ Add field"), not the scroll area.
8. (Author, same day) Closing the settings window with unsaved changes asks "Discard your changes?" (Discard / Keep editing, Keep editing default and Esc). No question when nothing changed; Save never asks.
9. (Author, same day) No message after adding a field ('Added "X". It starts as …' removed); problem hints stay.

Also from the author: the tag search order (shortest match first, "#edit" before "#edited") is intended. USER_GUIDE now says that a cloze an update removes leaves an empty card, which the add-on leaves alone (Tools → Empty Cards clears it); no code for that by decision.

### Where things stand on 17 Nov 2026, evening (read this first when resuming)

1. **Real-Anki pass: done and passed.** The full Anki app (25.02.7 and 26.09.4, Xvfb + openbox) installed beta 6, updated a practice collection built from the author's real files (9,190 notes updated, 10,122 added, 606 fields kept, 1,020 protected tags kept, about 2.2 s), and one Undo restored it exactly. No Critical/High/Medium defects. Screenshots were sent to the author. Not covered: Windows/macOS, a real file-manager drag, sync, dark theme, "Import deck options" on during an import.
2. **The nine rough-edge fixes from that pass are done and in this commit** (beta 7; listed in the author-feedback section below). The orchestrator re-ran the full matrix afterwards: engine 107 and acceptance 87 on all 8 headless versions, ui 73, flow 102 (aqt 25.02.7) / 85 (aqt 26.09.4).
3. **Next feature, approved by the author: fields kept per protected tag.** The full design is in `docs/DESIGN_TAG_RULES.md`. If no later commit contains it, it has not been built: give it to one worker (model, config, engine, settings window, flow summary, tests, docs), then verify with the full matrix and the author's files.
4. Small leftover for the same worker: the summary window still sizes itself with `resize(540, sizeHint().height())` and shows a large gap above the undo note; give it the same fit-to-content treatment the question window got.
5. Author decisions recorded today: tag search order (shortest match first) is right; the add-on does nothing about empty cards and shows no message; "Import deck options" wording; every default field row removable; ask before discarding unsaved settings.
6. How to run the real Anki app here again: see /tmp/sfa-real/gui/scr (may be gone in a new workspace). Needs `apt install openbox x11-utils libxcb-cursor0 libxcb-icccm4` and friends, `Xvfb :99 -screen 0 1440x960x24 &`, `DISPLAY=:99 openbox &`, env `QT_QPA_PLATFORM=xcb ANKI_NOHIGHDPI=1 QTWEBENGINE_CHROMIUM_FLAGS="--no-sandbox --disable-gpu" QTWEBENGINE_DISABLE_SANDBOX=1`, a base folder with `prefs21.db` prepared, and a small driver add-on that steps a generator from a QTimer and uses QTest clicks.
7. The author's two files (Ankoma1 = current collection, Ankoma2 = newest release) were attached in the chat and are private: they are NOT in the repository. Ask the author for them again if the workspace no longer has /tmp/sfa-real/in.

### Next steps

1. Manual pass in desktop Anki on a COPY of the author's profile, with the author's go-ahead: install `builds/special_fields_by_ankoma-0.1.0-beta7.ankiaddon` (Tools → Add-ons → Install from file), then check: the Tools menu item; the settings window; the question on double-click, drag-and-drop and File → Import; progress; the summary; Edit → Undo label; a backup appears in the profile's backups folder; sync.
2. Author decisions still open: (a) invest in making more kinds of note type move succeed, or avoid moving notes between note types in releases; (b) run `tools/check_shared_ids.py` on a COPY of the collection (do Ankoma's note types share ids?); (c) accept or not: when notes move in both directions between two note types, each type keeps the other's non-clashing fields as empty fields (no data lost); (d) the pre-import backup (rule 11) and rule 9; (e) license for the public repository; (f) what the Unrestricted note types are; (g) a v1.3 file for the beta.
3. After the manual pass: fix what it finds, bump `human_version` in `manifest.json`, rebuild with `python3 tools/build_addon.py`, then the author's beta with a real v1.3.
4. Release: author reviews `docs/USER_GUIDE.md` and `docs/ANKIWEB_LISTING.md`, uploads to AnkiWeb; ankomapath.com page after the author approves its content. The plan doc (claude.ai artifact) now ends with a section summarising rules 9 to 13; `docs/CONTRACT.md` remains the current, binding spec.

Which note type moves complete today: between note types whose card templates have the same name (cloze types; Image Occlusion types one way); to a brand-new note type; a user-changed note type; a same-named note type with a different id; cloned note types (shared field ids), one way or both; cloze moves both ways. Refused cleanly: notes from two types into one standard type; a standard old type whose template name differs from the target's or that has an extra template; Image Occlusion moves both ways in one release; cloze ↔ standard.

Run the tests with `bash tools/run_matrix.sh` (the folder mount ignores the executable bit). Full-size import (18,600 notes, 7,400 fields and 7,440 tags restored) measured 2.3 to 2.6 s; accepted.

## Decisions the orchestrator made during the build (tell the author)

- Engine: imports never bring in the file's review history or deck option presets (`with_scheduling=False`, `with_deck_configs=False`); existing cards are untouched either way. (Superseded 17 Nov 2026: both are now user switches, off by default; see the author feedback section.)
- Engine: the user's own settings for Anki's standard import screen are put back after each Special Fields import (Anki would otherwise overwrite them with "always update").
- Engine: with templates-and-styling off, existing templates and CSS stay identical, but a brand-new card template added by an update is still added.
- Settings window: the tag picker's Select button is plain (the accent is reserved for selections and Save); `open_settings(mw, parent=None)` takes an optional parent for the import flow.
- After verification: unlisted fields the update has no content for are left alone (rule 9); note type moves are followed and Anki's leftover "+" fields are removed (rule 10, as the author asked); the question dialog gains a one-line "sync first" tip. The author asked for rule 10's current form; rule 9 has been explained to the author but not explicitly confirmed.
- Backup: "Import with my choices" asks Anki for one of its normal backups before changing anything (contract rule 11), because Anki throws away its undo history if one of its own operations fails part-way. Not yet confirmed by the author.
- An unrepairable note type move rolls the whole import back and shows a plain warning (rule 10g) instead of leaving Anki's half-merged state.
- Legacy import: `ProfileManager.legacy_import_export()` is hard-coded to False on every supported version, so the old importer can't be reached from the UI; the legacy wrap is defence in depth only.
- Re-importing the same file reports unchanged notes as skipped (reason `unchanged`); the summary dialog should leave that reason out.

- Protecting a tag also protects its sub-tags: `#edited` keeps `#edited::images` too (`model.is_protected_tag`).
- Field names are matched ignoring case and surrounding spaces.

## Assumptions in force (the author can change them)

Default field rows (author's list, 2026-11-16): Header, Text, Extra, Personal Notes, Textbook, Citation, with only Personal Notes kept (Images is not a default row; users can add it); the templates-and-styling switch stays, on by default; new cards on existing notes go to the deck named in the release; ankomapath.com gets a download page only; new fields are only added at the end of a note type; style-file names are versioned per release.

## Still needed from the author

- What makes the Unrestricted / Unrestricted+ note types different.
- A real v1.3 export, or v1.2 plus a mocked v1.3, for the beta.

## Rebuilding the test environments in a fresh workspace

One environment per Anki version, headless: `uv venv /home/claude/venv-<ver> && uv pip install --python /home/claude/venv-<ver> anki==<ver> pytest` for 25.2.7 (also on Python 3.9), 25.7.5, 25.9.5, 26.5, 26.8.1, 26.9.4 and the 26.11 beta. For offscreen GUI tests: `aqt[qt]==26.9.4`, and `aqt==25.2.7` with PyQt 6.6, run with `QT_QPA_PLATFORM=offscreen`. Details in `research/spike/SPIKE_REPORT.md`, section 7.
