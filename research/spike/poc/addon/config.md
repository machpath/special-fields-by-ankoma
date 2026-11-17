**protected_fields**: field names whose *local* value is kept on update (applies to every note type that has a field with that name). Candidates: Header, Text, Images, Extra, Personal Notes, Textbook, Citation, ID (hidden), Image, Question Mask, Footer, Remarks, Sources, Extra 1, Extra 2, Answer Mask, Original Mask.

**tag_mode**: `overwrite` (author's tags replace yours), `preserve` (keep your tags), `merge` (author's `##ANKOMA-v*` tags + your other tags).

**update_notetypes**: `true` = take the author's templates and styling (your CSS edits are lost).

**merge_notetypes**: keep `true`; needed when the author adds fields. A schema change forces a one-way full sync.
