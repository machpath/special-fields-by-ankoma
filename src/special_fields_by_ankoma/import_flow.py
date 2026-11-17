"""Import flow for Special Fields by Ankoma (workstream E).

Anki imports this module only when its main window exists (see
`__init__.py`). On import it:

* wraps `aqt.import_export.importing.ApkgImporter.do_import`, which every
  .apkg route reaches (File > Import, drag-and-drop, double-click / open
  with), so that EVERY .apkg first shows the question dialog;
* where the legacy importer still exists (Anki 25.02 to 26.08), also wraps
  `aqt.importing.importFile` for .apkg files, so no legacy route skips the
  question either (see `install_legacy_wrapper`);
* adds Tools > "Special Fields by Ankoma", which opens the settings window.

Nothing here raises at import time: if wrapping fails on some Anki version,
Anki's importer is left untouched and the error is only printed.

The two dialogs take plain data and expose the user's choice, so they can be
built and driven offscreen without a running Anki. Only the functions in the
"Anki glue" section touch `mw`.

Widgets carry objectNames:

    QuestionDialog (special_fields_question)
        question_heading, file_label, keep_note, sync_note, choices_box,
        choices_title,
        choice_row (property "label"), choice_label, choice_value,
        import_button, change_button, standard_button
    SummaryDialog (special_fields_summary)
        summary_heading, file_label, summary_rows, summary_row (property
        "label"), row_label, row_value, skip_details, full_sync_notice,
        full_sync_text, undo_note, undo_button, done_button
"""

from __future__ import annotations

import os
import re
import sys
import traceback
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from aqt.qt import *  # noqa: F401,F403  (PyQt6 via aqt)

from .model import ACCENT_COLOR, ADDON_NAME, UNDO_LABEL, ImportResult, Settings
from .settings_dialog import (
    ON_TEXT,
    _Colors,
    _css,
    _mix,
    _plain_tooltip,
    choices_summary,
    load_settings,
    open_settings,
)

WINDOW_TITLE = ADDON_NAME
QUESTION_HEADING = "Would you like to update with Special Fields by Ankoma?"
KEEP_NOTE = "Your review history, and any cards you moved to other decks, are always kept."
SYNC_NOTE = "If you've studied on another device, sync this computer before you update."
CHOICES_TITLE = "Your saved choices"
IMPORT_LABEL = "Import with my choices"
CHANGE_LABEL = "Change choices…"
STANDARD_LABEL = "Use Anki's standard import"

SUMMARY_HEADING = "Update complete"
SKIPPED_LABEL = "Notes skipped"
UNCHANGED_REASON = "unchanged"
FIXED_SUMMARY_ROWS: Tuple[Tuple[str, str], ...] = (
    ("Tags", "Replaced with the update's"),
    ("Review history and deck moves", "Unchanged"),
)
FULL_SYNC_NOTICE = (
    "This update changed a note type, so your next sync will be a one-way "
    "full sync. Choose “Upload to AnkiWeb” so this computer's "
    "updated copy is kept. If you studied on another device and hadn't "
    "synced this computer first, undo this update, sync, then import again."
)
MERGE_REPAIR_WARNING = (
    "Nothing was imported. This file moves some notes to a different note type, "
    "and Special Fields couldn't apply that change safely to your collection. "
    "Your collection is unchanged. You can import this file with Anki's standard "
    "import instead, or ask the deck's author for help."
)
UNDO_NOTE_PLAIN = "Not what you expected? Edit → Undo %s reverses the whole update." % UNDO_LABEL
UNDO_BUTTON_LABEL = "Undo update"
DONE_LABEL = "Done"

MENU_ACTION_NAME = "special_fields_by_ankoma_settings_action"

# Choices the question dialog exposes.
CHOICE_IMPORT = "import"
CHOICE_STANDARD = "standard"
CHOICE_CANCEL = "cancel"
# Choices the summary dialog exposes.
CHOICE_UNDO = "undo"
CHOICE_DONE = "done"

# A warm amber that reads on both light and dark window colours; used only
# for the full-sync notice's border and a faint tint (the text keeps the
# palette's own colour).
_NOTICE_COLOR = "#C98A12"

