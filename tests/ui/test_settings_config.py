"""load_settings / save_settings / open_settings with a small fake `mw`,
and choices_summary rows."""

from __future__ import annotations

import importlib
import shutil
import sys
from types import SimpleNamespace

import pytest

from special_fields_by_ankoma import settings_dialog as sd
from special_fields_by_ankoma.config import default_config, default_settings
from special_fields_by_ankoma.model import FieldChoice, Settings

PKG = "special_fields_by_ankoma"


class FakeAddonManager:
    def __init__(self, configs=None):
        self.configs = dict(configs or {})
        self.read_keys = []
        self.writes = []

    def getConfig(self, key):  # noqa: N802 (Anki API)
        self.read_keys.append(key)
        cfg = self.configs.get(key)
        return None if cfg is None else dict(cfg)

    def writeConfig(self, key, cfg):  # noqa: N802
        self.writes.append((key, cfg))
        self.configs[key] = cfg


class FakeModels:
    def __init__(self, notetypes):
        self._nts = notetypes  # {id: {"name":..., "flds":[{"name":...}]}}

    def all_names_and_ids(self):
        return [SimpleNamespace(id=i, name=nt["name"]) for i, nt in self._nts.items()]

    def get(self, ntid):
        return self._nts.get(ntid)


class FakeTags:
    def __init__(self, tags):
        self._tags = tags

    def all(self):
        return list(self._tags)


def fake_mw(config=None, key=PKG, col=None):
    am = FakeAddonManager({key: config} if config is not None else {})
    return SimpleNamespace(addonManager=am, col=col)


CUSTOM = Settings(
    fields=(FieldChoice("Text", True), FieldChoice("Remarks", False), FieldChoice("Personal Notes", True)),
    protected_tags=("#edited", "board-review::missed"),
    update_note_types=False,
    import_scheduling=True,
)


def test_addon_key_is_top_level_package():
    assert sd._addon_key() == PKG


def test_load_defaults_when_no_config():
    mw = fake_mw()
    assert sd.load_settings(mw) == default_settings()
    assert mw.addonManager.read_keys == [PKG]


def test_load_from_config_json_defaults():
    mw = fake_mw(default_config())
    assert sd.load_settings(mw) == default_settings()


def test_load_tolerates_junk():
    mw = fake_mw({"fields": "nonsense", "protected_tags": [1, "", "#a", "#A"], "update_note_types": "x"})
    s = sd.load_settings(mw)
    assert s.fields == default_settings().fields
    assert s.protected_tags == ("#a",)
    assert s.update_note_types is True


def test_save_then_load_round_trip():
    mw = fake_mw(default_config())
    sd.save_settings(mw, CUSTOM)
    key, written = mw.addonManager.writes[-1]
    assert key == PKG
    assert written["fields"] == [
        {"name": "Text", "keep": True},
        {"name": "Remarks", "keep": False},
        {"name": "Personal Notes", "keep": True},
    ]
    assert written["protected_tags"] == ["#edited", "board-review::missed"]
    assert written["update_note_types"] is False
    assert written["import_scheduling"] is True
    assert written["import_deck_presets"] is False
    assert sd.load_settings(mw) == CUSTOM


def test_import_switches_round_trip_and_old_config():
    for sched, presets in ((True, True), (False, True), (True, False), (False, False)):
        mw = fake_mw(default_config())
        s = Settings(fields=(), import_scheduling=sched, import_deck_presets=presets)
        sd.save_settings(mw, s)
        assert sd.load_settings(mw) == s
    # A config saved by an earlier beta has neither key: both off.
    old = default_config()
    del old["import_scheduling"], old["import_deck_presets"]
    loaded = sd.load_settings(fake_mw(old))
    assert loaded.import_scheduling is False and loaded.import_deck_presets is False
    assert loaded == default_settings()


def test_save_keeps_unknown_keys():
    cfg = default_config()
    cfg["something_else"] = 42
    mw = fake_mw(cfg)
    sd.save_settings(mw, CUSTOM)
    assert mw.addonManager.configs[PKG]["something_else"] == 42


