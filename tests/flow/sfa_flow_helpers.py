"""Shared helpers for the import-flow tests (workstream E).

A uniquely named module (not `conftest`), so `pytest tests/flow tests/ui`
and `pytest tests` never pick up another folder's conftest by mistake.
Import it as `sfa_flow_helpers`; tests/flow/conftest.py puts this folder on
sys.path.

What is FAKED here (and therefore not proven by these tests):

* `FakeMW` stands in for Anki's main window `aqt.main.AnkiQt`. It is a real
  QMainWindow (so dialogs get a real parent) with only the attributes the
  flow and aqt's `CollectionOp` / undo touch:
    - `col`: a REAL `anki.collection.Collection` in a temp folder;
    - `addonManager`: getConfig / writeConfig on an in-memory dict;
    - `form.menuTools`: a real QMenu;
    - `taskman.with_backend_progress` / `with_progress`: runs the task on a
      real background thread (ThreadPoolExecutor), waits for it, then calls
      `on_done(future)` on the main thread. Anki's real progress window,
      its 100 ms delay and the backend progress polling are NOT exercised;
      the progress callback is only recorded;
    - `progress.single_shot` / `timer`: plain QTimers; `start` / `finish`:
      no-ops;
    - `taskman.run_in_background` (used by the legacy importer): same
      synchronous background-thread runner as above; `reset()`: a counter;
    - `_increase_background_ops` / `_decrease_background_ops` /
      `update_undo_actions`: counters.
  aqt's own `CollectionOp`, `on_op_finished`, `aqt.operations.collection.undo`
  and `gui_hooks` run for real against that fake.
* Anki's UI language is set with `anki.lang.set_lang("en_US")` instead of by
  loading a profile.
* `aqt.mw` is pointed at the fake for the duration of a test (aqt's
  `CollectionOp.run_in_background` and `tooltip` read it).
"""

from __future__ import annotations

import concurrent.futures
import os
import types
from typing import Any, Callable, Dict, List, Optional

from aqt.qt import QApplication, QMainWindow, QMenu, QTimer, QWidget

SCRATCH = "/tmp/sfa-e"


class FakeTaskman:
    def __init__(self) -> None:
        self.progress_updates: List[Any] = []
        self.parents: List[Any] = []
        self._pool = concurrent.futures.ThreadPoolExecutor(max_workers=1)

    def _run(self, task: Callable[[], Any], on_done: Optional[Callable[[Any], None]]) -> None:
        fut = self._pool.submit(task)
        concurrent.futures.wait([fut])
        if on_done is not None:
            on_done(fut)

    def with_backend_progress(self, task, progress_update, on_done=None, parent=None, **_kw) -> None:
        self.progress_updates.append(progress_update)
        self.parents.append(parent)
        self._run(task, on_done)

    def with_progress(self, task, on_done=None, parent=None, **_kw) -> None:
        self.parents.append(parent)
        self._run(task, on_done)

    def run_in_background(self, task, on_done=None, *args, **_kw) -> None:
        # used by Anki's legacy importer (aqt/importing.py)
        self._run(task, on_done)


class FakeProgress:
    def __init__(self) -> None:
        self._timers: List[QTimer] = []

    def single_shot(self, ms: int, func: Callable[[], None], requires_collection: bool = True) -> None:
        QTimer.singleShot(ms, func)

    def timer(self, ms, func, repeat, requiresCollection=True, parent=None):
        t = QTimer(parent)
        t.setSingleShot(not repeat)
        t.timeout.connect(func)
        t.start(ms)
        self._timers.append(t)
        return t

    def start(self, *args, **kwargs) -> None:  # legacy importer
        pass

    def finish(self) -> None:
        pass


class FakeAddonManager:
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config
        self.writes: List[Any] = []

    def getConfig(self, key: str):  # noqa: N802 (Anki API)
        return self.config

    def writeConfig(self, key: str, cfg) -> None:  # noqa: N802
        self.writes.append((key, cfg))
        self.config = cfg


class FakeMW(QMainWindow):
    def __init__(self, col: Any = None, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__()
        self.col = col
        self.addonManager = FakeAddonManager(config)
        self.form = types.SimpleNamespace(menuTools=QMenu("Tools", self))
        self.taskman = FakeTaskman()
        self.progress = FakeProgress()
        self.app = QApplication.instance()
        self.background_ops = 0
        self.undo_action_updates = 0
        self.resets = 0

    def _increase_background_ops(self) -> None:
        self.background_ops += 1

    def _decrease_background_ops(self) -> None:
        self.background_ops -= 1

    def update_undo_actions(self) -> None:
        self.undo_action_updates += 1

    def reset(self) -> None:  # legacy importer calls mw.reset() when done
        self.resets += 1


def find_top_level(object_name: str) -> Optional[QWidget]:
    for w in QApplication.topLevelWidgets():
        if w.objectName() == object_name and w.isVisible():
            return w
    return None


def when_shown(object_name: str, action: Callable[[QWidget], None], timeout_ms: int = 5000) -> Dict[str, Any]:
    """Poll until a visible top-level widget named `object_name` exists (a
    modal dialog inside exec()), then run `action(widget)` once. Returns a
    dict whose "widget" key is set once the action ran."""
    state: Dict[str, Any] = {"widget": None, "tries": 0}

    def poll() -> None:
        w = find_top_level(object_name)
        if w is not None:
            state["widget"] = w
            action(w)
            return
        state["tries"] += 1
        if state["tries"] * 10 < timeout_ms:
            QTimer.singleShot(10, poll)

    QTimer.singleShot(0, poll)
    return state


def build_apkg(make_col, path: str, notes: int = 3, deck: str = "Flow Deck", legacy: bool = False) -> List[str]:
    """Export a tiny Basic deck to `path`; returns the note guids.
    legacy=True writes the older package format that Anki's legacy Python
    importer can read (it cannot read the default zstd format)."""
    from anki.collection import DeckIdLimit, ExportAnkiPackageOptions

    col = make_col("author-" + os.path.basename(path))
    did = col.decks.id(deck)
    nt = col.models.by_name("Basic")
    guids = []
    for i in range(notes):
        note = col.new_note(nt)
        note["Front"] = "front %d" % i
        note["Back"] = "back %d" % i
        note.tags = ["author::v1"]
        col.add_note(note, did)
        guids.append(note.guid)
    col.export_anki_package(
        out_path=path,
        options=ExportAnkiPackageOptions(
            with_scheduling=False, with_deck_configs=False, with_media=True, legacy=legacy
        ),
        limit=DeckIdLimit(did),
    )
    return guids
