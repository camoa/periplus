"""Read YAML at ``typ='safe'`` with ruamel's C parser where it gives what the pure one gives.

The C parser (``ruamel.yaml.clib``) loads pack files about six times faster. It is not the pure
parser. Measured on ruamel 0.19.1 with clib 0.2.15, by comparing the two on real files, on
mutated ones and on random documents:

* It succeeds with another result on some text: a tab the pure parser refuses before a comment or
  after a colon; a ``%YAML 1.1`` directive it ignores, where the pure parser reads ``yes`` as true
  and ``017`` as 15; a paragraph separator it counts as a line break, which moves every later
  line; a byte order mark inside the text, which it skips; a ``...`` line the pure parser reads
  otherwise; an anchor or alias name it ends at a character the pure parser keeps; a tag the pure
  parser refuses; a ``:`` with no space after it inside ``[]`` or ``{}``, which it reads as a key's
  colon; and several forms of block scalar (``|`` or ``>``), among them a ``#`` right after the
  header and blank lines indented deeper than the text. So text holding a tab, one of the three
  Unicode line breaks, a byte order mark or a line that starts with ``%`` or ``...`` never reaches
  it, and neither does text its own scanner finds a tag or a block scalar in, a key's colon not
  followed by a space or a line end, or an anchor or alias whose name is followed by anything but
  a space, a line end or ``,[]{}``.
* It fails where the pure parser does not (``{a:1}``, a reserved directive), and its error text
  differs where both fail. Any failure is read again by the pure parser, so a file the pure parser
  reads gives its document and a broken file gives the pure parser's message, marks and all.
* An empty mapping value starts at the end of its key's line rather than at the next token. Only
  the end of a node and that start differ, and no reader here uses either.

So every result and every message is the pure parser's, whether or not the C parser is installed;
without it ``YAML(typ='safe')`` is the pure parser and only the speed changes. The round-trip
loader has no C form and is not read here.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from contextlib import suppress
from typing import IO, Any

from ruamel.yaml import YAML
from ruamel.yaml.tokens import AliasToken, AnchorToken, ScalarToken, TagToken, ValueToken

__all__ = ["compose", "load", "load_file"]

_PURE_ONLY = re.compile("[\t\x85\u2028\u2029\ufeff]|(?:^|\r)(?:%|\\.\\.\\.)", re.MULTILINE)
_SCANNED = re.compile("[&*!|>]|:[^ \r\n]")
_NAME_END = frozenset(" \r\n,[]{}")
_VALUE_END = frozenset(" \r\n")
_LINE_BREAK = re.compile("\r\n|\r|\n")


def _c_reads_as_pure(text: str) -> bool:
    if _PURE_ONLY.search(text) is not None:
        return False
    if _SCANNED.search(text) is None:
        return True
    lines = _LINE_BREAK.split(text)
    for token in YAML(typ="safe").scan(text):
        if isinstance(token, TagToken) or (
            isinstance(token, ScalarToken) and token.style in ("|", ">")
        ):
            return False
        if isinstance(token, AnchorToken | AliasToken | ValueToken):
            line, column = token.end_mark.line, token.end_mark.column
            following = lines[line][column : column + 1] if line < len(lines) else ""
            ends = _NAME_END if isinstance(token, AnchorToken | AliasToken) else _VALUE_END
            if following and following not in ends:
                return False
    return True


def load(text: str) -> Any:
    """The document in ``text``, or the pure parser's ``YAMLError``."""
    with suppress(Exception):
        if _c_reads_as_pure(text):
            return YAML(typ="safe").load(text)
    return YAML(typ="safe", pure=True).load(text)


def compose(text: str) -> Any:
    """The node tree of the document in ``text``, or the pure parser's ``YAMLError``."""
    with suppress(Exception):
        if _c_reads_as_pure(text):
            return YAML(typ="safe").compose(text)
    return YAML(typ="safe", pure=True).compose(text)


def load_file(opener: Callable[[], IO[str]]) -> Any:
    """The document in the stream ``opener`` opens, or what the pure parser raises reading it.

    A failure to open or decode is raised by opening again for the pure parser, so its text is the
    one the stream gives the pure parser's reader.
    """
    with suppress(Exception):
        with opener() as stream:
            text = stream.read()
        if _c_reads_as_pure(text):
            return YAML(typ="safe").load(text)
    with opener() as stream:
        return YAML(typ="safe", pure=True).load(stream)