_FILE_NAME_WIDTH = 400  # px before a long file name is elided (tooltip has it all)
_VALUE_WRAP_WIDTH = 300  # px; longer "saved choices" values wrap


# ---------------------------------------------------------------------------
# Pure helpers


def summary_rows(result: ImportResult) -> List[Tuple[str, str]]:
    """(label, value) rows for the summary dialog, in display order.

    `ImportResult.summary_rows()` without its "Notes skipped" row; a
    "Notes skipped" row is added back only when reasons other than
    "unchanged" add up to more than zero, with that sum. Then the fixed rows.
    """
    rows = [r for r in result.summary_rows() if r[0] != SKIPPED_LABEL]
    skipped = sum(n for _reason, n in skip_details(result))
    if skipped > 0:
        rows.append((SKIPPED_LABEL, str(skipped)))
    rows.extend(FIXED_SUMMARY_ROWS)
    return rows


def skip_details(result: ImportResult) -> List[Tuple[str, int]]:
    """Skip reasons to list under "Notes skipped" ("unchanged" left out),
    largest first, as (reason, count)."""
    out = []
    for reason, n in (result.skip_reasons or {}).items():
        try:
            n = int(n)
        except (TypeError, ValueError):
            continue
        if n > 0 and str(reason).strip().casefold() != UNCHANGED_REASON:
            out.append((str(reason), n))
    out.sort(key=lambda x: (-x[1], x[0]))
    return out


def skip_details_text(result: ImportResult) -> str:
    parts = []
    for reason, n in skip_details(result):
        text = reason[:1].upper() + reason[1:]
        parts.append("%s: %d" % (text, n))
    return " · ".join(parts)


def _log_exception(where: str) -> None:
    sys.stderr.write("%s: %s failed:\n%s" % (ADDON_NAME, where, traceback.format_exc()))


# ---------------------------------------------------------------------------
# Shared look


def _dialog_css(c: _Colors) -> str:
    """Stylesheet shared by both dialogs. Colours come from the palette; the
    accent fills only the primary button."""
    return """
        QFrame#choices_box {
            background: %(box)s; border: 1px solid %(soft)s; border-radius: 8px;
        }
        QFrame#choices_box QLabel { border: none; background: transparent; }
        QFrame#summary_rows { border: 1px solid %(border)s; border-radius: 8px; }
        QFrame#summary_rows QLabel { border: none; background: transparent; }
        QFrame#row_separator { border: none; border-top: 1px solid %(soft)s; }
        QFrame#full_sync_notice {
            background: %(notice_bg)s; border: 1px solid %(notice)s;
            border-left: 4px solid %(notice)s; border-radius: 6px;
        }
        QFrame#full_sync_notice QLabel { border: none; background: transparent; }
        QPushButton#import_button, QPushButton#done_button {
            background: %(accent)s; color: %(on)s; font-weight: 600;
            border: 1px solid %(accent)s; border-radius: 6px; padding: 7px 18px;
        }
        QPushButton#import_button:focus, QPushButton#done_button:focus {
            border: 2px solid %(focus)s; padding: 6px 17px;
        }
        QPushButton#import_button:pressed, QPushButton#done_button:pressed {
            background: %(accent_dark)s;
        }
    """ % {
        "box": _css(_mix(c.window, c.text, 0.04)),
        "soft": _css(c.border_soft),
        "border": _css(c.border),
        "notice": _NOTICE_COLOR,
        "notice_bg": _css(_mix(c.window, QColor(_NOTICE_COLOR), 0.14)),
        "focus": _css(c.focus),
        "accent": ACCENT_COLOR,
        "accent_dark": _css(c.accent.darker(125)),
        "on": ON_TEXT,
    }


def _plain_label(text: str, parent: QWidget, name: str = "") -> QLabel:
    lab = QLabel(parent)
    lab.setTextFormat(Qt.TextFormat.PlainText)
    lab.setText(text)
    lab.setWordWrap(True)
    if name:
        lab.setObjectName(name)
    return lab


