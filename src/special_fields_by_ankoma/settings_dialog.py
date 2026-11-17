"""Settings window for Special Fields by Ankoma (workstream C).

Native Qt widgets only (no web view). `SettingsDialog` takes plain data, so
it can be built and driven in an offscreen test without a running Anki.
Only `open_settings`, `load_settings` and `save_settings` touch `mw`.

Widgets carry objectNames so tests and other workstreams can find them:

    field_rows        frame holding one `FieldRow` per field
    field_row         one row (property "field_name" holds the name)
    keep_button       left side of a row's toggle ("Keep mine")
    take_button       right side of a row's toggle ("Take the update's")
    remove_field_button   the ✕ on a row the user added
    add_field_button  "+ Add field"
    field_picker      the inline field search (hidden until opened)
    field_search, field_matches, field_done_button, field_hint
    tag_chips         container of `TagChip` widgets ("tag_chip")
    remove_tag_button the ✕ on a chip
    tag_input, tag_list, tag_hint
    styling_switch    "Update card templates and styling"
    restore_button, cancel_button, save_button
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from aqt.qt import *  # noqa: F401,F403  (PyQt6 via aqt)

from .config import (
    DEFAULT_FIELDS,
    default_settings,
    settings_from_config,
    settings_to_config,
)
from .model import (
    ACCENT_COLOR,
    ADDON_NAME,
    FieldChoice,
    Settings,
    norm_field,
    norm_tag,
)

WINDOW_TITLE = ADDON_NAME + ": Settings"
KEEP_LABEL = "Keep mine"
TAKE_LABEL = "Take the update's"
FIELDS_HEADING = "Fields: when an update changes a card…"
FIELDS_HELP = (
    "Matched by field name, so field order doesn't matter. "
    "A field a note type doesn't have is skipped for that type."
)
NO_FIELDS_TEXT = "No fields listed. Every field takes the update's content."
TAGS_HEADING = "Protected tags"
TAGS_HELP = (
    "An update never removes these tags from your notes, even when tags are "
    "replaced. The rest of the note still updates as usual."
)
STYLING_HEADING = "Update card templates and styling"
STYLING_HELP = (
    "On: an update may replace your card templates and styling. "
    "Off: yours are kept exactly as they are. Note content updates either way."
)
ON_TEXT = "#FFFFFF"

# How many matching tags the list shows at once. Matching itself always uses
# every tag, so "the only match" is judged on the full collection.
MAX_TAGS_SHOWN = 100


_ENTER_KEYS = (Qt.Key.Key_Return, Qt.Key.Key_Enter)


# ---------------------------------------------------------------------------
# Pure helpers (no widgets)


def _addon_key() -> str:
    """The add-on's config key: the package's top-level module name.

    AnkiWeb installs the add-on in a folder named by number, so the name is
    never hard-coded.
    """
    return __name__.split(".")[0]


def _rank(query: str, candidates: Iterable[str], exclude: Iterable[str], norm) -> List[str]:
    """Case-insensitive substring matches of `query`, prefix matches first,
    then shorter names, then alphabetical. Names in `exclude` are left out,
    and duplicates (by `norm`) keep their first spelling. An empty query
    matches everything."""
    q = query.strip().casefold()
    skip = {norm(x) for x in exclude}
    seen = set()
    out = []
    for name in candidates:
        key = norm(name)
        if not key or key in skip or key in seen:
            continue
        seen.add(key)
        if q and q not in name.casefold():
            continue
        out.append(name)
    out.sort(
        key=lambda n: (
            0 if (q and n.casefold().startswith(q)) else 1,
            len(n),
            n.casefold(),
        )
    )
    return out


def filter_tags(query: str, all_tags: Iterable[str], exclude: Iterable[str] = ()) -> List[str]:
    """Tags matching `query` for the protected-tag picker.

    An empty query lists nothing (the list appears once the user types).
    """
    if not query.strip():
        return []
    return _rank(query, all_tags, exclude, norm_tag)


def filter_fields(query: str, all_fields: Iterable[str], exclude: Iterable[str] = ()) -> List[str]:
    """Field names matching `query` for "+ Add field" (all of them if empty)."""
    return _rank(query, all_fields, exclude, norm_field)


def _pick_target(query: str, matches: Sequence[str], norm) -> Optional[str]:
    """What Enter adds in the field picker when nothing is highlighted: the
    exact match (ignoring case), else the only match, else nothing."""
    q = norm(query)
    if not q:
        return None
    for m in matches:
        if norm(m) == q:
            return m
    if len(matches) == 1:
        return matches[0]
    return None


def choices_summary(settings: Settings) -> List[Tuple[str, str]]:
    """Rows for the "Your saved choices" box, in display order."""
    kept = [f.name for f in settings.fields if f.keep]
    return [
        ("Fields you keep", ", ".join(kept) if kept else "None"),
        (
            "Protected tags",
            ", ".join(settings.protected_tags) if settings.protected_tags else "None",
        ),
        ("Tags", "Replaced with the update's"),
        ("Card styling", "Update" if settings.update_note_types else "Keep mine"),
    ]


# ---------------------------------------------------------------------------
# Colours (taken from the palette so light and dark themes both work)


def _plain_tooltip(text: str) -> str:
    """A tooltip that shows `text` literally. Qt guesses whether tooltip text
    is rich text, so user-supplied names are escaped inside a rich-text
    wrapper (a field named "<b>x</b>" must not turn bold)."""
    escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return "<span>%s</span>" % escaped


def _plain(lab: QLabel) -> QLabel:
    """Labels show their text literally, never as rich text: field names,
    tags and hints that echo typed text may contain markup."""
    lab.setTextFormat(Qt.TextFormat.PlainText)
    return lab


def _mix(a: QColor, b: QColor, t: float) -> QColor:
    """`a` moved a fraction `t` of the way towards `b`."""
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
    )


def _css(c: QColor) -> str:
    if c.alpha() == 255:
        return c.name()
    return "rgba(%d, %d, %d, %d)" % (c.red(), c.green(), c.blue(), c.alpha())


class _Colors:
    def __init__(self, pal: QPalette) -> None:
        role = QPalette.ColorRole
        self.window = pal.color(role.Window)
        self.text = pal.color(role.WindowText)
        self.base = pal.color(role.Base)
        self.base_text = pal.color(role.Text)
        self.muted = _mix(self.window, self.text, 0.70)
        self.plain_text = _mix(self.base, self.base_text, 0.85)
        self.border = _mix(self.window, self.text, 0.25)
        self.border_soft = _mix(self.window, self.text, 0.14)
        self.chip_bg = _mix(self.window, self.text, 0.07)
        self.track_off = _mix(self.window, self.text, 0.40)
        hl = QColor(pal.color(role.Highlight))
        hl.setAlpha(255)
        self.focus = hl
        self.accent = QColor(ACCENT_COLOR)
        # The accent is fixed, so make sure a focus ring drawn over it is visible.
        if abs(hl.lightness() - self.accent.lightness()) < 40 and abs(hl.hue() - self.accent.hue()) < 30:
            self.focus = self.text


def _segment_css(colors: _Colors, selected: bool, side: str) -> str:
    """Stylesheet for one side of a two-part toggle.

    The selected side is accent-filled with white text; the other is plain.
    Border + padding add up to the same size with and without focus, so the
    row doesn't jump when focus moves.
    """
    if selected:
        bg, fg, bd, weight = colors.accent, QColor(ON_TEXT), colors.accent, 600
    else:
        bg, fg, bd, weight = colors.base, colors.plain_text, colors.border, 400
    if side == "left":
        radius = "border-top-left-radius: 6px; border-bottom-left-radius: 6px;"
        normal = "border: 1px solid %s; padding: 5px 12px;" % _css(bd)
        focus = "border: 2px solid %s; padding: 4px 11px;" % _css(colors.focus)
    else:
        radius = "border-top-right-radius: 6px; border-bottom-right-radius: 6px;"
        normal = "border: 1px solid %s; border-left: none; padding: 5px 12px 5px 13px;" % _css(bd)
        focus = "border: 2px solid %s; padding: 4px 11px 4px 11px;" % _css(colors.focus)
    return (
        "QPushButton { background: %s; color: %s; font-weight: %d; margin: 0; %s %s }"
        "QPushButton:focus { %s }"
        % (_css(bg), _css(fg), weight, radius, normal, focus)
    )


# ---------------------------------------------------------------------------
# Small widgets


class _FlowLayout(QLayout):
    """Lays children out left to right, wrapping onto new lines (tag chips)."""

    def __init__(self, parent: Optional[QWidget] = None, spacing: int = 6) -> None:
        super().__init__(parent)
        self._items: List[QLayoutItem] = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item: QLayoutItem) -> None:  # noqa: N802 (Qt API)
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> Optional[QLayoutItem]:  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> Optional[QLayoutItem]:  # noqa: N802
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientation:  # noqa: N802
        return Qt.Orientation.Horizontal

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        return self._layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QRect) -> None:  # noqa: N802
        super().setGeometry(rect)
        self._layout(rect, False)

    def sizeHint(self) -> QSize:  # noqa: N802
        return self.minimumSize()

    def minimumSize(self) -> QSize:  # noqa: N802
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _layout(self, rect: QRect, test_only: bool) -> int:
        m = self.contentsMargins()
        area = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_height = area.x(), area.y(), 0
        for item in self._items:
            hint = item.sizeHint()
            if x > area.x() and x + hint.width() > area.right() + 1:
                x = area.x()
                y += line_height + self._spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + self._spacing
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + m.bottom()


class ToggleSwitch(QCheckBox):
    """A checkbox drawn as an on/off switch. Space toggles it; it keeps the
    checkbox role for screen readers."""

    def __init__(self, colors: _Colors, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._colors = colors
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:  # noqa: N802
        h = max(26, self.fontMetrics().height() + 10)
        return QSize(round(h * 1.7) + 4, h + 4)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    def hitButton(self, pos: QPoint) -> bool:  # noqa: N802
        return self.rect().contains(pos)

    def paintEvent(self, event: Any) -> None:  # noqa: N802
        c = self._colors
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        outer = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        track = outer.adjusted(1, 1, -1, -1)
        radius = track.height() / 2
        if self.hasFocus():
            pen = QPen(c.focus)
            pen.setWidthF(2.0)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(outer, outer.height() / 2, outer.height() / 2)
        p.setPen(Qt.PenStyle.NoPen)
        colour = QColor(c.accent if self.isChecked() else c.track_off)
        if not self.isEnabled():
            colour.setAlpha(110)
        p.setBrush(colour)
        p.drawRoundedRect(track, radius, radius)
        d = track.height() - 6
        x = track.right() - 3 - d if self.isChecked() else track.left() + 3
        p.setBrush(QColor(ON_TEXT))
        p.drawEllipse(QRectF(x, track.top() + 3, d, d))
        p.end()


class FieldToggle(QWidget):
    """Two-part toggle: "Keep mine" | "Take the update's"."""

    changed = pyqtSignal(bool)

    def __init__(self, name: str, keep: bool, colors: _Colors, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("field_toggle")
        self._colors = colors
        self.setAccessibleName(name)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.keep_button = QPushButton(KEEP_LABEL, self)
        self.keep_button.setObjectName("keep_button")
        self.take_button = QPushButton(TAKE_LABEL, self)
        self.take_button.setObjectName("take_button")
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        bold = QFont(self.font())
        bold.setWeight(QFont.Weight.DemiBold)
        fm = QFontMetrics(bold)
        for btn, label in ((self.keep_button, KEEP_LABEL), (self.take_button, TAKE_LABEL)):
            btn.setCheckable(True)
            btn.setAutoDefault(False)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setAccessibleName("%s: %s" % (name, label))
            # Wide enough for the bold (selected) text so toggling doesn't
            # change the row's width.
            btn.setMinimumWidth(fm.horizontalAdvance(label) + 32)
            self._group.addButton(btn)
            lay.addWidget(btn)
        self.keep_button.setChecked(keep)
        self.take_button.setChecked(not keep)
        self._group.buttonToggled.connect(self._on_toggled)
        self._restyle()

    def keep(self) -> bool:
        return self.keep_button.isChecked()

    def set_keep(self, keep: bool) -> None:
        (self.keep_button if keep else self.take_button).setChecked(True)

    def selected_button(self) -> QPushButton:
        return self.keep_button if self.keep() else self.take_button

    def _on_toggled(self, button: QAbstractButton, checked: bool) -> None:
        if not checked:
            return
        self._restyle()
        self.changed.emit(self.keep())

    def _restyle(self) -> None:
        keep = self.keep()
        self.keep_button.setStyleSheet(_segment_css(self._colors, keep, "left"))
        self.take_button.setStyleSheet(_segment_css(self._colors, not keep, "right"))


class FieldRow(QWidget):
    """One field: name, ✕ (every row can be removed, the defaults too), and
    the toggle."""

    remove_requested = pyqtSignal(str)

    def __init__(self, name: str, keep: bool, colors: _Colors, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("field_row")
        self.setProperty("field_name", name)
        self.name = name
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 10, 6)
        lay.setSpacing(6)
        self.label = _plain(QLabel(self))
        self.label.setObjectName("field_name_label")
        self.label.setText(self.label.fontMetrics().elidedText(name, Qt.TextElideMode.ElideMiddle, 230))
        self.label.setToolTip(_plain_tooltip(name))
        lay.addWidget(self.label, 0)
        rb = QToolButton(self)
        rb.setObjectName("remove_field_button")
        rb.setText("✕")
        rb.setAutoRaise(True)
        rb.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        rb.setCursor(Qt.CursorShape.PointingHandCursor)
        rb.setToolTip("Remove this field from the list")
        rb.setAccessibleName("Remove field %s" % name)
        rb.clicked.connect(lambda: self.remove_requested.emit(self.name))
        self.remove_button = rb
        lay.addWidget(rb, 0)
        lay.addStretch(1)
        self.toggle = FieldToggle(name, keep, colors, self)
        lay.addWidget(self.toggle, 0)

    def choice(self) -> FieldChoice:
        return FieldChoice(self.name, self.toggle.keep())


class TagChip(QFrame):
    remove_requested = pyqtSignal(str)

    def __init__(self, tag: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("tag_chip")
        self.setProperty("tag", tag)
        self.tag = tag
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 2, 3, 2)
        lay.setSpacing(2)
        label = _plain(QLabel(self))
        label.setObjectName("tag_chip_label")
        fm = label.fontMetrics()
        label.setText(fm.elidedText(tag, Qt.TextElideMode.ElideMiddle, 360))
        label.setToolTip(_plain_tooltip(tag))
        lay.addWidget(label)
        rb = QToolButton(self)
        rb.setObjectName("remove_tag_button")
        rb.setText("✕")
        rb.setAutoRaise(True)
        rb.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        rb.setCursor(Qt.CursorShape.PointingHandCursor)
        rb.setToolTip("Stop protecting this tag")
        rb.setAccessibleName("Remove protected tag %s" % tag)
        rb.clicked.connect(lambda: self.remove_requested.emit(self.tag))
        self.remove_button = rb
        lay.addWidget(rb)


# ---------------------------------------------------------------------------
# The dialog


class SettingsDialog(QDialog):
    """The add-on's settings window. Takes plain data; no `mw` needed."""

    def __init__(
        self,
        parent: Optional[QWidget],
        settings: Settings,
        all_field_names: Sequence[str],
        all_tags: Sequence[str],
    ) -> None:
        super().__init__(parent)
        self.setObjectName("special_fields_settings")
        self.setWindowTitle(WINDOW_TITLE)
        self._all_fields = list(all_field_names)
        self._all_tags = list(all_tags)
        self._colors = _Colors(self.palette())
        self._rows: List[FieldRow] = []
        self._tags: List[str] = []
        self._tag_matches: List[str] = []
        self._field_matches: List[str] = []
        self._result: Optional[Settings] = None

        self._build()
        self._apply_settings(settings)
        self._size_to_content()

    # ----- construction -----------------------------------------------------

    def _muted_label(self, text: str, name: str = "") -> QLabel:
        lab = _plain(QLabel(self))
        lab.setText(text)
        lab.setWordWrap(True)
        lab.setStyleSheet("color: %s;" % _css(self._colors.muted))
        f = QFont(lab.font())
        if f.pointSizeF() > 0:
            f.setPointSizeF(max(8.0, f.pointSizeF() - 1))
        lab.setFont(f)
        if name:
            lab.setObjectName(name)
        return lab

    def _heading(self, text: str) -> QLabel:
        lab = _plain(QLabel(self))
        lab.setText(text)
        f = QFont(lab.font())
        f.setWeight(QFont.Weight.DemiBold)
        if f.pointSizeF() > 0:
            f.setPointSizeF(f.pointSizeF() + 0.5)
        lab.setFont(f)
        lab.setWordWrap(True)
        return lab

    def _build(self) -> None:
        c = self._colors
        self.setStyleSheet(
            """
            QFrame#field_rows, QFrame#field_picker {
                border: 1px solid %(border)s; border-radius: 8px;
            }
            QFrame#field_rows QLabel, QFrame#field_picker QLabel { border: none; }
            QFrame#row_separator { border: none; border-top: 1px solid %(soft)s; }
            QFrame#tag_chip {
                border: 1px solid %(border)s; border-radius: 6px; background: %(chip)s;
            }
            QFrame#tag_chip QLabel { border: none; background: transparent; }
            QToolButton#remove_field_button, QToolButton#remove_tag_button {
                border: 1px solid transparent; border-radius: 4px; padding: 1px 4px;
                color: %(muted)s; background: transparent;
            }
            QToolButton#remove_field_button:hover, QToolButton#remove_tag_button:hover {
                border-color: %(border)s;
            }
            QToolButton#remove_field_button:focus, QToolButton#remove_tag_button:focus {
                border: 1px solid %(focus)s;
            }
            QPushButton#add_field_button {
                border: 1px dashed %(border)s; border-radius: 6px; padding: 5px 10px;
                color: %(text)s; background: transparent;
            }
            QPushButton#add_field_button:focus { border: 1px solid %(focus)s; }
            QListWidget#tag_list::item, QListWidget#field_matches::item { padding: 3px 6px; }
            QListWidget#tag_list::item:selected, QListWidget#field_matches::item:selected {
                background: %(accent)s; color: %(on)s;
            }
            QPushButton#save_button {
                background: %(accent)s; color: %(on)s; font-weight: 600;
                border: 1px solid %(accent)s; border-radius: 6px; padding: 5px 18px;
            }
            QPushButton#save_button:focus { border: 2px solid %(focus)s; padding: 4px 17px; }
            QPushButton#save_button:pressed { background: %(accent_dark)s; }
            """
            % {
                "border": _css(c.border),
                "soft": _css(c.border_soft),
                "chip": _css(c.chip_bg),
                "muted": _css(c.muted),
                "focus": _css(c.focus),
                "text": _css(c.text),
                "accent": ACCENT_COLOR,
                "accent_dark": _css(c.accent.darker(125)),
                "on": ON_TEXT,
            }
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.scroll = QScrollArea(self)
        self.scroll.setObjectName("settings_scroll")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget(self.scroll)
        body.setObjectName("settings_body")
        self.body = body
        lay = QVBoxLayout(body)
        lay.setContentsMargins(20, 18, 20, 12)
        lay.setSpacing(20)
        self.scroll.setWidget(body)
        outer.addWidget(self.scroll, 1)

        lay.addLayout(self._build_fields_section())
        lay.addLayout(self._build_tags_section())
        lay.addLayout(self._build_styling_section())
        lay.addStretch(1)

        # Bottom bar (outside the scroll area so it is always visible).
        line = QFrame(self)
        line.setObjectName("row_separator")
        line.setFixedHeight(1)
        outer.addWidget(line)
        bar = QHBoxLayout()
        bar.setContentsMargins(20, 12, 20, 14)
        bar.setSpacing(8)
        self.restore_button = QPushButton("Restore defaults", self)
        self.restore_button.setObjectName("restore_button")
        self.restore_button.setAutoDefault(False)
        self.restore_button.setToolTip("Put back the add-on's default choices (not saved until you press Save)")
        self.restore_button.clicked.connect(self.restore_defaults)
        bar.addWidget(self.restore_button)
        bar.addStretch(1)
        self.cancel_button = QPushButton("Cancel", self)
        self.cancel_button.setObjectName("cancel_button")
        self.cancel_button.setAutoDefault(False)
        self.cancel_button.clicked.connect(self.reject)
        bar.addWidget(self.cancel_button)
        self.save_button = QPushButton("Save", self)
        self.save_button.setObjectName("save_button")
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self.accept)
        bar.addWidget(self.save_button)
        outer.addLayout(bar)

        for w in (self.tag_input, self.tag_list, self.field_search, self.field_matches):
            w.installEventFilter(self)

    def _build_fields_section(self) -> QVBoxLayout:
        sec = QVBoxLayout()
        sec.setSpacing(8)
        sec.addWidget(self._heading(FIELDS_HEADING))
        sec.addWidget(self._muted_label(FIELDS_HELP))

        self.field_rows_frame = QFrame(self)
        self.field_rows_frame.setObjectName("field_rows")
        self._rows_layout = QVBoxLayout(self.field_rows_frame)
        self._rows_layout.setContentsMargins(1, 1, 1, 1)
        self._rows_layout.setSpacing(0)
        sec.addWidget(self.field_rows_frame)
        self.no_fields_label = self._muted_label(NO_FIELDS_TEXT, "no_fields_label")
        self.no_fields_label.hide()
        sec.addWidget(self.no_fields_label)

        self.add_field_button = QPushButton("+ Add field", self)
        self.add_field_button.setObjectName("add_field_button")
        self.add_field_button.setAutoDefault(False)
        self.add_field_button.setAccessibleName("Add field")
        self.add_field_button.setToolTip("Add a field from your note types")
        self.add_field_button.clicked.connect(self.open_field_picker)
        row = QHBoxLayout()
        row.addWidget(self.add_field_button)
        row.addStretch(1)
        sec.addLayout(row)

        picker = QFrame(self)
        picker.setObjectName("field_picker")
        self.field_picker = picker
        pl = QVBoxLayout(picker)
        pl.setContentsMargins(10, 10, 10, 10)
        pl.setSpacing(6)
        lab = _plain(QLabel("Add a field from your note types", picker))
        f = QFont(lab.font())
        f.setWeight(QFont.Weight.DemiBold)
        lab.setFont(f)
        pl.addWidget(lab)
        line = QHBoxLayout()
        line.setSpacing(6)
        self.field_search = QLineEdit(picker)
        self.field_search.setObjectName("field_search")
        self.field_search.setPlaceholderText("Start typing a field name…")
        self.field_search.setAccessibleName("Search fields to add")
        self.field_search.setClearButtonEnabled(True)
        self.field_search.textChanged.connect(self._refresh_field_matches)
        lab.setBuddy(self.field_search)
        line.addWidget(self.field_search, 1)
        self.field_done_button = QPushButton("Done", picker)
        self.field_done_button.setObjectName("field_done_button")
        self.field_done_button.setAutoDefault(False)
        self.field_done_button.clicked.connect(self.close_field_picker)
        line.addWidget(self.field_done_button)
        pl.addLayout(line)
        self.field_matches = QListWidget(picker)
        self.field_matches.setObjectName("field_matches")
        self.field_matches.setAccessibleName("Fields you can add")
        self.field_matches.setToolTip("Click a field to add it")
        self.field_matches.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.field_matches.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.field_matches.itemClicked.connect(lambda item: self._add_field_from_list(item.text()))
        pl.addWidget(self.field_matches)
        self.field_hint = self._muted_label("", "field_hint")
        pl.addWidget(self.field_hint)
        picker.hide()
        sec.addWidget(picker)
        return sec

    def _build_tags_section(self) -> QVBoxLayout:
        sec = QVBoxLayout()
        sec.setSpacing(8)
        sec.addWidget(self._heading(TAGS_HEADING))
        sec.addWidget(self._muted_label(TAGS_HELP, "tags_help"))

        self.tag_chips_widget = QWidget(self)
        self.tag_chips_widget.setObjectName("tag_chips")
        self._chips_layout = _FlowLayout(self.tag_chips_widget)
        sec.addWidget(self.tag_chips_widget)
        self.no_tags_label = self._muted_label("No protected tags yet.", "no_tags_label")
        sec.addWidget(self.no_tags_label)

        line = QHBoxLayout()
        line.setSpacing(6)
        self.tag_input = QLineEdit(self)
        self.tag_input.setObjectName("tag_input")
        self.tag_input.setPlaceholderText("Start typing a tag from your collection…")
        self.tag_input.setAccessibleName("Add a protected tag")
        self.tag_input.setAccessibleDescription(
            "Type to list matching tags. Up and Down move through the list, "
            "Enter adds the highlighted tag, or click a tag to add it."
        )
        self.tag_input.textChanged.connect(self._refresh_tag_matches)
        line.addWidget(self.tag_input, 1)
        sec.addLayout(line)

        self.tag_list = QListWidget(self)
        self.tag_list.setObjectName("tag_list")
        self.tag_list.setAccessibleName("Matching tags")
        self.tag_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tag_list.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        # One click adds the tag: no highlight-then-confirm step.
        self.tag_list.itemClicked.connect(self._on_tag_clicked)
        self.tag_list.hide()
        sec.addWidget(self.tag_list)

        self.tag_hint = self._muted_label("", "tag_hint")
        self.tag_hint.setAccessibleName("Tag hint")
        self.tag_hint.hide()
        sec.addWidget(self.tag_hint)
        return sec

    def _build_styling_section(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(self._heading(STYLING_HEADING))
        text.addWidget(self._muted_label(STYLING_HELP))
        row.addLayout(text, 1)
        self.styling_switch = ToggleSwitch(self._colors, self)
        self.styling_switch.setObjectName("styling_switch")
        self.styling_switch.setAccessibleName(STYLING_HEADING)
        self.styling_switch.setToolTip(STYLING_HEADING)
        row.addWidget(self.styling_switch, 0, Qt.AlignmentFlag.AlignVCenter)
        return row

    def _size_to_content(self) -> None:
        self.body.adjustSize()
        width = 600
        height = self.body.layout().totalHeightForWidth(width) + 70
        screen = self.screen() if hasattr(self, "screen") else None
        if screen is not None:
            height = min(height, int(screen.availableGeometry().height() * 0.9))
        self.setMinimumWidth(480)
        self.resize(width, max(420, height))

    # ----- state ------------------------------------------------------------

    def _apply_settings(self, settings: Settings) -> None:
        for row in list(self._rows):
            self._drop_row(row)
        for fc in settings.fields:
            self._append_row(fc.name, fc.keep)
        self._show_rows_or_empty_note()
        self._tags = list(settings.protected_tags)
        self._rebuild_chips()
        self.styling_switch.setChecked(bool(settings.update_note_types))
        self.tag_input.clear()
        self._set_tag_hint("")
        self.close_field_picker()

    def result_settings(self) -> Settings:
        """The choices currently shown (the saved ones after accept())."""
        if self._result is not None:
            return self._result
        return self._current_settings()

    def _current_settings(self) -> Settings:
        return Settings(
            fields=tuple(r.choice() for r in self._rows),
            protected_tags=tuple(self._tags),
            update_note_types=self.styling_switch.isChecked(),
        )

    def accept(self) -> None:
        self._result = self._current_settings()
        super().accept()

    def restore_defaults(self) -> None:
        self._apply_settings(default_settings())
        self.restore_button.setFocus()

    # ----- fields -----------------------------------------------------------

    def field_rows(self) -> List[FieldRow]:
        return list(self._rows)

    def row_for(self, name: str) -> Optional[FieldRow]:
        key = norm_field(name)
        for r in self._rows:
            if norm_field(r.name) == key:
                return r
        return None

    def _append_row(self, name: str, keep: bool) -> FieldRow:
        if self._rows:
            sep = QFrame(self.field_rows_frame)
            sep.setObjectName("row_separator")
            sep.setFixedHeight(1)
            self._rows_layout.addWidget(sep)
        row = FieldRow(name, keep, self._colors, self.field_rows_frame)
        row.remove_requested.connect(self.remove_field)
        self._rows_layout.addWidget(row)
        self._rows.append(row)
        self._show_rows_or_empty_note()
        return row

    def _show_rows_or_empty_note(self) -> None:
        self.field_rows_frame.setVisible(bool(self._rows))
        self.no_fields_label.setVisible(not self._rows)

    def _drop_row(self, row: FieldRow) -> None:
        idx = self._rows_layout.indexOf(row)
        self._rows.remove(row)
        # Remove the separator that belongs to this row (above it, or the one
        # below if it was the first row).
        sep_idx = idx - 1 if idx > 0 else (1 if self._rows_layout.count() > 1 else -1)
        for w in (row, self._rows_layout.itemAt(sep_idx).widget() if sep_idx >= 0 else None):
            if w is None:
                continue
            self._rows_layout.removeWidget(w)
            w.hide()
            w.setParent(None)
            w.deleteLater()
        self._show_rows_or_empty_note()

    def remove_field(self, name: str) -> bool:
        row = self.row_for(name)
        if row is None:
            return False
        self._drop_row(row)
        self._refresh_field_matches()
        self.add_field_button.setFocus()
        return True

    def open_field_picker(self) -> None:
        self.add_field_button.hide()
        self.field_picker.show()
        self.field_search.clear()
        self._refresh_field_matches()
        self.field_search.setFocus()

    def close_field_picker(self) -> None:
        had_focus = self.field_picker.isAncestorOf(QApplication.focusWidget()) if QApplication.focusWidget() else False
        self.field_picker.hide()
        self.field_search.blockSignals(True)
        self.field_search.clear()
        self.field_search.blockSignals(False)
        self._set_field_hint("")
        self.add_field_button.show()
        if had_focus:
            self.add_field_button.setFocus()

    def _refresh_field_matches(self, *_args: Any) -> None:
        query = self.field_search.text()
        self._field_matches = filter_fields(query, self._all_fields, [r.name for r in self._rows])
        self.field_matches.clear()
        self.field_matches.addItems(self._field_matches)
        target = _pick_target(query, self._field_matches, norm_field)
        if target is not None:
            self.field_matches.setCurrentRow(self._field_matches.index(target))
        self._fit_list(self.field_matches, 6)
        if self._field_matches:
            self._set_field_hint("")
        elif query.strip() and self.row_for(query) is not None:
            self._set_field_hint('"%s" is already in the list.' % self.row_for(query).name)
        else:
            self._set_field_hint("No other fields in your note types match.")
        self.field_matches.setVisible(bool(self._field_matches))

    def _set_field_hint(self, text: str) -> None:
        self.field_hint.setText(text)
        self.field_hint.setVisible(bool(text))

    def _field_target(self) -> Optional[str]:
        item = self.field_matches.currentItem()
        if item is not None and item.isSelected():
            return item.text()
        return _pick_target(self.field_search.text(), self._field_matches, norm_field)

    def add_field(self, name: str) -> bool:
        """Add a row for `name` if it is one of the user's field names and not
        already a row. New rows start as "Take the update's"."""
        known = {norm_field(n): n for n in reversed(self._all_fields)}
        key = norm_field(name)
        if key not in known:
            self._set_field_hint("Only fields from your note types can be added.")
            return False
        if self.row_for(name) is not None:
            self._set_field_hint('"%s" is already in the list.' % self.row_for(name).name)
            return False
        spelled = known[key]
        self._append_row(spelled, False)
        self.field_search.blockSignals(True)
        self.field_search.clear()
        self.field_search.blockSignals(False)
        self._refresh_field_matches()
        self._set_field_hint('Added "%s". It starts as "%s".' % (spelled, TAKE_LABEL))
        return True

    def _add_field_from_list(self, name: str) -> None:
        if self.add_field(name):
            self.field_search.setFocus()

    def _field_enter(self) -> None:
        target = self._field_target()
        if target is not None:
            self.add_field(target)
        elif self._field_matches:
            self._set_field_hint("Keep typing, or pick a field in the list.")
        else:
            self._set_field_hint("Only fields from your note types can be added.")

    # ----- tags -------------------------------------------------------------

    def protected_tags(self) -> List[str]:
        return list(self._tags)

    def tag_chips(self) -> List[TagChip]:
        out = []
        for i in range(self._chips_layout.count()):
            w = self._chips_layout.itemAt(i).widget()
            if isinstance(w, TagChip):
                out.append(w)
        return out

    def tag_matches(self) -> List[str]:
        """Every tag matching the current text (the list may show fewer)."""
        return list(self._tag_matches)

    def _rebuild_chips(self) -> None:
        while self._chips_layout.count():
            item = self._chips_layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        for tag in self._tags:
            chip = TagChip(tag, self.tag_chips_widget)
            chip.remove_requested.connect(self.remove_tag)
            self._chips_layout.addWidget(chip)
            chip.show()
        self.tag_chips_widget.setVisible(bool(self._tags))
        self.no_tags_label.setVisible(not self._tags)
        self._chips_layout.invalidate()
        # Keep the Tab order: chips' ✕ buttons come right before the text box.
        prev: Optional[QWidget] = None
        for chip in self.tag_chips():
            if prev is not None:
                QWidget.setTabOrder(prev, chip.remove_button)
            prev = chip.remove_button
        if prev is not None:
            QWidget.setTabOrder(prev, self.tag_input)

    def _is_protected(self, tag: str) -> bool:
        key = norm_tag(tag)
        return any(norm_tag(t) == key for t in self._tags)

    def _refresh_tag_matches(self, *_args: Any) -> None:
        query = self.tag_input.text()
        self._tag_matches = filter_tags(query, self._all_tags, self._tags)
        shown = self._tag_matches[:MAX_TAGS_SHOWN]
        self.tag_list.blockSignals(True)
        self.tag_list.clear()
        self.tag_list.addItems(shown)
        # The first match is highlighted, ready for Enter. The exception: the
        # typed text is itself an already protected tag, so Enter must not add
        # a different (sub-) tag by accident.
        if shown and not self._is_protected(query):
            self.tag_list.setCurrentRow(0)
        self.tag_list.blockSignals(False)
        self._fit_list(self.tag_list, 8)
        self.tag_list.setVisible(bool(shown))
        if not query.strip():
            self._set_tag_hint("")
        elif self._is_protected(query):
            self._set_tag_hint('"%s" is already protected.' % query.strip())
        elif not self._tag_matches:
            self._set_tag_hint(
                'No tag in your collection matches "%s". Only existing tags can be added.'
                % query.strip()
            )
        elif len(self._tag_matches) > MAX_TAGS_SHOWN:
            self._set_tag_hint(
                "Showing the first %d of %d matching tags. Keep typing to narrow the list."
                % (MAX_TAGS_SHOWN, len(self._tag_matches))
            )
        else:
            self._set_tag_hint("")

    def _set_tag_hint(self, text: str) -> None:
        """The line under the tag box: shown only when there is something to say."""
        self.tag_hint.setText(text)
        self.tag_hint.setVisible(bool(text))

    def _fit_list(self, lst: QListWidget, max_rows: int) -> None:
        rows = min(max(lst.count(), 1), max_rows)
        row_h = lst.sizeHintForRow(0) if lst.count() else lst.fontMetrics().height() + 8
        lst.setFixedHeight(rows * row_h + 2 * lst.frameWidth() + 4)

    def tag_target(self) -> Optional[str]:
        """The tag Enter would add now (the highlighted one), or None."""
        item = self.tag_list.currentItem()
        if item is not None and item.isSelected() and self.tag_input.text().strip():
            return item.text()
        return None

    def _on_tag_clicked(self, item: QListWidgetItem) -> None:
        if self.add_tag(item.text()):
            self.tag_input.setFocus()

    def add_tag(self, tag: str) -> bool:
        """Protect `tag` if it exists in the collection; returns True if added."""
        key = norm_tag(tag)
        existing = None
        for t in self._all_tags:
            if norm_tag(t) == key:
                existing = t
                break
        if existing is None:
            self._set_tag_hint(
                'No tag in your collection matches "%s". Only existing tags can be added.' % tag.strip()
            )
            return False
        if self._is_protected(existing):
            self._set_tag_hint('"%s" is already protected.' % existing)
            return False
        self._tags.append(existing)
        self._rebuild_chips()
        self.tag_input.blockSignals(True)
        self.tag_input.clear()
        self.tag_input.blockSignals(False)
        self._refresh_tag_matches()
        return True

    def select_tag(self) -> bool:
        """Enter: add the highlighted tag."""
        target = self.tag_target()
        if target is not None:
            ok = self.add_tag(target)
            if ok:
                self.tag_input.setFocus()
            return ok
        if not self.tag_input.text().strip():
            self._set_tag_hint("")
        elif self._is_protected(self.tag_input.text()):
            self._set_tag_hint('"%s" is already protected.' % self.tag_input.text().strip())
        elif self._tag_matches:
            self._set_tag_hint("Pick a tag in the list.")
        else:
            self._set_tag_hint(
                'No tag in your collection matches "%s". Only existing tags can be added.'
                % self.tag_input.text().strip()
            )
        return False

    def remove_tag(self, tag: str) -> bool:
        key = norm_tag(tag)
        before = len(self._tags)
        self._tags = [t for t in self._tags if norm_tag(t) != key]
        if len(self._tags) == before:
            return False
        self._rebuild_chips()
        self._refresh_tag_matches()
        self.tag_input.setFocus()
        return True

    def _move_list_selection(self, lst: QListWidget, step: int) -> None:
        n = lst.count()
        if not n:
            return
        item = lst.currentItem()
        cur = lst.currentRow() if (item is not None and item.isSelected()) else -1
        if cur < 0:
            new = 0
        else:
            new = max(0, min(n - 1, cur + step))
        lst.setCurrentRow(new)
        lst.scrollToItem(lst.item(new))

    # ----- keyboard ---------------------------------------------------------

    def eventFilter(self, obj: Any, event: Any) -> bool:  # noqa: N802
        if event.type() != QEvent.Type.KeyPress:
            return super().eventFilter(obj, event)
        key = event.key()
        if obj is self.tag_input or obj is self.tag_list:
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up) and obj is self.tag_input:
                self._move_list_selection(self.tag_list, 1 if key == Qt.Key.Key_Down else -1)
                return True
            if key in _ENTER_KEYS:
                self.select_tag()
                return True
            if key == Qt.Key.Key_Escape and self.tag_input.text():
                self.tag_input.clear()
                self._set_tag_hint("")
                self.tag_input.setFocus()
                return True
        if obj is self.field_search or obj is self.field_matches:
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up) and obj is self.field_search:
                self._move_list_selection(self.field_matches, 1 if key == Qt.Key.Key_Down else -1)
                return True
            if key in _ENTER_KEYS:
                self._field_enter()
                return True
            if key == Qt.Key.Key_Escape:
                if self.field_search.text():
                    self.field_search.clear()
                else:
                    self.close_field_picker()
                return True
        return super().eventFilter(obj, event)


