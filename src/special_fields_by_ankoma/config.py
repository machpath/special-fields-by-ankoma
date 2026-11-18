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
    """`protected_tags` as stored (contract rule 14). A tag with its own
    frozen table: {"tag", "fields", "keep_all_fields"} (the only form the
    settings window saves). Entries of earlier betas that were not frozen
    yet are written back as they came: a plain string (follows the main
    list) or beta 8's {"tag", "keep_fields", "keep_all_fields"}."""
    out: List[Any] = []
    for tag in settings.protected_tags:
        rule = settings.rule_for(tag)
        if rule is None or (not rule.is_frozen() and not rule.keeps_any()):
            out.append(tag)
        elif rule.is_frozen():
            out.append({
                "tag": tag,
                "fields": list(rule.fields or ()),
                "keep_all_fields": bool(rule.keep_all),
            })
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
    """Protected tag names and their tables (contract rule 14). Each entry
    is one of:

    - {"tag": ..., "fields": [...], "keep_all_fields": bool}: the tag's own
      frozen table (`fields` empty = keeps no fields);
    - a plain string (beta 7 and earlier): follows the main list;
    - {"tag": ..., "keep_fields": [...], "keep_all_fields": bool} (beta 8):
      the main list plus `keep_fields`; one that keeps nothing is read like
      a plain string.

    Unknown keys are ignored. A `fields` that is not a list of names (a
    single string counts as a list of one) is ignored, so the entry is read
    as an earlier beta's. A wrong `keep_fields` or `keep_all_fields` keeps
    nothing extra. A tag listed twice keeps its first position; its tables
    are joined (frozen entries with frozen entries; when none is frozen,
    beta 8's `keep_fields` as beta 8 did)."""
    if isinstance(raw, (str, dict)):
        raw = [raw]  # a single tag typed without the list brackets
    if not isinstance(raw, list):
        return (), ()
    tags: List[str] = []
    frozen: Dict[str, Optional[List[str]]] = {}
    extra: Dict[str, List[str]] = {}
    keep_all: Dict[str, bool] = {}
    for entry in raw:
        names: List[str] = []
        table: Optional[List[str]] = None
        every = False
        if isinstance(entry, dict):
            tag = entry.get("tag")
            if isinstance(entry.get("fields"), (list, str)):
                table = _read_names(entry.get("fields"))
            else:
                names = _read_names(entry.get("keep_fields"))
            every = _read_bool(entry.get("keep_all_fields", False), False)
        else:
            tag = entry
        if not isinstance(tag, str) or not tag.strip():
            continue
        key = norm_tag(tag)
        if key not in extra:
            tags.append(tag.strip())
            frozen[key] = None
            extra[key] = []
            keep_all[key] = False
        if table is not None:
            have_list = frozen[key]
            if have_list is None:
                have_list = frozen[key] = []
            have = {norm_field(n) for n in have_list}
            have_list.extend(n for n in table if norm_field(n) not in have)
        have = {norm_field(n) for n in extra[key]}
        extra[key].extend(n for n in names if norm_field(n) not in have)
        keep_all[key] = keep_all[key] or every
    rules: List[TagRule] = []
    for tag in tags:
        key = norm_tag(tag)
        if frozen[key] is not None:
            rules.append(TagRule(tag, (), keep_all[key], tuple(frozen[key] or ())))
        elif keep_all[key]:
            rules.append(TagRule(tag, (), True))
        elif extra[key]:
            rules.append(TagRule(tag, tuple(extra[key]), False))
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
