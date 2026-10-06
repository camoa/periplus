"""Step one: read every rule file of the loaded packs into typed records and the type table."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any

from periplus.engine.pattern import compile_pattern
from periplus.engine.select import FileTypes, FolderUnresolved, holds_double_star
from periplus.engine.tree import STEPS, Grammar, ImportRule, Step, _parser
from periplus.errors import ExitCode, HarnessError, Problem
from periplus.manifest import MANIFEST_FILENAME, LoadedPack
from periplus.validate import MANIFEST_SCHEMA, PACK_FILE_SCHEMA, _load, _schema, _yaml_files

__all__ = [
    "PATTERN_VALUE",
    "PLACEHOLDER",
    "TEXT",
    "Condition",
    "EXECUTED_KEYS",
    "UNEXECUTED_KEYS",
    "EdgeKind",
    "EdgeSpec",
    "FileInfo",
    "HasKey",
    "IdMatches",
    "KeyEquals",
    "PackRulesUnreadable",
    "Rule",
    "RuleSet",
    "TypeInfo",
    "Value",
    "load_rules",
    "namespace_of",
    "namespaces",
    "node_types",
    "twin_type",
    "unexecuted",
]

#: The prefix of a rule's key paths.
_RULE = "file.rules.*."

#: The key paths, below their holder, of resolution steps and the separator beside them.
_RESOLVE = (
    *(".resolve", ".resolve.*.full_if_prefixed", ".resolve.*.prefix_with"),
    *(".resolve.*.prefix_bare_with", ".separator"),
)

#: Every key path of the two pack schemas that the engine or the pack check executes. ``*`` is one
#: key or item. A path starts with the document it sits in: ``manifest.`` or ``file.``.
EXECUTED_KEYS = frozenset(
    {
        *(f"manifest.{k}" for k in ("pack", "version", "depends", "folders", "identity")),
        *(f"manifest.identity.call_{k}" for k in ("arguments", "argument", "argument_name")),
        *(f"manifest.identity.call_literal{k}" for k in ("s", "_content", "_delimiters")),
        *(f"manifest.detect{k}" for k in ("", ".any_of", ".any_of.*.path", ".any_of.*.contains")),
        *(
            f"manifest.grammar{k}"
            for k in ("", ".provider", ".provider_version", ".language", ".grammar_version")
        ),
        *(
            f"manifest.files{k}"
            for k in (
                *("", ".extends", ".extensions", ".add_extensions", ".exclude", ".add_excludes"),
                *(".types", ".types.*.endings", ".types.*.names", ".types.*.reader"),
                ".types.*.format",
                *(f".types.*.path_values{k}" for k in ("", ".*.pattern", ".*.template")),
                ".types.*.path_values.*.relative_to",
                *(f".types.*.path_values.*{k}" for k in (".case", ".normalize")),
                *(f".types.*.path_values.*.normalize.*{k}" for k in (".replace", ".with")),
                *(f".types.*.sections{k}" for k in ("", ".*.name", ".*.open", ".*.close")),
                *(f".types.*.spans{k}" for k in ("", ".*.name", ".*.open", ".*.balance")),
                *(f".types.*{k}" for k in _RESOLVE),
            )
        ),
        *(f"file.needs{k}" for k in ("", ".types", ".roles")),
        *("file.roles", "file.roles.*.name"),
        *(f"file.edge_kinds{k}" for k in ("", ".*.kind", ".*.from", ".*.to")),
        *(
            f"file.node_types{k}"
            for k in ("", ".*.name", ".*.parent", ".*.abstract", ".*.id_namespace")
        ),
        *(f"file.imports{k}" for k in ("", ".*.ast", ".*.group_ast", ".*.clause", ".*.facts")),
        *(f"file.imports.*.bind{k}" for k in ("", ".name", ".prefix_from_group", ".strip_prefix")),
        "file.imports.*.bind.skip_when_field_set",
        *(f"file.imports.*.bind{k}" for k in (".unbound_aliases", ".normalize")),
        *(f"file.imports.*.bind.normalize.*{k}" for k in (".replace", ".with")),
        "file.rules",
        *(f"{_RULE}{k}" for k in ("rule", "reads", "in", "confidence", "match", "id", "emits")),
        *(f"{_RULE}line{k}" for k in ("", ".capture")),
        *(f"{_RULE}values{k}" for k in ("", ".*.from", ".*.from.capture", ".*.template")),
        *(f"{_RULE}values.*{k}" for k in (".from.enclosing", ".join")),
        *(
            f"{_RULE}values.*{k}"
            for k in (".normalize", ".normalize.*.replace", ".normalize.*.with")
        ),
        f"{_RULE}values.*.case",
        *(
            f"{_RULE}match.{k}"
            for k in (
                *("file", "filetype", "each", "where", "declaration", "name_child"),
                *("reference", "skip_names", "whole_written"),
                *("body_child", "attribute", "annotation", "text", "reads_sections"),
            )
        ),
        *(
            f"{_RULE}match.where.*.{k}"
            for k in ("key", "has_key", "id_matches", "is_mapping", "applies_to", "has_child")
        ),
        *(f"{_RULE}match.where.*.name_matches{k}" for k in ("", ".child", ".pattern")),
        *(
            f"{_RULE}id.{k}"
            for k in (
                *("from", "from.capture", "from.attribute_argument", "from.annotation_key"),
                *("from.argument", "pattern"),
                *("template", "must_be", "normalize", "normalize.*.replace", "normalize.*.with"),
            )
        ),
        *(f"{_RULE}id{k}" for k in _RESOLVE),
        *(f"{_RULE}emits.*.binding{k}" for k in ("", ".name", ".target")),
        *(f"{_RULE}emits.*.{k}" for k in ("node", "node.type", "attribute", "attribute.name")),
        *(f"{_RULE}emits.*.{k}" for k in ("attribute.from", "attribute.template", "edge")),
        f"{_RULE}emits.*.edge.kind",
        f"{_RULE}emits.*.edge.to.from.attribute_argument",
        f"{_RULE}emits.*.edge.to.from.argument",
        *(
            f"{_RULE}emits.*.edge.{end}{k}"
            for end in ("from", "to")
            for k in (
                *("", ".from", ".template", ".type", ".each", ".pattern", ".where", ".on_miss"),
                *(".where.*.matches", ".where.*.listed_at", ".from.key", ".from.capture"),
                *(".from.*.key", ".from.*.each", ".types", ".declared", *_RESOLVE),
            )
        ),
    }
)


def _schema_paths(schema: Mapping[str, Any], node: object, path: str) -> set[str]:
    """Each key path below ``path`` the schema node accepts, its ``$defs`` followed. ``$schema``
    names the contract a file is written against and carries no data, so it is left out."""
    if not isinstance(node, Mapping):
        return set()
    if "$ref" in node:
        return _schema_paths(schema, schema["$defs"][node["$ref"].rsplit("/", 1)[-1]], path)
    found: set[str] = set()
    for name, child in node.get("properties", {}).items():
        if name != "$schema":
            found |= {f"{path}.{name}", *_schema_paths(schema, child, f"{path}.{name}")}
    for branch in (*node.get("oneOf", ()), *node.get("anyOf", ())):
        found |= _schema_paths(schema, branch, path)
    for key in ("items", "additionalProperties"):
        found |= _schema_paths(schema, node.get(key), f"{path}.*")
    return found


#: Every other key path the two pack schemas accept. A rule that holds one is not executed; a pack
#: that holds any other one is reported as a rule the engine cannot execute.
UNEXECUTED_KEYS: tuple[str, ...] = tuple(
    sorted(
        {
            path
            for name, document in (("manifest", MANIFEST_SCHEMA), ("file", PACK_FILE_SCHEMA))
            for path in _schema_paths(_schema(document), _schema(document), name)
        }
        - EXECUTED_KEYS
    )
)


def unexecuted(document: object, prefix: str) -> list[str]:
    """The paths of ``UNEXECUTED_KEYS`` that start with ``prefix`` and that the document holds,
    each without the prefix, leaving out a path below another one found. A rule's paths are found
    only under the rule prefix ``file.rules.*.``, since the rule itself is reported."""
    found = [
        path.removeprefix(prefix)
        for path in UNEXECUTED_KEYS
        if path.startswith(prefix)
        and (prefix == _RULE or not path.startswith(_RULE))
        and _holds(document, path.removeprefix(prefix).split("."))
    ]
    return [path for path in found if not any(path.startswith(f"{q}.") for q in found)]


def _holds(value: object, segments: Sequence[str]) -> bool:
    if not segments:
        return True
    head, rest = segments[0], segments[1:]
    if head == "*":
        children = list(value.values()) if isinstance(value, Mapping) else []
        children += value if isinstance(value, list) else []
        return any(_holds(child, rest) for child in children)
    return isinstance(value, Mapping) and head in value and _holds(value[head], rest)


#: The keys of the rule shapes this engine executes. A rule with any other key is not run.
_RULE_KEYS = {"rule", "reads", "in", "match", "id", "emits", "confidence"}

#: The match keys of a rule that reads a parse tree.
_DECLARATION_MATCH = {"declaration", "name_child", "body_child", "where", "filetype", "file"}

#: The names the engine fills for a declaration rule's id. Any other name its template holds is a
#: path value, a settings value or a field of the matched node.
_TREE_FILLED = {"declared_name", "namespace", "qualified_name", "enclosing_type"}

#: The edge ends of a tree rule that name a node, where the other kind of end is a written name.
_TREE_ENDS = {"this_node", "enclosing_class"}

#: The edge ends of an attribute rule that name a node; the other kind is an argument's value.
_ATTRIBUTE_ENDS = {"this_node", "enclosing_class", "enclosing_method"}

#: The edge ends whose value is the whole id another rule minted, namespace and all.
_WHOLE_ENDS = {"enclosing_declaration", "enclosing_class", "enclosing_method", "declared"}

#: A ``{name}`` in an id or edge template.
PLACEHOLDER = re.compile(r"\{(\w+)\}")

#: A ``{name}`` in an id pattern: a path or settings value, filled as literal text. A name starts
#: with a letter, so a quantifier such as ``{2}`` stays one.
PATTERN_VALUE = re.compile(r"\{([A-Za-z]\w*)\}")

#: The key path an edge source ``text`` reads: an entry whose value is text holds it under this key
#: alone, which no other key path reaches.
TEXT = ""


class PackRulesUnreadable(HarnessError):
    """A rule file cannot be read, a type is declared twice, or a rule emits an undeclared type."""

    code = ExitCode.PACK_RULES_UNREADABLE


@dataclass(frozen=True, slots=True)
class TypeInfo:
    """One node type: its id namespace, its parent type, and the pack that declared it."""

    name: str
    id_namespace: str | None
    parent: str | None
    pack: str


@dataclass(frozen=True, slots=True)
class KeyEquals:
    """A ``where`` condition: a value at the key path equals ``value``, type included, or with
    ``negate`` none does.

    An absent key equals ``None``.
    """

    path: str
    value: Any
    negate: bool = False


@dataclass(frozen=True, slots=True)
class HasKey:
    """A ``where`` condition: the key path reaches something."""

    path: str


@dataclass(frozen=True, slots=True)
class IdMatches:
    """A ``where`` condition: the pattern is found in the entry's key or the file's stem."""

    pattern: re.Pattern[str]


@dataclass(frozen=True, slots=True)
class IsMapping:
    """A ``where`` condition: whether the entry's value is a mapping, an empty value counting as an
    empty mapping, equals ``value``. A whole file's root is a mapping."""

    value: bool


