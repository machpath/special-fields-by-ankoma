# Special Fields by Ankoma: user guide

DRAFT. Not yet checked against a real Anki install.

Special Fields by Ankoma lets you import an updated version of a deck without losing the parts you chose to protect. It was built for the Ankoma deck and works with any deck that ships as an `.apkg` file.

It runs in Anki on a computer (Windows, Mac or Linux), Anki 25.02 or newer. Phones and tablets get the result through sync.

## Set it up once

1. Open **Tools → Special Fields by Ankoma**.
2. **Fields.** For each field, pick **Keep mine** or **Take the update's**. Out of the box, only Personal Notes is kept. Use **+ Add field** to add any other field from your note types, and the **✕** beside a field to take it off the list. The starting fields are only suggestions: remove any your decks don't use. A field that isn't listed takes the update's content. One exception protects you: if the update leaves a field empty on every card of a note type (a personal notes field, for example), your text in that field stays even when the field isn't listed.
3. **Protected tags.** Start typing a tag you already use, then click it in the list, or press Enter to add the highlighted one. An update never removes a protected tag from your notes. Protecting `#edited` also protects its sub-tags, such as `#edited::images`. A protected tag can also keep extra fields on the cards that have it (see below).
4. **Update card templates and styling.** On: an update can replace how your cards look. Off: your existing templates and styling are left as they are. A brand-new card type added by an update still arrives.
5. **Import learning progress** (off unless you turn it on). On: cards that are new to your collection arrive with the scheduling and review history stored in the file. Cards you already have always keep your own progress. Off: new cards arrive as new.
6. **Import deck options** (off unless you turn it on). Deck options are the settings behind a deck's gear icon: daily limits, learning steps, FSRS settings. Anki saves each set of them as a "preset". On: presets in the file that you don't have yet are added, and the decks in the file switch to the preset the file gives them (a deck the file puts on "Default" keeps yours). Presets you already have are never changed. Off: no presets are imported and no deck changes its preset.
7. Press **Save**. Your choices are used for every import until you change them.

## Keep extra fields on cards with a tag

Sometimes you want to keep more on some cards than on others. Each protected tag has its own **+ Add field**: the fields you add there are kept on every card that has the tag, on top of the fields you keep everywhere.

Example: Personal Notes is set to **Keep mine**, and everything else to **Take the update's**. You tag the cards you rewrote with `#edited`, protect `#edited`, and add **Text** and **Extra** to it. When you update:

- cards tagged `#edited` keep your Text, Extra and Personal Notes, and get the update's Header, Textbook, Citation and tags (`#edited` stays);
- every other card keeps only your Personal Notes.

Good to know:

- Sub-tags count: a card tagged `#edited::images` follows the rule of `#edited`.
- What counts is the tags a card has before the update.
- A card with several protected tags keeps the fields of all of them.
- Choose **Every field** in a tag's list to keep everything you have on those cards. A field the update adds that the card didn't have yet still arrives.
- A tag with no fields added ("Tag only") just keeps the tag, as before.
- Remove a field, or the whole tag, with its **✕**.

## Update a deck

If you've studied on a phone or another computer, sync this computer first.

1. Open the new `.apkg` the way you always do: double-click it, drag it onto Anki, or use **File → Import**.
2. Anki asks: **Would you like to update with Special Fields by Ankoma?** Your saved choices are listed.
   - **Import with my choices** runs the update.
   - **Change choices…** opens the settings, then returns to the question.
   - **Use Anki's standard import** imports the file as if the add-on were not installed.
3. When the update finishes, a summary shows what changed.
4. Sync as usual so your other devices get the update.

The question appears for every `.apkg` you open, including decks that are new to you. Choosing "Import with my choices" on a brand-new deck simply imports it.

## What an update does

- **Fields set to "Take the update's"** get the new content. Fields set to **Keep mine** keep what you had, and so do the fields you added to a protected tag, on the cards that have that tag.
- **Fields that aren't in your list** take the update's content. If the update has nothing at all for a field, such as one you added to the note type yourself, yours is left alone. To be certain a field of yours is kept, add it to the list as **Keep mine**.
- **Tags** on an updated note are replaced with the update's tags. The only tags that stay are the ones you protected. If you want to keep a tag of your own, protect it before you update.
- **Your review history** is never changed. With **Import learning progress** on, cards that are new to your collection also bring the history stored in the file; the history of cards you already have stays exactly as it was.
- **Cards you moved** to another deck stay where you put them. New notes go to the deck named in the update.
- Every note in the file is updated, including notes you have edited. Anki's standard import skips those by default.

## Moving to another computer without syncing

You can carry your progress to a new computer with a file instead of AnkiWeb: on the old computer, export the deck with **Include scheduling information** (and **Include deck presets** if you want those) ticked. On the new computer, turn on **Import learning progress** (and **Import deck presets**), then open the file and choose **Import with my choices**.

This brings your progress only for cards the new computer doesn't have yet. If the new computer already has some of the cards, those keep the progress they have there; the file's progress for them is not used. To copy everything exactly, including progress for cards both computers have, use AnkiWeb sync or **File → Export** of the whole collection (a `.colpkg`) instead.

## Undo and backups

Before each update, the add-on asks Anki to save one of its normal backups (restore one from **File → Switch Profile → Open Backup**).

The whole update is one step. **Edit → Undo Special Fields update** (or the **Undo update** button on the summary) puts everything back as it was.

## If the summary mentions a full sync

When an update changes a note type (for example, it adds a field), Anki needs a one-way full sync the next time you sync. Choose **Upload to AnkiWeb** so the updated copy on this computer is the one that's kept.

Uploading replaces what's on AnkiWeb. If you studied on another device and hadn't synced this computer before updating, undo the update, sync, and import again, or those reviews will be lost.

## Good to know

- If an update moves notes to a different note type, the add-on follows the move and still keeps the fields you chose to keep. In the rare case it can't do that safely, nothing is imported and a message says so.
- A cloze note can't be turned into a non-cloze note (or the reverse) by an update. Anki refuses that, and nothing is imported.
- If you added a field of your own to a note type, Anki's standard import won't update that note type's notes. "Import with my choices" will.
- If you keep your own Text on a cloze note and the update adds a new cloze number to it, Anki creates a card with nothing to show. Remove it with **Tools → Empty Cards**.
- When an update removes a cloze from a note you already have, Anki keeps the old card as an empty card. The add-on leaves these alone; you can clear them with **Tools → Empty Cards**.
- Deck option presets stored inside an `.apkg` are imported only when **Import deck options** is on. Undo puts your decks back on the presets they used before.
- Notes that a new release removed are not deleted from your collection.
- Review history stored inside an `.apkg` is imported only when **Import learning progress** is on, and only for cards that are new to your collection.
- Settings are saved on this computer and are not synced to your other computers.

## Help

Questions and bug reports: [https://github.com/machpath/special-fields-by-ankoma/issues](https://github.com/machpath/special-fields-by-ankoma/issues)
