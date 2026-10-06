"""Parse a source file with the grammar its pack pins, and read full names from the tree.

The engine knows no language. The grammar's distribution, module and function names are built
from the ``language`` value of a pack's ``grammar`` block, and every tree node type read here comes
from a pack.
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from functools import cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from tree_sitter import Language, Node, Parser

from periplus.engine.pattern import reshape
from periplus.errors import ExitCode, Problem
from periplus.manifest import MANIFEST_FILENAME, LoadedPack

__all__ = [
    "Grammar",
    "ImportRule",
    "STEPS",
    "ParsedFile",
    "Step",
    "argument_of",
    "grammar_problems",
    "line_of",
    "literal_of",
    "parse_file",
    "resolve_name",
    "text_of",
]

#: A resolution step as a rutter declares it: its kind, and its argument or ``""``.
Step = tuple[str, str]

#: Each step kind, and whether it takes an argument.
STEPS = {
    "full_if_prefixed": True,
    "bound_first_segment": False,
    "prefix_with": True,
    "prefix_bare_with": True,
    "as_written": False,
}


def resolve_name(
    written: str,
    steps: Sequence[Step],
    separator: str,
    bindings: Mapping[str, str],
    values: Mapping[str, str],
) -> str | None:
    """The name the first step that holds gives; ``None`` when none holds.

    ``full_if_prefixed`` holds when the name starts with its text and gives the rest.
    ``bound_first_segment`` holds when ``bindings`` holds the name's first segment and gives the
    bound target joined with the remaining segments. ``prefix_with`` holds when ``values`` holds
    the value it names and gives that value joined with the name, an empty part left out.
    ``prefix_bare_with`` does the same for a name that does not hold the separator.
    ``as_written`` always holds.
    """
    for kind, argument in steps:
        if kind == "full_if_prefixed" and written.startswith(argument):
            return written.removeprefix(argument)
        if kind == "bound_first_segment":
            first, _, rest = written.partition(separator) if separator else (written, "", "")
            if first in bindings:
                return separator.join(part for part in (bindings[first], rest) if part)
        bare = kind == "prefix_bare_with" and not (separator and separator in written)
        if (kind == "prefix_with" or bare) and argument in values:
            return separator.join(part for part in (values[argument], written) if part)
        if kind == "as_written":
            return written
    return None


@dataclass(frozen=True, slots=True)
class ImportRule:
    """One ``imports`` entry of a pack file.

    ``declaration`` and ``group`` are the tree node types of an import and of its grouped form,
    and ``clause`` the node that binds one name. ``facts`` pairs a fact's name with the tree field
    it names, read on the clause or else on the declaration. The rest is the entry's ``bind``:
    ``names`` are the sources of the bound name, tried in order, each a fact, ``last_segment`` or
    ``path``; ``normalize`` reshapes the name; a fact whose text is in ``unbound_aliases`` binds
    nothing; ``prefix_from_group`` joins a clause of the grouped form to the declaration's written
    prefix; ``strip_prefix`` is stripped from the path's front; and a declaration or clause where
    the field of the fact ``skip_when`` is set binds nothing.
    """

    declaration: str
    group: str | None
    clause: str
    facts: tuple[tuple[str, str], ...]
    names: tuple[str, ...] = ()
    prefix_from_group: bool = False
    strip_prefix: str = ""
    skip_when: str = ""
    normalize: tuple[tuple[re.Pattern[str], str], ...] = ()
    unbound_aliases: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class Grammar:
    """What the pack that owns a file type says about its tree and its names.

    ``parts`` and ``separator`` build a full name, and ``resolve`` holds the steps that turn a
    written name into a full one. ``namespace`` is the node type that declares a
    namespace and ``namespace_name`` the field holding its name; ``namespace_value`` names instead
    the value of the file's table that is its one namespace. ``written`` holds the node types
    of a name written in source.

    ``attribute`` is the node type of an attribute and ``attribute_list`` the node that holds it on
    a declaration; ``arguments`` is the field of its arguments, ``argument`` the node type of one,
    and ``argument_name`` the field of a named argument's name. ``literals`` are the node types of
    a text literal and ``literal_content`` the node type of its text. Each is empty when the pack
    declares no attribute. ``comment`` is the node type of a comment, empty when none is declared.
    ``call_arguments`` is the field of a call's arguments. ``call_argument`` is the node type of
    one, and each named child that is not an extra is one when it is empty; ``call_argument_name``
    is the field of a named argument's name. ``call_literals`` are the node types of a call's text
    literal, ``call_literal_content`` those of its text, and ``call_literal_delimiters`` those of
    its children that are skipped.
    """

    language: str
    parts: tuple[str, ...]
    separator: str
    namespace: str
    namespace_name: str
    written: frozenset[str]
    imports: tuple[ImportRule, ...]
    attribute: str = ""
    attribute_list: str = ""
    arguments: str = ""
    argument: str = ""
    argument_name: str = ""
    literals: frozenset[str] = frozenset()
    literal_content: str = ""
    comment: str = ""
    resolve: tuple[Step, ...] = ()
    namespace_value: str = ""
    call_arguments: str = ""
    call_argument: str = ""
    call_argument_name: str = ""
    call_literals: frozenset[str] = frozenset()
    call_literal_content: frozenset[str] = frozenset()
    call_literal_delimiters: frozenset[str] = frozenset()

    def join(self, values: Mapping[str, str]) -> str | None:
        """The full name: each part's value that is not empty, joined by the separator; ``None``
        when a part is absent."""
        if any(part not in values for part in self.parts):
            return None
        return self.separator.join(values[part] for part in self.parts if values[part])


@dataclass(frozen=True, slots=True)
class ParsedFile:
    """One parsed file: whether its tree holds an error, its nodes by type, and its names."""

    broken: bool
    by_type: Mapping[str, tuple[Node, ...]]
    namespaces: tuple[tuple[int, str], ...]
    #: The import table of each namespace block, keyed by the block's index in ``namespaces``;
    #: ``-1`` is the code before the first namespace declaration.
    imports: Mapping[int, Mapping[str, str]]
    #: The file's value table: its path values and the project's settings values.
    values: Mapping[str, str] = field(default_factory=dict)

    def namespace_at(self, node: Node) -> str:
        """The name of the last namespace declaration that starts before the node, or ``""``."""
        block = self.block_at(node.start_byte)
        return self.namespaces[block][1] if block >= 0 else ""

    def block_at(self, start: int) -> int:
        """The index of the last namespace declaration that starts before the byte, or ``-1``."""
        found = -1
        for index, (begins, _) in enumerate(self.namespaces):
            if begins >= start:
                break
            found = index
        return found

    def resolve(self, written: Node, grammar: Grammar) -> str | None:
        """The full name a written name stands for, by the grammar's resolution steps; ``None``
        when no step holds, and the name as written when the grammar declares none.

        The bindings are the imports of the name's namespace block, and the value ``namespace``
        is the namespace in force.
        """
        return resolve_name(
            text_of(written),
            grammar.resolve or (("as_written", ""),),
            grammar.separator,
            self.imports.get(self.block_at(written.start_byte), {}),
            {"namespace": self.namespace_at(written)},
        )


def text_of(node: Node) -> str:
    """The node's source text."""
    return (node.text or b"").decode("utf-8", "replace")


