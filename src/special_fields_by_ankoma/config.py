"""Settings <-> add-on config (the dict Anki stores for the add-on).

Pure Python: no `anki` or `aqt` imports, so it can be tested anywhere.
Reading is tolerant: a missing or malformed value falls back to the default
instead of raising, because users can hand-edit the config in Anki.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .model import FieldChoice, Settings, TagRule, norm_field, norm_tag

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
        import_scheduling=False,
        import_deck_presets=False,
    )


def settings_to_config(settings: Settings) -> Dict[str, Any]:
    return {
        "config_version": CONFIG_VERSION,
        "fields": [{"name": f.name, "keep": bool(f.keep)} for f in settings.fields],
        "protected_tags": _tags_to_config(settings),
        "update_note_types": bool(settings.update_note_types),
        "import_scheduling": bool(settings.import_scheduling),
        "import_deck_presets": bool(settings.import_deck_presets),
    }


def _tags_to_config(settings: Settings) -> List[Any]:
    """`protected_tags` as stored: a plain string for a tag that keeps no
    fields (the format of earlier betas, which can still read it), an object
    for a tag with a rule (contract rule 14)."""
    out: List[Any] = []
    for tag in settings.protected_tags:
        rule = settings.rule_for(tag)
        if rule is None:
            out.append(tag)
        else:
            out.append({
                "tag": tag,
                "keep_fields": [] if rule.keep_all else list(rule.keep_fields),
                "keep_all_fields": bool(rule.keep_all),
            })
    return out


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


def _read_names(raw: Any) -> List[str]:
    """A list of field names (a single string is taken as a list of one);
    anything else gives none."""
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    out: List[str] = []
    seen = set()
    for name in raw:
        if not isinstance(name, str) or not name.strip():
            continue
        key = norm_field(name)
        if key in seen:
            continue
        seen.add(key)
        out.append(name.strip())
    return out


def _read_tags(raw: Any) -> Tuple[Tuple[str, ...], Tuple[TagRule, ...]]:
    """Protected tag names and their rules. Each entry is a tag (a plain
    string, as saved by earlier betas: "Tag only") or an object
    {"tag": ..., "keep_fields": [...], "keep_all_fields": bool} (rule 14).
    Unknown keys are ignored; a wrong `keep_fields` or `keep_all_fields`
    means "Tag only". A tag listed twice keeps its first position and the
    fields of both entries."""
    if isinstance(raw, (str, dict)):
        raw = [raw]  # a single tag typed without the list brackets
    if not isinstance(raw, list):
        return (), ()
    tags: List[str] = []
    fields: Dict[str, List[str]] = {}
    keep_all: Dict[str, bool] = {}
    for entry in raw:
        names: List[str] = []
        every = False
        if isinstance(entry, dict):
            tag = entry.get("tag")
            names = _read_names(entry.get("keep_fields"))
            every = _read_bool(entry.get("keep_all_fields", False), False)
        else:
            tag = entry
        if not isinstance(tag, str) or not tag.strip():
            continue
        key = norm_tag(tag)
        if key not in fields:
            tags.append(tag.strip())
            fields[key] = []
            keep_all[key] = False
        have = {norm_field(n) for n in fields[key]}
        fields[key].extend(n for n in names if norm_field(n) not in have)
        keep_all[key] = keep_all[key] or every
    rules: List[TagRule] = []
    for tag in tags:
        key = norm_tag(tag)
        if keep_all[key]:
            rules.append(TagRule(tag, (), True))
        elif fields[key]:
            rules.append(TagRule(tag, tuple(fields[key]), False))
    return tuple(tags), tuple(rules)


def settings_from_config(cfg: Optional[Dict[str, Any]]) -> Settings:
    """Build Settings from a stored config dict; None or junk -> defaults."""
    defaults = default_settings()
    if not isinstance(cfg, dict):
        return defaults
    fields = _read_fields(cfg.get("fields"))
    if fields is None:
        fields = defaults.fields
    tags, rules = _read_tags(cfg.get("protected_tags"))
    return Settings(
        fields=fields,
        protected_tags=tags,
        update_note_types=_read_bool(cfg.get("update_note_types"), defaults.update_note_types),
        # Missing in configs saved before these choices existed: off.
        import_scheduling=_read_bool(cfg.get("import_scheduling"), defaults.import_scheduling),
        import_deck_presets=_read_bool(cfg.get("import_deck_presets"), defaults.import_deck_presets),
        tag_rules=rules,
    )
