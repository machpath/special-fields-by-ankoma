# Spike report: Ankoma Special Fields (Anki 25.02 → 26.x)

Date: 2026-11-16. Source was read at tag `26.09.4` and diffed against `25.02.7`, `25.07.5`, `25.09.2`, `26.05`, `26.08.1` and `main`. Permalinks below point at tag `26.09.4`.

## TL;DR

**Recommendation: Architecture A, simplified.** The add-on owns the Ankoma import:
1. In one SQL pass, snapshot the user's protected field values and tags from the **user's own collection**.
2. Run the **native** importer: `col.import_anki_package` with `update_notes=ALWAYS`, `merge_notetypes=True`, `with_scheduling=False`.
3. Restore protected fields and tags **only on the notes the importer reports as `log.updated`**.
4. Fold everything into **one undo step** with `add_custom_undo_entry` / `merge_undo_entries`.

This approach never reads the package itself, so the zstd problem goes away. Deck placement and scheduling are kept by Anki's own importer: it never modifies existing cards.

A PoC passes **18/18 checks** at full scale (18,600 notes / 24,300 cards) on Anki 25.02.7 (on Python 3.9 and on 3.13), 25.07.5, 25.09.5, 26.09.4 and 26.11b1. The whole import takes **about 1 second**.

## 1. Version matrix (desktop releases from 2025 on)

| Release line | Stable versions (PyPI date) | Bundled Python | Default Qt (PyQt6) | Notes |
|---|---|---|---|---|
| 25.02.x | 25.02 (2025-02-11) … 25.02.7 (2025-06-06) | **3.9.18** (python-build-standalone) | 6.6.2 (PyQt 6.6.1); a 6.8.1 variant was also built | last "classic" bundled installer |
| 25.07.x (betas were called 25.06) | 25.07 (2025-07-04) … 25.07.5 (2025-07-25) | **3.13.5** (new uv-based launcher) | 6.9.1 (WebEngine 6.8.2); launcher also offers qt66/qt67/qt68 | 25.05 and 25.06 were betas only |
| 25.09.x | 25.09 (2025-09-06) … 25.09.5 (2026-06-18) | 3.13.5 | 6.9.1 (+ qt66/67/68 options) | |
| 26.05 | 26.05 (2026-06-16) | 3.13.13 | 6.11.0 (+ qt610/qt69/qt68 options) | wheels move to cp310 |
| 26.08.x | 26.08, 26.08.1 (2026-08-05) | 3.13.13 | 6.11.0 | `notetype/merge.rs` panic fix lands here |
| 26.09.x | 26.09 (2026-09-14) … 26.09.4 (2026-11-04) | 3.13.18 | 6.11.2 | **legacy Python importer removed** |
| 26.11 | 26.11b1 beta (2026-11-12) | 3.13.18 | 6.11.2 | PoC passes |

Sources: PyPI `anki`/`aqt` release metadata (`requires_dist` Qt pins), `.python-version` at each tag, and `build/ninja_gen/src/python.rs` plus `python/requirements.qt6_6.txt` at `25.02.7`.

**Implications:**
- The add-on must run on **Python 3.9**: no `match`, no runtime `X | Y` unions; use `from __future__ import annotations`.
- It must work on **Qt 6.6 through 6.11**: use only `aqt.qt` imports.
- Recommended `min_point_version`: **250200** (`point_version()` returns 250207 on 25.02.7 and 260904 on 26.09.4).

