"""Resolve a node id a person pasted from ``periplus find`` output, or a short name of one."""

from __future__ import annotations

import re

from periplus.navigate.listing import first_location, place
from periplus.navigate.mapfile import MapIndex, NodeNotFound, as_text
from periplus.report import _escape

_ESCAPE = re.compile(r"\\(?:(\\)|n|r|t|x([0-9a-f]{2})|u([0-9a-f]{4}))")
_SIMPLE = {"n": "\n", "r": "\r", "t": "\t"}
#: The most candidates a tie lists.
_SHOWN = 20


def _unescape(text: str) -> str:
    """The inverse of ``report._escape``, in one pass so a produced escape is not read twice."""

    def one(match: re.Match[str]) -> str:
        if match.group(1):
            return "\\"
        hexa = match.group(2) or match.group(3)
        return chr(int(hexa, 16)) if hexa else _SIMPLE[match.group(0)[1]]

    return _ESCAPE.sub(one, text)


def _short(node_id: str, text: str) -> bool:
    """Whether ``text``, case-folded, is the id's name or a tail of it that starts after a
    character other than a letter, digit or underscore.

    The name is the id after its first ``::``, so an id ending in ``.MyForm::build`` has the short
    names ``MyForm::build`` and ``build``, and the type before the ``::`` names nothing. No
    separator is listed, so an id written with ``#`` or ``->`` splits the same way.
    """
    name = node_id.split("::", 1)[-1].casefold()
    if name == text:
        return True
    before = len(name) - len(text) - 1
    if before < 0 or not name.endswith(text):
        return False
    return not (name[before].isalnum() or name[before] == "_")


def resolve(index: MapIndex, text: str) -> tuple[str, tuple[str, ...]]:
    """The id ``text`` names, and a warning when it named it by a short name.

    A full id or its escaped form is taken as it is. Otherwise ``text`` is matched, ignoring case,
    against each id's short names: one match is used, several or none is ``NodeNotFound``.
    """
    unescaped = _unescape(text)
    for given in (text, unescaped):
        if given in index.nodes:
            return given, ()
    matches: list[str] = []
    for given in dict.fromkeys((text, unescaped)):
        folded = given.casefold()
        matches = sorted(i for i in index.nodes if folded and _short(as_text(i), folded))
        if matches:
            break
    if len(matches) == 1:
        return matches[0], (f"resolved {text!r} to {matches[0]}",)
    if matches:
        raise NodeNotFound(
            f"{text!r} matches {len(matches)} nodes; give one of these ids",
            {
                "id": text,
                "candidates": tuple(_candidate(index, i) for i in matches[:_SHOWN]),
                "total": len(matches),
            },
        )
    try:
        index.node(text)
    except NodeNotFound as error:
        raise NodeNotFound(
            str(error), {**error.detail, "lines": f"hint: run periplus find {_escape(text)}"}
        ) from None
    return text, ()


def _candidate(index: MapIndex, node_id: str) -> dict[str, str | None]:
    """One tie candidate as its raw id, type and first ``file:line``, or ``None`` for no place."""
    node = index.nodes[node_id]
    loc = first_location(node)
    return {"id": node_id, "type": as_text(node["type"]), "location": place(loc) if loc else None}