def argument_of(attribute: Node, key: str, grammar: Grammar, call: bool = False) -> Node | None:
    """The value of the attribute's argument named ``key``, or at position ``key`` when it is a
    whole number; ``None`` when the attribute has no such argument. ``call`` reads a call's
    arguments by the grammar's call keys. A wrapped or named argument's value is its last named
    child."""
    field, wrapper, named = (
        (grammar.call_arguments, grammar.call_argument, grammar.call_argument_name)
        if call
        else (grammar.arguments, grammar.argument, grammar.argument_name)
    )
    holder = attribute.child_by_field_name(field)
    found = [
        c
        for c in (holder.named_children if holder else ())
        if (c.type == wrapper if wrapper else not c.is_extra)
    ]
    for position, argument in enumerate(found):
        name = argument.child_by_field_name(named)
        if text_of(name) == key if name is not None else key == str(position):
            return argument.named_children[-1] if wrapper or name is not None else argument
    return None


def literal_of(node: Node, grammar: Grammar, call: bool = False) -> str | None:
    """The text of a text literal; ``None`` for any other node, or a literal holding more.
    ``call`` reads it by the grammar's call keys."""
    literals, content, delimiters = (
        (grammar.call_literals, grammar.call_literal_content, grammar.call_literal_delimiters)
        if call
        else (grammar.literals, frozenset({grammar.literal_content}), frozenset())
    )
    parts = [p for p in node.named_children if p.type not in delimiters]
    if node.type not in literals or any(p.type not in content for p in parts):
        return None
    return "".join(text_of(part) for part in parts)


def line_of(node: Node) -> int:
    """The node's 1-based start line."""
    # Indexed, not ``.row``: tree-sitter 0.26.0's ``Point.row`` drops a reference to the row on
    # each read, which frees a row above 256 while it is still in use and crashes the process.
    return node.start_point[0] + 1