def _with_font(lab: QLabel, delta: float = 0.0, weight: Optional[Any] = None) -> QLabel:
    f = QFont(lab.font())
    if delta and f.pointSizeF() > 0:
        f.setPointSizeF(max(7.0, f.pointSizeF() + delta))
    if weight is not None:
        f.setWeight(weight)
    lab.setFont(f)
    return lab


def _muted(lab: QLabel, c: _Colors) -> QLabel:
    lab.setStyleSheet("color: %s;" % _css(c.muted))
    return lab


def _heading(text: str, parent: QWidget, name: str) -> QLabel:
    lab = _plain_label(text, parent, name)
    _with_font(lab, 3.0, QFont.Weight.DemiBold)
    lab.setAccessibleName(text)
    return lab


def _file_label(file_name: str, parent: QWidget, c: _Colors) -> QLabel:
    lab = QLabel(parent)
    lab.setObjectName("file_label")
    lab.setTextFormat(Qt.TextFormat.PlainText)
    _with_font(lab, -0.5)
    shown = lab.fontMetrics().elidedText(file_name, Qt.TextElideMode.ElideMiddle, _FILE_NAME_WIDTH)
    lab.setText("File: " + shown)
    lab.setToolTip(_plain_tooltip(file_name))
    lab.setAccessibleName("File: " + file_name)
    # The (elided) name never decides the dialog's width.
    lab.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    _muted(lab, c)
    lab.setProperty("file_name", file_name)
    return lab


def _separator(parent: QWidget) -> QFrame:
    sep = QFrame(parent)
    sep.setObjectName("row_separator")
    sep.setFixedHeight(1)
    return sep


# ---------------------------------------------------------------------------
# Question dialog


