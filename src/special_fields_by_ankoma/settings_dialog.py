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
    info_button       an (i) bubble (property "topic": "Fields",
                      "Protected tags" or a switch's title); the dialog's
                      `info_buttons` dict has them by "fields", "tags",
                      "styling", "scheduling", "presets"
    tag_input, tag_list, tag_hint
    tag_blocks        container of one `TagBlock` per protected tag, under
                      the tag box ("tag_block", property "tag"; `TagChip`
                      is the old name of the class)
    tag_header        a tag's line: tag_expand_button (the arrowhead),
                      tag_chip_label (the tag, elided in the middle),
                      tag_summary ("keeps Header, Personal Notes"),
                      remove_tag_button (the ✕)
    tag_table         the tag's table, shown when the tag is open:
                      tag_field_rows holding one "tag_field_row" (property
                      "field_name") per field, each with a compact toggle,
                      and tag_keep_all ("Keep every field")
    styling_switch    "Update card templates and styling"
    scheduling_switch "Import learning progress"
    presets_switch    "Import deck options"
    restore_button, cancel_button, save_button
    discard_question  the "Discard your changes?" box (discard_button,
                      keep_editing_button), shown by `confirm_discard`
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
    TagRule,
    norm_field,
    norm_tag,
)

WINDOW_TITLE = ADDON_NAME + ": Settings"
KEEP_LABEL = "Keep mine"
TAKE_LABEL = "Take the update's"
FIELDS_HEADING = "Fields"
FIELDS_INFO = (
    "Choose what happens to each field when an update changes a card you already "
    "have. Keep mine: your text in that field stays. Take the update's: the "
    "update's text replaces yours. Fields are matched by name, so their order "
    "doesn't matter, and a field a note type doesn't have is skipped. A field that "
    "isn't listed takes the update's text, unless the update leaves that field "
    "empty on every card."
)
NO_FIELDS_TEXT = (
    "No fields listed. Every field takes the update's content. Where the update "
    "leaves a field empty on every card, your text in it stays."
)
TAGS_HEADING = "Protected tags"
TAGS_INFO = (
    "An update replaces a card's tags with the update's. A protected tag is never "
    "removed from your cards; its sub-tags are covered too. Cards with a protected "
    "tag follow that tag's own field choices instead of the choices above: open a "
    "tag to set them. A new tag starts with the previous tag's choices plus every "
    "field you keep above; after that, a tag's choices change only when you change "
    "them. A card with several protected tags keeps a field if any of them keeps it."
)
KEEP_EVERY_FIELD_LABEL = "Keep every field"
STYLING_HEADING = "Update card templates and styling"
STYLING_INFO = (
    "On: an update may replace your card templates and styling with its own. "
    "Off: yours stay exactly as they are. Card content updates either way."
)
SCHEDULING_HEADING = "Import learning progress"
SCHEDULING_INFO = (
    "On: cards that are new to your collection arrive with the scheduling and "
    "review history saved in the file. Cards you already have always keep your "
    "own progress. Off: new cards arrive as new. Useful for moving a deck to "
    "another computer without syncing."
)
# Anki calls these "deck presets"; the author found "deck options" clearer.
PRESETS_HEADING = "Import deck options"
PRESETS_INFO = (
    "On: deck options saved in the file (daily limits, learning steps, FSRS "
    "settings) come in as new presets, and the file's decks use them. Options "
    "you already have are never changed. Off: no deck options are imported."
)
# The (i) texts wrap at about this many pixels, so a bubble is never wide.
INFO_WRAP_WIDTH = 340
# The tag column of the collapsed tag lines is at most this wide.
TAG_COLUMN_WIDTH = 190
ON_TEXT = "#FFFFFF"
DISCARD_QUESTION = "Discard your changes?"
DISCARD_LABEL = "Discard"
KEEP_EDITING_LABEL = "Keep editing"

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


def confirm_discard(parent: Optional[QWidget]) -> bool:
    """Ask "Discard your changes?"; True if the user chose "Discard".

    "Keep editing" is the default button and the Esc choice, so a second Esc
    never discards. Tests replace this function or answer the box (object
    name "discard_question") from a timer."""
    box = QMessageBox(parent)
    box.setObjectName("discard_question")
    box.setWindowTitle(ADDON_NAME)
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setText(DISCARD_QUESTION)
    box.setIcon(QMessageBox.Icon.Question)
    discard = box.addButton(DISCARD_LABEL, QMessageBox.ButtonRole.DestructiveRole)
    discard.setObjectName("discard_button")
    keep = box.addButton(KEEP_EDITING_LABEL, QMessageBox.ButtonRole.RejectRole)
    keep.setObjectName("keep_editing_button")
    box.setDefaultButton(keep)
    box.setEscapeButton(keep)
    try:
        box.exec()
        return box.clickedButton() is discard
    finally:
        box.deleteLater()


def choices_summary(settings: Settings) -> List[Tuple[str, str]]:
    """Rows for the "Your saved choices" box, in display order."""
    kept = [f.name for f in settings.fields if f.keep]
    entries = tag_summary_entries(settings)
    return [
        ("Fields you keep", ", ".join(kept) if kept else "None"),
        ("Protected tags", ", ".join(entries) if entries else "None"),
        ("Tags", "Replaced with the update's"),
        ("Card styling", "Update" if settings.update_note_types else "Keep mine"),
        (
            "Learning progress",
            "Imported for new cards" if settings.import_scheduling else "Not imported",
        ),
        ("Deck options", "Imported" if settings.import_deck_presets else "Not imported"),
    ]


