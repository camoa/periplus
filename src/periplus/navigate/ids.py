"""Resolve a node id a person pasted from ``periplus find`` output."""

from __future__ import annotations

import re

from periplus.navigate.mapfile import MapIndex

_ESCAPE = re.compile(r"\\(?:(\\)|n|r|t|x([0-9a-f]{2})|u([0-9a-f]{4}))")
_SIMPLE = {"n": "\n", "r": "\r", "t": "\t"}


def _unescape(text: str) -> str:
    """The inverse of ``report._escape``, in one pass so a produced escape is not read twice."""

    def one(match: re.Match[str]) -> str:
        if match.group(1):
            return "\\"
        hexa = match.group(2) or match.group(3)
        return chr(int(hexa, 16)) if hexa else _SIMPLE[match.group(0)[1]]

    return _ESCAPE.sub(one, text)


def resolve(index: MapIndex, text: str) -> str:
    """The id as given when the map holds it, else the id the escaped form stands for."""
    if text in index.nodes:
        return text
    unescaped = _unescape(text)
    return unescaped if unescaped in index.nodes else text