class QuestionDialog(QDialog):
    """The question shown before every .apkg import.

    `rows` are the "Your saved choices" rows. `change_choices`, if given, is
    called by "Change choices…" and returns the refreshed rows (or None to
    keep the current ones); the dialog stays open. After exec(), `choice()`
    is CHOICE_IMPORT, CHOICE_STANDARD or CHOICE_CANCEL (Escape / close).
    """

    def __init__(
        self,
        parent: Optional[QWidget],
        file_name: str,
        rows: Sequence[Tuple[str, str]],
        change_choices: Optional[Callable[[], Optional[Sequence[Tuple[str, str]]]]] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("special_fields_question")
        self.setWindowTitle(WINDOW_TITLE)
        self.setAccessibleName(WINDOW_TITLE)
        self.file_name = file_name
        self._change_choices = change_choices
        self._choice = CHOICE_CANCEL
        self._colors = _Colors(self.palette())
        self._rows: List[Tuple[str, str]] = []
        self._build()
        self.set_rows(rows)
        self.setMinimumWidth(500)
        self.resize(540, self.sizeHint().height())

    # ----- construction -------------------------------------------------

    def _build(self) -> None:
        c = self._colors
        self.setStyleSheet(_dialog_css(c))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(16)

        top = QVBoxLayout()
        top.setSpacing(6)
        self.heading = _heading(QUESTION_HEADING, self, "question_heading")
        top.addWidget(self.heading)
        self.file_label = _file_label(self.file_name, self, c)
        top.addWidget(self.file_label)
        self.keep_note = _plain_label(KEEP_NOTE, self, "keep_note")
        top.addWidget(self.keep_note)
        self.sync_note = _muted(_plain_label(SYNC_NOTE, self, "sync_note"), c)
        top.addWidget(self.sync_note)
        lay.addLayout(top)

        box = QFrame(self)
        box.setObjectName("choices_box")
        box.setAccessibleName(CHOICES_TITLE)
        self.choices_box = box
        bl = QVBoxLayout(box)
        bl.setContentsMargins(16, 12, 16, 12)
        bl.setSpacing(8)
        title = _plain_label(CHOICES_TITLE, box, "choices_title")
        f = QFont(title.font())
        f.setCapitalization(QFont.Capitalization.AllUppercase)
        f.setWeight(QFont.Weight.DemiBold)
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 104)
        if f.pointSizeF() > 0:
            f.setPointSizeF(max(7.0, f.pointSizeF() - 1))
        title.setFont(f)
        _muted(title, c)
        bl.addWidget(title)
        self._rows_layout = QVBoxLayout()
        self._rows_layout.setSpacing(6)
        bl.addLayout(self._rows_layout)
        lay.addWidget(box)

        self.import_button = QPushButton(IMPORT_LABEL, self)
        self.import_button.setObjectName("import_button")
        self.import_button.setAccessibleName(IMPORT_LABEL)
        self.import_button.setDefault(True)
        self.import_button.setAutoDefault(True)
        self.import_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.import_button.clicked.connect(self._on_import)
        lay.addWidget(self.import_button)

        pair = QHBoxLayout()
        pair.setSpacing(8)
        self.change_button = QPushButton(CHANGE_LABEL, self)
        self.change_button.setObjectName("change_button")
        self.change_button.setAccessibleName("Change choices")
        self.change_button.setToolTip("Open the Special Fields settings, then come back here")
        self.standard_button = QPushButton(STANDARD_LABEL, self)
        self.standard_button.setObjectName("standard_button")
        self.standard_button.setAccessibleName(STANDARD_LABEL)
        self.standard_button.setToolTip("Import this file with Anki's own import screen; the add-on stays out of the way")
        for b in (self.change_button, self.standard_button):
            b.setAutoDefault(False)
            b.setDefault(False)
            b.setMinimumHeight(self.import_button.sizeHint().height())
            pair.addWidget(b, 1)
        self.change_button.clicked.connect(self._on_change)
        self.standard_button.clicked.connect(self._on_standard)
        lay.addLayout(pair)

        QWidget.setTabOrder(self.import_button, self.change_button)
        QWidget.setTabOrder(self.change_button, self.standard_button)
        self.import_button.setFocus()

    # ----- data ---------------------------------------------------------

    def rows(self) -> List[Tuple[str, str]]:
        """The rows currently shown in "Your saved choices"."""
        return list(self._rows)

    def set_rows(self, rows: Sequence[Tuple[str, str]]) -> None:
        while self._rows_layout.count():
            item = self._rows_layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        self._rows = [(str(a), str(b)) for a, b in rows]
        c = self._colors
        for label, value in self._rows:
            row = QWidget(self.choices_box)
            row.setObjectName("choice_row")
            row.setProperty("label", label)
            row.setAccessibleName("%s: %s" % (label, value))
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(12)
            lab = _plain_label(label, row, "choice_label")
            lab.setWordWrap(False)
            _muted(lab, c)
            val = _plain_label(value, row, "choice_value")
            val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
            _with_font(val, 0.0, QFont.Weight.DemiBold)
            # Wrap only values too long for one line: a word-wrapped QLabel
            # in a row layout otherwise reserves a second, empty line.
            val.setWordWrap(val.fontMetrics().horizontalAdvance(value) > _VALUE_WRAP_WIDTH)
            val.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            rl.addWidget(lab, 0, Qt.AlignmentFlag.AlignTop)
            rl.addWidget(val, 1)
            self._rows_layout.addWidget(row)
        self.choices_box.setAccessibleDescription(
            "; ".join("%s: %s" % r for r in self._rows)
        )
        self.adjustSize()

    def choice(self) -> str:
        return self._choice

    # ----- actions ------------------------------------------------------

    def _on_import(self) -> None:
        self._choice = CHOICE_IMPORT
        self.accept()

    def _on_standard(self) -> None:
        self._choice = CHOICE_STANDARD
        self.accept()

    def _on_change(self) -> None:
        if self._change_choices is None:
            return
        rows = self._change_choices()
        if rows is not None:
            self.set_rows(rows)
        self.import_button.setFocus()

    def reject(self) -> None:
        self._choice = CHOICE_CANCEL
        super().reject()


# ---------------------------------------------------------------------------
# Summary dialog


