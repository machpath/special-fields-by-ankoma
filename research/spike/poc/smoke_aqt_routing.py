"""Verify import_file() routes Ankoma .apkg files to our wrapper and others to stock.
usage: QT_QPA_PLATFORM=offscreen python smoke_aqt_routing.py ADDON_PARENT_DIR"""
import json, os, sys, types
from aqt.qt import QApplication, QMenu
app = QApplication([])
import aqt
cfg = json.load(open(os.path.join(sys.argv[1], "ankoma_special_fields", "config.json")))
from aqt.qt import QObject
stub = QObject()
stub.addonManager = types.SimpleNamespace(getConfig=lambda n: cfg)
stub.form = types.SimpleNamespace(menuTools=QMenu())
import tempfile
from anki.collection import Collection
stub.col = Collection(os.path.join(tempfile.mkdtemp(), "c.anki2"))  # 25.02 import_file reads mw.col
aqt.mw = stub
sys.path.insert(0, sys.argv[1])
import aqt.utils
import ankoma_special_fields as addon
calls = []
addon.run_ankoma_import = lambda p: calls.append(("ankoma", p))
addon.askUser = lambda *a, **k: True
from aqt.import_export import importing
importing.askUser = lambda *a, **k: calls.append(("colpkg-confirm", None)) and False
importing.tr = types.SimpleNamespace(importing_this_will_delete_your_existing_collection=lambda: "")
importing.ImportDialog = lambda mw, args: calls.append(("stock", args.path))
importing.import_file(stub, "/x/Ankoma-v1.3.apkg")
importing.import_file(stub, "/x/Some other deck.apkg")
importing.import_file(stub, "/x/collection.apkg")  # ColpkgImporter claims this first
print(calls, "menu actions:", [a.text() for a in stub.form.menuTools.actions()])
assert [c[0] for c in calls] == ["ankoma", "stock", "colpkg-confirm"], calls
print("ROUTING OK")
