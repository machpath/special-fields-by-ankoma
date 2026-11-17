"""Shared fixtures for the acceptance tests (workstream D).

Run (inside one Anki environment):
    PYTHONPATH=<project>/src python -m pytest tests/acceptance
Full-size run (check 13), only on request:
    PYTHONPATH=<project>/src python -m pytest tests/acceptance -m slow
    (or set SFA_RUN_SLOW=1)

Fixtures are built once per Anki version and Python line under
/tmp/sfa-d/fixtures/ by tools/build_fixtures.py and reused while the builder
is unchanged. Set SFA_FIXTURE_ROOT to build them somewhere else.
"""

from __future__ import annotations

import os
import sys
from typing import Any, Callable, Dict

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "tools"))
sys.path.insert(0, HERE)

import build_fixtures  # noqa: E402
import sfa_acc_helpers as H  # noqa: E402


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: full-size run (check 13); only on request")


def pytest_collection_modifyitems(config, items):
    markexpr = config.getoption("-m") or ""
    if "slow" in markexpr or os.environ.get("SFA_RUN_SLOW") == "1":
        return
    skip = pytest.mark.skip(reason="full-size run: select with -m slow or SFA_RUN_SLOW=1")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip)


def _fixture_dir(size: str) -> str:
    root = os.environ.get("SFA_FIXTURE_ROOT")
    if not root:
        return build_fixtures.default_out_dir(size)
    return os.path.join(root, "%s-py%d.%d" % (build_fixtures.anki_version(),
                                              sys.version_info[0], sys.version_info[1]), size)


class Fixtures:
    """The built fixture set plus cached, read-only snapshots of it."""

    def __init__(self, manifest: Dict[str, Any], scratch: str) -> None:
        self.m = manifest
        self.scratch = scratch
        self._ref: Dict[str, Dict[str, H.NoteSnap]] = {}
        self._ref_looks: Dict[str, Dict[str, Any]] = {}
        self._ref_decks: Dict[str, Dict[Any, str]] = {}
        self._before = None
        self._before_looks = None
        self._before_cards = None
        self._before_revlog = None
        self._before_decks = None

    def package(self, key: str) -> str:
        return self.m["packages"][key]

    def _load_ref(self, key: str) -> None:
        dst = H.copy_collection(self.m["references"][key],
                                os.path.join(self.scratch, "ref-" + key), "ref")
        col = H.open_collection(dst)
        try:
            self._ref[key] = H.notes_by_guid(col)
            self._ref_looks[key] = H.notetype_looks(col)
            self._ref_decks[key] = H.card_decks_by_note_ord(col)
        finally:
            col.close()

    def update(self, key: str) -> Dict[str, H.NoteSnap]:
        """The update's notes (guid -> NoteSnap) for package `key`."""
        if key not in self._ref:
            self._load_ref(key)
        return self._ref[key]

    def update_looks(self, key: str) -> Dict[str, Any]:
        if key not in self._ref_looks:
            self._load_ref(key)
        return self._ref_looks[key]

    def update_card_decks(self, key: str) -> Dict[Any, str]:
        if key not in self._ref_decks:
            self._load_ref(key)
        return self._ref_decks[key]

    def _load_before(self) -> None:
        dst = H.copy_collection(self.m["user_collection"], os.path.join(self.scratch, "before"))
        col = H.open_collection(dst)
        try:
            self._before = H.notes_by_guid(col)
            self._before_looks = H.notetype_looks(col)
            self._before_cards = H.card_rows(col)
            self._before_revlog = H.revlog_rows(col)
            self._before_decks = H.card_decks_by_note_ord(col)
        finally:
            col.close()

    @property
    def before(self) -> Dict[str, H.NoteSnap]:
        if self._before is None:
            self._load_before()
        return self._before

    @property
    def before_looks(self):
        if self._before is None:
            self._load_before()
        return self._before_looks

    @property
    def before_cards(self):
        if self._before is None:
            self._load_before()
        return self._before_cards

    @property
    def before_revlog(self):
        if self._before is None:
            self._load_before()
        return self._before_revlog

    def before_by_nid(self) -> Dict[int, H.NoteSnap]:
        return {s.nid: s for s in self.before.values()}


@pytest.fixture(scope="session")
def fx(tmp_path_factory) -> Fixtures:
    manifest = build_fixtures.ensure(_fixture_dir("small"), "small", verbose=False)
    return Fixtures(manifest, str(tmp_path_factory.mktemp("sfa-fixture-cache")))


@pytest.fixture
def user_col(fx, tmp_path):
    """A fresh copy of the simulated user's collection, opened."""
    path = H.copy_collection(fx.m["user_collection"], str(tmp_path / "col"))
    col = H.open_collection(path)
    yield col
    col.close()


@pytest.fixture
def empty_col(tmp_path):
    os.makedirs(str(tmp_path / "empty"), exist_ok=True)
    col = H.open_collection(str(tmp_path / "empty" / "empty.anki2"))
    yield col
    col.close()


@pytest.fixture(scope="session")
def run_import() -> Callable:
    """special_fields_by_ankoma.engine.run_import, or a clear failure."""
    try:
        from special_fields_by_ankoma.engine import run_import as fn
    except ImportError as e:  # engine not written yet / not on PYTHONPATH
        pytest.fail("cannot import special_fields_by_ankoma.engine.run_import (%s); "
                    "is engine.py present and src/ on PYTHONPATH?" % e, pytrace=False)
    return fn