class SummaryDialog(QDialog):
    """Shown after a successful import. After exec(), `choice()` is
    CHOICE_UNDO ("Undo update") or CHOICE_DONE ("Done", Escape, close)."""

    def __init__(self, parent: Optional[QWidget], result: ImportResult, file_name: str = "") -> None:
        super().__init__(parent)
        self.setObjectName("special_fields_summary")
        self.setWindowTitle(WINDOW_TITLE)
        self.setAccessibleName(WINDOW_TITLE)
        self.result_data = result
        self.file_name = file_name
        self._choice = CHOICE_DONE
        self._colors = _Colors(self.palette())
        self._rows = summary_rows(result)
        self._build()
        self.setMinimumWidth(500)
        self.resize(540, self.sizeHint().height())

    def _build(self) -> None:
        c = self._colors
        self.setStyleSheet(_dialog_css(c))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(16)

        top = QVBoxLayout()
        top.setSpacing(6)
        self.heading = _heading(SUMMARY_HEADING, self, "summary_heading")
        top.addWidget(self.heading)
        self.file_label = None  # type: Optional[QLabel]
        if self.file_name:
            self.file_label = _file_label(self.file_name, self, c)
            top.addWidget(self.file_label)
        lay.addLayout(top)

        table = QFrame(self)
        table.setObjectName("summary_rows")
        table.setAccessibleName("Summary")
        self.rows_frame = table
        tl = QVBoxLayout(table)
        tl.setContentsMargins(1, 1, 1, 1)
        tl.setSpacing(0)
        self.skip_details_label = None  # type: Optional[QLabel]
        for i, (label, value) in enumerate(self._rows):
            if i:
                tl.addWidget(_separator(table))
            row = QWidget(table)
            row.setObjectName("summary_row")
            row.setProperty("label", label)
            row.setAccessibleName("%s: %s" % (label, value))
            rv = QVBoxLayout(row)
            rv.setContentsMargins(14, 8, 14, 8)
            rv.setSpacing(2)
            line = QHBoxLayout()
            line.setSpacing(12)
            lab = _plain_label(label, row, "row_label")
            lab.setWordWrap(False)
            val = _plain_label(value, row, "row_value")
            val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            _with_font(val, 0.0, QFont.Weight.DemiBold)
            val.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            line.addWidget(lab, 0)
            line.addWidget(val, 1)
            rv.addLayout(line)
            if label == SKIPPED_LABEL:
                details = skip_details_text(self.result_data)
                det = _plain_label(details, row, "skip_details")
                _with_font(det, -1.0)
                _muted(det, c)
                det.setAccessibleName("Reasons: " + details)
                rv.addWidget(det)
                self.skip_details_label = det
                row.setAccessibleName("%s: %s (%s)" % (label, value, details))
            tl.addWidget(row)
        lay.addWidget(table)

        self.full_sync_notice = None  # type: Optional[QFrame]
        if self.result_data.note_types_changed:
            box = QFrame(self)
            box.setObjectName("full_sync_notice")
            box.setAccessibleName("Full sync needed")
            box.setAccessibleDescription(FULL_SYNC_NOTICE)
            bl = QHBoxLayout(box)
            bl.setContentsMargins(12, 10, 12, 10)
            bl.setSpacing(10)
            icon = QLabel(box)
            icon.setObjectName("full_sync_icon")
            ic = self.style().standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning)
            icon.setPixmap(ic.pixmap(22, 22))
            bl.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
            text = _plain_label(FULL_SYNC_NOTICE, box, "full_sync_text")
            _with_font(text, 0.0, QFont.Weight.DemiBold)
            bl.addWidget(text, 1)
            lay.addWidget(box)
            self.full_sync_notice = box

        self.undo_note = QLabel(self)
        self.undo_note.setObjectName("undo_note")
        self.undo_note.setTextFormat(Qt.TextFormat.RichText)
        self.undo_note.setText(
            "Not what you expected? <b>Edit → Undo %s</b> reverses the whole update."
            % _html_escape(UNDO_LABEL)
        )
        self.undo_note.setAccessibleName(UNDO_NOTE_PLAIN)
        self.undo_note.setWordWrap(True)
        _with_font(self.undo_note, -0.5)
        _muted(self.undo_note, c)
        lay.addWidget(self.undo_note)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addStretch(1)
        self.undo_button = QPushButton(UNDO_BUTTON_LABEL, self)
        self.undo_button.setObjectName("undo_button")
        self.undo_button.setAccessibleName(UNDO_BUTTON_LABEL)
        self.undo_button.setToolTip("Reverse the whole update now (same as Edit → Undo)")
        self.undo_button.setAutoDefault(False)
        self.undo_button.setDefault(False)
        self.undo_button.clicked.connect(self._on_undo)
        bar.addWidget(self.undo_button)
        self.done_button = QPushButton(DONE_LABEL, self)
        self.done_button.setObjectName("done_button")
        self.done_button.setAccessibleName(DONE_LABEL)
        self.done_button.setDefault(True)
        self.done_button.setAutoDefault(True)
        self.done_button.clicked.connect(self._on_done)
        bar.addWidget(self.done_button)
        lay.addLayout(bar)
        QWidget.setTabOrder(self.undo_button, self.done_button)
        self.done_button.setFocus()

    def rows(self) -> List[Tuple[str, str]]:
        return list(self._rows)

    def choice(self) -> str:
        return self._choice

    def _on_undo(self) -> None:
        self._choice = CHOICE_UNDO
        self.accept()

    def _on_done(self) -> None:
        self._choice = CHOICE_DONE
        self.accept()

    def reject(self) -> None:
        self._choice = CHOICE_DONE
        super().reject()