def test_config_key_follows_renamed_folder(tmp_path, monkeypatch):
    """AnkiWeb installs the add-on in a folder named by number."""
    src = sys.modules[PKG].__path__[0]
    renamed = "1234567890"
    shutil.copytree(src, tmp_path / renamed, ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        mod = importlib.import_module(renamed + ".settings_dialog")
        assert mod._addon_key() == renamed
        mw = fake_mw({"fields": [{"name": "Text", "keep": True}]}, key=renamed)
        assert mod.load_settings(mw).keeps_field("text")
        mod.save_settings(mw, default_settings())
        assert mw.addonManager.writes[-1][0] == renamed
    finally:
        for name in [m for m in sys.modules if m == renamed or m.startswith(renamed + ".")]:
            del sys.modules[name]


# --------------------------------------------------------------------------
# choices_summary


def test_choices_summary_defaults():
    assert sd.choices_summary(default_settings()) == [
        ("Fields you keep", "Personal Notes"),
        ("Protected tags", "None"),
        ("Tags", "Replaced with the update's"),
        ("Card styling", "Update"),
        ("Learning progress", "Not imported"),
        ("Deck options", "Not imported"),
    ]


def test_choices_summary_custom():
    assert sd.choices_summary(CUSTOM) == [
        ("Fields you keep", "Text, Personal Notes"),
        ("Protected tags", "#edited, board-review::missed"),
        ("Tags", "Replaced with the update's"),
        ("Card styling", "Keep mine"),
        ("Learning progress", "Imported for new cards"),
        ("Deck options", "Not imported"),
    ]


def test_choices_summary_deck_presets_on():
    s = Settings(fields=(), import_deck_presets=True)
    assert sd.choices_summary(s)[-2:] == [
        ("Learning progress", "Not imported"),
        ("Deck options", "Imported"),
    ]


def test_choices_summary_nothing_kept():
    s = Settings(fields=(FieldChoice("Text", False),), protected_tags=(), update_note_types=True)
    assert sd.choices_summary(s)[0] == ("Fields you keep", "None")


# --------------------------------------------------------------------------
# open_settings with a fake collection


def fake_col():
    models = FakeModels({
        1: {"name": "Cloze-Ankoma-AP", "flds": [{"name": n} for n in
            ("Header", "Text", "Extra", "Personal Notes", "Textbook", "Citation")]},
        2: {"name": "Image Occlusion Enhanced", "flds": [{"name": n} for n in
            ("ID (hidden)", "Header", "Image", "Remarks", "Sources")]},
        3: {"name": "Basic", "flds": [{"name": "Front"}, {"name": "back"}, {"name": "REMARKS"}]},
    })
    return SimpleNamespace(models=models, tags=FakeTags(["#edited", "weak-areas"]))


def test_collection_field_names_dedupes():
    names = sd._collection_field_names(fake_col())
    assert names == ["Header", "Text", "Extra", "Personal Notes", "Textbook", "Citation",
                     "ID (hidden)", "Image", "Remarks", "Sources", "Front", "back"]


def test_open_settings_save(qapp, monkeypatch):
    seen = {}

    def fake_exec(self):
        seen["fields"] = list(self._all_fields)
        seen["tags"] = list(self._all_tags)
        assert self.add_field("Remarks")
        assert self.add_tag("#edited")
        self.row_for("Text").toggle.set_keep(True)
        self.accept()
        return self.result()

    monkeypatch.setattr(sd.SettingsDialog, "exec", fake_exec)
    mw = fake_mw(default_config(), col=fake_col())
    got = sd.open_settings(mw)
    assert seen["tags"] == ["#edited", "weak-areas"]
    assert "Remarks" in seen["fields"] and "Front" in seen["fields"]
    assert got is not None
    assert got.keeps_field("Text") and got.protected_tags == ("#edited",)
    assert [f.name for f in got.fields][-1] == "Remarks"
    assert mw.addonManager.writes and sd.load_settings(mw) == got


def test_open_settings_cancel(qapp, monkeypatch):
    def fake_exec(self):
        self.row_for("Text").toggle.set_keep(True)
        self.reject()
        return self.result()

    monkeypatch.setattr(sd.SettingsDialog, "exec", fake_exec)
    mw = fake_mw(default_config(), col=fake_col())
    assert sd.open_settings(mw) is None
    assert mw.addonManager.writes == []


def test_open_settings_without_collection(qapp, monkeypatch):
    def fake_exec(self):
        assert self._all_fields == [] and self._all_tags == []
        self.accept()
        return self.result()

    monkeypatch.setattr(sd.SettingsDialog, "exec", fake_exec)
    mw = fake_mw(None, col=None)
    assert sd.open_settings(mw) == default_settings()