# ---------------------------------------------------------------------------
# Anki glue (the only code that touches `mw`)


def load_settings(mw: Any) -> Settings:
    """The saved choices from the add-on config (defaults if missing/bad)."""
    try:
        cfg = mw.addonManager.getConfig(_addon_key())
    except Exception:
        cfg = None
    return settings_from_config(cfg)


def save_settings(mw: Any, settings: Settings) -> None:
    """Write `settings` to the add-on config, keeping any unknown keys."""
    key = _addon_key()
    current = mw.addonManager.getConfig(key)
    cfg: Dict[str, Any] = dict(current) if isinstance(current, dict) else {}
    cfg.update(settings_to_config(settings))
    mw.addonManager.writeConfig(key, cfg)


def _collection_field_names(col: Any) -> List[str]:
    """Every field name in the user's note types (first spelling wins)."""
    names: List[str] = []
    seen = set()
    for entry in col.models.all_names_and_ids():
        nt = col.models.get(entry.id)
        if not nt:
            continue
        for fld in nt.get("flds", []):
            name = fld.get("name", "")
            key = norm_field(name)
            if key and key not in seen:
                seen.add(key)
                names.append(name)
    return names


def _collection_tags(col: Any) -> List[str]:
    return list(col.tags.all())


def _code(value: Any) -> int:
    """PyQt6 returns exec() codes as int but DialogCode is an Enum."""
    return int(getattr(value, "value", value))


_GEOM_KEY = "special_fields_by_ankoma_settings"


def open_settings(mw: Any, parent: Optional[QWidget] = None) -> Optional[Settings]:
    """Show the settings window. On Save, write the config and return the new
    Settings; return None if the user cancels.

    `parent` defaults to `mw`; the import flow can pass its own dialog.
    """
    settings = load_settings(mw)
    col = getattr(mw, "col", None)
    fields: List[str] = []
    tags: List[str] = []
    if col is not None:
        fields = _collection_field_names(col)
        tags = _collection_tags(col)
    if parent is None and isinstance(mw, QWidget):
        parent = mw
    dlg = SettingsDialog(parent, settings, fields, tags)
    try:
        from aqt.utils import restoreGeom

        restoreGeom(dlg, _GEOM_KEY)
    except Exception:
        pass
    accepted = _code(dlg.exec()) == _code(QDialog.DialogCode.Accepted)
    try:
        from aqt.utils import saveGeom

        saveGeom(dlg, _GEOM_KEY)
    except Exception:
        pass
    if not accepted:
        return None
    new = dlg.result_settings()
    save_settings(mw, new)
    return new