def _html_escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# ---------------------------------------------------------------------------
# Anki glue (the only code that touches `mw`)


# The original `do_import` (a plain function), kept so "Use Anki's standard
# import" can call it untouched. Set once by `install_import_wrapper`.
_original_do_import: Optional[Callable[..., Any]] = None


def _refreshed_rows(mw: Any) -> List[Tuple[str, str]]:
    return choices_summary(load_settings(mw))


def _change_choices(mw: Any, dlg: QWidget) -> Optional[List[Tuple[str, str]]]:
    """"Change choices…": the settings window over the question, then the
    saved choices as they are now (whether the user saved or cancelled)."""
    try:
        open_settings(mw, parent=dlg)
    except Exception as exc:  # show it like Anki does, keep the question open
        _show_error(dlg, exc)
    return _refreshed_rows(mw)


def _show_error(parent: Optional[QWidget], exc: Exception) -> None:
    try:
        from aqt.errors import show_exception

        show_exception(parent=parent, exception=exc)
    except Exception:
        _log_exception("showing an error")


def ask(mw: Any, path: str) -> str:
    """Show the question for `path`; return the user's choice."""
    dlg = QuestionDialog(
        mw if isinstance(mw, QWidget) else None,
        os.path.basename(path),
        _refreshed_rows(mw),
    )
    dlg._change_choices = lambda: _change_choices(mw, dlg)
    try:
        dlg.exec()
        return dlg.choice()
    finally:
        dlg.deleteLater()


def handle_apkg(
    original: Callable[..., Any],
    args: Tuple[Any, ...],
    kwargs: Dict[str, Any],
    path_kw: str = "path",
) -> None:
    """The body of the wrapped `ApkgImporter.do_import(mw, path)` and of the
    wrapped legacy `aqt.importing.importFile(mw, file)` (path_kw="file").
    "Use Anki's standard import" calls `original` with the same arguments."""
    mw = args[0] if args else kwargs.get("mw")
    path = args[1] if len(args) > 1 else kwargs.get(path_kw)
    try:
        choice = ask(mw, str(path))
    except Exception:
        # A bug in the add-on must never stop the user from importing:
        # fall back to Anki's own importer.
        _log_exception("showing the question")
        original(*args, **kwargs)
        return
    if choice == CHOICE_STANDARD:
        original(*args, **kwargs)
    elif choice == CHOICE_IMPORT:
        run_import_with_choices(mw, str(path), load_settings(mw))
    # CHOICE_CANCEL: nothing is imported.


