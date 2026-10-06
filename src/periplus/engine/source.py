"""Read a YAML source file as plain values that keep the line of every key and list item."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError
from ruamel.yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from periplus.errors import ExitCode, HarnessError

__all__ = [
    "DATA_READERS",
    "SHORT_FORM_FORMAT",
    "Entry",
    "Hit",
    "SourceUnreadable",
    "load_data",
    "load_text",
    "plain",
    "resolve_path",
]

_CORE = "tag:yaml.org,2002:"
# binary and timestamp are standard types an exporter writes; both are read as their text.
_TAGS = {
    _CORE + name
    for name in ("str", "int", "float", "bool", "null", "map", "seq", "binary", "timestamp")
}


class SourceUnreadable(HarnessError):
    """A source file cannot be read as data."""

    code = ExitCode.SOURCE_UNREADABLE


@dataclass(frozen=True, slots=True)
class Entry:
    """A value with its 1-based line: a scalar, a ``dict`` of entries, or a ``list`` of entries."""

    value: Any
    line: int


@dataclass(frozen=True, slots=True)
class Hit:
    """One place a key path reached: its value, the line of its key or item, and its last key."""

    value: Any
    line: int
    key: str | None


def load_data(path: Path, name: str) -> dict[str, Entry]:
    """The file's root mapping. ``name`` is the repository-relative path used in the message.

    Raises ``SourceUnreadable`` for a parse error, bytes that are not UTF-8, a root that is not a
    mapping, a tag outside the YAML core set on a key, a tag in the YAML namespace outside that set
    on a value, and a key written twice in one mapping. A value with a local tag, one written with
    a single ``!``, is read as if untagged: text as its text. The text is composed, never
    constructed, so no tag runs anything.
    """
    try:
        root = YAML(typ="safe", pure=True).compose(path.read_bytes().decode("utf-8"))
    except (UnicodeDecodeError, YAMLError) as error:
        raise SourceUnreadable(f"{name} cannot be read: {error}", {"file": name}) from error
    if not isinstance(root, MappingNode):
        raise SourceUnreadable(f"{name} does not hold a mapping at its root", {"file": name})
    value: dict[str, Entry] = _convert(root, name, ())
    return value


#: Each data format the engine reads, by the name a declared file type gives under ``format``.
DATA_READERS: Mapping[str, Callable[[Path, str], dict[str, Entry]]] = {"yaml": load_data}

#: The format of a data type that names none: the short form ``extensions`` and the settings'.
SHORT_FORM_FORMAT = "yaml"


def load_text(path: Path, name: str) -> str:
    """The file's text, each carriage return and line feed made one line feed, so a checkout with
    either line end gives one map. Raises ``SourceUnreadable`` for bytes that are not UTF-8."""
    try:
        return path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    except UnicodeDecodeError as error:
        raise SourceUnreadable(f"{name} cannot be read as text: {error}", {"file": name}) from error


def _convert(node: Node, name: str, active: tuple[int, ...]) -> Any:
    local = str(node.tag).startswith("!")
    if (node.tag not in _TAGS and not local) or id(node) in active:
        raise SourceUnreadable(
            f"{name} line {node.start_mark.line + 1} holds the tag {node.tag} "
            "or an alias that contains itself",
            {"file": name},
        )
    inside = (*active, id(node))
    if isinstance(node, MappingNode):
        mapping: dict[str, Entry] = {}
        for key, item in node.value:
            if key.tag not in _TAGS:
                raise SourceUnreadable(
                    f"{name} line {key.start_mark.line + 1} holds the key tag {key.tag}",
                    {"file": name},
                )
            text = str(key.value) if isinstance(key, ScalarNode) else ""
            if not text or text in mapping:
                raise SourceUnreadable(
                    f"{name} line {key.start_mark.line + 1} writes the key {text!r} twice "
                    "or uses a key that is not a plain scalar",
                    {"file": name},
                )
            mapping[text] = Entry(_convert(item, name, inside), key.start_mark.line + 1)
        return mapping
    if isinstance(node, SequenceNode):
        return [
            Entry(_convert(item, name, inside), item.start_mark.line + 1) for item in node.value
        ]
    return str(node.value) if local else _scalar(str(node.tag).removeprefix(_CORE), str(node.value))


def _scalar(tag: str, text: str) -> Any:
    if tag == "null":
        return None
    if tag == "bool":
        return text.lower() == "true"
    if tag == "int":
        try:
            return int(text)
        except ValueError:
            return int(text, 0)
    if tag == "float":
        lowered = text.lower().replace("_", "")
        if lowered.endswith(".inf"):
            return -math.inf if lowered.startswith("-") else math.inf
        return math.nan if lowered == ".nan" else float(lowered)
    return text


def plain(value: Any) -> Any:
    """The value with every ``Entry`` unwrapped, for writing into the map."""
    if isinstance(value, dict):
        return {key: plain(item.value) for key, item in value.items()}
    if isinstance(value, list):
        return [plain(item.value) for item in value]
    return value


def resolve_path(root: dict[str, Entry], path: str) -> list[Hit]:
    """Every place the key path reaches. A star as a whole segment takes each key or item."""
    hits = [Hit(root, 1, None)]
    for segment in path.split("."):
        found: list[Hit] = []
        for hit in hits:
            found.extend(_step(hit.value, segment))
        hits = found
    return hits


def _step(value: Any, segment: str) -> Sequence[Hit]:
    if isinstance(value, dict):
        keys = list(value) if segment == "*" else [segment] if segment in value else []
        return [Hit(value[key].value, value[key].line, key) for key in keys]
    if isinstance(value, list) and segment == "*":
        return [Hit(item.value, item.line, None) for item in value]
    return []