def keeps_text(fields: Sequence[str], keep_all: bool) -> str:
    """A tag's table in a few words: "keeps Header, Personal Notes",
    "keeps every field" or "keeps no fields"."""
    if keep_all:
        return "keeps every field"
    if not fields:
        return "keeps no fields"
    return "keeps " + ", ".join(fields)


def tag_summary_entries(settings: Settings) -> List[str]:
    """One entry per protected tag for the summary: "#edited (keeps Header,
    Personal Notes)", "(keeps every field)", "(keeps no fields)"; a tag
    saved by an earlier beta, with no frozen table yet, by name only."""
    out = []
    for tag in settings.protected_tags:
        rule = settings.rule_for(tag)
        if rule is None or not rule.is_frozen():
            out.append(tag)
        else:
            out.append("%s (%s)" % (tag, keeps_text(rule.fields or (), rule.keep_all)))
    return out


def split_tag_summary(value: str) -> List[str]:
    """The entries of a "Protected tags" summary value, as joined by
    `choices_summary`. Anki tags never contain a space, so an entry is a tag
    up to the first space, then, if it follows, "(keeps …)" up to the first
    ")" that ends the value or is followed by ", "."""
    out: List[str] = []
    i, n = 0, len(value)
    while i < n:
        j = i
        while j < n and value[j] != " " and not value.startswith(", ", j):
            j += 1
        if value.startswith(" (", j):
            k = j + 2
            while k < n:
                if value[k] == ")" and (k + 1 == n or value.startswith(", ", k + 1)):
                    break
                k += 1
            j = min(k + 1, n)
        out.append(value[i:j])
        i = j + 2 if value.startswith(", ", j) else j + 1
    return [e for e in out if e]


def wrap_plain(text: str, fm: QFontMetrics, width: int) -> str:
    """`text` broken into lines no wider than `width` pixels (at spaces), for
    a plain-text tooltip: Qt does not wrap plain tooltips by itself."""
    lines: List[str] = []
    line = ""
    for word in text.split():
        trial = word if not line else line + " " + word
        if line and fm.horizontalAdvance(trial) > width:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return "\n".join(lines)


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


def _segment_css(colors: _Colors, selected: bool, side: str, compact: bool = False) -> str:
    """Stylesheet for one side of a two-part toggle.

    The selected side is accent-filled with white text; the other is plain.
    Border + padding add up to the same size with and without focus, so the
    row doesn't jump when focus moves. `compact`: the smaller toggle of a
    tag's table.
    """
    v, h = (2, 9) if compact else (5, 12)
    if selected:
        bg, fg, bd, weight = colors.accent, QColor(ON_TEXT), colors.accent, 600
    else:
        bg, fg, bd, weight = colors.base, colors.plain_text, colors.border, 400
    if side == "left":
        radius = "border-top-left-radius: 6px; border-bottom-left-radius: 6px;"
        normal = "border: 1px solid %s; padding: %dpx %dpx;" % (_css(bd), v, h)
        focus = "border: 2px solid %s; padding: %dpx %dpx;" % (_css(colors.focus), v - 1, h - 1)
    else:
        radius = "border-top-right-radius: 6px; border-bottom-right-radius: 6px;"
        normal = "border: 1px solid %s; border-left: none; padding: %dpx %dpx %dpx %dpx;" % (_css(bd), v, h, v, h + 1)
        focus = "border: 2px solid %s; padding: %dpx %dpx;" % (_css(colors.focus), v - 1, h - 1)
    return (
        "QPushButton { background: %s; color: %s; font-weight: %d; margin: 0; %s %s }"
        "QPushButton:focus { %s }"
        % (_css(bg), _css(fg), weight, radius, normal, focus)
    )


# ---------------------------------------------------------------------------
# Small widgets


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


class _ElidingDelegate(QStyledItemDelegate):
    """Item delegate for the tag and field lists: every row is only as wide
    as the list, so the view never needs a horizontal scroll bar and a long
    name is elided (in the middle, by the view's text elide mode) instead of
    being cut off. The item's own text stays the full name."""

    def sizeHint(self, option: Any, index: Any) -> QSize:  # noqa: N802
        hint = super().sizeHint(option, index)
        return QSize(1, hint.height())


class FieldToggle(QWidget):
    """Two-part toggle: "Keep mine" | "Take the update's"."""

    changed = pyqtSignal(bool)

    def __init__(
        self, name: str, keep: bool, colors: _Colors, parent: Optional[QWidget] = None, compact: bool = False
    ) -> None:
        super().__init__(parent)
        self.setObjectName("field_toggle")
        self._colors = colors
        self._compact = compact
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
        font = QFont(self.font())
        if compact and font.pointSizeF() > 0:
            font.setPointSizeF(max(8.0, font.pointSizeF() - 1))
        bold = QFont(font)
        bold.setWeight(QFont.Weight.DemiBold)
        fm = QFontMetrics(bold)
        for btn, label in ((self.keep_button, KEEP_LABEL), (self.take_button, TAKE_LABEL)):
            if compact:
                btn.setFont(font)
            btn.setCheckable(True)
            btn.setAutoDefault(False)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setAccessibleName("%s: %s" % (name, label))
            # Wide enough for the bold (selected) text so toggling doesn't
            # change the row's width.
            btn.setMinimumWidth(fm.horizontalAdvance(label) + (24 if compact else 32))
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
        self.keep_button.setStyleSheet(_segment_css(self._colors, keep, "left", self._compact))
        self.take_button.setStyleSheet(_segment_css(self._colors, not keep, "right", self._compact))


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