def run_import_with_choices(mw: Any, path: str, settings: Settings) -> None:
    """Run the engine in a CollectionOp on the background thread with Anki's
    import progress. The op returns the ImportResult, whose `changes` aqt
    uses to refresh the UI and the undo menu. A note type move the engine
    could not repair (`engine.MergeRepairError`, contract rule 10g) gets a
    plain warning; every other error goes to Anki's normal error dialog, as
    before. Either way the engine has left the collection as it was."""
    from aqt.operations import CollectionOp

    from . import engine

    try:
        from aqt.import_export.importing import import_progress_update
    except Exception:  # pragma: no cover - present on 25.02 and 26.09
        import_progress_update = None

    file_name = os.path.basename(path)
    backup_folder = _backup_folder(mw)  # read on the main thread

    def op(col: Any) -> ImportResult:
        backup_before_import(col, backup_folder)
        return engine.run_import(col, path, settings)

    def on_success(result: ImportResult) -> None:
        # aqt calls this before it refreshes the UI and the undo actions;
        # show the summary once that is done.
        _later(mw, lambda: show_summary(mw, result, file_name))

    def on_failure(exc: Exception) -> None:
        if isinstance(exc, engine.MergeRepairError):
            show_merge_repair_warning(mw)
            return
        # What CollectionOp does itself when no failure handler is given.
        import aqt.operations

        aqt.operations.show_exception(parent=mw, exception=exc)

    CollectionOp(parent=mw, op=op).success(on_success).failure(on_failure).with_backend_progress(
        import_progress_update
    ).run_in_background()


def _backup_folder(mw: Any) -> Optional[str]:
    """The profile's backup folder, or None when it can't be found."""
    try:
        folder = mw.pm.backupFolder()
    except Exception:
        return None
    return str(folder) if folder else None


def backup_before_import(col: Any, backup_folder: Optional[str]) -> bool:
    """Safety net: ask Anki to write one of its normal backups before the
    import changes anything.

    Undo is the first line of defence, but Anki throws its whole undo history
    away if one of its own operations fails part-way, so a backup is the only
    recovery that never depends on undo. It is Anki's own backup (File ->
    Switch Profile -> Open Backup restores it) and Anki prunes old ones as
    usual. Best effort: a backup that can't be made never blocks the import.
    Returns True if Anki reports a backup was created.
    """
    if not backup_folder:
        return False
    try:
        return bool(col.create_backup(backup_folder=backup_folder, force=True, wait_for_completion=True))
    except Exception as exc:
        print("Special Fields by Ankoma: could not create a backup before the import: %r" % (exc,), file=sys.stderr)
        return False


def show_merge_repair_warning(mw: Any) -> None:
    """Anki's ordinary warning box with plain text, not its exception dialog."""
    from aqt.utils import showWarning

    showWarning(
        MERGE_REPAIR_WARNING,
        parent=mw if isinstance(mw, QWidget) else None,
        title=ADDON_NAME,
        textFormat="plain",
    )


def _later(mw: Any, func: Callable[[], None]) -> None:
    progress = getattr(mw, "progress", None)
    single_shot = getattr(progress, "single_shot", None)
    if single_shot is not None:
        single_shot(0, func, False)
    else:
        QTimer.singleShot(0, func)


def show_summary(mw: Any, result: ImportResult, file_name: str = "") -> str:
    dlg = SummaryDialog(mw if isinstance(mw, QWidget) else None, result, file_name)
    try:
        dlg.exec()
        choice = dlg.choice()
    finally:
        dlg.deleteLater()
    if choice == CHOICE_UNDO:
        undo_update(mw)
    return choice


def undo_update(mw: Any) -> bool:
    """Anki's undo, through aqt's undo operation (so the UI refreshes), but
    only if the step on top of the undo stack is still this update."""
    col = getattr(mw, "col", None)
    try:
        top = col.undo_status().undo if col is not None else ""
    except Exception:
        top = ""
    if top != UNDO_LABEL:
        try:
            from aqt.utils import showWarning

            showWarning(
                "The last change is no longer the Special Fields update, so it "
                "was not undone. Use Edit → Undo to see what would be undone.",
                parent=mw if isinstance(mw, QWidget) else None,
                title=ADDON_NAME,
            )
        except Exception:
            _log_exception("warning about undo")
        return False
    from aqt.operations.collection import undo

    undo(parent=mw)
    return True


# ----- installation ------------------------------------------------------


