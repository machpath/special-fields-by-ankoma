# AnkiWeb listing text

DRAFT for the deck author to review and paste into the AnkiWeb upload form. Nothing has been uploaded.

**Title:** Special Fields by Ankoma

**Supported Anki versions (upload form):** minimum 25.02. Set the maximum to the newest version the test matrix has passed on.

**Tags (upload form):** import, update, deck, fields, tags

---

## Description

**Update a shared deck without losing your own notes.**

When a deck author releases a new version, Anki's standard import makes you choose: skip every card you've edited, or overwrite your edits. Special Fields by Ankoma gives you both the author's updates and the parts you want to keep.

Built for the [Ankoma](https://ankomapath.com) pathology deck. Works with any deck that ships as an .apkg file.

### How it works

1. Open **Tools → Special Fields by Ankoma** once and choose what to protect.
2. Import the new .apkg the way you always do.
3. Answer one question: **Import with my choices**, or use Anki's standard import.

### What you can protect

- **Fields.** For each field, choose "Keep mine" or "Take the update's". By default only Personal Notes is kept. Add any field from your own note types.
- **Tags.** Updates replace a note's tags with the author's. Protect the tags you want to keep and an update will never remove them.
- **Card templates and styling.** Choose whether updates can change how your existing cards look.

### Always kept

- Your review history.
- The decks you moved cards into.

### Also

- Every note in the file is updated, including ones you've edited (Anki's standard import skips those by default).
- One undo step reverses the whole update.
- A summary after each update shows what changed.

### Requirements

Anki 25.02 or newer on Windows, Mac or Linux. Phones and tablets receive the result through sync.

### Notes

- The question appears each time you open an .apkg file. Choose "Use Anki's standard import" to import as if the add-on weren't installed.
- Notes removed in a new release are not deleted from your collection.
- Sync this computer before updating if you've studied on another device. If an update changes a note type, Anki will ask for a one-way full sync; choose "Upload to AnkiWeb".
- If a file uses different note types than the same notes in your collection, nothing is imported and a message explains why.

### Support

Questions and bug reports: [https://github.com/machpath/special-fields-by-ankoma/issues](https://github.com/machpath/special-fields-by-ankoma/issues)
