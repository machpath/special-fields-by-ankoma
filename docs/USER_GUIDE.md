# Special Fields by Ankoma: user guide

DRAFT. Not yet checked against a real Anki install.

Special Fields by Ankoma lets you import an updated version of a deck without losing the parts you chose to protect. It was built for the Ankoma deck and works with any deck that ships as an `.apkg` file.

It runs in Anki on a computer (Windows, Mac or Linux), Anki 25.02 or newer. Phones and tablets get the result through sync.

## Set it up once

1. Open **Tools → Special Fields by Ankoma**.
2. **Fields.** For each field, pick **Keep mine** or **Take the update's**. Out of the box, only Personal Notes is kept. Use **+ Add field** to add any other field from your note types.
3. **Protected tags.** Start typing a tag you already use, pick it from the list, and press **Select**. An update never removes a protected tag from your notes. Protecting `#edited` also protects its sub-tags, such as `#edited::images`.
4. **Update card templates and styling.** On: an update can replace how your cards look. Off: your existing templates and styling are left as they are. A brand-new card type added by an update still arrives.
5. Press **Save**. Your choices are used for every import until you change them.

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

- **Fields set to "Take the update's"** get the new content. Fields set to **Keep mine** keep what you had.
- **Fields that aren't in your list** take the update's content. If the update has nothing at all for a field, such as one you added to the note type yourself, yours is left alone. To be certain a field of yours is kept, add it to the list as **Keep mine**.
- **Tags** on an updated note are replaced with the update's tags. The only tags that stay are the ones you protected. If you want to keep a tag of your own, protect it before you update.
- **Your review history** is never changed.
- **Cards you moved** to another deck stay where you put them. New notes go to the deck named in the update.
- Every note in the file is updated, including notes you have edited. Anki's standard import skips those by default.

## Undo

The whole update is one step. **Edit → Undo Special Fields update** (or the **Undo update** button on the summary) puts everything back as it was.

## If the summary mentions a full sync

When an update changes a note type (for example, it adds a field), Anki needs a one-way full sync the next time you sync. Choose **Upload to AnkiWeb** so the updated copy on this computer is the one that's kept.

Uploading replaces what's on AnkiWeb. If you studied on another device and hadn't synced this computer before updating, undo the update, sync, and import again, or those reviews will be lost.

## Good to know

- If the file uses different note types than the same notes in your collection (for example, you changed a note's type), nothing is imported and a message explains why. Use Anki's standard import for that file.
- If you keep your own Text on a cloze note and the update adds a new cloze number to it, Anki creates a card with nothing to show. Remove it with **Tools → Empty Cards**.
- Deck option presets stored inside an `.apkg` are not imported by "Import with my choices".
- Notes that a new release removed are not deleted from your collection.
- Review history stored inside an `.apkg` is not imported by "Import with my choices". Use Anki's standard import for that.
- Settings are saved on this computer and are not synced to your other computers.

## Help

Questions and bug reports: [https://github.com/machpath/special-fields-by-ankoma/issues](https://github.com/machpath/special-fields-by-ankoma/issues)
