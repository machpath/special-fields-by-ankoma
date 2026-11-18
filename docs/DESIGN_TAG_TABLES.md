# Design: a field table per protected tag, and (i) bubbles

Status: **approved by the author on 17 Nov 2026 (evening), not yet built.** It replaces the chips design of beta 8 (contract rule 14 as first written). When it is built, rewrite rule 14 and the settings-window section of `docs/CONTRACT.md` from this file and delete this file.

## What the author asked for (their words, shortened)

- "I want a collapsable one of these [the Fields table with Keep mine / Take the update's] to be also present for the tags." Structure: "Protected tags", the "start typing a tag…" bar, below it an arrow, collapsed by default; clicking it opens the area. "Once a tag is selected, that collapsable thing automatically folds out."
- "a table per tag. but i want it that if a rule is made for the first tag, that rule is automatically carried over to the next tag." Example: tag 1 `#edited` protects Header only; tag 2 `#hard` opens with Header already selected, kept; tag 3 `#easy` opens with Header, changed to Text and Extra; tag 4 `#text-based` opens with Text and Extra, changed to Citation only.
- "i want you to also add by default whatever the master rule said on top. if i chose to select personal notes for all cards, all tags will have personal notes auto-selected whether or not the previous tag had it selected. It needs to be un-selected manually for each individual tag."
- "if a tag does not select personal notes but the overall [list] on top does, then [cards with that] tag will not be protected for that field."
- "(i) bubble to indicate highlight here for information" next to Protected tags, next to "Fields" (remove the colon and the words after it), and for "Update card templates and styling", "Import learning progress" and "Import deck options", replacing the grey text under each. "not cluttery".

## Behaviour at update time (replaces rule 14 b–f of beta 8)

1. A protected tag is never removed from a note (rule 4, unchanged). Sub-tags count: a note tagged `#edited::images` carries `#edited`. Matching is case-insensitive. The note's tags BEFORE the import decide.
2. Every protected tag has its own field table. A note that carries one or more protected tags follows those tables and NOT the main list.
3. A tag's table, field by field: "Keep mine" or "Take the update's". A tag's table can switch off a field the main list keeps: then notes with that tag are not protected for that field.
4. A note with several protected tags keeps a field if ANY of their tables keeps it.
5. A note with no protected tag follows the main list (unchanged).
6. A tag's table is stored as differences from the main list: `keep_fields` (kept for this tag although the main list does not keep them) and `take_fields` (not kept for this tag although the main list keeps them). Effective kept fields of a tag = (main list's kept fields − `take_fields`) ∪ `keep_fields`. Consequences, all intended:
   - a tag with no differences behaves exactly like the main list, so configs with plain-string tags (beta 7 and earlier) and beta 8's `{"tag", "keep_fields"}` objects keep their old meaning;
   - if the user later starts keeping a field in the main list, every tag picks it up unless that tag switched it off itself.