def install_import_wrapper() -> bool:
    """Wrap `ApkgImporter.do_import` once. Returns True if our wrapper is in
    place afterwards. Idempotent: a second call changes nothing."""
    global _original_do_import
    from aqt.import_export import importing

    cls = importing.ApkgImporter
    current = cls.__dict__.get("do_import")
    func = current.__func__ if isinstance(current, staticmethod) else getattr(cls, "do_import", None)
    if func is None or not callable(func):
        return False
    previous = getattr(func, "_sfa_original", None)
    if previous is not None:  # already wrapped (maybe by an earlier load)
        if _original_do_import is None:
            _original_do_import = previous
        return True

    original = func

    def do_import(*args: Any, **kwargs: Any) -> None:
        handle_apkg(original, args, kwargs)

    do_import._sfa_original = original  # type: ignore[attr-defined]
    do_import.__doc__ = getattr(original, "__doc__", None)
    do_import.__name__ = "do_import"
    _original_do_import = original
    cls.do_import = staticmethod(do_import)
    return True


def is_legacy_apkg(path: Any) -> bool:
    """True for an .apkg the legacy importer would add to the collection.

    Only .apkg (any letter case). Full-collection packages
    ("collection.apkg", "backup-*.apkg"), which the legacy importer hands to
    the full-restore path, are left alone, as are .colpkg, .zip, text, CSV
    and every other legacy import type."""
    try:
        base = os.path.basename(str(path)).lower()
    except Exception:
        return False
    if not base.endswith(".apkg"):
        return False
    if base == "collection.apkg" or re.match(r"backup-.*\.apkg$", base):
        return False
    return True


def install_legacy_wrapper() -> bool:
    """Wrap the legacy `aqt.importing.importFile(mw, file)` once, where it
    exists (Anki 25.02 to 26.08; the module is gone from 26.09).

    Every legacy route reaches `importFile` by a module-attribute lookup at
    call time: `aqt.importing.onImport` (File > Import), drag-and-drop and
    open-with in `aqt/main.py`, and the new importer's `import_file` for
    legacy-only file types. Only .apkg files (see `is_legacy_apkg`) get the
    question; everything else goes straight to Anki's function.

    Returns True if our wrapper is in place afterwards, False if there is
    nothing to wrap. Idempotent."""
    try:
        import aqt.importing as legacy  # absent on 26.09+
    except ImportError:
        return False
    func = getattr(legacy, "importFile", None)
    if func is None or not callable(func):
        return False
    if getattr(func, "_sfa_original", None) is not None:
        return True

    original = func

    def importFile(*args: Any, **kwargs: Any) -> None:  # noqa: N802 (Anki's name)
        path = args[1] if len(args) > 1 else kwargs.get("file")
        if is_legacy_apkg(path):
            handle_apkg(original, args, kwargs, path_kw="file")
        else:
            original(*args, **kwargs)

    importFile._sfa_original = original  # type: ignore[attr-defined]
    importFile.__doc__ = getattr(original, "__doc__", None)
    legacy.importFile = importFile
    return True


def open_settings_from_menu(mw: Any) -> None:
    try:
        open_settings(mw)
    except Exception as exc:
        _show_error(mw if isinstance(mw, QWidget) else None, exc)


def install_menu(mw: Any) -> Optional[QAction]:
    """Add Tools > "Special Fields by Ankoma" once."""
    menu = mw.form.menuTools
    for act in menu.actions():
        if act.objectName() == MENU_ACTION_NAME:
            return act
    action = QAction(ADDON_NAME, mw)
    action.setObjectName(MENU_ACTION_NAME)
    action.setToolTip("Choose what Special Fields by Ankoma keeps when you import an update")
    action.triggered.connect(lambda *_a: open_settings_from_menu(mw))
    menu.addAction(action)
    return action


def setup(mw: Any) -> None:
    """Install everything; never raises."""
    try:
        install_import_wrapper()
    except Exception:
        _log_exception("wrapping Anki's .apkg importer (left untouched)")
    try:
        install_legacy_wrapper()
    except Exception:
        _log_exception("wrapping Anki's legacy importer (left untouched)")
    try:
        install_menu(mw)
    except Exception:
        _log_exception("adding the Tools menu item")


def _setup_on_load() -> None:
    try:
        from aqt import mw
    except Exception:
        return
    if mw is not None:
        setup(mw)


_setup_on_load()