class _ElidedLabel(QLabel):
    """A plain-text label that shows `full` elided in the middle when it is
    narrower than its text, so a long tag never widens the window. The
    tooltip always has the full text."""

    def __init__(self, full: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        _plain(self)
        self._full = full
        self.setToolTip(_plain_tooltip(full))
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setText(full)

    def full_text(self) -> str:
        return self._full

    def set_full_text(self, full: str) -> None:
        self._full = full
        self.setToolTip(_plain_tooltip(full))
        self.setText(full)
        self.updateGeometry()
        self._elide()

    def sizeHint(self) -> QSize:  # noqa: N802
        fm = self.fontMetrics()
        return QSize(fm.horizontalAdvance(self._full) + 4, super().sizeHint().height())

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(min(self.sizeHint().width(), 60), super().minimumSizeHint().height())

    def resizeEvent(self, event: Any) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._elide()

    def _elide(self) -> None:
        width = self.contentsRect().width()
        text = self._full
        if width > 0 and self.fontMetrics().horizontalAdvance(text) > width:
            text = self.fontMetrics().elidedText(text, Qt.TextElideMode.ElideMiddle, width)
        if text != self.text():
            self.setText(text)


class InfoButton(QToolButton):
    """A small round "i" after a heading or a switch's title. Its text shows
    on hover (as a tooltip), and also when the button is clicked or, while
    it has focus, activated with Enter or Space, so it works without a
    mouse. The text is also the button's accessible description. Plain
    text, broken into short lines so the bubble is never wide."""

    def __init__(self, topic: str, text: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("info_button")
        self.setProperty("topic", topic)
        self._text = text
        self.setText("i")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAccessibleName("About %s" % topic)
        self.setAccessibleDescription(text)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setToolTip(self.bubble_text())
        self.clicked.connect(self.show_bubble)

    def info_text(self) -> str:
        return self._text

    def bubble_text(self) -> str:
        """The text as the bubble shows it: plain, in lines of at most
        INFO_WRAP_WIDTH pixels in the tooltip font."""
        return wrap_plain(self._text, QFontMetrics(QToolTip.font()), INFO_WRAP_WIDTH)

    def sizeHint(self) -> QSize:  # noqa: N802
        d = max(18, self.fontMetrics().height() + 2)
        return QSize(d, d)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return self.sizeHint()

    def show_bubble(self) -> None:
        """Show the text under the button (click, Enter or Space)."""
        QToolTip.showText(self.mapToGlobal(QPoint(0, self.height() + 4)), self.bubble_text(), self)

    def keyPressEvent(self, event: Any) -> None:  # noqa: N802
        # Space clicks a tool button already; Enter does not, and must not
        # reach the dialog's Save button either.
        if event.key() in _ENTER_KEYS:
            self.click()
            event.accept()
            return
        super().keyPressEvent(event)


class _ArrowButton(QToolButton):
    """The arrowhead that opens or closes a tag's table: Space clicks it, as
    any tool button; Enter does too (and never reaches the Save button)."""

    def keyPressEvent(self, event: Any) -> None:  # noqa: N802
        if event.key() in _ENTER_KEYS:
            self.click()
            event.accept()
            return
        super().keyPressEvent(event)


class TagFieldRow(QWidget):
    """One row of a protected tag's table: a field name and the same
    two-sided toggle as the main list, smaller. No ✕: fields are managed in
    the main list."""

    def __init__(self, name: str, tag: str, keep: bool, colors: _Colors, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("tag_field_row")
        self.setProperty("field_name", name)
        self.name = name
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 2, 6, 2)
        lay.setSpacing(6)
        self.label = _plain(QLabel(self))
        self.label.setObjectName("tag_field_name_label")
        self.label.setText(self.label.fontMetrics().elidedText(name, Qt.TextElideMode.ElideMiddle, 200))
        self.label.setToolTip(_plain_tooltip(name))
        lay.addWidget(self.label, 0)
        lay.addStretch(1)
        self.toggle = FieldToggle("%s on cards tagged %s" % (name, tag), keep, colors, self, compact=True)
        lay.addWidget(self.toggle, 0)


class TagBlock(QFrame):
    """One protected tag. Collapsed (the default): one line with the
    arrowhead button, the tag, a short summary ("keeps Header, Personal
    Notes") and ✕. Expanded: under that line, the tag's own table (the main
    list's rows, compact) and "Keep every field".

    The block only shows data; the dialog owns it and calls `set_rows()`
    and `set_summary()` after a change."""

    remove_requested = pyqtSignal(str)
    toggle_requested = pyqtSignal(str)

    def __init__(self, tag: str, colors: _Colors, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("tag_block")
        self.setProperty("tag", tag)
        self.setAccessibleName("Protected tag %s" % tag)
        self.tag = tag
        self._colors = colors
        self._rows: List[TagFieldRow] = []
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget(self)
        header.setObjectName("tag_header")
        header.installEventFilter(self)
        self.header = header
        top = QHBoxLayout(header)
        top.setContentsMargins(0, 1, 0, 1)
        top.setSpacing(6)
        eb = _ArrowButton(header)
        eb.setObjectName("tag_expand_button")
        eb.setAutoRaise(True)
        eb.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        eb.setCursor(Qt.CursorShape.PointingHandCursor)
        eb.clicked.connect(lambda: self.toggle_requested.emit(self.tag))
        self.expand_button = eb
        top.addWidget(eb, 0)
        self.label = _ElidedLabel(tag, header)
        self.label.setObjectName("tag_chip_label")
        f = QFont(self.label.font())
        f.setWeight(QFont.Weight.DemiBold)
        self.label.setFont(f)
        top.addWidget(self.label, 0)
        self.summary = _ElidedLabel("", header)
        self.summary.setObjectName("tag_summary")
        self.summary.setStyleSheet("color: %s;" % _css(colors.muted))
        top.addWidget(self.summary, 1)
        rb = QToolButton(header)
        rb.setObjectName("remove_tag_button")
        rb.setText("✕")
        rb.setAutoRaise(True)
        rb.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        rb.setCursor(Qt.CursorShape.PointingHandCursor)
        rb.setToolTip("Stop protecting this tag")
        rb.setAccessibleName("Remove protected tag %s" % tag)
        rb.clicked.connect(lambda: self.remove_requested.emit(self.tag))
        self.remove_button = rb
        top.addWidget(rb, 0)
        outer.addWidget(header)

        table = QWidget(self)
        table.setObjectName("tag_table")
        tl = QVBoxLayout(table)
        # Indented under the tag's name (past the arrowhead).
        tl.setContentsMargins(28, 2, 0, 8)
        tl.setSpacing(4)
        self.rows_frame = QFrame(table)
        self.rows_frame.setObjectName("tag_field_rows")
        self._rows_layout = QVBoxLayout(self.rows_frame)
        self._rows_layout.setContentsMargins(1, 3, 1, 3)
        self._rows_layout.setSpacing(0)
        tl.addWidget(self.rows_frame)
        self.keep_all_box = QCheckBox(KEEP_EVERY_FIELD_LABEL, table)
        self.keep_all_box.setObjectName("tag_keep_all")
        self.keep_all_box.setAccessibleName("Keep every field on cards tagged %s" % tag)
        self.keep_all_box.setToolTip(
            "Every field the card already has keeps your text; a field new to the card takes the update's"
        )
        tl.addWidget(self.keep_all_box)
        table.hide()
        self.table = table
        outer.addWidget(table)
        self._show_expanded(False)

    # ----- view --------------------------------------------------------

    def is_expanded(self) -> bool:
        return not self.table.isHidden()

    def _show_expanded(self, expanded: bool) -> None:
        self.table.setVisible(expanded)
        self.expand_button.setArrowType(
            Qt.ArrowType.DownArrow if expanded else Qt.ArrowType.RightArrow)
        state = "expanded" if expanded else "collapsed"
        self.expand_button.setAccessibleName("Field choices for %s, %s" % (self.tag, state))
        self.expand_button.setToolTip(
            "Hide this tag's field choices" if expanded else "Show this tag's field choices")

    def set_expanded(self, expanded: bool) -> None:
        self._show_expanded(expanded)

    def set_summary(self, text: str) -> None:
        self.summary.set_full_text(text)

    def rows(self) -> List[TagFieldRow]:
        return list(self._rows)

    def row_for(self, name: str) -> Optional[TagFieldRow]:
        key = norm_field(name)
        for row in self._rows:
            if norm_field(row.name) == key:
                return row
        return None

    def set_rows(self, rows: Sequence[Tuple[str, bool]]) -> List[TagFieldRow]:
        """Replace the table's rows with (field name, kept) pairs."""
        for row in self._rows:
            row.hide()
            self._rows_layout.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        self._rows = []
        for name, keep in rows:
            row = TagFieldRow(name, self.tag, keep, self._colors, self.rows_frame)
            self._rows_layout.addWidget(row)
            self._rows.append(row)
        self.rows_frame.setVisible(bool(self._rows))
        return list(self._rows)

    def show_keep_all(self, keep_all: bool, fields: Iterable[str]) -> None:
        """Ticked: every row shows as kept and is disabled. Unticked: the
        rows show the tag's own fields."""
        kept = {norm_field(f) for f in fields}
        self.keep_all_box.blockSignals(True)
        self.keep_all_box.setChecked(keep_all)
        self.keep_all_box.blockSignals(False)
        for row in self._rows:
            row.toggle.blockSignals(True)
            row.toggle.set_keep(keep_all or norm_field(row.name) in kept)
            row.toggle._restyle()
            row.toggle.blockSignals(False)
            row.toggle.setEnabled(not keep_all)

    def eventFilter(self, obj: Any, event: Any) -> bool:  # noqa: N802
        # A click anywhere on the tag's line (not only the arrowhead) opens
        # or closes its table.
        if obj is self.header and event.type() == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:
                self.toggle_requested.emit(self.tag)
                return True
        return super().eventFilter(obj, event)


# Earlier name of the class (a protected tag used to be a chip).
TagChip = TagBlock


# ---------------------------------------------------------------------------
# The dialog


def _layout_height(lay: QLayout, width: int) -> int:
    """The height `lay` needs at `width`: its height-for-width when some
    item wraps, else its size hint (Qt answers -1 when nothing wraps)."""
    height = lay.totalHeightForWidth(width)
    if height < 0:
        height = lay.totalSizeHint().height()
    return height


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
        # Rule 14, per protected tag (by `norm_tag`): its own frozen table
        # (the fields kept on its cards) and whether every field is kept.
        self._tag_fields: Dict[str, List[str]] = {}
        self._tag_all: Dict[str, bool] = {}
        self._blocks: List[TagBlock] = []
        self._open_tag: Optional[str] = None  # `norm_tag` of the expanded tag
        self._applying = False
        self.info_buttons: Dict[str, InfoButton] = {}
        self._tag_matches: List[str] = []
        self._field_matches: List[str] = []
        self._result: Optional[Settings] = None
        # The smallest height the window keeps when its content shrinks: the
        # height it opened with, or whatever the user resized it to.
        self._floor_height = 0
        self._auto_resizing = False

        self._build()
        self._apply_settings(settings)
        # What the window opened with, as it shows it: closing without
        # saving asks first only when the choices differ from this.
        self._opened_with = self._current_settings()
        self._size_to_content()
        self._focus_first_control()

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
            QFrame#tag_block { border: none; }
            QFrame#tag_block QLabel { border: none; background: transparent; }
            QFrame#tag_field_rows { border: 1px solid %(soft)s; border-radius: 6px; }
            QFrame#tag_field_rows QLabel { border: none; }
            QFrame#row_separator { border: none; border-top: 1px solid %(soft)s; }
            QToolButton#remove_field_button, QToolButton#remove_tag_button,
            QToolButton#tag_expand_button {
                border: 1px solid transparent; border-radius: 4px; padding: 1px 4px;
                color: %(muted)s; background: transparent;
            }
            QToolButton#remove_field_button:hover, QToolButton#remove_tag_button:hover,
            QToolButton#tag_expand_button:hover {
                border-color: %(border)s;
            }
            QToolButton#remove_field_button:focus, QToolButton#remove_tag_button:focus,
            QToolButton#tag_expand_button:focus {
                border: 1px solid %(focus)s;
            }
            QToolButton#info_button {
                border: 1px solid %(muted)s; border-radius: %(info_r)dpx; padding: 0;
                color: %(muted)s; background: transparent; font-weight: 600;
            }
            QToolButton#info_button:hover { border-color: %(text)s; color: %(text)s; }
            QToolButton#info_button:focus { border: 2px solid %(focus)s; color: %(text)s; }
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
                "muted": _css(c.muted),
                "focus": _css(c.focus),
                "text": _css(c.text),
                "accent": ACCENT_COLOR,
                "accent_dark": _css(c.accent.darker(125)),
                "on": ON_TEXT,
                "info_r": max(18, self.fontMetrics().height() + 2) // 2,
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
        # The three switch rows sit a little closer together than sections.
        switches = QVBoxLayout()
        switches.setSpacing(12)
        switches.addLayout(self._build_styling_section())
        self.scheduling_switch, row = self._switch_row(
            SCHEDULING_HEADING, SCHEDULING_INFO, "scheduling_switch")
        switches.addLayout(row)
        self.presets_switch, row = self._switch_row(PRESETS_HEADING, PRESETS_INFO, "presets_switch")
        switches.addLayout(row)
        lay.addLayout(switches)
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
        sec.addLayout(self._heading_row(FIELDS_HEADING, self._info(FIELDS_HEADING, FIELDS_INFO, "fields")))

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
        self._setup_list(self.field_matches)
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
        sec.addLayout(self._heading_row(TAGS_HEADING, self._info(TAGS_HEADING, TAGS_INFO, "tags")))

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
        self._setup_list(self.tag_list)
        # One click adds the tag: no highlight-then-confirm step.
        self.tag_list.itemClicked.connect(self._on_tag_clicked)
        self.tag_list.hide()
        sec.addWidget(self.tag_list)

        self.tag_hint = self._muted_label("", "tag_hint")
        self.tag_hint.setAccessibleName("Tag hint")
        self.tag_hint.hide()
        sec.addWidget(self.tag_hint)

        # One line per protected tag, under the tag box.
        self.tag_chips_widget = QWidget(self)
        self.tag_chips_widget.setObjectName("tag_blocks")
        self._chips_layout = QVBoxLayout(self.tag_chips_widget)
        self._chips_layout.setContentsMargins(0, 0, 0, 0)
        self._chips_layout.setSpacing(0)
        self.tag_chips_widget.hide()
        sec.addWidget(self.tag_chips_widget)
        return sec

    def _setup_list(self, lst: QListWidget) -> None:
        """No horizontal scroll bar (it would hide the last row): long names
        are elided in the middle, so both the start and the leaf of a
        hierarchical tag stay readable; the tooltip has the full name."""
        lst.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lst.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        lst.setWordWrap(False)
        lst.setItemDelegate(_ElidingDelegate(lst))

    def _fill_list(self, lst: QListWidget, names: Sequence[str]) -> None:
        """Rows for `names`; each row's text is the full name (what gets
        added) and its tooltip shows the full name too."""
        lst.clear()
        for name in names:
            item = QListWidgetItem(name)
            item.setToolTip(_plain_tooltip(name))
            lst.addItem(item)

    def _build_styling_section(self) -> QHBoxLayout:
        self.styling_switch, row = self._switch_row(STYLING_HEADING, STYLING_INFO, "styling_switch")
        return row

    def _info(self, topic: str, text: str, name: str) -> InfoButton:
        button = InfoButton(topic, text, self)
        self.info_buttons[name] = button
        return button

    def _heading_row(self, heading: str, info: InfoButton) -> QHBoxLayout:
        """A heading followed by its (i) button."""
        row = QHBoxLayout()
        row.setSpacing(6)
        lab = self._heading(heading)
        lab.setWordWrap(False)
        row.addWidget(lab, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addWidget(info, 0, Qt.AlignmentFlag.AlignVCenter)
        row.addStretch(1)
        return row

    def _switch_row(self, heading: str, info_text: str, name: str) -> Tuple[ToggleSwitch, QHBoxLayout]:
        """A heading with its (i) button, and a switch on the right."""
        row = QHBoxLayout()
        row.setSpacing(12)
        info = self._info(heading, info_text, name.replace("_switch", ""))
        row.addLayout(self._heading_row(heading, info), 1)
        switch = ToggleSwitch(self._colors, self)
        switch.setObjectName(name)
        switch.setAccessibleName(heading)
        switch.setToolTip(heading)
        row.addWidget(switch, 0, Qt.AlignmentFlag.AlignVCenter)
        return switch, row

    def _focus_first_control(self) -> None:
        """On opening, keyboard focus goes to the first field row's toggle
        (its selected side), or to "+ Add field" when there are no rows; never
        to the scroll area or the tag box."""
        if self._rows:
            self._rows[0].toggle.selected_button().setFocus()
        else:
            self.add_field_button.setFocus()

    def _fit_height(self) -> None:
        """Grow or shrink the window to fit its content after a list or the
        field picker opens or closes: never above 90% of the screen height
        (nor past the screen's bottom edge), never below the height it
        opened with or the user gave it. Only the height changes, so the
        top-left corner stays where it is."""
        if not self.isVisible():
            return
        # Inner boxes first, so no cached height is stale (a row just added).
        boxes: List[QWidget] = [self.field_rows_frame, self.field_picker]
        for block in self._blocks:
            boxes += [block.rows_frame, block.table, block.header, block]
        boxes.append(self.tag_chips_widget)
        for box in boxes:
            box.layout().invalidate()
            box.layout().activate()
        lay = self.body.layout()
        lay.invalidate()
        lay.activate()
        # Measured as if the vertical scroll bar were showing: the scroll area
        # decides whether to keep a bar it already shows at that narrower
        # width, and a few spare pixels go to the stretch at the bottom.
        bar = self.scroll.verticalScrollBar().sizeHint().width()
        width = max(1, self.scroll.width() - bar)
        want = _layout_height(lay, width) + (self.height() - self.scroll.height())
        cap = want
        screen = self.screen() if hasattr(self, "screen") else None
        if screen is not None:
            avail = screen.availableGeometry()
            cap = int(avail.height() * 0.9)
            frame_extra = self.frameGeometry().height() - self.height()
            room = avail.bottom() + 1 - self.frameGeometry().top() - frame_extra
            cap = min(cap, max(room, self.height()))
        target = max(min(want, cap), self._floor_height, self.minimumHeight())
        if target != self.height():
            self._auto_resizing = True
            try:
                self.resize(self.width(), target)
            finally:
                self._auto_resizing = False

    def resizeEvent(self, event: Any) -> None:  # noqa: N802
        super().resizeEvent(event)
        if not self._auto_resizing:
            self._floor_height = self.height()

    def _size_to_content(self) -> None:
        self.body.adjustSize()
        width = 600
        height = _layout_height(self.body.layout(), width) + 70
        screen = self.screen() if hasattr(self, "screen") else None
        if screen is not None:
            height = min(height, int(screen.availableGeometry().height() * 0.9))
        self.setMinimumWidth(480)
        self.resize(width, max(420, height))

    # ----- state ------------------------------------------------------------

    def _apply_settings(self, settings: Settings) -> None:
        self._applying = True
        try:
            self._apply(settings)
        finally:
            self._applying = False
        self._tag_tab_order()

    def _apply(self, settings: Settings) -> None:
        for row in list(self._rows):
            self._drop_row(row)
        for fc in settings.fields:
            self._append_row(fc.name, fc.keep)
        self._show_rows_or_empty_note()
        # Every tag is shown (and saved) with its own frozen table; a tag
        # saved by an earlier beta is frozen at what it means now.
        frozen = settings.with_frozen_tags()
        self._tags = []
        self._tag_fields = {}
        self._tag_all = {}
        for tag in frozen.protected_tags:
            key = norm_tag(tag)
            if not key or key in self._tag_fields:
                continue
            rule = frozen.rule_for(tag)
            self._tags.append(tag)
            self._tag_all[key] = bool(rule and rule.keep_all)
            self._tag_fields[key] = list(rule.fields or ()) if rule is not None else []
        self._open_tag = None  # all collapsed when the window opens
        self._tags, tags = [], self._tags
        self._rebuild_chips()  # drop every block: the data may differ
        self._tags = tags
        self._rebuild_chips()
        self.styling_switch.setChecked(bool(settings.update_note_types))
        self.scheduling_switch.setChecked(bool(settings.import_scheduling))
        self.presets_switch.setChecked(bool(settings.import_deck_presets))
        self.tag_input.clear()
        self._set_tag_hint("")
        self.close_field_picker()

    def result_settings(self) -> Settings:
        """The choices currently shown (the saved ones after accept())."""
        if self._result is not None:
            return self._result
        return self._current_settings()

    def _current_settings(self) -> Settings:
        rules = []
        for tag in self._tags:
            key = norm_tag(tag)
            rules.append(TagRule(tag, (), bool(self._tag_all.get(key)), tuple(self._ordered_tag_fields(key))))
        return Settings(
            fields=tuple(r.choice() for r in self._rows),
            protected_tags=tuple(self._tags),
            update_note_types=self.styling_switch.isChecked(),
            import_scheduling=self.scheduling_switch.isChecked(),
            import_deck_presets=self.presets_switch.isChecked(),
            tag_rules=tuple(rules),
        )

    def accept(self) -> None:
        self._result = self._current_settings()
        super().accept()

    def has_changes(self) -> bool:
        """True if the choices shown differ from the ones the window opened
        with (changed and changed back counts as unchanged)."""
        return self._current_settings() != self._opened_with

    def reject(self) -> None:
        """Esc, Cancel and the close box: ask before discarding changes."""
        if self.has_changes() and not confirm_discard(self):
            return
        super().reject()

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
        # A new row shows in every tag's table ("Take the update's" there).
        self._refresh_tag_tables()
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
        # The row leaves every tag's table that does not keep it.
        self._refresh_tag_tables()

    def remove_field(self, name: str) -> bool:
        row = self.row_for(name)
        if row is None:
            return False
        self._drop_row(row)
        self._tag_tab_order()
        self._refresh_field_matches()
        self.add_field_button.setFocus()
        return True

    def open_field_picker(self) -> None:
        self.add_field_button.hide()
        self.field_picker.show()
        self.field_search.clear()
        self._refresh_field_matches()
        self.field_search.setFocus()
        self._fit_height()

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
        self._fit_height()

    def _refresh_field_matches(self, *_args: Any) -> None:
        query = self.field_search.text()
        self._field_matches = filter_fields(query, self._all_fields, [r.name for r in self._rows])
        self._fill_list(self.field_matches, self._field_matches)
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
        self._fit_height()

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
        self._tag_tab_order()
        self.field_search.blockSignals(True)
        self.field_search.clear()
        self.field_search.blockSignals(False)
        self._refresh_field_matches()
        # No message after adding (like the tag picker); hints only report
        # a problem.
        self._set_field_hint("")
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

    def tag_chips(self) -> List[TagBlock]:
        """One block per protected tag, in order (`tag_blocks`)."""
        return list(self._blocks)

    def tag_blocks(self) -> List[TagBlock]:
        return list(self._blocks)

    def tag_block(self, tag: str) -> Optional[TagBlock]:
        key = norm_tag(tag)
        for block in self._blocks:
            if norm_tag(block.tag) == key:
                return block
        return None

    def tag_matches(self) -> List[str]:
        """Every tag matching the current text (the list may show fewer)."""
        return list(self._tag_matches)

    def _rebuild_chips(self) -> None:
        """One block per protected tag, in order. Blocks of tags still
        protected are kept as they are (open or not, focus included); new
        tags get a new block, removed tags lose theirs."""
        old = {norm_tag(b.tag): b for b in self._blocks}
        blocks: List[TagBlock] = []
        for tag in self._tags:
            block = old.pop(norm_tag(tag), None)
            if block is None:
                block = TagBlock(tag, self._colors, self.tag_chips_widget)
                block.remove_requested.connect(self.remove_tag)
                block.toggle_requested.connect(self.toggle_tag)
                block.keep_all_box.toggled.connect(lambda on, t=tag: self.set_tag_keep_all(t, on))
                self._fill_tag_table(block)
            blocks.append(block)
        for block in old.values():
            block.hide()
            self._chips_layout.removeWidget(block)
            block.setParent(None)
            block.deleteLater()
        for block in blocks:
            self._chips_layout.removeWidget(block)
        # The tags line up in one column, as wide as the longest tag needs
        # (long ones are elided in the middle, tooltip in full).
        bold = QFont(self.font())
        bold.setWeight(QFont.Weight.DemiBold)
        fm = QFontMetrics(bold)
        column = min(TAG_COLUMN_WIDTH, max([fm.horizontalAdvance(t) + 8 for t in self._tags] or [0]))
        for block in blocks:
            # Fixed, not the label's own "Ignored": an ignored item gets no
            # room in the line, and the summary would be drawn over it.
            block.label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            block.label.setFixedWidth(column)
            self._chips_layout.addWidget(block)
            block.set_expanded(norm_tag(block.tag) == self._open_tag)
            block.show()
        self._blocks = blocks
        self.tag_chips_widget.setVisible(bool(self._tags))
        self._chips_layout.invalidate()
        self._tag_tab_order()

    def _tag_tab_order(self) -> None:
        """The whole window's Tab order, top to bottom (rows and tag lines are
        made after the rest, so Qt alone would put them last): the Fields
        (i), each field row (its ✕, its toggle), "+ Add field" and its
        search; the Protected tags (i), the tag box and its list, each tag's
        line (its arrowhead, its ✕, and, when open, its table's toggles and
        "Keep every field"); then each switch's (i) and switch, and the
        buttons. Hidden widgets are skipped by Qt."""
        chain: List[QWidget] = [self.info_buttons["fields"]]
        for row in self._rows:
            chain += [row.remove_button, row.toggle.keep_button, row.toggle.take_button]
        chain += [self.add_field_button, self.field_search, self.field_done_button, self.field_matches]
        chain += [self.info_buttons["tags"], self.tag_input, self.tag_list]
        for block in self._blocks:
            chain += [block.expand_button, block.remove_button]
            for trow in block.rows():
                chain += [trow.toggle.keep_button, trow.toggle.take_button]
            chain.append(block.keep_all_box)
        for name, switch in (("styling", self.styling_switch), ("scheduling", self.scheduling_switch),
                             ("presets", self.presets_switch)):
            chain += [self.info_buttons[name], switch]
        chain += [self.restore_button, self.cancel_button, self.save_button]
        for a, b in zip(chain, chain[1:]):
            QWidget.setTabOrder(a, b)

    def _is_protected(self, tag: str) -> bool:
        key = norm_tag(tag)
        return any(norm_tag(t) == key for t in self._tags)

    def _refresh_tag_matches(self, *_args: Any) -> None:
        query = self.tag_input.text()
        self._tag_matches = filter_tags(query, self._all_tags, self._tags)
        shown = self._tag_matches[:MAX_TAGS_SHOWN]
        self.tag_list.blockSignals(True)
        self._fill_list(self.tag_list, shown)
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
        self._fit_height()

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
        """Protect `tag` if it exists in the collection; returns True if added.
        Its table starts as the previous tag's kept fields plus every field
        the main list keeps now ("Keep every field" copied from that tag; the
        first tag starts as the main list), and it opens, closing any other."""
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
        fields: List[str] = []
        keep_all = False
        if self._tags:
            prev = norm_tag(self._tags[-1])
            fields = list(self._tag_fields.get(prev, []))
            keep_all = bool(self._tag_all.get(prev))
        have = {norm_field(f) for f in fields}
        for row in self._rows:
            if row.toggle.keep() and norm_field(row.name) not in have:
                have.add(norm_field(row.name))
                fields.append(row.name)
        self._tags.append(existing)
        self._tag_fields[norm_tag(existing)] = fields
        self._tag_all[norm_tag(existing)] = keep_all
        self._open_tag = norm_tag(existing)
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
        """Stop protecting `tag`; its table goes with it."""
        key = norm_tag(tag)
        before = len(self._tags)
        self._tags = [t for t in self._tags if norm_tag(t) != key]
        if len(self._tags) == before:
            return False
        self._tag_fields.pop(key, None)
        self._tag_all.pop(key, None)
        if self._open_tag == key:
            self._open_tag = None
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

    # ----- each protected tag's own table (rule 14) ----------------------------

    def tag_rule(self, tag: str) -> Tuple[List[str], bool]:
        """(fields the tag keeps, in display order; every field?) as shown."""
        key = norm_tag(tag)
        return self._ordered_tag_fields(key), bool(self._tag_all.get(key))

    def open_tag(self) -> Optional[str]:
        """The tag whose table is open, or None."""
        for block in self._blocks:
            if block.is_expanded():
                return block.tag
        return None

    def _ordered_tag_fields(self, key: str) -> List[str]:
        """A tag's kept fields in the main list's order, then any it keeps
        that are no longer in the main list (in the order they were kept)."""
        fields = self._tag_fields.get(key, [])
        kept = {norm_field(f): f for f in fields}
        out = [r.name for r in self._rows if norm_field(r.name) in kept]
        listed = {norm_field(r.name) for r in self._rows}
        out += [f for f in fields if norm_field(f) not in listed]
        return out

    def _fill_tag_table(self, block: TagBlock) -> None:
        """The tag's rows: the main list's rows, in order, then the fields
        it keeps that are no longer in the main list."""
        key = norm_tag(block.tag)
        kept = {norm_field(f) for f in self._tag_fields.get(key, [])}
        rows = [(r.name, norm_field(r.name) in kept) for r in self._rows]
        listed = {norm_field(r.name) for r in self._rows}
        rows += [(f, True) for f in self._tag_fields.get(key, []) if norm_field(f) not in listed]
        for row in block.set_rows(rows):
            row.toggle.changed.connect(lambda keep, t=block.tag, n=row.name: self.set_tag_field(t, n, keep))
        block.show_keep_all(bool(self._tag_all.get(key)), self._tag_fields.get(key, []))
        block.set_summary(keeps_text(self._ordered_tag_fields(key), bool(self._tag_all.get(key))))

    def _refresh_tag_tables(self) -> None:
        """After a main-list row was added or removed."""
        if not self._blocks or self._applying:
            return
        for block in self._blocks:
            self._fill_tag_table(block)
        self._tag_tab_order()
        self._fit_height()

    def toggle_tag(self, tag: str) -> None:
        block = self.tag_block(tag)
        if block is None:
            return
        if block.is_expanded():
            self.collapse_tag(tag)
        else:
            self.expand_tag(tag)

    def expand_tag(self, tag: str) -> None:
        """Open `tag`'s table; only one tag is open at a time."""
        key = norm_tag(tag)
        if self.tag_block(tag) is None:
            return
        self._open_tag = key
        for block in self._blocks:
            block.set_expanded(norm_tag(block.tag) == key)
        self._fit_height()

    def collapse_tag(self, tag: str) -> None:
        block = self.tag_block(tag)
        if block is None:
            return
        if self._open_tag == norm_tag(tag):
            self._open_tag = None
        block.set_expanded(False)
        self._fit_height()

    def set_tag_field(self, tag: str, name: str, keep: bool) -> bool:
        """"Keep mine" (`keep`) or "Take the update's" for field `name` in
        `tag`'s own table. Changes nothing else, the main list included."""
        block = self.tag_block(tag)
        if block is None:
            return False
        key = norm_tag(tag)
        fields = self._tag_fields.setdefault(key, [])
        fkey = norm_field(name)
        have = any(norm_field(f) == fkey for f in fields)
        if keep and not have:
            fields.append(name)
        elif not keep and have:
            self._tag_fields[key] = [f for f in fields if norm_field(f) != fkey]
        else:
            return False
        row = block.row_for(name)
        if row is not None and row.toggle.keep() != keep:
            row.toggle.set_keep(keep)
        listed = {norm_field(r.name) for r in self._rows}
        if not keep and fkey not in listed:
            # A field no longer in the main list stays in the tag's table
            # only while the tag keeps it.
            focus = QApplication.focusWidget()
            refocus = block.keep_all_box if (row is not None and focus is not None
                                             and row.toggle.isAncestorOf(focus)) else None
            self._fill_tag_table(block)
            self._tag_tab_order()
            if refocus is not None:
                refocus.setFocus()
            self._fit_height()
        block.set_summary(keeps_text(self._ordered_tag_fields(key), bool(self._tag_all.get(key))))
        return True

    def set_tag_keep_all(self, tag: str, keep_all: bool) -> None:
        """"Keep every field" for `tag`: its rows show as kept and are
        disabled; unticked, they show the tag's own choices again."""
        block = self.tag_block(tag)
        if block is None:
            return
        key = norm_tag(tag)
        self._tag_all[key] = bool(keep_all)
        block.show_keep_all(bool(keep_all), self._tag_fields.get(key, []))
        block.set_summary(keeps_text(self._ordered_tag_fields(key), bool(keep_all)))

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