Condition = KeyEquals | HasKey | IdMatches | IsMapping


@dataclass(frozen=True, slots=True)
class Value:
    """A named value: one capture, or a template filled from the values known, then reshaped by
    ``normalize`` and then ``case``, ``lower``, ``upper`` or ``""``. A path value holds the
    ``pattern`` searched in the file's path, and its template is filled from that pattern's
    captures; with ``relative_to``, a folder name, the pattern is searched in the path below the
    deepest directory of that folder that holds the file. ``enclosing`` names a span and one
    capture of its opening: the value joins that capture of each span holding the match with
    ``join``."""

    name: str
    capture: str
    template: str | None
    normalize: tuple[tuple[re.Pattern[str], str], ...] = ()
    case: str = ""
    pattern: re.Pattern[str] | None = None
    relative_to: str = ""
    enclosing: tuple[str, str] | None = None
    join: str = ""


@dataclass(frozen=True, slots=True)
class FileInfo:
    """What a declared file type says about its files: the values its path gives, and its
    sections, each a name, an opening pattern and a closing template; and the resolution steps,
    with their separator, an edge end of a text rule takes when it declares none. Last its spans,
    each a name, an opening pattern, and the opening and closing characters it balances."""

    path_values: tuple[Value, ...] = ()
    sections: tuple[tuple[str, re.Pattern[str], str], ...] = ()
    resolve: tuple[Step, ...] = ()
    separator: str = ""
    spans: tuple[tuple[str, re.Pattern[str], str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class Rule:
    """One rule. ``supported`` is false for a shape this engine does not execute.

    ``each`` is the key path whose mapping entries the rule fires on, ``""`` for the file's top
    level, or ``None`` for the whole file. ``id_template`` names ``{file_stem}`` and ``{key}``.

    A rule that reads a parse tree holds ``declaration``, the tree node type it fires on, and its
    ``id_template`` names the tree sources instead; it is ``""`` for an edge rule with no id, and
    for an id from the call's argument ``id_argument``, a position.

    A rule that matches an attribute holds ``attribute``, the full name of its class, and
    ``applies_to``, the tree node type the attribute sits on. Its id is the value of the argument
    ``id_argument``, a name or a position, and ``must_be_literal`` says that value must be a text
    literal. Its ``attributes`` pair a name with an argument.

    A rule that matches a docblock annotation holds ``annotation``, the bare name written after the
    at sign, and ``applies_to``; ``id_argument`` and the second of each ``attributes`` pair name a
    key of the annotation's body.
    """

    pack: str
    name: str
    supported: bool
    folders: tuple[str, ...]
    glob: str
    filetype: str
    node_type: str
    confidence: str
    where: tuple[Condition, ...] = ()
    normalize: tuple[tuple[re.Pattern[str], str], ...] = ()
    attributes: tuple[tuple[str, str], ...] = ()
    edges: tuple[EdgeSpec, ...] = ()
    reason: str = ""
    twin_type: str = ""
    each: str | None = None
    id_template: str = "{file_stem}"
    #: A declaration rule: the pattern searched in the text of the source ``id_source``, its named
    #: captures joining the values ``id_template`` may name; ``""`` for none.
    id_pattern: str = ""
    id_source: str = ""
    declaration: str = ""
    name_child: str = ""
    body_child: str = ""
    #: A declaration rule: the tree node types the match must have as direct children, and the
    #: fields of the matched node its id names.
    has_child: tuple[str, ...] = ()
    fields: tuple[str, ...] = ()
    #: A declaration or reference rule: each child, by field or node type, and the pattern its
    #: whole text must match.
    name_matches: tuple[tuple[str, re.Pattern[str]], ...] = ()
    attribute: str = ""
    applies_to: str = ""
    id_argument: str = ""
    must_be_literal: bool = False
    annotation: str = ""
    #: A reference rule: the tree node type it fires on, its ``name_child`` the written name's
    #: child, and ``member_child`` the child whose text follows the resolved name, or ``""``.
    #: ``skip_names`` holds the written names that make nothing, and ``whole_written`` says every
    #: node below the written name must be a written name too.
    reference: str = ""
    member_child: str = ""
    skip_names: frozenset[str] = frozenset()
    whole_written: bool = False
    #: A rule that reads its file as text: the pattern it fires on, and the capture of the id.
    #: Its ``attributes`` and each edge's ``key`` name a capture.
    text: re.Pattern[str] | None = None
    id_capture: str = ""
    #: A text rule's named values in order, the sections its match reads inside, and each
    #: attribute given as a name and a template; a text rule's ``id_template`` is its id template.
    values: tuple[Value, ...] = ()
    reads_sections: tuple[str, ...] = ()
    templates: tuple[tuple[str, str], ...] = ()
    #: A text rule's bindings, each a name template and a target template, and its id's
    #: resolution steps with their separator.
    bindings: tuple[tuple[str, str], ...] = ()
    id_resolve: tuple[Step, ...] = ()
    id_separator: str = ""
    #: A text rule's ``line`` capture: the node, its values and templates sit at its line.
    line_capture: str = ""


@dataclass(frozen=True, slots=True)
class EdgeSpec:
    """One edge a rule emits. ``parts`` is the list form of the end's source.

    A part is ``("key", path)``, ``("each", path)`` or ``("entry", "")`` for the entry's own key;
    without parts the end reads ``key``. A rule
    that reads data runs from ``this_node`` to that end, and ``finish`` is ``""``. A rule that
    reads a parse tree names each end in ``start`` and ``finish``: ``this_node``,
    ``enclosing_class``, ``declared`` for the node of the type ``declared`` holds at that end, or,
    for ``finish``, ``qualified_name`` for each name written in the match. An attribute rule also
    names ``enclosing_method``, and its ``finish`` may be ``attribute_argument`` with the argument
    in ``key``. A reference rule's ``key`` is the position of the call's argument its end reads,
    or ``""`` for the written name.
    """

    kind: str
    key: str
    each: bool
    matches: str | None
    pattern: re.Pattern[str] | None
    template: str | None
    parts: tuple[tuple[str, str], ...]
    start: str = "this_node"
    finish: str = ""
    #: The template begins with a declared id namespace and two colons, so its value is a full id.
    full_id: bool = False
    #: The key path of a list in the same file that must hold the end's value; ``None`` for none.
    listed_at: str | None = None
    #: The type the composed end has when no rule finds it; ``""`` for the kind's types there.
    #: A data or text rule's composed end is the from end when ``start`` is ``""``.
    to_type: str = ""
    #: The composed end becomes an unresolved node when no rule maps its id.
    on_miss: bool = False
    #: A text rule's end: its resolution steps and their separator.
    resolve: tuple[Step, ...] = ()
    separator: str = ""
    #: The composed end's candidate types, in order, in place of ``to_type``; ``to_type`` is the
    #: first of them.
    types: tuple[str, ...] = ()
    #: The node type of a ``declared`` end, at from and at to; ``""`` at an end that is not one.
    declared: tuple[str, str] = ("", "")


@dataclass(frozen=True, slots=True)
class EdgeKind:
    """One edge kind: the types allowed at each end."""

    name: str
    from_types: tuple[str, ...]
    to_types: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RuleSet:
    """Every rule in load order, the table of declared types and the table of edge kinds.

    ``grammars`` holds, for each file type a supported tree rule reads, the grammar of its pack.
    ``values`` holds the project's settings values, which every template may name.
    """

    rules: tuple[Rule, ...]
    types: Mapping[str, TypeInfo]
    edge_kinds: Mapping[str, EdgeKind]
    conflicts: tuple[Problem, ...] = ()
    grammars: Mapping[str, Grammar] = field(default_factory=dict)
    files: Mapping[str, FileInfo] = field(default_factory=dict)
    values: Mapping[str, str] = field(default_factory=dict)


def load_rules(
    packs: Sequence[LoadedPack],
    values: Mapping[str, str] | None = None,
    origins: Mapping[str, str] | None = None,
) -> RuleSet:
    """Read each pack's rule files, in pack order and then file order, and check the types.

    Raises ``PackRulesUnreadable`` for an unreadable file, a type entry with no string name, a
    type declared twice, and a supported rule that emits a type with no id namespace. An edge kind
    declared twice with different ends is left in ``RuleSet.conflicts``, so the run can report it
    beside the other problems of the packs, and so is a name the settings ``values`` and a pack
    both give, a path value template naming a value nothing gives, and a declaration rule's id
    naming a name that is no field of its grammar and no value. ``origins`` names the settings
    file of each settings value. Every pack given has passed its schema.
    """
    values = dict(values or {})
    types: dict[str, TypeInfo] = {}
    kinds: dict[str, EdgeKind] = {}
    conflicts: list[Problem] = []
    declared_at: dict[str, tuple[str, str]] = {}
    rules: list[Rule] = []
    items: list[Mapping[str, Any]] = []
    sources: list[str] = []
    siblings: dict[str, list[Mapping[str, Any]]] = {}
    imports: dict[str, list[Mapping[str, Any]]] = {}
    for pack in packs:
        for relative, node in _yaml_files(pack.directory):
            if relative == MANIFEST_FILENAME:
                continue
            document, readable = _load(node, [])
            if not readable or not isinstance(document, Mapping):
                raise PackRulesUnreadable(
                    f"{pack.name.pack}/{relative} cannot be read as a rule file",
                    {"pack": pack.name.pack, "file": relative},
                )
            _read_types(pack.name.pack, document.get("node_types"), types)
            _read_kinds(
                pack.name.pack, relative, document.get("edge_kinds"), kinds, conflicts, declared_at
            )
            imports.setdefault(pack.name.pack, []).extend(document.get("imports", []))
            for item in document.get("rules", []):
                rules.append(_read_rule(pack.name.pack, item))
                items.append(item)
                sources.append(relative)
                siblings.setdefault(pack.name.pack, []).append(item)
    prefixes = tuple(f"{t.id_namespace}::" for t in types.values() if t.id_namespace)
    rules = [
        _check_edges(_full_ids(_with_twin(rule, item, siblings[rule.pack]), prefixes), types, kinds)
        for rule, item in zip(rules, items, strict=True)
    ]
    file_types = FileTypes.build(packs, {})
    rules = [_check_reader(rule, file_types) for rule in rules]
    files = _file_info(packs)
    rules = [_check_names(rule, files.get(rule.filetype, FileInfo()), values) for rule in rules]
    conflicts.extend(_collisions(rules, sources, files, packs, values, origins or {}))
    grammars: dict[str, Grammar] = {}
    for index, rule in enumerate(rules):
        tree = rule.declaration or rule.attribute or rule.annotation or rule.reference
        if rule.supported and tree and rule.filetype not in grammars:
            try:
                grammars[rule.filetype] = _grammar(rule.filetype, packs, imports)
            except _Unsupported as reason:
                rules[index] = replace(rule, supported=False, reason=str(reason))
        if rules[index].supported and rule.declaration:
            conflicts.extend(_unknown_fields(rule, sources[index], grammars[rule.filetype]))
        if rules[index].supported and rule.attribute and not grammars[rule.filetype].attribute:
            missing = f"the grammar for {rule.filetype} declares no identity.attribute block"
            rules[index] = replace(rule, supported=False, reason=missing)
        if rules[index].supported and rule.annotation and not grammars[rule.filetype].comment:
            missing = f"the grammar for {rule.filetype} declares no identity.comment"
            rules[index] = replace(rule, supported=False, reason=missing)
    for rule in rules:
        if (
            rule.supported
            and rule.node_type in types
            and namespace_of(types, rule.node_type) is None
        ):
            raise PackRulesUnreadable(
                f"rule {rule.name} of {rule.pack} emits {rule.node_type}, "
                "which no loaded pack declares with an id_namespace",
                {"pack": rule.pack, "rule": rule.name, "type": rule.node_type},
            )
    return RuleSet(
        rules=tuple(rules),
        types=types,
        edge_kinds=kinds,
        conflicts=tuple(conflicts),
        grammars=grammars,
        files=files,
        values=values,
    )


def _file_info(packs: Sequence[LoadedPack]) -> dict[str, FileInfo]:
    """Each declared file type's path values, sections and spans, by type name.

    Raises ``PackRulesUnreadable`` for a pattern that does not compile, a span whose balance is not
    two different characters, and a ``relative_to`` naming a folder no loaded pack declares or
    whose value holds ``**``, naming the pack.
    """
    found: dict[str, FileInfo] = {}
    for pack in packs:
        files = pack.manifest.document.get("files")
        declared = files.get("types") if isinstance(files, Mapping) else None
        for name, spec in declared.items() if isinstance(declared, Mapping) else ():
            try:
                values = tuple(
                    _read_value(str(key), value, path=True)
                    for key, value in spec.get("path_values", {}).items()
                )
                sections = tuple(
                    (str(s["name"]), _regex(s["open"]), _closing(s["close"], s["open"]))
                    for s in spec.get("sections", [])
                )
                steps = _read_steps(spec.get("resolve", []))
                spans = tuple(
                    (str(s["name"]), _regex(s["open"]), *_balance(s["balance"]))
                    for s in spec.get("spans", [])
                )
                for value in values:
                    _flat_folder(value, packs)
            except _Unsupported as reason:
                raise PackRulesUnreadable(
                    f"{pack.name.pack}/{MANIFEST_FILENAME}: the file type {name}: {reason}",
                    {"pack": pack.name.pack, "file": MANIFEST_FILENAME, "name": str(name)},
                ) from reason
            known = found.get(name, FileInfo())
            found[name] = FileInfo(
                known.path_values + values,
                known.sections + sections,
                known.resolve or steps,
                known.separator if known.resolve else str(spec.get("separator", "")),
                known.spans + spans,
            )
    return found


def _balance(pair: object) -> tuple[str, str]:
    """A span's opening and closing characters."""
    if not (
        isinstance(pair, list)
        and len(pair) == 2
        and all(isinstance(c, str) and len(c) == 1 for c in pair)
        and pair[0] != pair[1]
    ):
        raise _Unsupported("a span's balance is not two different characters")
    return pair[0], pair[1]


def _flat_folder(value: Value, packs: Sequence[LoadedPack]) -> None:
    """Refuse a ``relative_to`` naming a folder no loaded pack declares, or whose value holds
    ``**``: the deepest directory below it would win over the folder itself."""
    if not value.relative_to:
        return
    key = f"path_values.{value.name}.relative_to"
    try:
        deep = holds_double_star(value.relative_to, packs, {})
    except FolderUnresolved as error:
        raise _Unsupported(f"{key} names the folder {value.relative_to}: {error}") from error
    if deep:
        raise _Unsupported(f"{key} names the folder {value.relative_to}, whose value holds **")


def _closing(close: object, opening: object) -> str:
    """The closing template, checked to compile with each placeholder of a named capture of the
    opening pattern standing for empty text."""
    groups = _regex(opening).groupindex
    if not isinstance(close, str):
        raise _Unsupported("a section's close is not a string")
    _regex(PLACEHOLDER.sub(lambda p: "" if p.group(1) in groups else p.group(0), close))
    return close


def _check_names(rule: Rule, info: FileInfo, values: Mapping[str, str]) -> Rule:
    """The rule, marked not executed when a template names a value nothing gives, a value's
    template names a value defined after it, or the match reads a section its file type does not
    declare. A declaration rule is given the fields its id names."""
    tree = rule.declaration or rule.attribute or rule.annotation or rule.reference
    known = {value.name for value in info.path_values} | set(values)
    if rule.supported and rule.declaration:
        captures = set(compile_pattern(PATTERN_VALUE.sub("", rule.id_pattern)).groupindex)
        clash = captures & (_TREE_FILLED | known)
        unknown = set(PATTERN_VALUE.findall(rule.id_pattern)) - known
        if clash or unknown:
            reason = (
                f"the id pattern captures {', '.join(sorted(clash))}, a name the engine, a path "
                "value or a settings value gives"
                if clash
                else f"the id pattern names {', '.join(sorted(unknown))}, which is no path value "
                "or settings value"
            )
            return replace(rule, supported=False, reason=reason)
        named = {*PLACEHOLDER.findall(rule.id_template), rule.id_source} - {""}
        named = named - _TREE_FILLED - known - captures
        return replace(rule, fields=tuple(sorted(named)))
    if not rule.supported or tree:
        return rule
    if rule.text is not None:
        before = known | set(rule.text.groupindex)
        for value in rule.values:
            later = set(PLACEHOLDER.findall(value.template or "")) - before
            if later:
                missing = ", ".join(sorted(later))
                reason = (
                    f"the value {value.name} names {missing}, which is no capture, path value, "
                    "settings value or value defined before it"
                )
                return replace(rule, supported=False, reason=reason)
            before.add(value.name)
        known |= {*rule.text.groupindex, *(value.name for value in rule.values)}
        templates = [rule.id_template, *(v.template or "" for v in rule.values)]
        templates += [t for _, t in rule.templates] + [e.template or "" for e in rule.edges]
        templates += [t for binding in rule.bindings for t in binding]
    else:
        known |= {"file_stem", *(("key",) if rule.each is not None else ())}
        templates = [rule.id_template]
    names = {name for template in templates for name in PLACEHOLDER.findall(template)}
    if names - known:
        missing = ", ".join(sorted(names - known))
        return replace(
            rule,
            supported=False,
            reason=f"a template names {missing}, which is "
            "no capture, value, path value or settings value the rule has",
        )
    if rule.text is not None:
        steps = [*rule.id_resolve, *(step for edge in rule.edges for step in edge.resolve)]
        prefixing = ("prefix_with", "prefix_bare_with")
        named = {argument for kind, argument in steps if kind in prefixing} - known
        if any(not edge.resolve for edge in rule.edges):
            paths = {value.name for value in info.path_values} | set(values)
            named |= {argument for kind, argument in info.resolve if kind in prefixing} - paths
        if named:
            return replace(
                rule,
                supported=False,
                reason=f"a prefix_with step names {', '.join(sorted(named))}, which is "
                "no capture, value, path value or settings value the rule has",
            )
    sections = {name for name, _, _ in info.sections}
    if set(rule.reads_sections) - sections:
        missing = ", ".join(sorted(set(rule.reads_sections) - sections))
        reason = f"match.reads_sections names {missing}, which its file type does not declare"
        return replace(rule, supported=False, reason=reason)
    captured = {(name, group) for name, opening, _, _ in info.spans for group in opening.groupindex}
    for value in rule.values:
        if value.enclosing is not None and value.enclosing not in captured:
            span, capture = value.enclosing
            reason = (
                f"the value {value.name} names the capture {capture} of the span {span}, which "
                "its file type does not declare"
            )
            return replace(rule, supported=False, reason=reason)
    return rule


def _unknown_fields(rule: Rule, source: str, grammar: Grammar) -> list[Problem]:
    """A problem for each name the declaration rule's id reads as a node field that is no field of
    the grammar, naming the rule, the template and the name. A grammar that cannot be imported
    is left to the grammar check."""
    try:
        language = _parser(grammar.language).language
    except Exception:  # noqa: BLE001 - any failure of a grammar's import, reported elsewhere
        language = None
    if language is None:
        return []
    return [
        Problem(
            ExitCode.PACK_RULES_UNREADABLE,
            f"{rule.pack}/{source}: the rule {rule.name} has the id template "
            f"{rule.id_template}, which names {name}, no field of the {grammar.language} "
            "grammar, path value or settings value",
            {"pack": rule.pack, "file": source, "rule": rule.name, "name": name},
        )
        for name in rule.fields
        if language.field_id_for_name(name) is None
    ]


def _collisions(
    rules: Sequence[Rule],
    sources: Sequence[str],
    files: Mapping[str, FileInfo],
    packs: Sequence[LoadedPack],
    values: Mapping[str, str],
    origins: Mapping[str, str],
) -> list[Problem]:
    """Each path value name that the engine fills already (on a tree file type, also the names it
    fills for a declaration rule and ``line``), that a rule on its file type captures or names as
    a value, or that a settings value gives; each settings value name the engine fills, or a rule
    captures or names as a value; and each path value template naming a name that is no capture
    of its pattern and no settings value, or both: a problem naming the pack, the file and the
    names, and the settings file of a settings value."""
    problems: list[Problem] = []
    tree_filled = {"file_stem", "key", "line", *_TREE_FILLED}

    def setting(name: str) -> str:
        origin = f" of {origins[name]}" if name in origins else ""
        return f"the settings value {name}{origin}"

    for pack in packs:
        files_block = pack.manifest.document.get("files")
        declared = files_block.get("types") if isinstance(files_block, Mapping) else None
        for kind, spec in declared.items() if isinstance(declared, Mapping) else ():
            path_values = spec.get("path_values", {}) if isinstance(spec, Mapping) else {}
            tree = isinstance(spec, Mapping) and spec.get("reader") == "tree"
            for name, value in path_values.items():
                if name in (tree_filled if tree else {"file_stem", "key"}):
                    problems.append(_collision(pack.name.pack, MANIFEST_FILENAME, name, kind))
                where = f"{pack.name.pack}/{MANIFEST_FILENAME}: the path value {name} of the file "
                detail = {"pack": pack.name.pack, "file": MANIFEST_FILENAME, "name": name}
                if name in values:
                    message = f"{where}type {kind} has the name of {setting(name)}"
                    problems.append(Problem(ExitCode.PACK_RULES_UNREADABLE, message, detail))
                captures = set(compile_pattern(value["pattern"]).groupindex)
                named = set(PLACEHOLDER.findall(value["template"]))
                for missing in sorted(named - captures - set(values)):
                    message = (
                        f"{where}type {kind} has the template {value['template']}, which names "
                        f"{missing}, no capture of its pattern and no settings value"
                    )
                    problems.append(Problem(ExitCode.PACK_RULES_UNREADABLE, message, detail))
                for both in sorted(named & captures & set(values)):
                    message = (
                        f"{where}type {kind} has the template {value['template']}, which names "
                        f"{both}, both a capture of its pattern and a settings value"
                    )
                    problems.append(Problem(ExitCode.PACK_RULES_UNREADABLE, message, detail))
    for rule, source in zip(rules, sources, strict=True):
        names = {value.name for value in files.get(rule.filetype, FileInfo()).path_values}
        given = {*(rule.text.groupindex if rule.text is not None else ())}
        given |= {value.name for value in rule.values}
        problems.extend(
            _collision(rule.pack, source, name, rule.filetype) for name in sorted(names & given)
        )
        problems.extend(
            Problem(
                ExitCode.PACK_RULES_UNREADABLE,
                f"{rule.pack}/{source}: the rule {rule.name} captures or names the value {name}, "
                f"which is also {setting(name)}",
                {"pack": rule.pack, "file": source, "name": name},
            )
            for name in sorted(set(values) & given)
        )
    problems.extend(
        Problem(
            ExitCode.PACK_RULES_UNREADABLE,
            f"{setting(name)} has a name the engine fills",
            {"name": name},
        )
        for name in sorted(set(values) & tree_filled)
    )
    return problems


def _collision(pack: str, file: str, name: str, kind: str) -> Problem:
    return Problem(
        ExitCode.PACK_RULES_UNREADABLE,
        f"{pack}/{file}: the path value {name} of the file type {kind} is a name the engine or "
        "a rule already fills",
        {"pack": pack, "file": file, "name": name},
    )


def _check_reader(rule: Rule, types: FileTypes) -> Rule:
    """The rule, marked not executed when every type of its file type is read otherwise than the
    rule reads: a text rule text, a tree rule a tree, any other rule that reads content data. A
    file type no pack declares is read as data."""
    if rule.text is not None:
        needed = "text"
    elif rule.declaration or rule.attribute or rule.annotation or rule.reference:
        needed = "tree"
    elif rule.where or rule.attributes or rule.edges or rule.each is not None:
        needed = "data"
    else:
        return rule
    readers = {kind.reader for kind in types.named(rule.filetype)} or {"data"}
    if not rule.supported or needed in readers:
        return rule
    reason = f"the rule reads {needed}, and the file type {rule.filetype} is read as "
    return replace(rule, supported=False, reason=reason + ", ".join(sorted(readers)))


def _grammar(
    filetype: str, packs: Sequence[LoadedPack], imports: Mapping[str, list[Mapping[str, Any]]]
) -> Grammar:
    """The grammar of the pack that declares the file type read as a tree, and pins one.

    Its ``identity`` block, an open object in the manifest schema, gives the full-name parts and
    separator, the namespace declaration and its name field, and the written-name node types.
    """
    owners = {kind.pack for kind in FileTypes.build(packs, {}).named(filetype)}
    for pack in packs:
        document = pack.manifest.document
        grammar, identity = document.get("grammar"), document.get("identity")
        if pack.name.pack not in owners or not isinstance(grammar, Mapping):
            continue
        unread = _Unsupported(
            f"{pack.name.pack}/{MANIFEST_FILENAME} declares the grammar for {filetype}, and "
            "its identity block or an imports entry lacks a key the engine reads: "
            "qualified_name.parts and .separator, namespace.declaration and .name_child or "
            "namespace.path_value, "
            "written_names, an import's ast, clause and facts with a bind naming only its "
            "facts, last_segment or path, an optional attribute mapping, an optional comment and "
            "optional resolution steps"
        )
        if not isinstance(identity, Mapping):
            raise unread
        try:
            qualified, namespace = identity["qualified_name"], identity["namespace"]
            attribute = identity.get("attribute", {})
            if "path_value" in namespace:
                namespace = {"declaration": "", "name_child": "", **namespace}
            return Grammar(
                language=str(grammar["language"]),
                parts=tuple(str(part) for part in qualified["parts"]),
                separator=str(qualified["separator"]),
                namespace=str(namespace["declaration"]),
                namespace_name=str(namespace["name_child"]),
                namespace_value=str(namespace.get("path_value", "")),
                written=frozenset(str(name) for name in identity["written_names"]),
                imports=tuple(_import_rule(entry) for entry in imports.get(pack.name.pack, [])),
                attribute=str(attribute.get("node", "")),
                attribute_list=str(attribute.get("list", "")),
                arguments=str(attribute.get("arguments", "")),
                argument=str(attribute.get("argument", "")),
                argument_name=str(attribute.get("argument_name", "")),
                literals=frozenset(str(name) for name in attribute.get("literals", [])),
                literal_content=str(attribute.get("literal_content", "")),
                comment=str(identity.get("comment", "")),
                resolve=_read_steps(identity.get("resolve", [])),
                call_arguments=str(identity.get("call_arguments", "arguments")),
                call_argument=str(identity.get("call_argument", "")),
                call_argument_name=str(identity.get("call_argument_name", "")),
                call_literals=frozenset(map(str, identity.get("call_literals", []))),
                call_literal_content=frozenset(map(str, identity.get("call_literal_content", []))),
                call_literal_delimiters=frozenset(
                    map(str, identity.get("call_literal_delimiters", []))
                ),
            )
        except (KeyError, TypeError) as error:
            raise unread from error
    raise _Unsupported(f"no loaded pack declares a grammar for the file type {filetype}")


def _import_rule(entry: Mapping[str, Any]) -> ImportRule:
    """One ``imports`` entry. Raises ``KeyError`` when its ``bind`` names a fact it lacks."""
    bind, facts = entry.get("bind", {}), {str(k): str(v) for k, v in entry["facts"].items()}
    rule = ImportRule(
        declaration=entry["ast"],
        group=entry.get("group_ast"),
        clause=entry["clause"],
        facts=tuple(facts.items()),
        names=tuple(str(source) for source in bind.get("name", [])),
        prefix_from_group=bind.get("prefix_from_group") is True,
        strip_prefix=str(bind.get("strip_prefix", "")),
        skip_when=str(bind.get("skip_when_field_set", "")),
        normalize=_read_normalize(bind["normalize"]) if "normalize" in bind else (),
        unbound_aliases=frozenset(str(alias) for alias in bind.get("unbound_aliases", [])),
    )
    for fact in (*rule.names, *([rule.skip_when] if rule.skip_when else [])):
        if fact not in ("last_segment", "path") and fact not in facts:
            raise KeyError(fact)
    return rule


def namespace_of(types: Mapping[str, TypeInfo], name: str) -> str | None:
    """The type's own id namespace, or the nearest ancestor's along ``parent``."""
    seen: set[str] = set()
    while name in types and name not in seen:
        seen.add(name)
        if types[name].id_namespace is not None:
            return types[name].id_namespace
        parent = types[name].parent
        if parent is None:
            return None
        name = parent
    return None


def namespaces(types: Mapping[str, TypeInfo], names: Sequence[str]) -> list[str]:
    """The distinct id namespaces of the types that have one, sorted so the first is stable."""
    found = {namespace_of(types, name) for name in names}
    return sorted(namespace for namespace in found if namespace is not None)


def node_types(rule: Mapping[str, Any]) -> list[str]:
    """The type of each node the rule entry emits."""
    return [str(emit["node"]["type"]) for emit in rule.get("emits", []) if "node" in emit]


def twin_type(rule: Mapping[str, Any], siblings: Sequence[Mapping[str, Any]]) -> str | None:
    """The node type of the edge rule's twin, or ``None`` when it has none.

    The twin is the first other rule of the same pack that emits a node and whose ``match``, ``id``
    and ``in`` equal the edge rule's as documents. ``siblings`` is every rule entry of that pack.
    """
    for other in siblings:
        nodes = node_types(other)
        if (
            other is not rule
            and nodes
            and all(other.get(key) == rule.get(key) for key in ("match", "id", "in"))
        ):
            return nodes[0]
    return None


def _with_twin(rule: Rule, item: Mapping[str, Any], siblings: Sequence[Mapping[str, Any]]) -> Rule:
    """An edge rule, given the type of its twin node rule."""
    if not (rule.supported and rule.edges):
        return rule
    found = twin_type(item, siblings)
    return replace(rule, twin_type=found) if found else rule


def _full_ids(rule: Rule, prefixes: tuple[str, ...]) -> Rule:
    """The rule, each edge marked ``full_id`` when its template begins with one of the prefixes."""
    edges = tuple(
        replace(edge, full_id=(edge.template or "").startswith(prefixes)) for edge in rule.edges
    )
    return replace(rule, edges=edges) if edges != rule.edges else rule


def _check_edges(rule: Rule, types: Mapping[str, TypeInfo], kinds: Mapping[str, EdgeKind]) -> Rule:
    """The rule, marked not executed when an edge it emits cannot be minted."""
    for edge in rule.edges if rule.supported else ():
        kind = kinds.get(edge.kind)
        if kind is None:
            continue
        from_twin = bool(rule.twin_type) and edge.start == "this_node"
        to_twin = bool(rule.twin_type) and edge.finish == "this_node"
        # A composed end that is a full id, or that lists its types, needs no namespace of its
        # kind's types; neither does an end that takes the whole id of a node another rule found.
        composed_full = edge.full_id or bool(edge.types)
        from_full = composed_full and not edge.start or edge.start in _WHOLE_ENDS
        to_full = composed_full and bool(edge.start) or edge.finish in _WHOLE_ENDS
        if any(namespace_of(types, name) is None for name in edge.types):
            reason = f"a type the end of {edge.kind} lists has no id namespace"
            return replace(rule, supported=False, reason=reason)
        if not from_twin and not from_full and len(namespaces(types, kind.from_types)) != 1:
            reason = f"the types at the from end of {edge.kind} do not share one id namespace"
        elif not to_twin and not to_full and len(namespaces(types, kind.to_types)) != 1:
            reason = f"the types at the to end of {edge.kind} do not share one id namespace"
        else:
            continue
        return replace(rule, supported=False, reason=reason)
    return rule


def _read_kinds(
    pack: str,
    file: str,
    declared: object,
    kinds: dict[str, EdgeKind],
    conflicts: list[Problem],
    declared_at: dict[str, tuple[str, str]],
) -> None:
    for entry in declared if isinstance(declared, list) else []:
        name = entry.get("kind") if isinstance(entry, Mapping) else None
        ends: list[tuple[str, ...]] = []
        for end in (entry.get("from"), entry.get("to")) if isinstance(entry, Mapping) else ():
            listed = [end] if isinstance(end, str) else end
            if isinstance(listed, list) and all(isinstance(t, str) for t in listed):
                ends.append(tuple(sorted(listed)))
        if not isinstance(name, str) or len(ends) != 2:
            raise PackRulesUnreadable(
                f"an edge_kinds entry of {pack} is not a mapping with a string kind and its ends",
                {"pack": pack},
            )
        kind = EdgeKind(name, ends[0], ends[1])
        first_pack, first_file = declared_at.setdefault(name, (pack, file))
        if kinds.setdefault(name, kind) != kind:
            message = (
                f"the edge kind {name} is declared with different ends in {pack}/{file}, "
                f"after {first_pack}/{first_file}"
            )
            detail = {"kind": name, "pack": pack, "file": file}
            conflicts.append(Problem(ExitCode.PACK_RULES_UNREADABLE, message, detail))


def _read_types(pack: str, declared: object, types: dict[str, TypeInfo]) -> None:
    for entry in declared if isinstance(declared, list) else []:
        name = entry.get("name") if isinstance(entry, Mapping) else None
        if not isinstance(name, str):
            raise PackRulesUnreadable(
                f"a node_types entry of {pack} is not a mapping with a string name",
                {"pack": pack},
            )
        if name in types:
            raise PackRulesUnreadable(
                f"the type {name} is declared by both {types[name].pack} and {pack}",
                {"type": name},
            )
        types[name] = TypeInfo(
            name=name,
            id_namespace=entry.get("id_namespace"),
            parent=entry.get("parent"),
            pack=pack,
        )


class _Unsupported(Exception):
    """A rule shape the engine does not execute, with the reason."""


def _read_rule(pack: str, item: Any) -> Rule:
    """The rule as a record; ``supported`` holds only for the shapes the engine runs."""
    name = str(item.get("rule")) if isinstance(item, Mapping) else ""
    try:
        keys = unexecuted(item, _RULE)
        if keys:
            raise _Unsupported(f"the key {', '.join(keys)} is accepted and not executed")
        return _build_rule(pack, item)
    except _Unsupported as reason:
        return Rule(pack, name, False, (), "", "", "", "", reason=str(reason))


def _build_rule(pack: str, item: Any) -> Rule:
    if (
        isinstance(item.get("id"), Mapping)
        and "pattern" in item["id"]
        and "declaration" not in item["match"]
    ):
        raise _Unsupported("only the id of a tree declaration rule takes a pattern")
    if "text" in item["match"]:
        return _build_text(pack, item)
    if isinstance(item.get("id"), Mapping) and {"resolve", "separator"} & set(item["id"]):
        raise _Unsupported("only the id of a text rule takes resolution steps")
    if "declaration" in item["match"]:
        return _build_declaration(pack, item)
    if "reference" in item["match"]:
        return _build_reference(pack, item)
    if "attribute" in item["match"] or "annotation" in item["match"]:
        return _build_attribute(pack, item)
    shape = _Unsupported("the rule has a shape the engine does not execute")
    if not isinstance(item, Mapping) or set(item) != _RULE_KEYS or item["reads"] != "file":
        raise shape
    match, emits, folders = item["match"], item["emits"], item["in"]
    if (
        not isinstance(folders, list)
        or not all(isinstance(folder, str) for folder in folders)
        or not isinstance(match, dict)
        or not {"file", "filetype"} <= set(match) <= {"file", "filetype", "where", "each"}
        or not isinstance(match["file"], str)
        or not isinstance(match["filetype"], str)
        or not isinstance(item["id"], dict)
        or not set(item["id"]) <= {"from", "normalize", "template"}
        or not isinstance(emits, list)
        or not isinstance(item["confidence"], str)
    ):
        raise shape
    entries = [e for e in emits if isinstance(e, dict) and len(e) == 1]
    if len(entries) != len(emits) or not entries:
        raise shape
    nodes = [e["node"] for e in entries if "node" in e]
    attributes = [e["attribute"] for e in entries if "attribute" in e]
    edges = [e["edge"] for e in entries if "edge" in e]
    if len(nodes) + len(attributes) + len(edges) != len(entries) or (
        edges and (nodes or attributes)
    ):
        raise shape
    if not edges and (
        len(nodes) != 1 or not isinstance(nodes[0], dict) or set(nodes[0]) != {"type"}
    ):
        raise shape
    each = _read_each(match["each"]) if "each" in match else None
    read_edges = tuple(_read_edge(e) for e in edges)
    if each is None and any(edge.key == TEXT and not edge.parts for edge in read_edges):
        raise _Unsupported("an edge end from text needs match.each")
    return Rule(
        pack=pack,
        name=str(item["rule"]),
        supported=True,
        folders=tuple(folders),
        glob=match["file"],
        filetype=match["filetype"],
        node_type=str(nodes[0]["type"]) if nodes else "",
        confidence=item["confidence"],
        where=_read_where(match.get("where", [])),
        normalize=_read_normalize(item["id"].get("normalize", [])),
        attributes=tuple(_read_attribute(a) for a in attributes),
        edges=read_edges,
        each=each,
        id_template=_id_template(item["id"], each is not None),
    )


def _build_text(pack: str, item: Mapping[str, Any]) -> Rule:
    """A rule that reads its file as text and fires on each match of ``match.text``. The id comes
    from one capture or a template; each attribute from one capture, one value or a template; each
    edge runs between this_node and an end from one capture or a template, in either direction.
    A template names captures, path values and the rule's ``values``. A rule that emits bindings
    emits nothing else and has no id; the id and an edge end may hold resolution steps."""
    match, emits, block = item["match"], item["emits"], item.get("id")
    bindings = [emit["binding"] for emit in emits if "binding" in emit]
    if bindings:
        if "id" in item or len(bindings) != len(emits):
            raise _Unsupported("a text rule with a binding emits only bindings and has no id")
        block = {"template": ""}
    if (
        not _RULE_KEYS - {"id"} <= set(item) <= {*_RULE_KEYS, "values", "line"}
        or item["reads"] != "file"
        or not {"file", "filetype", "text"} <= set(match)
        or not set(match) <= {"file", "filetype", "text", "reads_sections"}
        or not isinstance(block, Mapping)
        or not set(block) <= {"from", "template", "normalize", "resolve", "separator"}
        or len({"from", "template"} & set(block)) != 1
        or not isinstance(block.get("template", ""), str)
        or not isinstance(match.get("reads_sections", []), list)
    ):
        raise _Unsupported(
            "a text rule is not a file rule with in, an id from one capture or a template, and "
            "match.file, match.filetype and match.text, with optional reads_sections, values "
            "and line"
        )
    pattern = _regex(match["text"])
    values = item.get("values", {})
    if not isinstance(values, Mapping):
        raise _Unsupported("the values of a text rule are not a mapping")
    read_values = tuple(_read_value(str(name), spec) for name, spec in values.items())
    nodes = node_types(item)
    attributes = [emit["attribute"] for emit in emits if "attribute" in emit]
    edges = [emit["edge"] for emit in emits if "edge" in emit]
    if (
        len(nodes) + len(attributes) + len(edges) + len(bindings) != len(emits)
        or len(nodes) > 1
        or any(emit["node"].keys() != {"type"} for emit in emits if "node" in emit)
        or (edges and (nodes or attributes))
        or (not edges and not nodes and not bindings)
        or not all(isinstance(b.get(k), str) for b in bindings for k in ("name", "target"))
    ):
        raise _Unsupported(
            "a text rule emits one node with a type and attributes, edges, or bindings"
        )
    read: list[tuple[str, str]] = []
    templates: list[tuple[str, str]] = []
    captures = [_capture(block["from"])] if "from" in block else []
    named = [value.name for value in read_values]
    for attribute in attributes:
        name, source = attribute.get("name"), attribute.get("from")
        if not isinstance(name, str) or set(attribute) not in (
            {"name", "from"},
            {"name", "template"},
        ):
            raise _Unsupported(
                "an attribute of a text rule is not a name and a capture, a value or a template"
            )
        if "template" in attribute and isinstance(attribute["template"], str):
            templates.append((name, attribute["template"]))
        elif isinstance(source, Mapping) and set(source) == {"value"} and source["value"] in named:
            read.append((name, str(source["value"])))
        else:
            read.append((name, _capture(source)))
            captures.append(read[-1][1])
    specs = []
    for edge in edges:
        flipped = edge.get("to") == "this_node" != edge.get("from")
        end = edge.get("from") if flipped else edge.get("to")
        if (
            set(edge) != {"kind", "from", "to"}
            or "this_node" not in (edge.get("from"), edge.get("to"))
            or not isinstance(end, Mapping)
            or not set(end)
            <= {"from", "template", "type", "types", "on_miss", "resolve", "separator"}
            or not {"from", "template"} & set(end)
            or not isinstance(end.get("template", ""), str)
            or not _types_ok(end)
        ):
            raise _Unsupported(
                "an edge of a text rule does not run between this_node and a capture or a template"
            )
        key = _capture(end["from"]) if "from" in end else ""
        captures += [key] if key else []
        specs.append(
            EdgeSpec(
                edge["kind"],
                key,
                False,
                None,
                None,
                end.get("template"),
                (),
                start="" if flipped else "this_node",
                finish="this_node" if flipped else "",
                to_type=end.get("type", next(iter(end.get("types", [])), "")),
                on_miss="on_miss" in end,
                resolve=_read_steps(end.get("resolve", [])),
                separator=str(end.get("separator", "")),
                types=tuple(end.get("types", ())),
            )
        )
    captures += [value.capture for value in read_values if value.capture]
    line = _capture(item["line"]) if "line" in item else ""
    captures += [line] if line else []
    if any(capture not in pattern.groupindex for capture in captures):
        raise _Unsupported("a capture a text rule names is not a named group of match.text")
    if set(named) & set(pattern.groupindex):
        raise _Unsupported("a value of a text rule has the name of a capture")
    return Rule(
        pack=pack,
        name=str(item["rule"]),
        supported=True,
        folders=tuple(item["in"]),
        glob=match["file"],
        filetype=match["filetype"],
        node_type=nodes[0] if nodes else "",
        confidence=item["confidence"],
        normalize=_read_normalize(block.get("normalize", [])),
        attributes=tuple(read),
        edges=tuple(specs),
        id_template=block.get("template", ""),
        text=pattern,
        id_capture=_capture(block["from"]) if "from" in block else "",
        values=read_values,
        reads_sections=tuple(str(name) for name in match.get("reads_sections", [])),
        templates=tuple(templates),
        bindings=tuple((b["name"], b["target"]) for b in bindings),
        id_resolve=_read_steps(block.get("resolve", [])),
        id_separator=str(block.get("separator", "")),
        line_capture=line,
    )


def _read_steps(steps: object) -> tuple[Step, ...]:
    """Resolution steps: each a kind that takes no text, or a mapping of one kind to its text."""
    read: list[Step] = []
    for step in steps if isinstance(steps, list) else [None]:
        pair = next(iter(step.items()), (None, "")) if isinstance(step, Mapping) else (step, "")
        kind, text = pair
        if (
            not isinstance(kind, str)
            or kind not in STEPS
            or (isinstance(step, Mapping) and len(step) != 1)
            or STEPS[kind] != (isinstance(text, str) and text != "")
        ):
            raise _Unsupported(
                "a resolution step is not bound_first_segment, as_written, or one of "
                "full_if_prefixed, prefix_with and prefix_bare_with with its text"
            )
        read.append((kind, text))
    return tuple(read)


def _read_value(name: str, spec: object, path: bool = False) -> Value:
    """One value: from one capture, the capture of each enclosing span with a join, or a
    template, or for a path value a pattern and a template with an optional ``relative_to``; with
    optional normalize and case."""
    keys = set(spec) - {"normalize", "case"} if isinstance(spec, Mapping) else set()
    source = spec.get("from") if isinstance(spec, Mapping) else None
    span = (
        source if isinstance(source, Mapping) and set(source) == {"enclosing", "capture"} else None
    )
    enclosing = span is not None
    if path:
        wanted = keys - {"relative_to"} == {"pattern", "template"}
    else:
        wanted = keys in ({"from"}, {"template"}) or (enclosing and keys == {"from", "join"})
    if (
        not isinstance(spec, Mapping)
        or not wanted
        or not all(isinstance(spec.get(k, ""), str) for k in ("template", "relative_to", "join"))
        or spec.get("case", "") not in ("", "lower", "upper")
    ):
        raise _Unsupported(
            f"the value {name} is not from one capture, from an enclosing span's capture, or a "
            "template, with optional normalize and case"
        )
    return Value(
        name,
        _capture(source) if "from" in spec and not enclosing else "",
        spec.get("template"),
        _read_normalize(spec.get("normalize", [])),
        str(spec.get("case", "")),
        _regex(spec["pattern"]) if path else None,
        str(spec.get("relative_to", "")),
        (str(span["enclosing"]), str(span["capture"])) if span is not None else None,
        str(spec.get("join", "")),
    )


def _capture(source: object) -> str:
    """The group ``{capture: name}`` names."""
    if not isinstance(source, Mapping) or set(source) != {"capture"}:
        raise _Unsupported("a source of a text rule is not one capture")
    return str(source["capture"])


def _build_declaration(pack: str, item: Mapping[str, Any]) -> Rule:
    """A rule that reads a parse tree: it fires on each tree node of the ``declaration`` type."""
    match, emits = item["match"], item["emits"]
    if (
        set(item) | {"id"} != _RULE_KEYS
        or item["reads"] != "file"
        or not set(match) <= _DECLARATION_MATCH
        or "filetype" not in match
        or not isinstance(match.get("name_child", ""), str)
    ):
        raise _Unsupported(
            "a declaration rule is not a file rule with in, match.filetype and no match keys "
            "beyond declaration, name_child, body_child, where and file"
        )
    where = match.get("where", [])
    if not isinstance(where, list) or not all(
        isinstance(c, Mapping)
        and len(c) == 1
        and set(c) <= {"has_child", "name_matches"}
        and (isinstance(next(iter(c.values())), str) or "name_matches" in c)
        for c in where
    ):
        raise _Unsupported(
            "the match.where of a declaration rule holds only has_child and name_matches conditions"
        )
    nodes = node_types(item)
    edges = [_read_tree_edge(emit["edge"]) for emit in emits if "edge" in emit]
    if (
        len(nodes) + len(edges) != len(emits)
        or len(nodes) > 1
        or any(emit["node"].keys() != {"type"} for emit in emits if "node" in emit)
    ):
        raise _Unsupported("a declaration rule emits one node with a type, or edges only")
    block = item.get("id", {})
    argument = _argument(block.get("from"), "argument") if isinstance(block, Mapping) else None
    if argument is not None and not set(block) <= {"from", "normalize"}:
        raise _Unsupported("an id from a call's argument takes only an optional normalize")
    if argument is not None and "body_child" in match:
        raise _Unsupported("an id from a call's argument cannot be combined with match.body_child")
    template = _tree_id(item["id"]) if "id" in item and argument is None else ""
    pattern = block.get("pattern", "") if template else ""
    if pattern:
        _regex(PATTERN_VALUE.sub("", pattern))
    if not (template or argument) and (
        nodes or any("this_node" in (e.start, e.finish) for e in edges)
    ):
        raise _Unsupported("a declaration rule that emits a node or names this_node needs an id")
    if "name_child" not in match and {"declared_name", "qualified_name"} & set(
        PLACEHOLDER.findall(template + (f"{{{block['from']}}}" if pattern else ""))
    ):
        raise _Unsupported("an id from declared_name or qualified_name needs match.name_child")
    return Rule(
        pack=pack,
        name=str(item["rule"]),
        supported=True,
        folders=tuple(item["in"]),
        glob=match.get("file", "*"),
        filetype=match["filetype"],
        node_type=nodes[0] if nodes else "",
        confidence=item["confidence"],
        edges=tuple(edges),
        id_template=template,
        id_pattern=pattern,
        id_source=str(block["from"]) if pattern else "",
        normalize=_read_normalize(item["id"].get("normalize", [])) if "id" in item else (),
        declaration=match["declaration"],
        name_child=match.get("name_child", ""),
        body_child=match.get("body_child", ""),
        has_child=tuple(c["has_child"] for c in where if "has_child" in c),
        id_argument=argument or "",
        name_matches=_name_matches(where, match.get("name_child")),
    )


def _types_ok(end: Mapping[str, Any]) -> bool:
    """Whether an end gives ``type`` or a list of ``types``, not both."""
    listed = end.get("types", [])
    return not {"type", "types"} <= set(end) and all(isinstance(t, str) for t in listed)


def _build_reference(pack: str, item: Mapping[str, Any]) -> Rule:
    """A rule that fires on each tree node of the ``reference`` type: an edge from the node the
    nearest enclosing declaration was given to the name its ``name_child`` writes."""
    match, emits = item["match"], item["emits"]
    child = match.get("name_child")
    fields = [child] if isinstance(child, str) else child if isinstance(child, list) else []
    if (
        set(item) != _RULE_KEYS - {"id"}
        or item["reads"] != "file"
        or not set(match)
        <= {"reference", "name_child", "filetype", "file", "skip_names", "whole_written", "where"}
        or "filetype" not in match
        or not fields
        or not all(isinstance(field, str) for field in fields)
        or any("edge" not in emit for emit in emits)
    ):
        raise _Unsupported(
            "a reference rule is not a file rule with in, match.reference, match.name_child, "
            "match.filetype and edges only, and no id"
        )
    where = match.get("where", [])
    if not isinstance(where, list) or not all(
        isinstance(c, Mapping) and set(c) == {"name_matches"} for c in where
    ):
        raise _Unsupported("the match.where of a reference rule holds only name_matches conditions")
    specs = []
    for emit in emits:
        edge = emit["edge"]
        end = edge.get("to")
        argument = _argument(end.get("from"), "argument") if isinstance(end, Mapping) else None
        if (
            set(edge) != {"kind", "from", "to"}
            or edge["from"] != "enclosing_declaration"
            or not isinstance(end, Mapping)
            or not set(end) <= {"type", "types", "on_miss", "resolve", "separator", "from"}
            or ("from" in end and argument is None)
            or not _types_ok(end)
        ):
            raise _Unsupported(
                "an edge of a reference rule does not run from enclosing_declaration to an end "
                "of type or types, resolve, separator and on_miss, and from a call's argument"
            )
        specs.append(
            EdgeSpec(
                edge["kind"],
                argument or "",
                False,
                None,
                None,
                None,
                (),
                start="enclosing_declaration",
                to_type=end.get("type", next(iter(end.get("types", [])), "")),
                on_miss="on_miss" in end,
                resolve=_read_steps(end.get("resolve", [])),
                separator=str(end.get("separator", "")),
                # The one-type form is a list of that one type.
                types=tuple(end.get("types", ())) or tuple(end.get("type", "").split()),
            )
        )
    return Rule(
        pack=pack,
        name=str(item["rule"]),
        supported=True,
        folders=tuple(item["in"]),
        glob=match.get("file", "*"),
        filetype=match["filetype"],
        node_type="",
        confidence=item["confidence"],
        edges=tuple(specs),
        id_template="",
        name_child=fields[0],
        reference=match["reference"],
        member_child=fields[1] if len(fields) > 1 else "",
        skip_names=frozenset(match.get("skip_names", ())),
        whole_written=match.get("whole_written") is True,
        name_matches=_name_matches(where, fields[0]),
    )


def _build_attribute(pack: str, item: Mapping[str, Any]) -> Rule:
    """A rule that fires on each attribute of one class, or each docblock annotation of one name,
    written on one kind of declaration."""
    match, emits = item["match"], item["emits"]
    where = match.get("where")
    shape = "annotation" if "annotation" in match else "attribute"
    key = "annotation_key" if shape == "annotation" else "attribute_argument"
    if (
        set(item) | {"id"} != _RULE_KEYS
        or item["reads"] != "file"
        or not set(match) <= {shape, "filetype", "where"}
        or "filetype" not in match
        or not (isinstance(where, list) and len(where) == 1 and set(where[0]) == {"applies_to"})
    ):
        raise _Unsupported(
            f"an {shape} rule is not a file rule with in, match.filetype and one where condition, "
            "applies_to"
        )
    nodes = node_types(item)
    attributes = [emit["attribute"] for emit in emits if "attribute" in emit]
    edges = [_read_attribute_edge(emit["edge"]) for emit in emits if "edge" in emit]
    if (
        len(nodes) + len(attributes) + len(edges) != len(emits)
        or len(nodes) > 1
        or any(emit["node"].keys() != {"type"} for emit in emits if "node" in emit)
        or (edges and (nodes or attributes))
        or (not edges and not nodes)
    ):
        raise _Unsupported(f"an {shape} rule emits one node with a type and attributes, or edges")
    if shape == "annotation" and any({e.start, e.finish} - _TREE_ENDS for e in edges):
        raise _Unsupported("an annotation rule's edge runs between this_node and enclosing_class")
    block = item.get("id", {})
    source = block.get("from") if isinstance(block, Mapping) else None
    if "id" in item and (not set(block) <= {"from", "must_be"} or _argument(source, key) is None):
        raise _Unsupported(f"the id block of an {shape} rule is not from one {key}")
    if "id" not in item and (nodes or any("this_node" in (e.start, e.finish) for e in edges)):
        raise _Unsupported(f"an {shape} rule that emits a node or names this_node needs an id")
    read = [(a.get("name"), _argument(a.get("from"), key)) for a in attributes]
    if any(not isinstance(name, str) or argument is None for name, argument in read):
        raise _Unsupported(f"an attribute of an {shape} rule is not a name and an {key}")
    return Rule(
        pack=pack,
        name=str(item["rule"]),
        supported=True,
        folders=tuple(item["in"]),
        glob="*",
        filetype=match["filetype"],
        node_type=nodes[0] if nodes else "",
        confidence=item["confidence"],
        attributes=tuple((str(name), str(argument)) for name, argument in read),
        edges=tuple(edges),
        id_template="",
        attribute=match.get("attribute", ""),
        applies_to=where[0]["applies_to"],
        id_argument=_argument(source, key) or "",
        must_be_literal=block.get("must_be") == "string_literal",
        annotation=match.get("annotation", ""),
    )


def _name_matches(
    where: list[Mapping[str, Any]], name_child: str | None
) -> tuple[tuple[str, re.Pattern[str]], ...]:
    """The child and pattern of each ``name_matches`` condition: a ``{child, pattern}`` mapping, or
    a pattern alone, which tests ``name_child`` and so needs it."""
    found = []
    for condition in (c["name_matches"] for c in where if "name_matches" in c):
        if isinstance(condition, Mapping):
            if set(condition) != {"child", "pattern"} or not isinstance(condition["child"], str):
                raise _Unsupported("a name_matches mapping is not a child and a pattern")
            found.append((condition["child"], _regex(condition["pattern"])))
        elif name_child is None:
            raise _Unsupported("a name_matches condition needs match.name_child")
        else:
            found.append((name_child, _regex(condition)))
    return tuple(found)


def _argument(source: object, key: str = "attribute_argument") -> str | None:
    """The argument or annotation key ``{key: name or position}`` names, or ``None``."""
    if not isinstance(source, Mapping) or set(source) != {key}:
        return None
    found = source[key]
    return str(found) if isinstance(found, (str, int)) and not isinstance(found, bool) else None


def _read_attribute_edge(edge: Mapping[str, Any]) -> EdgeSpec:
    """An edge of an attribute rule: between node ends, or to the id an argument's value names."""
    start, end = edge["from"], edge["to"]
    argument = (
        _argument(end.get("from")) if isinstance(end, Mapping) and set(end) == {"from"} else None
    )
    if (
        set(edge) != {"kind", "from", "to"}
        or not (isinstance(start, str) and start in _ATTRIBUTE_ENDS)
        or (argument is None and not (isinstance(end, str) and end in _ATTRIBUTE_ENDS))
    ):
        raise _Unsupported(
            "an edge of an attribute rule does not run from this_node, enclosing_class or "
            "enclosing_method to one of them or to {from: {attribute_argument: ...}}"
        )
    if argument is not None:
        return EdgeSpec(
            edge["kind"], argument, False, None, None, None, (), start, "attribute_argument"
        )
    return EdgeSpec(edge["kind"], "", False, None, None, None, (), start, end)


def _tree_id(block: Mapping[str, Any]) -> str:
    """The id block of a declaration rule as one template over its sources: a name the engine
    fills, a path value, a settings value or a field of the matched node."""
    source, template = block.get("from"), block.get("template")
    if "pattern" in block and set(block) <= {"from", "pattern", "template", "normalize"}:
        if not (isinstance(source, str) and PLACEHOLDER.fullmatch(f"{{{source}}}")):
            raise _Unsupported(
                "an id pattern reads one source, a name and not a list"
                if isinstance(source, list)
                else "an id pattern has no `from` naming the one source it reads"
                if source is None
                else "an id pattern reads one source, and its `from` is not a name"
            )
        return f"{{{source}}}" if template is None else str(template)
    if set(block) <= {"from", "template", "normalize"}:
        if isinstance(source, str) and PLACEHOLDER.fullmatch(f"{{{source}}}") and template is None:
            return f"{{{source}}}"
        if (
            isinstance(source, list)
            and isinstance(template, str)
            and set(PLACEHOLDER.findall(template)) == set(source)
        ):
            return template
    raise _Unsupported(
        "the id block of a declaration rule is not from one source, or from several with a "
        "template naming each, and an optional normalize"
    )


def _read_tree_edge(edge: Mapping[str, Any]) -> EdgeSpec:
    """An edge of a declaration rule: from a node end to a node end or to the written names. A node
    end ``{declared: <type>}`` is the node of that type another rule declares at the match."""
    start, end = edge["from"], edge["to"]
    declared = (_declared(start), _declared(end))
    start = "declared" if declared[0] else start
    finish = "declared" if declared[1] else end if isinstance(end, str) else ""
    if end == {"from": "qualified_name"}:
        finish = "qualified_name"
    if (
        set(edge) != {"kind", "from", "to"}
        or not (declared[0] or isinstance(start, str) and start in _TREE_ENDS)
        or not (declared[1] or finish in {*_TREE_ENDS, "qualified_name"})
    ):
        raise _Unsupported(
            "an edge of a declaration rule does not run from this_node, enclosing_class or "
            "{declared: <type>} to one of them or to {from: qualified_name}"
        )
    return EdgeSpec(edge["kind"], "", False, None, None, None, (), start, finish, declared=declared)


def _declared(end: object) -> str:
    """The node type an end ``{declared: <type>}`` names; ``""`` for any other end."""
    if isinstance(end, Mapping) and set(end) == {"declared"} and isinstance(end["declared"], str):
        return end["declared"]
    return ""


def _read_each(path: object) -> str:
    """The key path of the mapping whose entries a rule fires on; ``""`` for the top level."""
    if not isinstance(path, str) or path.count("*") != 1 or path.split(".")[-1] != "*":
        raise _Unsupported("match.each is not a key path whose last segment alone is a star")
    return path.removesuffix("*").removesuffix(".")


def _id_template(block: Mapping[str, Any], entries: bool) -> str:
    """The id block as one template over ``{file_stem}`` and ``{key}``."""
    source, template = block.get("from"), block.get("template")
    if source == "file_stem" and template is None:
        return "{file_stem}"
    if source == "key" and template is None and entries:
        return "{key}"
    named = [source] if isinstance(source, str) else source if source is not None else []
    allowed = {"file_stem", "key"} if entries else {"file_stem"}
    # A placeholder beyond the sources must be a path value, checked once the file types are read.
    if (
        isinstance(named, list)
        and set(named) <= allowed
        and isinstance(template, str)
        and set(named) <= set(PLACEHOLDER.findall(template))
    ):
        return template
    raise _Unsupported(
        "the id block is not from file_stem, from key with match.each, or a template naming its "
        "sources, file_stem, key with match.each, and path values"
    )


def _regex(expression: object) -> re.Pattern[str]:
    if not isinstance(expression, str):
        raise _Unsupported("a regular expression is not a string")
    try:
        return compile_pattern(expression)
    except re.error as error:
        raise _Unsupported(f"the expression {expression} does not compile: {error}") from error


def _key_path(source: object) -> str:
    if not isinstance(source, dict) or set(source) != {"key"} or not isinstance(source["key"], str):
        raise _Unsupported("a source is not a single key path")
    return source["key"]


def _read_where(where: object) -> tuple[Condition, ...]:
    conditions: list[Condition] = []
    for condition in where if isinstance(where, list) else [None]:
        name, found = (
            next(iter(condition.items()))
            if isinstance(condition, dict) and len(condition) == 1
            else (None, None)
        )
        if (
            name == "key"
            and isinstance(found, dict)
            and set(found) in ({"name", "equals"}, {"name", "not_equals"})
            and isinstance(found["name"], str)
            and not isinstance(found.get("equals", found.get("not_equals")), (dict, list))
        ):
            negate = "not_equals" in found
            value = found["not_equals" if negate else "equals"]
            conditions.append(KeyEquals(found["name"], value, negate))
        elif (
            name == "has_key"
            and isinstance(found, dict)
            and set(found) == {"path"}
            and isinstance(found["path"], str)
        ):
            conditions.append(HasKey(found["path"]))
        elif name == "id_matches":
            conditions.append(IdMatches(_regex(found)))
        elif name == "is_mapping" and isinstance(found, bool):
            conditions.append(IsMapping(found))
        else:
            raise _Unsupported(
                "a match.where condition is not a key with name and equals or not_equals, "
                "a has_key with one path, an id_matches, or an is_mapping of true or false"
            )
    return tuple(conditions)


def _read_normalize(normalize: object) -> tuple[tuple[re.Pattern[str], str], ...]:
    steps = []
    for step in normalize if isinstance(normalize, list) else [None]:
        if not isinstance(step, dict) or set(step) != {"replace", "with"}:
            raise _Unsupported("a normalize step is not a replace and a with")
        if not isinstance(step["with"], str):
            raise _Unsupported("a normalize step has a replacement that is not a string")
        steps.append((_regex(step["replace"]), step["with"]))
    return tuple(steps)


def _read_attribute(attribute: object) -> tuple[str, str]:
    if (
        not isinstance(attribute, dict)
        or set(attribute) != {"name", "from"}
        or not isinstance(attribute["name"], str)
    ):
        raise _Unsupported("an attribute is not a name and a key source")
    return attribute["name"], _key_path(attribute["from"])


def _read_edge(edge: object) -> EdgeSpec:
    """An edge of a data rule: between this_node and a composed end, in either direction."""
    flipped = isinstance(edge, dict) and edge.get("to") == "this_node" != edge.get("from")
    end = (edge.get("from") if flipped else edge.get("to")) if isinstance(edge, dict) else None
    on_miss = isinstance(end, dict) and "on_miss" in end
    if isinstance(edge, dict) and isinstance(end, dict):
        end = {key: value for key, value in end.items() if key != "on_miss"}
        edge = {**edge, "from": "this_node", "to": end}
    spec = _read_forward(edge)
    if flipped:
        spec = replace(spec, start="", finish="this_node")
    return replace(spec, on_miss=on_miss)


def _read_forward(edge: object) -> EdgeSpec:
    end = edge.get("to") if isinstance(edge, dict) else None
    if (
        not isinstance(edge, dict)
        or set(edge) != {"kind", "from", "to"}
        or not isinstance(edge["kind"], str)
        or edge["from"] != "this_node"
        or not isinstance(end, dict)
        or not {"from"} <= set(end) <= {"from", "each", "where", "pattern", "template", "type"}
    ):
        raise _Unsupported("an edge is not from this_node to a from end")
    template, to_type = end.get("template"), end.get("type", "")
    if template is not None and not isinstance(template, str):
        raise _Unsupported("an edge template is not a string")
    source = end["from"]
    if isinstance(source, list):
        parts = tuple(_read_part(part) for part in source)
        where = end.get("where", [{"listed_at": None}])
        one = where[0] if isinstance(where, list) and len(where) == 1 else None
        listed = one["listed_at"] if isinstance(one, dict) and set(one) == {"listed_at"} else ""
        if (
            sum(mode == "each" for mode, _ in parts) > 1
            or template is None
            or not {"from", "template"} <= set(end) <= {"from", "template", "where", "type"}
            or not (listed is None or (isinstance(listed, str) and listed))
        ):
            raise _Unsupported(
                "a list source needs a template, at most one each, and at most one where "
                "condition, listed_at"
            )
        return EdgeSpec(
            edge["kind"], "", False, None, None, template, parts, listed_at=listed, to_type=to_type
        )
    where = end.get("where")
    matches = None
    if where is not None:
        found = where[0].get("matches") if isinstance(where, list) and len(where) == 1 else None
        if not isinstance(found, str) or set(where[0]) != {"matches"}:
            raise _Unsupported("an edge where is not one matches glob")
        matches = found
    pattern = _regex(end["pattern"]) if "pattern" in end else None
    if not isinstance(end.get("each", False), bool):
        raise _Unsupported("an edge each is not true or false")
    path = TEXT if source == "text" else _key_path(source)
    return EdgeSpec(
        edge["kind"], path, end.get("each", False), matches, pattern, template, (), to_type=to_type
    )


def _read_part(part: object) -> tuple[str, str]:
    if isinstance(part, dict) and set(part) == {"each"} and isinstance(part["each"], str):
        return "each", part["each"]
    if part == "key":
        return "entry", ""
    return "key", _key_path(part)
