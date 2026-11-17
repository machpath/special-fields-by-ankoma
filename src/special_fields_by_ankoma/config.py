"""Settings <-> add-on config (the dict Anki stores for the add-on).

Pure Python: no `anki` or `aqt` imports, so it can be tested anywhere.
Reading is tolerant: a missing or malformed value falls back to the default
instead of raising, because users can hand-edit the config in Anki.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .model import FieldChoice, Settings, norm_field, norm_tag

CONFIG_VERSION = 1

# Ankoma's cloze fields, in the order the settings window lists them.
DEFAULT_FIELDS: Tuple[Tuple[str, bool], ...] = (
    ("Header", False),
    ("Text", False),
    ("Extra", False),
    ("Personal Notes", True),
    ("Textbook", False),
    ("Citation", False),
)


def default_settings() -> Settings:
    return Settings(
        fields=tuple(FieldChoice(name, keep) for name, keep in DEFAULT_FIELDS),
        protected_tags=(),
        update_note_types=True,
    )


def settings_to_config(settings: Settings) -> Dict[str, Any]:
    return {
        "config_version": CONFIG_VERSION,
        "fields": [{"name": f.name, "keep": bool(f.keep)} for f in settings.fields],
        "protected_tags": list(settings.protected_tags),
        "update_note_types": bool(settings.update_note_types),
    }


def default_config() -> Dict[str, Any]:
    return settings_to_config(default_settings())


_TRUE_WORDS = ("true", "yes", "on", "1")
_FALSE_WORDS = ("false", "no", "off", "0")


def _read_bool(raw: Any, default: bool) -> bool:
    """Read a yes/no value a user may have typed by hand.

    Real booleans are taken as they are. The words true/false, yes/no, on/off
    and the numbers 1/0 are understood. Anything else gives `default`, so a
    typo never silently flips a choice.
    """
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, int):
        if raw in (0, 1):
            return bool(raw)
        return default
    if isinstance(raw, str):
        word = raw.strip().casefold()
        if word in _TRUE_WORDS:
            return True
        if word in _FALSE_WORDS:
            return False
    return default


def _read_fields(raw: Any) -> Optional[Tuple[FieldChoice, ...]]:
    if not isinstance(raw, list):
        return None
    out: List[FieldChoice] = []
    seen = set()
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        key = norm_field(name)
        if key in seen:
            continue
        seen.add(key)
        out.append(FieldChoice(name.strip(), _read_bool(item.get("keep", False), False)))
    return tuple(out)


def _read_tags(raw: Any) -> Tuple[str, ...]:
    if isinstance(raw, str):
        raw = [raw]  # a single tag typed without the list brackets
    if not isinstance(raw, list):
        return ()
    out: List[str] = []
    seen = set()
    for tag in raw:
        if not isinstance(tag, str) or not tag.strip():
            continue
        key = norm_tag(tag)
        if key in seen:
            continue
        seen.add(key)
        out.append(tag.strip())
    return tuple(out)


def settings_from_config(cfg: Optional[Dict[str, Any]]) -> Settings:
    """Build Settings from a stored config dict; None or junk -> defaults."""
    defaults = default_settings()
    if not isinstance(cfg, dict):
        return defaults
    fields = _read_fields(cfg.get("fields"))
    if fields is None:
        fields = defaults.fields
    return Settings(
        fields=fields,
        protected_tags=_read_tags(cfg.get("protected_tags")),
        update_note_types=_read_bool(cfg.get("update_note_types"), defaults.update_note_types),
    )