def parse_file(path: Path, grammar: Grammar, values: Mapping[str, str]) -> ParsedFile:
    """The file parsed with the grammar, indexed by node type, with its namespaces, imports and
    value table. With ``namespace_value``, the value of that name is one namespace over the whole
    file, and the file has none when the value is absent."""
    tree = _parser(grammar.language).parse(path.read_bytes())
    by_type: dict[str, list[Node]] = {}
    pending = [tree.root_node]
    while pending:
        node = pending.pop()
        by_type.setdefault(node.type, []).append(node)
        pending.extend(reversed(node.children))
    namespaces = tuple(
        (node.start_byte, text_of(name) if name is not None else "")
        for node in by_type.get(grammar.namespace, [])
        for name in [node.child_by_field_name(grammar.namespace_name)]
    )
    if grammar.namespace_value:
        found = values.get(grammar.namespace_value)
        namespaces = ((-1, found),) if found is not None else ()
    parsed = ParsedFile(
        broken=tree.root_node.has_error,
        by_type={name: tuple(nodes) for name, nodes in by_type.items()},
        namespaces=namespaces,
        imports={},
        values=values,
    )
    imports: dict[int, dict[str, str]] = {}
    for rule in grammar.imports:
        for declaration in by_type.get(rule.declaration, []):
            block = parsed.block_at(declaration.start_byte)
            imports.setdefault(block, {}).update(_bound(declaration, rule, grammar))
    return replace(parsed, imports=imports)


def _bound(declaration: Node, rule: ImportRule, grammar: Grammar) -> dict[str, str]:
    """Each name one import declaration binds, to the path it is written with, as the rule's
    ``bind`` says; a clause no name source gives a name binds nothing."""
    facts = dict(rule.facts)
    skip = facts.get(rule.skip_when, "")
    if skip and declaration.child_by_field_name(skip) is not None:
        return {}
    groups = [child for child in declaration.children if child.type == rule.group]
    prefix = next((text_of(c) for c in declaration.children if c.type in grammar.written), "")
    clauses = [
        clause
        for holder in groups or [declaration]
        for clause in holder.children
        if clause.type == rule.clause
    ]
    bound: dict[str, str] = {}
    for clause in clauses:
        if skip and clause.child_by_field_name(skip) is not None:
            continue
        named = {
            s: clause.child_by_field_name(facts[s]) or declaration.child_by_field_name(facts[s])
            for s in rule.names
            if s in facts
        }
        path = next(
            (
                text_of(c)
                for c in clause.children
                if c.type in grammar.written and c not in named.values()
            ),
            None,
        )
        if path is None:
            continue
        if groups and rule.prefix_from_group:
            path = grammar.separator.join((prefix, path))
        path = path.removeprefix(rule.strip_prefix)
        name = None
        for source in rule.names:
            node = named.get(source)
            if node is not None:
                name = None if text_of(node) in rule.unbound_aliases else text_of(node)
                break
            if source in ("last_segment", "path"):
                name = path if source == "path" else path.rsplit(grammar.separator, 1)[-1]
                break
        if name is not None:
            bound[reshape(name, rule.normalize)] = path
    return bound


@cache
def _parser(language: str) -> Parser:
    """A parser for the language: module ``tree_sitter_<language>``, its ``language_<language>``
    function, or ``language`` when it has no such function."""
    module = importlib.import_module(f"tree_sitter_{language}")
    function = getattr(module, f"language_{language}", None) or module.language
    return Parser(Language(function()))


def grammar_problems(packs: Sequence[LoadedPack]) -> list[Problem]:
    """Each pin of a loaded pack's grammar that the installed distributions do not meet, and each
    pinned grammar that is installed at its version and cannot be imported."""
    problems: list[Problem] = []
    for pack in packs:
        grammar = pack.manifest.document.get("grammar")
        if not isinstance(grammar, Mapping):
            continue
        runtime = str(grammar["provider"])
        for distribution, pinned in (
            (runtime, str(grammar["provider_version"])),
            (f"{runtime}-{grammar['language']}", str(grammar["grammar_version"])),
        ):
            try:
                found = version(distribution)
            except PackageNotFoundError:
                found = "none"
            if found == pinned and distribution != runtime:
                try:
                    _parser(str(grammar["language"]))
                except Exception as error:  # noqa: BLE001 - any failure of a grammar's import
                    problems.append(
                        Problem(
                            ExitCode.GRAMMAR_MISMATCH,
                            f"{pack.name.pack}/{MANIFEST_FILENAME} pins the grammar "
                            f"{distribution} {pinned}, and it cannot be imported: {error}",
                            {"pack": pack.name.pack, "distribution": distribution},
                        )
                    )
            elif found != pinned:
                problems.append(
                    Problem(
                        ExitCode.GRAMMAR_MISMATCH,
                        f"{pack.name.pack}/{MANIFEST_FILENAME} pins {distribution} {pinned}, "
                        f"and the version found is {found}",
                        {
                            "pack": pack.name.pack,
                            "distribution": distribution,
                            "pinned": pinned,
                            "found": found,
                        },
                    )
                )
    return problems
