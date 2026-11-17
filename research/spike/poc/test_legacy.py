"""Legacy package variants: export with legacy=True (collection.anki21, schema 11) and import with our strategy."""
import os, sys, shutil, zipfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from anki.collection import Collection, ExportAnkiPackageOptions, DeckIdLimit
import ankoma_core as core
work = sys.argv[1]; src = os.path.join(work, "author.anki2")
tmp = os.path.join(work, "legacy"); shutil.rmtree(tmp, ignore_errors=True); os.makedirs(tmp)
shutil.copy(src, os.path.join(tmp, "a.anki2"))
a = Collection(os.path.join(tmp, "a.anki2"))
p = os.path.join(tmp, "Ankoma-legacy.apkg")
a.export_anki_package(out_path=p, options=ExportAnkiPackageOptions(with_media=False, legacy=True), limit=DeckIdLimit(a.decks.id("Ankoma")))
a.close()
print("legacy zip members:", zipfile.ZipFile(p).namelist()[:3])
shutil.copy(os.path.join(work, "user.anki2"), os.path.join(tmp, "u.anki2"))
u = Collection(os.path.join(tmp, "u.anki2"))
r = core.import_ankoma_package(u, p, core.Settings(protected_fields={"Personal Notes"}))
print("legacy import:", r.found, "found", r.updated, "updated", r.restored_fields, "restored", r.conflicting, "conflicting")
n = u.get_note(sorted(u.find_notes('"note:Ankoma Cloze"'))[3]); print(" sample:", n["Personal Notes"][:20], "|", n["Text"][:25])
assert r.updated > 0 and n["Personal Notes"].startswith("MY NOTE")
print("LEGACY OK")