7. "Keep every field" per tag (`keep_all_fields`): every field the note had before the import keeps the user's value; fields new to the note take the update's. Unchanged from beta 8.
8. Field names match by normalized name within the note's note type; a field the note type lacks is skipped; notes moved to another note type are matched by field name (rule 10a).
9. Rule 9 (an unlisted field the update leaves empty on every note of a note type keeps the user's text): for a note carrying protected tags, a field counts as listed if it is in the main list or in `keep_fields`/`take_fields` of a tag the note carries. So a field switched off in a tag's table really takes the update's value, even when that is empty.
10. Counters, gate, undo: as today.

## How a new tag's table starts (settings window only)

When a tag is added: its effective table = the effective table of the last tag in the list (the one added before it) ∪ every field the main list keeps, and `keep_all_fields` copied from that tag. The first tag starts equal to the main list. Stored as: `keep_fields` = previous tag's effective kept fields that the main list does not keep; `take_fields` = empty.

Worked example with Personal Notes kept in the main list: `#edited` opens with Personal Notes; set to Header + Personal Notes. `#hard` opens with Header + Personal Notes. `#easy` opens with Header + Personal Notes; changed to Text + Extra (Personal Notes switched off). `#text-based` opens with Text + Extra + Personal Notes (Personal Notes back on, because the main list keeps it).

## Settings window

```
Fields (i)
[ table as today, + Add field ]

Protected tags (i)
[ Start typing a tag from your collection…        ]
›  #edited        keeps Header, Personal Notes        ✕
›  #hard          keeps Header, Personal Notes        ✕
⌄  #easy          keeps Text, Extra                    ✕
      Header           [Keep mine][Take the update's]
      Text             [Keep mine][Take the update's]
      …                (same rows as the main list, compact)
      ☐ Keep every field

Update card templates and styling (i)      [switch]
Import learning progress (i)               [switch]
Import deck options (i)                    [switch]
```

- One line per tag when collapsed: arrowhead, tag (elided in the middle if long, full tag as tooltip), a short summary ("keeps Header, Personal Notes" / "keeps every field" / "keeps no fields"; elided if long), ✕.
- Collapsed by default when the window opens. The arrowhead (a real button: Enter/Space toggles, accessible name says expanded or collapsed) opens that tag's table. Only one tag is open at a time. A tag that has just been added opens automatically (closing any other).
- A tag's table has the same rows as the main list, in the same order, with the same two-sided toggle, smaller. No "+ Add field" and no row ✕ inside a tag: fields are managed once, in the main table. A row for a field the tag keeps that is no longer in the main list is shown at the end of that tag's table until it is switched off.
- "Keep every field" is a small checkbox at the bottom of an open table; when ticked the rows show as kept and are disabled.
- Changing the main list updates every tag's rows and summaries immediately (point 6).
- No grey paragraphs: the sentences under "Fields", "Protected tags" and the three switches move into (i) bubbles. Hints that report a problem (no match, already protected…) stay.
- "Restore defaults", the "Discard your changes?" question, Tab order and the window's fit-to-content behaviour cover all of this.
- `choices_summary()` "Protected tags" row: `#edited (keeps Header, Personal Notes), #hard (keeps Header, Personal Notes), #eevee`; a tag whose table equals the main list is shown by name only; `(keeps every field)`, `(keeps no fields)` where they apply. The question window shows at most three lines of it, then "+N more" with the full text as tooltip.

## (i) bubbles

A small round "i" button after the heading or switch title. The text shows on hover (tooltip), and also when the button is clicked or activated with Enter/Space while focused (so it works without a mouse); it is also the button's accessible description. Plain text only. It must be readable in Anki's light and dark themes. Texts:

- **Fields** (heading is just "Fields"): "Choose what happens to each field when an update changes a card you already have. Keep mine: your text in that field stays. Take the update's: the update's text replaces yours. Fields are matched by name, so their order doesn't matter, and a field a note type doesn't have is skipped. A field that isn't listed takes the update's text, unless the update leaves that field empty on every card."
- **Protected tags**: "An update replaces a card's tags with the update's. A protected tag is never removed from your cards; its sub-tags are covered too. Cards with a protected tag follow that tag's own field choices instead of the choices above: open a tag to set them. A new tag starts with the previous tag's choices plus every field you keep above. A card with several protected tags keeps a field if any of them keeps it."
- **Update card templates and styling**: "On: an update may replace your card templates and styling with its own. Off: yours stay exactly as they are. Card content updates either way."
- **Import learning progress**: "On: cards that are new to your collection arrive with the scheduling and review history saved in the file. Cards you already have always keep your own progress. Off: new cards arrive as new. Useful for moving a deck to another computer without syncing."
- **Import deck options**: "On: deck options saved in the file (daily limits, learning steps, FSRS settings) come in as new presets, and the file's decks use them. Options you already have are never changed. Off: no deck options are imported."

## Config

`protected_tags` entries: a plain string, or `{"tag": "...", "keep_fields": [...], "take_fields": [...], "keep_all_fields": false}`. All keys but `tag` optional; reading stays tolerant; a tag with no differences is saved as a plain string. Beta 8 configs load with the same behaviour as in beta 8.

## Tests to add or change

Engine/acceptance oracle: the worked example; a tag switching off a main-list field (tagged notes lose it, untagged keep it); union across two tags; sub-tags; main list changed after tags exist; "keep every field"; rule 9 interplay; beta 7 and beta 8 configs give byte-identical results to those betas. Window: collapsed by default; add opens it and closes others; one open at a time; new tag defaults per the worked example; main-list change updates tags; summaries; no "+ Add field" in tags; bubbles (text, hover, keyboard, accessible description, no grey paragraphs left); restore defaults; discard question; Tab order. Real files and the real app as for beta 8, plus one pass in Anki's dark theme.