**Why the old add-on died:** it drove the legacy Python importer (`anki.importing.apkg`), behind the "Legacy import/export handling" preference ([forum, Jul 2024](https://forums.ankiweb.net/t/unable-to-use-special-fields-to-add-new-deck-due-to-version-error/47207); [forum, Nov 2025](https://forums.ankiweb.net/t/unable-to-read-file-it-probably-requires-a-newer-version-of-anki-to-import-special-fields/67364)). `pylib/anki/importing/` and every `legacy_import` reference in aqt exist up to 26.08.1 and are **gone in 26.09** (verified with `git ls-tree` / `git grep` per tag). So nothing can be built on the legacy path any more.

## 2. How the modern .apkg importer works (Rust, `rslib/src/import_export/package/apkg/import/`)

- **Entry points**
  - Python: [`Collection.import_anki_package(ImportAnkiPackageRequest)`](https://github.com/ankitects/anki/blob/26.09.4/pylib/anki/collection.py#L368) → backend `ImportAnkiPackage`.
  - Options: [`ImportAnkiPackageOptions`](https://github.com/ankitects/anki/blob/26.09.4/proto/anki/import_export.proto#L56) = `merge_notetypes`, `update_notes`, `update_notetypes`, `with_scheduling`, `with_deck_configs`.
  - Conditions: [`ImportAnkiPackageUpdateCondition`](https://github.com/ankitects/anki/blob/26.09.4/proto/anki/import_export.proto#L50) = `IF_NEWER` (0, the default), `ALWAYS`, `NEVER`. This proto is identical from 25.02.7 to `main`.
- **Transaction:** the whole import is one `transact(Op::Import)` ([mod.rs#L61](https://github.com/ankitects/anki/blob/26.09.4/rslib/src/import_export/package/apkg/import/mod.rs#L61)), so it is undoable as one step.
- **Note matching by GUID:** [`import_notes`](https://github.com/ankitects/anki/blob/26.09.4/rslib/src/import_export/package/apkg/import/notes.rs#L333) looks up `existing_guids.get(&note.guid)` (L347). [`maybe_update_existing_note`](https://github.com/ankitects/anki/blob/26.09.4/rslib/src/import_export/package/apkg/import/notes.rs#L416):
  - if `merge_notetypes` is off and the notetype differs → the note is logged **conflicting** and **not updated**;
  - else if [`should_update`](https://github.com/ankitects/anki/blob/26.09.4/rslib/src/import_export/package/apkg/import/notes.rs#L521) → the note is updated;
  - else → logged as **duplicate** (skipped).
- **`should_update`:**
  - `IfNewer`: `existing_mtime < incoming_mtime`;
  - **`Always`: `existing_mtime != incoming_mtime`** (so it is not truly "always");
  - `Never`: false.
- **[`update_note`](https://github.com/ankitects/anki/blob/26.09.4/rslib/src/import_export/package/apkg/import/notes.rs#L461):**
  - replaces **all fields and all tags** (`update_tags: true` only canonicalises; the incoming tag list wins);
  - **keeps the incoming note's mtime**;
  - does **not** generate cards.
- **Cards and decks:** [`import_cards`](https://github.com/ankitects/anki/blob/26.09.4/rslib/src/import_export/package/apkg/import/cards.rs#L100) only **adds** cards whose `(nid, ord)` does not exist yet: `// TODO: could update existing card` (L105).
  - Existing cards, their deck, scheduling, FSRS state and revlog are therefore **never touched**. Moved cards stay where the user put them.
  - Revlog rows are only imported for newly added cards.
  - Decks are matched **by name** ([decks.rs#L63](https://github.com/ankitects/anki/blob/26.09.4/rslib/src/import_export/package/apkg/import/decks.rs#L63)), so new cards go to the author's deck name.
- **Notetypes:**
  - **Without merge** ([`update_or_duplicate_notetype`](https://github.com/ankitects/anki/blob/26.09.4/rslib/src/import_export/package/apkg/import/notes.rs#L160)): if `equal_schema` (same field/template count and ids, [L594](https://github.com/ankitects/anki/blob/26.09.4/rslib/src/import_export/package/apkg/import/notes.rs#L594)) fails, Anki creates a copy notetype ("Ankoma Cloze+") and every note becomes **conflicting**.
  - **With merge** ([`update_or_merge_notetype`](https://github.com/ankitects/anki/blob/26.09.4/rslib/src/import_export/package/apkg/import/notes.rs#L229)): fields and templates are unioned. Fields are matched by **field config id, falling back to name** ([merge.rs#L88](https://github.com/ankitects/anki/blob/26.09.4/rslib/src/notetype/merge.rs#L88)), so a renamed field keeps its data. Notes are re-mapped.
  - **Overwriting:** when `update_notetypes` says update, the author's notetype **replaces templates and CSS entirely** (the PoC confirms user CSS is lost).
- **Media:** a file with the same name but different content is renamed with a hash suffix, and references in incoming fields are rewritten. **Static files (`_*`, `latex-*`) are skipped if the name already exists, even when the content differs** ([media.rs#L88](https://github.com/ankitects/anki/blob/26.09.4/rslib/src/import_export/package/apkg/import/media.rs#L88)).
- **Stability:** the import logic is **semantically unchanged from 25.02.7 to `main`**. The diffs are a refactor of the `mtime` argument, deck day-limit correction (25.07) and copyright headers.

## 3. Hook points

- **No `gui_hooks` relate to .apkg import.** I checked `qt/tools/genhooks_gui.py` and `dir(gui_hooks)` on 25.02.7 and 26.09.4.
- **The stock import dialog is a Svelte page** ([import_dialog.py](https://github.com/ankitects/anki/blob/26.09.4/qt/aqt/import_export/import_dialog.py)). It calls the backend directly over mediasrv, via [`raw_backend_request("import_anki_package")`](https://github.com/ankitects/anki/blob/26.09.4/qt/aqt/mediasrv.py#L1245), on the web-server thread. Python's `col.import_anki_package` is **not** called, so patching it does nothing for GUI imports. Wrapping `mediasrv.post_handlers["importAnkiPackage"]` is possible but fragile: it runs off the main thread and the options are user-chosen inside the web page.
- **Recommended hook:** wrap [`ApkgImporter.do_import`](https://github.com/ankitects/anki/blob/26.09.4/qt/aqt/import_export/importing.py#L87). It is a staticmethod with signature `(mw, path)`, identical in 25.02.7 and 26.09.4. Every .apkg path reaches it through [`import_file`](https://github.com/ankitects/anki/blob/26.09.4/qt/aqt/import_export/importing.py#L137):
  - File › Import;
  - drag-and-drop ([main.py#L124](https://github.com/ankitects/anki/blob/26.09.4/qt/aqt/main.py#L124));
  - double-click / open-with ([main.py#L1379](https://github.com/ankitects/anki/blob/26.09.4/qt/aqt/main.py#L1379)).

  `ColpkgImporter` claims `collection.apkg` and `backup-*.apkg` first, so full-collection restores are never intercepted. Non-Ankoma files fall through to the original.
- **Run the work with** `CollectionOp(parent=mw, op=...).success(...).with_backend_progress(import_progress_update).run_in_background()`. All these exist in both versions. Returning the merged `OpChanges` makes aqt refresh the UI and clear its notetype cache.
- **Verified:** `poc/smoke_aqt_routing.py` runs on real `aqt` 25.02.7 and 26.09.4 with offscreen Qt: Ankoma file → add-on; other .apkg → stock dialog; `collection.apkg` → stock colpkg path.

## 4. Architecture evaluation

| | A: snapshot / native import / restore (**recommended**) | B: rewrite the .apkg first | C: custom importer |
|---|---|---|---|
| Reads the package? | **No.** Snapshot from the user's DB; restore set = `log.updated` | Yes: needs zstd for `collection.anki21b` **and** zstd media map, then re-zip | Yes |
| zstd available? | not needed | **No.** `zstandard` / `compression.zstd` are not importable in any Anki Python (not in `uv.lock`; 3.13 lacks `compression.zstd`). Would need vendored native wheels per OS × Py3.9/3.13, or legacy-format-only packages | same problem |
| Deck / scheduling | kept natively (cards untouched) | kept natively | must re-implement |
| Notetype schema changes, field renames, media renames, notetype merge | native | native, but rewritten fields must match the incoming schema | must re-implement (hard) |
| Undo | one step (verified) | one step | DIY |
| Speed at 18.6k notes | ~0.05 s snapshot + ~0.45 s import + ~0.33 s restore | + unzip/rewrite/re-zip of a large media package | ? |
| Robustness across versions | only public, stable APIs | depends on the package format (Legacy1/2/Latest) | high maintenance |

**A's trade-off:** restoring touches notes twice (author value, then local value), so ~4k notes get an extra mtime/usn bump. That is harmless for sync, which stays a normal incremental sync.

## 5. Exact API recipe (all public pylib API, Python 3.9-safe). See `poc/ankoma_core.py`.

```python
pos  = col.add_custom_undo_entry("Import Ankoma update")
snap = {nid: (flds, tags) for nid, mid, flds, tags in col.db.execute("select id, mid, flds, tags from notes")}  # protected fields only
out  = col.import_anki_package(ImportAnkiPackageRequest(package_path=path, options=ImportAnkiPackageOptions(
           merge_notetypes=True, update_notes=ALWAYS,
           update_notetypes=ALWAYS or NEVER,  # "take author's templates/CSS?" toggle
           with_scheduling=False, with_deck_configs=False)))
col.models._clear_cache()                         # see gotcha G1
for logged in out.log.updated:                    # logged.id.nid  (NoteId message, not int)
    note = col.get_note(logged.id.nid)            # restore protected fields (keyed by field config id, name fallback) + tag policy
col.update_notes(changed_notes)
changes = col.merge_undo_entries(pos)             # return from the CollectionOp
```

## 6. Gotchas and risks

| # | Item | Severity | Mitigation |
|---|---|---|---|
| G1 | **Stale notetype cache in pylib.** `ModelManager._cache` ([models.py#L114](https://github.com/ankitects/anki/blob/26.09.4/pylib/anki/models.py#L114)) is not invalidated by a backend import; aqt only clears it after an op finishes, on the main thread ([main.py#L873](https://github.com/ankitects/anki/blob/26.09.4/qt/aqt/main.py#L873)). Without clearing it, post-import code sees the old field list and CSS. This happened in the PoC. | High | call `col.models._clear_cache()` (private but present in every version; guarded with `getattr`) |
| G2 | **The `IF_NEWER` trap.** Any local edit (Personal Notes, a tag) makes the local note "newer", so the stock default **silently skips the author's update** for that note. Measured: **1,525 of 18,600** notes skipped. | High | always pass `ALWAYS`; protected values are restored afterwards |
| G3 | **Schema change + merge + `IF_NEWER`.** The merge rewrites all local notes of that notetype with mtime "now" *before* comparing, so **0 of 16,000** cloze notes update. | High | `ALWAYS` (verified) |
| G4 | **`ALWAYS` means `!=`.** A note whose local mtime equals the incoming one to the second is skipped. In practice this only happens with an identical note (fine), but it showed up as a test artefact. | Low | none needed |
| G5 | **Author adds/reorders fields** → without `merge_notetypes` every note is "conflicting" and a duplicate notetype is created. **With merge, `scm` is bumped → the next sync is a one-way FULL sync** (verified; also stated in [importing.ftl#L39](https://github.com/ankitects/anki/blob/26.09.4/ftl/core/importing.ftl#L39)). | Medium | force `merge_notetypes=True`; warn the user before a schema-changing release; the author should batch schema changes |
| G6 | `merge_notetypes` **panic fix** in `notetype/merge.rs` ("clamp so a longer `other` appends instead of panicking") is only in **26.08+**. On 25.02–26.05, merging can panic in edge cases where a field matches at an index past the end. | Medium | author must never reorder or duplicate fields; append new fields only; test schema-changing releases on 25.02.7 |
| G7 | `update_notetypes=ALWAYS` **overwrites user templates and CSS** (verified). `NEVER` keeps them but also blocks author template fixes. | Product | toggle (see decisions) |
| G8 | New cards of existing notes (e.g. author adds `c3`) go to the **author's deck by name**, not next to the user's moved siblings. If the user renamed the Ankoma root deck, the importer recreates it. | Product / Medium | optional post-step: move new cards of pre-existing notes into the sibling card's deck (detect via card ids before/after) |
| G9 | Static media (`_ankoma.css`, `_*.js`) is **never updated** if the name exists. | Medium | author must version static filenames (`_ankoma_v1.3.css`) |
| G10 | Packages are `collection.anki21b` + zstd (default export), `collection.anki21` ("support older versions"), or `collection.anki2`. The native importer handles all of them. A test of a legacy=True export passed. | Low | none (A never parses packages) |
| G11 | Detecting "is this an Ankoma package" is cheap only by filename (we can't read the zstd collection). | Low | filename regex + confirmation prompt + explicit Tools menu item |
| G12 | A user who **changed the notetype** of an Ankoma note: with merge, `resolve_notetype_conflicts` will merge or convert it. | Low | document it; detect before import if needed |
| G13 | Deleted notes upstream are out of scope. They simply remain locally. | — | — |

## 7. Testing approach (verified working)

- `pip install anki==<ver>` works headless on Linux for every 25.x/26.x release. Wheels are cp39-abi3 (25.x) and cp310-abi3 (26.x). `from anki.collection import Collection` works and `import_anki_package` / `export_anki_package` run without Qt.
- Use `uv python install 3.9` to test 25.02 on its real Python line.
- `poc/test_import.py WORKDIR [n_cloze n_io]` does the following:
  - builds author notetypes with the exact Ankoma field lists, creates 16,000 cloze + 2,600 IO notes (24,300 cards), and exports v1.2, v1.3 and v1.3b (adds a field);
  - simulates a user: Personal Notes, a Text typo fix, personal tags, 500 cards moved to "My Deck", 300 cards rescheduled, a CSS tweak, and local edits made "later";
  - checks: baseline trap, protected/overwritten fields, tag merge with v1.2→v1.3 root, deck kept, scheduling byte-identical, card/revlog counts, scm, CSS, single undo + undo correctness, and schema change with and without merge.
- **Results (logs in `poc/run_*.log`):** 18/18 on 25.02.7 (Py 3.9.25 and 3.13), 25.07.5, 25.09.5, 26.09.4 and 26.11b1.
- `poc/test_legacy.py`: legacy-format package OK on 25.02.7 and 26.09.4.
- GUI: `pip install "aqt[qt]==26.9.4"` (and aqt 25.2.7 + PyQt 6.6) runs with `QT_QPA_PLATFORM=offscreen`, enough for routing and smoke tests. A full `mw` boot was not attempted. A manual pass in real Anki 25.02.7, 25.09.x and 26.09.x desktop builds is still needed (progress dialog, undo menu label, sync).
- **CI suggestion:** a GitHub Actions matrix over `{anki 25.2.7 @ py3.9, 25.7.5, 25.9.5, 26.5, 26.8.1, 26.9.4, latest beta}` running `test_import.py`, plus the aqt smoke test on the oldest and newest versions.

## 8. AnkiWeb packaging

- Zip the add-on **contents** (no top-level folder), with **no `__pycache__`**, as `.ankiaddon`. `manifest.json` is optional for AnkiWeb (required only for distribution outside AnkiWeb) ([docs](https://docs.ankiweb.net/addons/sharing)).
- `config.json` + `config.md` drive the built-in config editor.
- Set the min/max supported versions on the AnkiWeb upload form.
- Example build: `poc/ankoma_special_fields.ankiaddon` (`__init__.py`, `ankoma_core.py`, `config.json`, `config.md`, `manifest.json`).

## 9. Product decisions needed from the deck author

1. **Default protected fields.** The PoC defaults to only `Personal Notes`; candidates are Personal Notes, Remarks, Extra 1/2. Should `Text` or `Extra` ever be protectable (then the user also misses author corrections)?
2. **Tag default.** The spec says "overwrite". Recommend offering `merge` (author `##ANKOMA-vX::*` tags replaced, user's own tags kept) as the default instead. Pure overwrite deletes users' personal tags on every update.
3. **Templates/CSS.** Always take the author's version (users lose their CSS tweaks), or keep the user's (author template fixes don't arrive)? A third option is a third-party CSS hook / field.
4. **New cards of existing notes:** put them in the author's deck, or next to the user's moved siblings?
5. **Schema changes** force a one-way full sync for every user. Accept that, announce it in release notes, and batch field additions; never reorder fields (G6).
6. **Detection UX:** filename pattern + prompt (current) vs. a Tools-menu-only flow. Also: should the add-on intercept at all when the user double-clicks the file?
7. **Static media:** the author must version `_`-prefixed filenames (G9).

## Files

- `poc/ankoma_core.py`: GUI-free core (snapshot / import / restore, single undo)
- `poc/addon/`: AnkiWeb-layout add-on skeleton (`__init__.py` wraps `ApkgImporter.do_import`, adds Tools › "Import Ankoma update…", runs a `CollectionOp`)
- `poc/ankoma_special_fields.ankiaddon`: built package (not uploaded)
- `poc/test_import.py`, `poc/test_legacy.py`, `poc/smoke_aqt_routing.py`, `poc/run_*.log`
