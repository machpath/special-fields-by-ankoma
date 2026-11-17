"""Load the add-on the way Anki does and check the routing (run in a fresh
interpreter by test_smoke.py; modelled on research/spike/poc/smoke_aqt_routing.py).

    QT_QPA_PLATFORM=offscreen python smoke_addon_load.py SRC_DIR SCRATCH_DIR

Anki imports the add-on package after the main window exists. Here
`aqt.mw` is a FakeMW (see sfa_flow_helpers.py) with a real collection, then the
package is imported for the first time: its `__init__` must import
`import_flow`, which must wrap ApkgImporter.do_import and add the Tools
menu item. Then `import_file` is called for several file names, with the
question answered automatically.
"""

from __future__ import annotations

import os
import sys

src, scratch = sys.argv[1], sys.argv[2]
sys.path.insert(0, src)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from aqt.qt import QApplication, QTimer  # noqa: E402

app = QApplication([])
import anki.lang  # noqa: E402

anki.lang.set_lang("en_US")
import aqt  # noqa: E402
from anki.collection import Collection  # noqa: E402

from sfa_flow_helpers import FakeMW, find_top_level  # noqa: E402

os.makedirs(scratch, exist_ok=True)
mw = FakeMW(Collection(os.path.join(scratch, "smoke.anki2")))
aqt.mw = mw

from aqt.import_export import importing  # noqa: E402

try:
    import aqt.importing as legacy  # Anki 25.02-26.08 only
except ImportError:
    legacy = None
stock_legacy = legacy.importFile if legacy is not None else None
stock = importing.ApkgImporter.do_import
assert "special_fields_by_ankoma" not in sys.modules
import special_fields_by_ankoma  # noqa: E402,F401  (as Anki loads an add-on)

flow = sys.modules["special_fields_by_ankoma.import_flow"]
wrapped = importing.ApkgImporter.do_import
assert wrapped is not stock and wrapped._sfa_original is stock, "not wrapped"
if legacy is not None:
    assert legacy.importFile._sfa_original is stock_legacy, "legacy importFile not wrapped"
menu = [a.text() for a in mw.form.menuTools.actions()]
assert menu == ["Special Fields by Ankoma"], menu

calls = []
importing.ImportDialog = lambda mw_, args: calls.append(("stock", os.path.basename(args.path)))
importing.askUser = lambda *a, **k: calls.append(("colpkg-confirm", None)) and False
flow.run_import_with_choices = lambda mw_, path, s: calls.append(("special", os.path.basename(path)))

answers = []


def answer_next() -> None:
    dlg = find_top_level("special_fields_question")
    if dlg is None:
        QTimer.singleShot(5, answer_next)
        return
    calls.append(("asked", dlg.file_name))
    getattr(dlg, answers.pop(0)).click()


def route(path: str, answer: str = "") -> None:
    if answer:
        answers.append(answer)
        QTimer.singleShot(0, answer_next)
    importing.import_file(mw, path)


route("/x/Ankoma-v1.3.apkg", "import_button")
route("/x/Some other deck.apkg", "standard_button")
route("/x/updated 2026.apkg", "import_button")
route("/x/collection.apkg")  # ColpkgImporter claims this first: no question
expected_legacy = []
if legacy is not None:
    # The legacy route (File > Import / drag-and-drop with the legacy
    # preference) also asks. "Standard" hands over to the original legacy
    # function, which is spied on here instead of being run.
    orig_handle = flow.handle_apkg

    def spy(original, args, kwargs, path_kw="path"):
        stock_spy = lambda *a, **k: calls.append(("legacy-stock", os.path.basename(a[1])))  # noqa: E731
        orig_handle(stock_spy, args, kwargs, path_kw)

    flow.handle_apkg = spy
    route_legacy = legacy.importFile
    answers.append("standard_button")
    QTimer.singleShot(0, answer_next)
    route_legacy(mw, "/x/legacy route.apkg")
    flow.handle_apkg = orig_handle
    expected_legacy = [("asked", "legacy route.apkg"), ("legacy-stock", "legacy route.apkg")]
print(calls)
assert calls[7:] == expected_legacy, calls
calls = calls[:7]
assert calls == [
    ("asked", "Ankoma-v1.3.apkg"), ("special", "Ankoma-v1.3.apkg"),
    ("asked", "Some other deck.apkg"), ("stock", "Some other deck.apkg"),
    ("asked", "updated 2026.apkg"), ("special", "updated 2026.apkg"),
    ("colpkg-confirm", None),
], calls
mw.col.close()
print("ADDON LOAD + ROUTING OK", "(legacy route checked)" if legacy is not None else "(no legacy importer on this Anki)")
