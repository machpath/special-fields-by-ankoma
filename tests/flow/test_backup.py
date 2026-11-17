"""A backup is requested from Anki before "Import with my choices" changes anything."""

import os

from special_fields_by_ankoma import import_flow
from special_fields_by_ankoma.config import default_settings


class _PM:
    def __init__(self, folder):
        self._folder = folder

    def backupFolder(self):
        os.makedirs(self._folder, exist_ok=True)
        return self._folder


def _backups(folder):
    return sorted(f for f in os.listdir(folder) if f.endswith(".colpkg")) if os.path.isdir(folder) else []


def test_backup_folder_lookup(tmp_path):
    class MW:
        pass

    mw = MW()
    assert import_flow._backup_folder(mw) is None  # no profile manager: no backup, no error
    mw.pm = _PM(str(tmp_path / "backups"))
    assert import_flow._backup_folder(mw) == str(tmp_path / "backups")


def test_backup_is_written_and_keeps_undo(make_col, tmp_path):
    col = make_col("user")
    note = col.new_note(col.models.by_name("Basic"))
    note["Front"] = "f"
    col.add_note(note, 1)
    undo_before = col.undo_status().undo
    assert undo_before
    folder = str(tmp_path / "backups")
    os.makedirs(folder)
    assert import_flow.backup_before_import(col, folder) is True
    assert len(_backups(folder)) == 1
    # the user's own last step can still be undone afterwards
    assert col.undo_status().undo == undo_before


def test_backup_failure_never_blocks(make_col, tmp_path):
    col = make_col("user")
    assert import_flow.backup_before_import(col, None) is False
    # a path that is a file, not a folder: Anki raises, we carry on
    bad = tmp_path / "not-a-folder"
    bad.write_text("x")
    assert import_flow.backup_before_import(col, str(bad)) is False


def test_import_with_choices_backs_up_first(fake_mw, apkg, tmp_path, monkeypatch):
    folder = str(tmp_path / "backups")
    fake_mw.pm = _PM(folder)
    order = []
    from special_fields_by_ankoma import engine

    real_backup = import_flow.backup_before_import
    real_run = engine.run_import

    def spy_backup(col, f):
        order.append(("backup", f))
        return real_backup(col, f)

    def spy_run(col, path, settings):
        order.append(("import", path))
        return real_run(col, path, settings)

    monkeypatch.setattr(import_flow, "backup_before_import", spy_backup)
    monkeypatch.setattr(engine, "run_import", spy_run)
    monkeypatch.setattr(import_flow, "show_summary", lambda *a, **k: None)
    import_flow.run_import_with_choices(fake_mw, apkg, default_settings())
    from aqt.qt import QApplication

    for _ in range(50):
        QApplication.processEvents()
        if len(order) == 2:
            break
    assert [o[0] for o in order] == ["backup", "import"]
    assert order[0][1] == folder
