"""Resolve a node id a person pasted from ``periplus find`` output, or a short name of one."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import TextIO

from periplus.errors import Problem
from periplus.navigate.listing import first_location, place, problem_lines
from periplus.navigate.mapfile import MapIndex, NodeNotFound, as_text, map_flag
from periplus.navigate.names import Names
from periplus.navigate.nesting import Places
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


def resolve(
    index: MapIndex, text: str, close: bool = True, prefer_main: bool = True
) -> tuple[str, tuple[str, ...]]:
    """The id ``text`` names, and a warning when it named it by a short name.

    A full id or its escaped form is taken as it is. Otherwise ``text`` is matched, ignoring case,
    against each id's short names: one match is used; of several, the only one whose type is not
    a part type (``Places.part_types``) is used; else several or none is ``NodeNotFound``. Without
    ``close``, a text that names nothing is not compared with every id for the closest ones.
    Without ``prefer_main``, several matches are refused whatever their types, so ``slice``
    searches such a word as it did.
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
    if prefer_main and len(matches) > 1:
        parts = Places(index, Names(index)).part_types()
        main = [i for i in matches if as_text(index.nodes[i]["type"]) not in parts]
        matches = main if len(main) == 1 else matches
    if len(matches) == 1:
        return matches[0], (f"resolved '{text}' to {matches[0]}",)
    if matches:
        raise NodeNotFound(
            f"'{text}' matches {len(matches)} nodes; give one of these ids",
            {
                "id": text,
                "candidates": tuple(_candidate(index, i) for i in matches[:_SHOWN]),
                "total": len(matches),
            },
        )
    if not close:
        raise NodeNotFound(f"no node has the id {text!r}", {"id": text})
    try:
        index.node(text)
    except NodeNotFound as error:
        hint = f"hint: run periplus find {_escape(text)}{_escape(map_flag(index.given))}"
        raise NodeNotFound(str(error), {**error.detail, "lines": hint}) from None
    return text, ()


def resolve_all(index: MapIndex, texts: Sequence[str]) -> tuple[list[str], list[str]]:
    """The ids ``texts`` name, each once in the order first named, and ``resolve``'s warnings."""
    found: list[str] = []
    notes: list[str] = []
    for text in texts:
        node_id, said = resolve(index, text)
        found.append(node_id)
        notes += said
    return list(dict.fromkeys(found)), notes


def _candidate(index: MapIndex, node_id: str) -> dict[str, str | None]:
    """One tie candidate as its raw id, type and first ``file:line``, or ``None`` for no place."""
    node = index.nodes[node_id]
    loc = first_location(node)
    return {"id": node_id, "type": as_text(node["type"]), "location": place(loc) if loc else None}


def read_ids(given: Sequence[str], stream: TextIO) -> list[str]:
    """``given`` with a ``-`` replaced by the lines of ``stream``, one id a line.

    Only the line ending is taken off, so an id keeps its spaces; an empty line is skipped. The
    stream is read at the first ``-``; a second ``-`` adds nothing.
    """
    ids: list[str] = []
    read = False
    for text in given:
        if text != "-":
            ids.append(text)
        elif not read:
            read = True
            lines = (line.removesuffix("\r") for line in stream.read().split("\n"))
            ids += [line for line in lines if line]
    return ids


def id_output(
    pieces: Iterable[Sequence[str]], warnings: Sequence[str], problems: Sequence[Problem]
) -> tuple[str, str]:
    """What ``--ids`` writes: one full id a line, a blank line between ``pieces``, nothing else;
    and for standard error, the count, the warnings and the problems.

    An id is printed as it is, but one holding a character ``_escape`` changes other than a
    backslash, such as a line break, which would split it: that one prints escaped, and ``resolve``
    reads it back.
    """
    blocks: list[str] = []
    count = escaped = 0
    for piece in pieces:
        lines = []
        for node_id in piece:
            shown = _escape(node_id)
            if shown == node_id.replace("\\", "\\\\"):
                shown = node_id
            else:
                escaped += 1
            lines.append(shown)
        count += len(lines)
        blocks.append("".join(f"{line}\n" for line in lines))
    err = [f"{count} id{'' if count == 1 else 's'}"]
    if escaped:
        err.append(
            f"{escaped} of them hold a control character and print escaped; periplus commands "
            "read the escaped form back"
        )
    err += [f"warning: {_escape(w)}" for w in warnings]
    err += problem_lines(problems)
    return "\n".join(b for b in blocks if b), "".join(f"{line}\n" for line in err)
