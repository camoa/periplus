"""Step three: run the supported rules over the selected files and count each fire."""

from __future__ import annotations

import posixpath
import re
from bisect import bisect_right
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from fnmatch import fnmatchcase
from itertools import product
from pathlib import Path
from typing import Any

from tree_sitter import Node

from periplus.engine.packload import (
    DECLARING_RECEIVERS,
    PATTERN_VALUE,
    PLACEHOLDER,
    TEXT,
    Condition,
    EdgeSpec,
    FileInfo,
    HasKey,
    IdMatches,
    IsMapping,
    Rule,
    RuleSet,
    Value,
    namespace_of,
    namespaces,
)
from periplus.engine.pattern import compile_pattern
from periplus.engine.pattern import reshape as _reshape
from periplus.engine.select import FileTypes, Selection, select_files
from periplus.engine.source import (
    DATA_READERS,
    SHORT_FORM_FORMAT,
    Entry,
    Hit,
    load_text,
    plain,
    resolve_path,
)
from periplus.engine.tree import (
    Grammar,
    ParsedFile,
    argument_of,
    line_of,
    literal_of,
    parse_file,
    resolve_name,
    text_of,
)
from periplus.manifest import LoadedPack

__all__ = ["FoundEdge", "FoundNode", "MapPass", "Skipped", "run_file_rules", "run_map_rules"]

#: One match that made nothing because its id argument is missing or not a text literal: the file,
#: the line of the attribute or annotation, the rule and the reason.
Skipped = tuple[str, int, str, str]

#: A docblock annotation value that is read: text in double quotes, or a nested annotation whose
#: body is one such text; its name is word characters and those of the grammar's separator.
_QUOTED = re.compile(r'"([^"]*)"')
_NESTED = r'@[\w{}]+\([\s*]*"([^"]*)"[\s*]*\)'

#: What is stripped around a key or a value of an annotation body: space and the docblock's stars.
_MARGIN = " \t\r\n*"

#: One span of a text file: its name, its start and end offsets, and its opening's captures.
Span = tuple[str, int, int, dict[str, str]]

#: One pass of the map rules: its number from 1, and each rule that added something in it, as its
#: pack, its name and its fires in that pass.
MapPass = tuple[int, tuple[tuple[str, str, int], ...]]


@dataclass(frozen=True, slots=True)
class FoundNode:
    """One node one rule found in one file, before nodes are merged on id.

    ``attributes`` holds the name, the plain value and the line of each attribute the rule read.
    """

    id: str
    type: str
    file: str
    line: int
    pack: str
    rule: str
    confidence: str
    attributes: tuple[tuple[str, Any, int], ...] = ()


@dataclass(frozen=True, slots=True)
class FoundEdge:
    """One edge one rule found in one file, before edges are merged on kind, from and to."""

    kind: str
    source: str
    target: str
    file: str
    line: int
    pack: str
    rule: str
    confidence: str
    #: The type the target has when no rule finds it; ``""`` for the kind's to types.
    target_type: str = ""
    #: The type the source has when no rule finds it; ``""`` for the kind's from types.
    source_type: str = ""
    #: The end declared ``on_miss: unresolved``, ``source`` or ``target``, and the name it
    #: searched for, without its namespace.
    on_miss: str = ""
    searched_for: str = ""
    #: The ids the composed end may take, one per candidate type in order; the first a rule maps
    #: wins, else the first. Empty for an end of one type.
    candidates: tuple[str, ...] = ()
    #: The composed end's candidate types, in the order tried; empty when the spec lists none.
    types_tried: tuple[str, ...] = ()
    #: The ends, ``source`` or ``target``, written ``{declared: <type>}``: when no rule finds such
    #: an end, it takes its named type alone, not the kind's.
    declared_ends: tuple[str, ...] = ()


def run_file_rules(
    root: Path,
    rule_set: RuleSet,
    packs: Sequence[LoadedPack],
    folders: Mapping[str, tuple[str, ...]],
    selection: Selection,
) -> tuple[
    list[FoundNode],
    list[FoundEdge],
    dict[tuple[str, str], int],
    list[str],
    set[str],
    set[str],
    list[str],
    list[Skipped],
]:
    """Run every supported rule; return the nodes, the edges, each rule's fires and files read.

    Then the candidate files the selection read and the ones it removed, the files read as a parse
    tree whose tree holds an error, and last the skipped matches, sorted. A rule that holds
    ``declaration``, ``attribute`` or ``annotation`` reads the tree, and a file is parsed once.

    A fire is one matched file, or one entry under the rule's ``each``, that meets the rule's
    ``where``; a binding rule's fire is one binding it gives. Binding rules run first, so a file's
    bindings are whole before any rule resolves a name with them. The file's stem is its name with
    the claimed ending removed, and the glob is matched against that stem. A whole-file node sits
    at line 1 and an entry's node at its key's line. A file is read once, and only for a rule that
    needs content. A rule reads the path values, sections and spans of its own file type, so two
    types of different readers that claim one file each keep their own.

    A fire of a rule other than a binding rule that makes no node and no edge is listed in the
    skipped matches as ``fired and emitted nothing``, unless it listed an edge that lacks a value
    or every source it names is absent.
    """
    nodes: list[FoundNode] = []
    edges: list[FoundEdge] = []
    fires: dict[tuple[str, str], int] = {}
    contents: dict[str, dict[str, Entry]] = {}
    trees: dict[str, ParsedFile] = {}
    texts: dict[str, str] = {}
    paths: dict[tuple[str, str], dict[str, str]] = {}
    sections: dict[tuple[str, str], list[tuple[str, int, int]]] = {}
    spans: dict[tuple[str, str], list[Span]] = {}
    bound: dict[str, list[tuple[int, str, str]]] = {}
    read: set[str] = set()
    removed: set[str] = set()
    skipped: list[Skipped] = []
    selected: dict[tuple[str, str], set[str]] = {}
    file_types = FileTypes.build(packs, selection.extensions)
    constants: dict[tuple[str, str], str] = {}
    # Every file a tree rule reads is parsed and its constants collected before any rule runs, so
    # a constant declared in a file read after its use is found.
    for rule in rule_set.rules:
        grammar = rule_set.grammars.get(rule.filetype)
        tree_rule = rule.declaration or rule.attribute or rule.annotation or rule.reference
        if not (rule.supported and rule.text is None and tree_rule and grammar):
            continue
        if not grammar.constant_declaration:
            continue
        info = rule_set.files.get(rule.filetype, FileInfo())
        holders = _holder_rules(rule_set, rule.filetype, frozenset(p.name.pack for p in packs))
        for file, _, _ in _matches(root, rule, packs, folders, selection, read, removed):
            own = (file, rule.filetype)
            if own not in paths:
                paths[own] = {**rule_set.values, **_path_values(file, info, rule_set, folders)}
            if file not in trees:
                trees[file] = parse_file(root / file, grammar, paths[own], constants)
                _collect(trees[file], grammar, holders, rule_set, constants)
    for rule in sorted(rule_set.rules, key=lambda one: not one.bindings):
        if not rule.supported or rule.matches_type:
            continue
        fired = 0
        info = rule_set.files.get(rule.filetype, FileInfo())
        for file, stem, _ in _matches(root, rule, packs, folders, selection, read, removed):
            own = (file, rule.filetype)
            if own not in paths:
                paths[own] = {**rule_set.values, **_path_values(file, info, rule_set, folders)}
            if rule.text is not None:
                if file not in texts:
                    texts[file] = load_text(root / file, file)
                if own not in sections:
                    sections[own] = _sections(texts[file], info.sections)
                    spans[own] = _spans(texts[file], info.spans, sections[own])
                read_from = (texts[file], paths[own], sections[own], spans[own])
                made = (nodes, edges, bound.setdefault(file, []), skipped)
                fired += _texts(rule, rule.text, rule_set, file, read_from, *made)
                continue
            if rule.declaration or rule.attribute or rule.annotation or rule.reference:
                grammar = rule_set.grammars[rule.filetype]
                if file not in trees:
                    trees[file] = parse_file(root / file, grammar, paths[own], constants)
                within = _within(rule.pack, packs)
                tree = (grammar, file, trees[file], within)
                if rule.reference:
                    for other in rule_set.rules:
                        owner = (other.pack, other.name)
                        if other.supported and other.declaration and owner not in selected:
                            hits = _matches(root, other, packs, folders, selection, read, removed)
                            selected[owner] = {found[0] for found in hits}
                    fired += _references(
                        rule, rule_set, grammar, file, trees[file], within, selected, edges, skipped
                    )
                elif rule.annotation:
                    found = (nodes, edges, skipped)
                    fired += _annotations(rule, rule_set, *tree, *found)
                elif rule.attribute:
                    found = (nodes, edges, skipped)
                    fired += _attributes(rule, rule_set, *tree, *found)
                else:
                    fired += _declarations(rule, rule_set, *tree, nodes, edges, skipped)
                continue
            data: dict[str, Entry] = {}
            if rule.where or rule.attributes or rule.edges or rule.each is not None:
                if file not in contents:
                    named = file_types.named(rule.filetype)
                    form = min((k.format for k in named if k.reader == "data"), default=None)
                    contents[file] = DATA_READERS[form or SHORT_FORM_FORMAT](root / file, file)
                data = contents[file]
            for key, line, scope, mapping in _entries(rule.each, data):
                if not all(_holds(scope, key or stem, mapping, c) for c in rule.where):
                    continue
                fired += 1
                values = {**paths[own], "file_stem": stem}
                values.update({} if key is None else {"key": key})
                node_id = _fill(rule.id_template, values)
                if node_id is None:
                    continue
                node_id = _reshape(node_id, rule.normalize)
                fire = (key, line)
                lists = (nodes, edges, skipped)
                _found(rule, rule_set, file, node_id, fire, scope, *lists, paths[own])
        fires[(rule.pack, rule.name)] = fired
    broken = sorted(file for file, parsed in trees.items() if parsed.broken)
    opened = sorted({*contents, *trees, *texts})
    return nodes, edges, fires, opened, read, removed, broken, sorted(skipped)


def run_map_rules(
    rule_set: RuleSet, nodes: Sequence[FoundNode], edges: Sequence[FoundEdge]
) -> tuple[list[FoundNode], list[FoundEdge], dict[tuple[str, str], int], list[MapPass]]:
    """Run every supported map rule over what the file rules found, in passes, until a pass adds
    nothing; return the nodes and edges the map rules made, each map rule's fires, and the passes.

    A pass reads the map as it stood when the pass began, rules in load order and nodes in id
    order, so a rule reads what another made only in a later pass. The ids a map rule reads are
    fixed by the file rules: each node they found and each end of their edges, an end with
    candidate ids on the first a rule found. A rule matches such a node that a rule found of its
    ``node_type`` or a type below it; it reads an edge whose two ends are such ids, and never an end
    a map rule composed that is no such id. So the records the passes can make are finite and the
    last pass adds none.

    A fire is one matched node that each ``where`` pattern fits, with one node its ``follow``
    reaches, that makes a node or edge record no pass made before. A record sits at the matched
    node's first location.
    """
    rules = [rule for rule in rule_set.rules if rule.supported and rule.matches_type]
    if not rules:
        return [], [], {}, []
    found = {node.id for node in nodes}
    ends = [_landed_end(edge, found) for edge in edges]
    known = found | {end for edge in ends for end in (edge.source, edge.target)}
    made_nodes: list[FoundNode] = []
    made_edges: list[FoundEdge] = []
    seen: set[FoundNode | FoundEdge] = set()
    fires = {(rule.pack, rule.name): 0 for rule in rules}
    passes: list[MapPass] = []
    while True:
        typed: dict[str, set[str]] = {}
        places: dict[str, tuple[str, int]] = {}
        for node in (*nodes, *made_nodes):
            if node.id in known:
                typed.setdefault(node.id, set()).add(node.type)
                places[node.id] = min(
                    places.get(node.id, (node.file, node.line)), (node.file, node.line)
                )
        found = set(typed)
        out: dict[tuple[str, str], set[str]] = {}
        for edge in (*ends, *(_landed_end(edge, found) for edge in made_edges)):
            if edge.source in known and edge.target in known:
                out.setdefault((edge.kind, edge.source), set()).add(edge.target)
        added: list[FoundNode | FoundEdge] = []
        fired: list[tuple[str, str, int]] = []
        for rule in rules:
            count = 0
            for node_id in sorted(typed):
                if not any(
                    _allows(rule_set, name, (rule.matches_type,)) for name in typed[node_id]
                ):
                    continue
                values = _captured(rule.where, node_id, dict(rule_set.values))
                if values is None:
                    continue
                for reached, captured in _follow(rule.follow, node_id, values, known, out):
                    made = _made(rule, rule_set, node_id, reached, captured, places[node_id])
                    new = [record for record in made if record not in seen]
                    seen.update(new)
                    added.extend(new)
                    count += bool(new)
            if count:
                fired.append((rule.pack, rule.name, count))
                fires[(rule.pack, rule.name)] += count
        passes.append((len(passes) + 1, tuple(fired)))
        if not added:
            return made_nodes, made_edges, fires, passes
        made_nodes.extend(record for record in added if isinstance(record, FoundNode))
        made_edges.extend(record for record in added if isinstance(record, FoundEdge))


def _landed_end(edge: FoundEdge, found: set[str]) -> FoundEdge:
    """The edge with its composed end on the first candidate id a rule found, else the first."""
    if not edge.candidates:
        return edge
    chosen = next((c for c in edge.candidates if c in found), edge.candidates[0])
    return replace(edge, source=chosen) if edge.source_type else replace(edge, target=chosen)


def _captured(
    where: Sequence[Condition], node_id: str, values: dict[str, str]
) -> dict[str, str] | None:
    """The values with the named captures of each ``id_matches`` pattern searched in the id;
    ``None`` when one does not fit."""
    for condition in where:
        found = condition.pattern.search(node_id) if isinstance(condition, IdMatches) else None
        if found is None:
            return None
        values.update({k: v for k, v in found.groupdict().items() if v is not None})
    return values


def _follow(
    steps: Sequence[tuple[str, Any]],
    at: str,
    values: dict[str, str],
    known: set[str],
    out: Mapping[tuple[str, str], set[str]],
) -> list[tuple[str, dict[str, str]]]:
    """Each id the steps reach from the id ``at``, in order, with the values its ``id_matches``
    steps captured. An ``ancestors`` step runs the steps after it from ``at``, else from the nearest
    ids its kinds reach, breadth first, that give any."""
    if not steps:
        return [(at, values)]
    (name, value), rest = steps[0], steps[1:]
    if name == "edge":
        return [
            r
            for to in sorted(out.get((value, at), ()))
            for r in _follow(rest, to, values, known, out)
        ]
    if name == "node":
        to = _fill(value, values)
        return _follow(rest, to, values, known, out) if to is not None and to in known else []
    if name == "id_matches":
        captured = _captured((IdMatches(value),), at, dict(values))
        return _follow(rest, at, captured, known, out) if captured is not None else []
    level, seen = [at], {at}
    while level:
        reached = [r for here in level for r in _follow(rest, here, values, known, out)]
        if reached:
            return reached
        level = sorted({t for h in level for k in value for t in out.get((k, h), ())} - seen)
        seen.update(level)
    return []


def _made(
    rule: Rule,
    rule_set: RuleSet,
    this: str,
    reached: str,
    values: Mapping[str, str],
    place: tuple[str, int],
) -> list[FoundNode | FoundEdge]:
    """The node or the edges one fire of a map rule makes, at ``place``: ``this`` is the id it
    matched and ``reached`` the id its follow reached. A template naming an absent capture makes
    nothing."""
    file, line = place
    if rule.node_type:
        filled = _fill(rule.id_template, values)
        if filled is None:
            return []
        node_id = f"{namespace_of(rule_set.types, rule.node_type)}::{filled}"
        return [
            FoundNode(node_id, rule.node_type, file, line, rule.pack, rule.name, rule.confidence)
        ]
    ends = {"this_node": this, "matched_node": reached}
    made: list[FoundNode | FoundEdge] = []
    for spec in rule.edges:
        if spec.template is None:
            source, target = ends[spec.start], ends[spec.finish]
            made.append(
                FoundEdge(
                    spec.kind, source, target, file, line, rule.pack, rule.name, rule.confidence
                )
            )
            continue
        composed = _fill(spec.template, values)
        if composed is not None:
            whole = ends[spec.start or spec.finish]
            made.extend(_edges(rule, rule_set, spec, file, "", [(composed, line)], whole=whole))
    return made


def _texts(
    rule: Rule,
    pattern: re.Pattern[str],
    rule_set: RuleSet,
    file: str,
    read_from: tuple[str, dict[str, str], list[tuple[str, int, int]], list[Span]],
    nodes: list[FoundNode],
    edges: list[FoundEdge],
    bound: list[tuple[int, str, str]],
    skipped: list[Skipped],
) -> int:
    """The node, the edges or the bindings of each match of the rule's pattern, in order; the
    number of fires.

    ``bound`` holds the file's bindings, each with the offset it was found at: a binding rule adds
    to it, one fire per binding whose name and target are not empty, and any other rule resolves a
    name with it, a later binding of a name winning. The id and an edge end take their resolution
    steps, an end without its own taking the file type's; a name no step gives makes nothing.

    ``read_from`` is the file's text, its path values, its sections and its spans. A match that
    makes no id, or whose id capture is empty, makes nothing, nor does an edge end whose capture is
    empty. An id, attribute or edge end whose template names an empty or absent value makes
    nothing; an empty attribute capture is an empty value. An edge end that makes nothing is listed
    in ``skipped`` with the edge's kind and the value it lacks, and the other edges still emit. A
    capture, and an attribute or edge end from it, sits at the line it starts on; the node, a value
    and anything made from a template at the line the match starts on, or the line its ``line``
    capture starts on.
    """
    text, paths, sections, spans = read_from
    types = rule_set.types
    fired = 0
    names = {name: target for _, name, target in sorted(bound, key=lambda one: one[0])}
    info = rule_set.files.get(rule.filetype, FileInfo())
    tables = rule_set.tables.get(rule.pack, {})
    for found in _outside(pattern, text, sections, rule.reads_sections):
        values = {name: value for name, value in found.groupdict().items() if value is not None}
        lines = {name: text.count("\n", 0, found.start(name)) + 1 for name in values}
        line = lines.get(rule.line_capture) or text.count("\n", 0, found.start()) + 1
        values.update(paths)
        for value in rule.values:
            if value.enclosing is not None:
                held = _held(spans, value.enclosing, found.start())
                values[value.name] = _reshape(value.join.join(held), value.normalize, value.case)
                continue
            made = _value(value, values)
            if made is not None:
                values[value.name] = made
        present = {name: value for name, value in values.items() if value}
        if rule.bindings:
            for name_template, target_template in rule.bindings:
                name, target = _fill(name_template, present), _fill(target_template, present)
                if name and target:
                    bound.append((found.start(), name, target))
                    fired += 1
            continue
        node_id = (
            values.get(rule.id_capture) if rule.id_capture else _fill(rule.id_template, present)
        )
        if node_id and rule.id_resolve:
            node_id = resolve_name(
                node_id, rule.id_resolve, rule.id_separator, names, present, tables=tables
            )
        if not node_id:
            continue
        node_id = _reshape(node_id, rule.normalize)
        fired += 1
        before = len(nodes) + len(edges)
        if rule.node_type:
            read = [
                (name, values[source], lines.get(source, line))
                for name, source in rule.attributes
                if source in values
            ]
            for name, template in rule.templates:
                filled = _fill(template, present)
                read += [(name, filled, line)] if filled is not None else []
            nodes.append(
                FoundNode(
                    id=f"{namespace_of(types, rule.node_type)}::{node_id}",
                    type=rule.node_type,
                    file=file,
                    line=line,
                    pack=rule.pack,
                    rule=rule.name,
                    confidence=rule.confidence,
                    attributes=tuple(read),
                )
            )
        silent, written = 0, len(skipped)
        for spec in rule.edges:
            lacking = f"capture {spec.key}" if spec.key else ""
            if spec.key and not values.get(spec.key):
                silent += spec.key not in values
                if spec.key in values:
                    row = f"edge {spec.kind}: no value for {lacking}"
                    skipped.append((file, line, rule.name, row))
                continue
            end = _fill(spec.template, present) if spec.template is not None else values[spec.key]
            if end is None:
                empty = sorted(set(PLACEHOLDER.findall(spec.template or "")) - set(present))
                silent += any(name not in values for name in empty)
                if all(name in values for name in empty):
                    row = f"edge {spec.kind}: no value for {', '.join(empty)}"
                    skipped.append((file, line, rule.name, row))
                continue
            steps = spec if spec.resolve else info
            if steps.resolve:
                end = resolve_name(
                    end, steps.resolve, steps.separator, names, present, tables=tables
                )
            if not end:
                reason = f"no resolution step holds for {lacking or spec.template}"
                skipped.append((file, line, rule.name, f"edge {spec.kind}: {reason}"))
                continue
            at = lines[spec.key] if spec.key else line
            edges.extend(_edges(rule, rule_set, spec, file, node_id, [(end, at)]))
        if (
            len(nodes) + len(edges) == before
            and len(skipped) == written
            and silent < len(rule.edges)
        ):
            skipped.append((file, line, rule.name, "fired and emitted nothing"))
    return fired


def _outside(
    pattern: re.Pattern[str],
    text: str,
    sections: list[tuple[str, int, int]],
    reads: tuple[str, ...],
) -> Iterator[re.Match[str]]:
    """Each match of the pattern, in order, leaving out one that starts inside a section the rule
    does not read; the search resumes at that section's end."""
    if not sections:
        yield from pattern.finditer(text)
        return
    starts = [begin for _, begin, _ in sections]
    at = 0
    while at <= len(text):
        found = pattern.search(text, at)
        if found is None:
            return
        index = bisect_right(starts, found.start()) - 1
        if index >= 0 and found.start() < sections[index][2] and sections[index][0] not in reads:
            at = sections[index][2]
            continue
        yield found
        at = found.end() if found.end() > found.start() else found.end() + 1


def _sections(
    text: str, declared: Sequence[tuple[str, re.Pattern[str], str]]
) -> list[tuple[str, int, int]]:
    """Each section of the text in one pass from the start: its name, start and end.

    The earliest opening wins, the first declared on a tie. A section runs to the end of the first
    closing match after its opening, or to the end of the text, and the search resumes after it.
    In the closing template a braced name of a capture of the opening stands for the text that
    capture matched, escaped.
    """
    found: list[tuple[str, int, int]] = []
    upcoming = [opening.search(text) for _, opening, _ in declared]
    at = 0
    while True:
        for index, (_, opening, _) in enumerate(declared):
            match = upcoming[index]
            if match is not None and match.start() < at:
                upcoming[index] = opening.search(text, at)
        opened = [
            (match.start(), index, match)
            for index, match in enumerate(upcoming)
            if match is not None
        ]
        if not opened:
            break
        begin, index, match = min(opened, key=lambda one: (one[0], one[1]))
        name, _, close = declared[index]
        closing = _closing(close, match)
        closed = closing.search(text, match.end())
        end = closed.end() if closed is not None else len(text)
        found.append((name, begin, end))
        at = max(end, begin + 1)
    return found


def _closing(close: str, opened: re.Match[str]) -> re.Pattern[str]:
    """The closing pattern, each braced name of a capture of the opening replaced by the text that
    capture matched, escaped."""
    captured = {name: re.escape(value or "") for name, value in opened.groupdict().items()}
    return compile_pattern(PLACEHOLDER.sub(lambda p: captured.get(p.group(1), p.group(0)), close))


def _spans(
    text: str,
    declared: Sequence[tuple[str, re.Pattern[str], str, str]],
    sections: list[tuple[str, int, int]],
) -> list[Span]:
    """Each span of the text, sorted by start: one per match of its opening outside the sections.

    From the end of the opening, each opening and closing character outside the sections counts
    one up and one down; the span ends after the closing character that brings the count to zero
    or below, or at the end of the text.
    """
    starts = [begin for _, begin, _ in sections]
    found: list[Span] = []
    for name, opening, open_char, close_char in declared:
        pair = re.compile(f"[{re.escape(open_char)}{re.escape(close_char)}]")
        for match in _outside(opening, text, sections, ()):
            depth, end = 0, len(text)
            for char in pair.finditer(text, match.end()):
                index = bisect_right(starts, char.start()) - 1
                if index >= 0 and char.start() < sections[index][2]:
                    continue
                depth += 1 if char.group() == open_char else -1
                if depth <= 0:
                    end = char.end()
                    break
            captured = {k: v for k, v in match.groupdict().items() if v is not None}
            found.append((name, match.start(), end, captured))
    return sorted(found, key=lambda span: (span[1], span[2], span[0]))


def _held(spans: list[Span], enclosing: tuple[str, str], at: int) -> list[str]:
    """The capture of each span of the name that holds the offset, outermost first; a span whose
    capture is absent or empty adds nothing."""
    name, capture = enclosing
    return [
        captured[capture]
        for span, begin, end, captured in spans
        if span == name and begin <= at < end and captured.get(capture)
    ]


def _value(value: Value, known: Mapping[str, str]) -> str | None:
    """The value made from the values known, reshaped; ``None`` when what it names is absent."""
    found = known.get(value.capture) if value.capture else _fill(value.template, known)
    return None if found is None else _reshape(found, value.normalize, value.case)


def _path_values(
    file: str, info: FileInfo, rule_set: RuleSet, folders: Mapping[str, tuple[str, ...]]
) -> dict[str, str]:
    """The path values of the file type for the file's path, each template filled from its
    pattern's captures and the settings values; one whose pattern does not match is absent.

    A value ``relative_to`` a folder searches the path below the deepest directory of that folder
    that holds the file, and is absent when none does.
    """
    found: dict[str, str] = {}
    for value in info.path_values:
        path: str | None = file
        if value.relative_to:
            holders = [d for d in folders.get(value.relative_to, ()) if _below(file, d)]
            deepest = max(holders, key=len, default=None)
            path = None if deepest is None else file.removeprefix(deepest.rstrip("/") + "/")
        match = value.pattern.search(path) if value.pattern is not None and path else None
        if match is not None:
            captured = {k: v for k, v in match.groupdict().items() if v is not None}
            made = _value(value, {**rule_set.values, **captured})
            if made is not None:
                found[value.name] = made
    return found


def _below(file: str, directory: str) -> bool:
    """Whether the file sits at any depth below the directory; ``.`` holds every file."""
    return directory == "." or file.startswith(f"{directory.rstrip('/')}/")


def _declarations(
    rule: Rule,
    rule_set: RuleSet,
    grammar: Grammar,
    file: str,
    parsed: ParsedFile,
    within: frozenset[str],
    nodes: list[FoundNode],
    edges: list[FoundEdge],
    skipped: list[Skipped],
) -> int:
    """The nodes or edges of each tree node of the rule's declaration type; the number of fires.

    A match without a direct child of each ``has_child`` type, or failing a ``name_matches``
    condition, is passed. A match whose name child is missing, or whose
    id names a source it lacks, is skipped; a field or value it lacks is listed in ``skipped`` once
    per file, at the first match that lacks it. A match whose id argument is missing, empty or not
    a text literal is skipped and listed at each such match. A node sits at the line
    of its name; an edge to a written name sits at that name's line, any other edge at the line of
    the match's name.
    """
    holders = _holder_rules(rule_set, rule.filetype, within)
    types = rule_set.types
    fired = 0
    absent: set[str] = set()
    needs_method = "enclosing_method" in PLACEHOLDER.findall(rule.id_template) or any(
        "enclosing_method" in (spec.start, spec.finish) for spec in rule.edges
    )
    for match in parsed.by_type.get(rule.declaration, ()):
        if not _fires(rule, match):
            continue
        values = _names(match, rule, grammar, parsed)
        if values is None:
            continue
        line = values.pop("line", None) or line_of(match)
        holder = _holder(match, holders, rule_set, grammar, parsed)
        holder_id = None
        if holder is not None:
            values["enclosing_type"], holder_id = holder
        method = None
        if needs_method:
            enclosing = holder[0] if holder else None
            method = _method(match, enclosing, holders, rule, rule_set, within, grammar, parsed)
            if method is not None and method[1] is not None:
                values["enclosing_method"] = method[1]
        node_id: str | None
        if rule.id_argument:
            node_id, row = _call_id(match, rule, grammar, parsed, holder[0] if holder else None)
            if node_id is None:
                skipped.append((file, line, rule.name, row))
                continue
        elif rule.id_template:
            node_id = _node_id(rule, values)
            if node_id is None:
                for name in _lacking(rule, grammar, values) - absent:
                    absent.add(name)
                    skipped.append((file, line, rule.name, f"the id source {name} is absent"))
                continue
        else:
            node_id = _reshape("", rule.normalize)
        fired += 1
        before, silent, written = len(nodes) + len(edges), 0, len(skipped)
        if rule.node_type:
            nodes.append(
                FoundNode(
                    id=f"{namespace_of(types, rule.node_type)}::{node_id}",
                    type=rule.node_type,
                    file=file,
                    line=line,
                    pack=rule.pack,
                    rule=rule.name,
                    confidence=rule.confidence,
                )
            )
        for spec in rule.edges:
            kind = rule_set.edge_kinds[spec.kind]
            ends: list[list[tuple[str, int]]] = []
            for end, allowed, declared in (
                (spec.start, kind.from_types, spec.declared[0]),
                (spec.finish, kind.to_types, spec.declared[1]),
            ):
                namespace = next(iter(namespaces(types, allowed)), None)
                unwritten = False
                if end == "this_node":
                    twin = namespace_of(types, rule.twin_type) if rule.twin_type else namespace
                    ends.append([(f"{twin}::{node_id}", line)])
                elif end == "enclosing_class":
                    ends.append([(holder_id, line)] if holder_id else [])
                elif end == "enclosing_method":
                    ends.append([(method[0], line)] if method else [])
                    unwritten = method is None
                elif end == "enclosing_file":
                    root = match
                    while root.parent is not None:
                        root = root.parent
                    found = next(
                        filter(
                            None,
                            (
                                _minted(
                                    root, None, rule.filetype, rule_set, within, grammar, parsed, t
                                )
                                for t in allowed
                            ),
                        ),
                        None,
                    )
                    ends.append([(found[0], line)] if found else [])
                elif declared:
                    found = _minted(
                        match,
                        holder[0] if holder else None,
                        rule.filetype,
                        rule_set,
                        within,
                        grammar,
                        parsed,
                        declared,
                    )
                    ends.append([(found[0], line)] if found else [])
                    end = f"{{declared: {declared}}}"
                else:
                    ends.append(
                        [
                            (f"{namespace}::{name}", line_of(child))
                            for child in match.children
                            if child.type in grammar.written
                            for name in [parsed.resolve(child, grammar)]
                            if name is not None
                        ]
                    )
                    unwritten = not any(child.type in grammar.written for child in match.children)
                silent += unwritten
                if not ends[-1] and not unwritten:
                    lacking = f"edge {spec.kind}: no value for {end}"
                    skipped.append((file, line, rule.name, lacking))
            edges.extend(
                FoundEdge(
                    spec.kind,
                    source,
                    target,
                    file,
                    at,
                    rule.pack,
                    rule.name,
                    rule.confidence,
                    target_type=spec.declared[1],
                    source_type=spec.declared[0],
                    declared_ends=tuple(
                        side
                        for side, named in zip(("source", "target"), spec.declared, strict=True)
                        if named
                    ),
                )
                for (source, _), (target, at) in product(*ends)
            )
        if (
            len(nodes) + len(edges) == before
            and len(skipped) == written
            and silent < len(rule.edges)
        ):
            skipped.append((file, line, rule.name, "fired and emitted nothing"))
    return fired


def _attributes(
    rule: Rule,
    rule_set: RuleSet,
    grammar: Grammar,
    file: str,
    parsed: ParsedFile,
    within: frozenset[str],
    nodes: list[FoundNode],
    edges: list[FoundEdge],
    skipped: list[Skipped],
) -> int:
    """The nodes or edges of each attribute of the rule's class on a declaration of its
    ``applies_to`` type; the number of fires.

    The attribute's written name is resolved as any written name is. A match whose id argument is
    missing, or is not a text literal where the rule needs one, makes nothing and is listed in
    ``skipped`` unless the rule is an edge rule whose twin node rule lists it. An argument that
    fills an attribute or an edge end is left out when it is not a text literal. Every node and
    edge sits at the line of the attribute.
    """
    holders = _holder_rules(rule_set, rule.filetype, within)
    types = rule_set.types
    fired = 0
    for match in parsed.by_type.get(grammar.attribute, ()):
        written = next((c for c in match.children if c.type in grammar.written), None)
        owner = match.parent
        while owner is not None and owner.type != grammar.attribute_list:
            owner = owner.parent
        owner = owner.parent if owner is not None else None
        if (
            written is None
            or owner is None
            or owner.type != rule.applies_to
            or parsed.resolve(written, grammar) != rule.attribute
        ):
            continue
        line = line_of(match)
        node_id = ""
        holder = _holder(match, holders, rule_set, grammar, parsed)
        enclosing = holder[0] if holder else None
        if rule.id_argument:
            value, text, row = _argument(match, rule.id_argument, grammar, parsed, enclosing)
            if value is not None and text is None and not rule.must_be_literal:
                text = text_of(value)
            if not text:
                if not rule.twin_type:
                    skipped.append((file, line, rule.name, row))
                continue
            node_id = text
        fired += 1
        before, silent, skipped_before = len(nodes) + len(edges), 0, len(skipped)
        if rule.node_type:
            read = ((name, argument_of(match, key, grammar)) for name, key in rule.attributes)
            found = (
                (name, _literal(v, grammar, parsed, enclosing), line_of(v)) for name, v in read if v
            )
            nodes.append(
                FoundNode(
                    id=f"{namespace_of(types, rule.node_type)}::{node_id}",
                    type=rule.node_type,
                    file=file,
                    line=line,
                    pack=rule.pack,
                    rule=rule.name,
                    confidence=rule.confidence,
                    attributes=tuple(a for a in found if a[1] is not None),
                )
            )
        method = None
        if owner.type not in holders and holder is not None:
            minted = _minted(owner, holder[0], rule.filetype, rule_set, within, grammar, parsed)
            method = minted[0] if minted else None
        for spec in rule.edges:
            kind = rule_set.edge_kinds[spec.kind]
            ends: list[str | None] = []
            for end, allowed in ((spec.start, kind.from_types), (spec.finish, kind.to_types)):
                namespace = next(iter(namespaces(types, allowed)), None)
                absent = False
                if end == "this_node":
                    twin = namespace_of(types, rule.twin_type) if rule.twin_type else namespace
                    ends.append(f"{twin}::{node_id}")
                elif end == "enclosing_class":
                    ends.append(holder[1] if holder else None)
                elif end == "enclosing_method":
                    ends.append(method)
                else:
                    value = argument_of(match, spec.key, grammar)
                    text = (
                        _literal(value, grammar, parsed, enclosing) if value is not None else None
                    )
                    ends.append(f"{namespace}::{text}" if text is not None else None)
                    end, absent = f"argument {spec.key}", value is None
                silent += absent
                if not ends[-1] and not absent:
                    skipped.append((file, line, rule.name, f"edge {spec.kind}: no value for {end}"))
            source, target = ends
            if source and target:
                edges.append(
                    FoundEdge(
                        spec.kind, source, target, file, line, rule.pack, rule.name, rule.confidence
                    )
                )
        if (
            len(nodes) + len(edges) == before
            and len(skipped) == skipped_before
            and silent < len(rule.edges)
        ):
            skipped.append((file, line, rule.name, "fired and emitted nothing"))
    return fired


def _annotations(
    rule: Rule,
    rule_set: RuleSet,
    grammar: Grammar,
    file: str,
    parsed: ParsedFile,
    within: frozenset[str],
    nodes: list[FoundNode],
    edges: list[FoundEdge],
    skipped: list[Skipped],
) -> int:
    """The nodes or edges of each docblock annotation of the rule's name on a declaration of its
    ``applies_to`` type; the number of fires.

    The docblock is the comment that is the declaration's previous sibling; no other comment is
    read. A match whose id key is missing, or whose value is not read, makes nothing and is listed
    in ``skipped`` unless the rule is an edge rule whose twin node rule lists it. A node and its
    edges sit at the line of the annotation's name, an attribute at the line of its key.
    """
    holders = _holder_rules(rule_set, rule.filetype, within)
    types = rule_set.types
    fired = 0
    for match in parsed.by_type.get(rule.applies_to, ()):
        comment = match.prev_sibling
        if comment is None or comment.type != grammar.comment:
            continue
        for line, entries in _annotation(comment, rule.annotation, grammar.separator):
            if entries is None:
                if not rule.twin_type:
                    skipped.append((file, line, rule.name, "the annotation never closes"))
                continue
            node_id = ""
            if rule.id_argument:
                value = entries.get(rule.id_argument, (None, line))[0]
                if value is None:
                    absent = rule.id_argument not in entries
                    state = "is missing" if absent else "is not quoted text"
                    if not rule.twin_type:
                        skipped.append((file, line, rule.name, f"key {rule.id_argument} {state}"))
                    continue
                node_id = value
            fired += 1
            before, written = len(nodes) + len(edges), len(skipped)
            if rule.node_type:
                read = ((name, *entries[key]) for name, key in rule.attributes if key in entries)
                nodes.append(
                    FoundNode(
                        id=f"{namespace_of(types, rule.node_type)}::{node_id}",
                        type=rule.node_type,
                        file=file,
                        line=line,
                        pack=rule.pack,
                        rule=rule.name,
                        confidence=rule.confidence,
                        attributes=tuple(a for a in read if a[1] is not None),
                    )
                )
            # The declaration's first child has the declaration itself as its nearest enclosing
            # type.
            holder = _holder(match.children[0], holders, rule_set, grammar, parsed)
            for spec in rule.edges:
                kind = rule_set.edge_kinds[spec.kind]
                ends: list[str | None] = []
                for end, allowed in ((spec.start, kind.from_types), (spec.finish, kind.to_types)):
                    if end == "this_node":
                        allowed = (rule.twin_type,) if rule.twin_type else allowed
                        ends.append(f"{next(iter(namespaces(types, allowed)), None)}::{node_id}")
                    else:
                        ends.append(holder[1] if holder else None)
                    if not ends[-1]:
                        lacking = f"edge {spec.kind}: no value for {end}"
                        skipped.append((file, line, rule.name, lacking))
                source, target = ends
                if source and target:
                    edges.append(
                        FoundEdge(
                            spec.kind,
                            source,
                            target,
                            file,
                            line,
                            rule.pack,
                            rule.name,
                            rule.confidence,
                        )
                    )
            if len(nodes) + len(edges) == before and len(skipped) == written:
                skipped.append((file, line, rule.name, "fired and emitted nothing"))
    return fired


def _annotation(
    comment: Node, name: str, separator: str
) -> list[tuple[int, dict[str, tuple[str | None, int]] | None]]:
    """Each annotation of the name in the comment: the line of its name, and each key at the top
    level of its body with its value and its line; ``None`` in place of the keys when the body or a
    quoted text in it never closes.

    The name follows an at sign at the start of a line, after the comment's own leading star and
    spaces, and an opening parenthesis follows it. The body runs to the matching closing
    parenthesis, counting nested ones and skipping quoted text. A value that is not read is
    ``None``. A start inside an earlier annotation's body is not another annotation.
    """
    text = text_of(comment)
    first = line_of(comment)
    found: list[tuple[int, dict[str, tuple[str | None, int]] | None]] = []
    done = 0
    nested = re.compile(_NESTED.format(re.escape(separator)))
    for start in re.finditer(rf"^[ \t]*(?:/\*+|\*)?[ \t]*@({re.escape(name)})\(", text, re.M):
        if start.start() < done:
            continue
        line = first + text.count("\n", 0, start.start(1))
        entries: dict[str, tuple[str | None, int]] = {}
        depth, begin, index = 0, start.end(), start.end()
        done = len(text)
        while index < len(text):
            char = text[index]
            if char == '"':
                index = text.find('"', index + 1)
                if index < 0:
                    break
            elif char in "({":
                depth += 1
            elif char in ")}" and depth:
                depth -= 1
            elif char in ",)" and not depth:
                key, equals, value = text[begin:index].partition("=")
                if equals and key.strip(_MARGIN):
                    at = begin + len(key) - len(key.lstrip(_MARGIN))
                    read = _QUOTED.fullmatch(value.strip(_MARGIN)) or nested.fullmatch(
                        value.strip(_MARGIN)
                    )
                    entries[key.strip(_MARGIN)] = (
                        read.group(1) if read else None,
                        first + text.count("\n", 0, at),
                    )
                if char == ")":
                    done = index
                    break
                begin = index + 1
            index += 1
        found.append((line, entries if done < len(text) else None))
    return found


def _fires(rule: Rule, node: Node) -> bool:
    """Whether the tree node has a direct child of each of the rule's ``has_child`` types, and has
    each ``name_matches`` child, whose whole text matches that condition's pattern."""
    return all(any(c.type == kind for c in node.children) for kind in rule.has_child) and all(
        (found := _child(node, child)) is not None and pattern.fullmatch(text_of(found))
        for child, pattern in rule.name_matches
    )


def _argument(
    node: Node,
    key: str,
    grammar: Grammar,
    parsed: ParsedFile,
    holder: str | None,
    call: bool = False,
) -> tuple[Node | None, str | None, str]:
    """The attribute's or, with ``call``, the call's argument at the key, ``None`` when missing;
    its text, as ``_literal`` reads it, ``None`` when it has none; and the skipped row for no
    text."""
    value = argument_of(node, key, grammar, call)
    literal = _literal(value, grammar, parsed, holder, call) if value is not None else None
    state = (
        "is missing"
        if value is None
        else "is empty"
        if literal == ""
        else "is a class constant with no declared text"
        if value.type == grammar.constant_access
        else "is not a text literal"
    )
    return value, literal, f"argument {key} {state}"


def _literal(
    value: Node, grammar: Grammar, parsed: ParsedFile, holder: str | None, call: bool = False
) -> str | None:
    """The text of a text literal; for a class constant access, the text the run collected for
    that constant, its scope resolved as a written name, or else the enclosing class ``holder``
    when the grammar's enclosing scope texts name this one; ``None`` for any other node, any
    other scope, or a constant with no collected text."""
    if value.type != grammar.constant_access:
        return literal_of(value, grammar, call)
    named = value.named_children
    if (
        len(named) < 2
        or named[0].type not in grammar.constant_scope
        or named[-1].type not in grammar.constant_name
    ):
        return None
    if named[0].type in grammar.written:
        scope = parsed.resolve(named[0], grammar)
    elif text_of(named[0]) in grammar.constant_enclosing:
        scope = holder
    else:
        return None
    return parsed.constants.get((scope, text_of(named[-1]))) if scope is not None else None


def _collect(
    parsed: ParsedFile,
    grammar: Grammar,
    holders: Mapping[str, tuple[Rule, ...]],
    rule_set: RuleSet,
    constants: dict[tuple[str, str], str],
) -> None:
    """Each class constant of the file whose value is a text literal into ``constants``, by the
    full name of its enclosing type declaration and its name; of two, the first read stays."""
    for node in parsed.by_type.get(grammar.constant_declaration, ()):
        named = node.named_children
        holder = _holder(node, holders, rule_set, grammar, parsed)
        if (
            len(named) < 2
            or holder is None
            or named[0].type not in grammar.constant_declared_name
            or named[-1].type not in grammar.constant_value
        ):
            continue
        text = literal_of(named[-1], grammar, call=True)
        if text is not None:
            constants.setdefault((holder[0], text_of(named[0])), text)


def _call_id(
    node: Node, rule: Rule, grammar: Grammar, parsed: ParsedFile, holder: str | None
) -> tuple[str | None, str]:
    """The bare id the rule's call argument gives at the node, ``None`` when it holds no text;
    and the skipped row for no text."""
    _, literal, row = _argument(node, rule.id_argument, grammar, parsed, holder, call=True)
    return (_reshape(literal, rule.normalize) if literal else None), row


def _holder_rules(
    rule_set: RuleSet, filetype: str, within: frozenset[str]
) -> dict[str, tuple[Rule, ...]]:
    """The supported node rules with a ``body_child`` that read the file type, by declaration type.

    Only rules of the packs in ``within`` count, the rule's own pack and those it depends on, so
    another pack's rule on the same tree node never names the holder. Packs load dependencies
    first, so for one declaration type the rules are listed last loaded first: of the rules that
    fire on a node, the rule's own pack wins, else the dependency loaded last.
    """
    found: dict[str, tuple[Rule, ...]] = {}
    for other in rule_set.rules:
        if (
            other.supported
            and other.body_child
            and other.node_type
            and other.filetype == filetype
            and other.pack in within
        ):
            found[other.declaration] = (other, *found.get(other.declaration, ()))
    return found


def _minted(
    node: Node,
    holder: str | None,
    filetype: str,
    rule_set: RuleSet,
    within: frozenset[str],
    grammar: Grammar,
    parsed: ParsedFile,
    node_type: str = "",
) -> tuple[str, str | None] | None:
    """The id the first node rule that fires on the tree node and mints an id there gives it, and
    the declared name that rule reads, inside the type ``holder`` when there is one, of the type
    ``node_type`` when that is given.

    Only rules of the packs in ``within`` count, as in ``_holder_rules``. A rule that fires and
    mints no id passes the node to the next, for ``enclosing_method`` as for ``{declared: <type>}``.
    """
    for rule in rule_set.rules:
        if not (
            rule.supported
            and rule.node_type
            and rule.node_type == (node_type or rule.node_type)
            and rule.declaration == node.type
            and rule.filetype == filetype
            and rule.pack in within
            and _fires(rule, node)
        ):
            continue
        values = _names(node, rule, grammar, parsed)
        if values is None:
            continue
        if rule.id_argument:
            node_id, _ = _call_id(node, rule, grammar, parsed, holder)
        else:
            node_id = _node_id(
                rule, values if holder is None else {**values, "enclosing_type": holder}
            )
        if node_id is not None:
            namespace = namespace_of(rule_set.types, rule.node_type)
            return f"{namespace}::{node_id}", values.get("declared_name")
    return None


def _method(
    match: Node,
    holder: str | None,
    holders: Mapping[str, tuple[Rule, ...]],
    rule: Rule,
    rule_set: RuleSet,
    within: frozenset[str],
    grammar: Grammar,
    parsed: ParsedFile,
) -> tuple[str, str | None] | None:
    """The id and the declared name ``_minted`` gives the member of the enclosing type ``holder``
    that holds the match, as for an attribute's ``enclosing_method``; ``None`` outside a type."""
    bodies = {other.body_child for rules in holders.values() for other in rules}
    member = match.parent
    while holder is not None and member is not None and member.parent is not None:
        if member.parent.type in bodies:
            return _minted(member, holder, rule.filetype, rule_set, within, grammar, parsed)
        member = member.parent
    return None


def _names(node: Node, rule: Rule, grammar: Grammar, parsed: ParsedFile) -> dict[str, Any] | None:
    """The file's values and the namespace in force; with a name child the declared and the full
    name and ``line``; and the text of each node field the rule's id names, read as the name child.

    ``None`` when the rule names a name child the node does not have. A field the node lacks, a
    namespace from an absent value and a full name with an absent part are left out.
    """
    values: dict[str, Any] = dict(parsed.values)
    if not grammar.namespace_value or grammar.namespace_value in parsed.values:
        values["namespace"] = parsed.namespace_at(node)
    if rule.name_child:
        name = node.child_by_field_name(rule.name_child)
        if name is None:
            return None
        values["declared_name"], values["line"] = text_of(name), line_of(name)
        qualified = grammar.join(values)
        if qualified is not None:
            values["qualified_name"] = qualified
    for field in rule.fields:
        child = node.child_by_field_name(field)
        if child is not None:
            written = parsed.resolve(child, grammar) if field in rule.qualified else None
            values[field] = written or text_of(child)
    return values


def _lacking(rule: Rule, grammar: Grammar, values: Mapping[str, Any]) -> set[str]:
    """The fields and values the id template names that are absent, a full name standing for its
    absent parts; an absent enclosing type or method is not one, since having none is not a gap.

    With an id pattern, its source and the values it names count too, and its captures do not; a
    source the pattern does not fit lacks nothing."""
    names = set(PLACEHOLDER.findall(rule.id_template)) - set(values)
    names -= {"enclosing_type", "enclosing_method"}
    if rule.id_pattern:
        pattern, source = _id_pattern(rule, values), values.get(rule.id_source)
        if pattern is not None and source is not None and pattern.search(source) is None:
            return set()
        captures = set(compile_pattern(PATTERN_VALUE.sub("", rule.id_pattern)).groupindex)
        named = {rule.id_source, *PATTERN_VALUE.findall(rule.id_pattern)}
        names = names - captures | named - set(values)
    if "qualified_name" in names:
        names = names - {"qualified_name"} | {p for p in grammar.parts if p not in values}
    if "namespace" in names and grammar.namespace_value:
        names = names - {"namespace"} | {grammar.namespace_value}
    return names


def _holder(
    node: Node,
    holders: Mapping[str, tuple[Rule, ...]],
    rule_set: RuleSet,
    grammar: Grammar,
    parsed: ParsedFile,
) -> tuple[str, str] | None:
    """The full name and the node id of the nearest enclosing type declaration, or ``None``.

    A type declaration is a tree node a declaration rule with a ``body_child`` fires on, and that
    rule mints its id. A nearer node that holds such a body but no rule fires on, an anonymous
    class, ends the walk with ``None``.
    """
    bodies = {rule.body_child for rules in holders.values() for rule in rules}
    parent = node.parent
    while parent is not None:
        rule = next((r for r in holders.get(parent.type, ()) if _fires(r, parent)), None)
        if rule is not None:
            values = _names(parent, rule, grammar, parsed)
            node_id = _node_id(rule, values, empty_ok=True) if values is not None else None
            if values is None or node_id is None or "qualified_name" not in values:
                return None
            namespace = namespace_of(rule_set.types, rule.node_type)
            return values["qualified_name"], f"{namespace}::{node_id}"
        if any(child.type in bodies for child in parent.children):
            return None
        parent = parent.parent
    return None


def _entries(each: str | None, data: dict[str, Entry]) -> list[tuple[str | None, int, Any, bool]]:
    """Each place a rule fires: its key, its line, the mapping its key paths read inside, and
    whether its value is a mapping or empty.

    Without ``each`` that is the whole file once. With it, each entry of the mapping ``each``
    names, in file order. An entry whose value is text holds that text under ``TEXT`` alone, and
    any other value that is not a mapping is read as empty.
    """
    if each is None:
        return [(None, 1, data, True)]
    found = []
    for hit in resolve_path(data, each) if each else [Hit(data, 1, None)]:
        for key, entry in hit.value.items() if isinstance(hit.value, dict) else []:
            scope = {TEXT: entry} if isinstance(entry.value, str) else entry.value
            mapping = entry.value is None or isinstance(entry.value, dict)
            found.append((key, entry.line, scope if isinstance(scope, dict) else {}, mapping))
    return found


def _found(
    rule: Rule,
    rule_set: RuleSet,
    file: str,
    node_id: str,
    entry: tuple[str | None, int],
    data: dict[str, Entry],
    nodes: list[FoundNode],
    edges: list[FoundEdge],
    skipped: list[Skipped],
    paths: Mapping[str, str],
) -> None:
    """The node or the edges one fire of the rule finds, appended to ``nodes`` or ``edges``.

    ``entry`` is the fire's key, ``None`` for a whole file, and its line. ``paths`` holds the
    file's path values, which an edge template may name. A fire that makes no edge though a key
    path of one of its edges reached a value, and lists no edge, is listed in ``skipped``. An edge
    whose key path reached a value and gave no end is listed only when it has no ``where``,
    ``pattern`` or ``listed_at``, which choose between edges; a key path that reaches nothing
    states no edge.
    """
    line = entry[1]
    types = rule_set.types
    if rule.node_type:
        namespace = namespace_of(types, rule.node_type)
        found = tuple(_attribute(data, name, path) for name, path in rule.attributes)
        nodes.append(
            FoundNode(
                id=f"{namespace}::{node_id}",
                type=rule.node_type,
                file=file,
                line=line,
                pack=rule.pack,
                rule=rule.name,
                confidence=rule.confidence,
                attributes=tuple(a for a in found if a is not None),
            )
        )
    before, stated, written = len(edges), False, len(skipped)
    for spec in rule.edges:
        ends = _ends(spec, data, entry, paths)
        sources = [path for mode, path in spec.parts if mode not in ("entry", "file")] or [spec.key]
        reached = any(resolve_path(data, path) for path in sources)
        stated = stated or reached
        filtered = spec.matches or spec.pattern or spec.listed_at or spec.not_matches
        if reached and not ends and not filtered:
            row = f"edge {spec.kind}: no value for key {', '.join(sources)}"
            skipped.append((file, line, rule.name, row))
        edges.extend(_edges(rule, rule_set, spec, file, node_id, ends))
    if stated and len(edges) == before and len(skipped) == written:
        skipped.append((file, line, rule.name, "fired and emitted nothing"))


def _edges(
    rule: Rule,
    rule_set: RuleSet,
    spec: EdgeSpec,
    file: str,
    node_id: str,
    ends: list[tuple[str, int]],
    whole: str = "",
) -> list[FoundEdge]:
    """One edge per composed end and its line, between it and the fire's own node, or the node of
    the id ``whole`` when it is given.

    The composed end is the from end when the spec's ``start`` is ``""``. An end that is not a
    full id takes the one id namespace of the kind's types at its side, and makes no edge when
    they have none.
    """
    kind = rule_set.edge_kinds[spec.kind]
    flipped = not spec.start
    near, far = (kind.to_types, kind.from_types) if flipped else (kind.from_types, kind.to_types)
    types = rule_set.types
    own = (
        ""
        if whole
        else namespace_of(types, rule.twin_type)
        if rule.twin_type
        else next(iter(namespaces(types, near)))
    )
    other = next(iter(namespaces(types, far)), None)
    found = []
    for end, at in ends:
        candidates = () if spec.full_id else _candidates(spec, types, end)
        if not spec.full_id and other is None and not candidates:
            continue
        this, composed = whole or f"{own}::{node_id}", end if spec.full_id else f"{other}::{end}"
        composed = candidates[0] if candidates else composed
        found.append(
            FoundEdge(
                kind=spec.kind,
                source=composed if flipped else this,
                target=this if flipped else composed,
                file=file,
                line=at,
                pack=rule.pack,
                rule=rule.name,
                confidence=rule.confidence,
                target_type="" if flipped else spec.to_type,
                source_type=spec.to_type if flipped else "",
                on_miss=("source" if flipped else "target") if spec.on_miss else "",
                searched_for=end.partition("::")[2] if spec.full_id else end,
                candidates=candidates,
                types_tried=spec.types,
            )
        )
    return found


def _candidates(spec: EdgeSpec, types: Mapping[str, Any], end: str) -> tuple[str, ...]:
    """The id of the end under each of the spec's candidate types, in order."""
    return tuple(f"{namespace_of(types, name)}::{end}" for name in spec.types)


def _within(pack: str, packs: Sequence[LoadedPack]) -> frozenset[str]:
    """The pack's name and the name of every pack it depends on, directly or not."""
    depends = {p.name.pack: [d.partition("@")[0] for d in p.manifest.depends] for p in packs}
    seen: set[str] = set()
    pending = [pack]
    while pending:
        name = pending.pop()
        if name not in seen:
            seen.add(name)
            pending.extend(depends.get(name, []))
    return frozenset(seen)


def _references(
    rule: Rule,
    rule_set: RuleSet,
    grammar: Grammar,
    file: str,
    parsed: ParsedFile,
    within: frozenset[str],
    selected: Mapping[tuple[str, str], set[str]],
    edges: list[FoundEdge],
    skipped: list[Skipped],
) -> int:
    """One edge per spec for each tree node of the rule's reference type; the number of fires.

    The edge runs from the node the nearest enclosing declaration was given: a tree node that a
    declaration rule of the rule's pack, or of a pack it depends on, gives a map node in this file,
    of a type each edge kind of the rule allows at its from end. ``selected`` holds the files each
    declaration rule reads, by pack and rule name.
    The name is the text of the name child, a written name the grammar resolves; a member child's
    text follows it, joined with the end's separator or the grammar's. An end that reads the call's
    argument takes that argument's text literal instead, unresolved by the grammar. The end's own
    steps then run on that name. A reference with no enclosing declaration, whose name child is not
    a written name, or holds a node that is not one under ``whole_written``, whose argument is
    missing, empty or not a text literal, or that no step gives a name, makes nothing and is listed
    in ``skipped``. A name written exactly as one of the rule's ``skip_names``, or a match failing a
    ``name_matches`` condition, makes nothing, is not listed and is not a fire. An edge
    sits at the reference's line.
    """
    holders = _holder_rules(rule_set, rule.filetype, within)
    declared: dict[str, list[Rule]] = {}
    for other in rule_set.rules:
        if (
            other.supported
            and other.declaration
            and other.node_type
            and other.filetype == rule.filetype
            and other.pack in within
            and file in selected[(other.pack, other.name)]
            and all(
                _allows(rule_set, other.node_type, rule_set.edge_kinds[spec.kind].from_types)
                for spec in rule.edges
            )
        ):
            declared.setdefault(other.declaration, []).append(other)
    tables = rule_set.tables.get(rule.pack, {})
    typed: dict[int, dict[str, str]] = {}
    fired = 0
    for match in parsed.by_type.get(rule.reference, ()):
        if not _fires(rule, match):
            continue
        line = line_of(match)
        written = _child(match, rule.name_child)
        if rule.receivers:
            written = _property(written, grammar)
            if written is None:
                continue
        member = _child(match, rule.member_child) if rule.member_child else None
        if (
            written is None
            or written.type not in grammar.written
            or (rule.member_child and member is None)
            or (rule.whole_written and not _all_written(written, grammar.written))
        ):
            skipped.append((file, line, rule.name, f"{rule.name_child} is not a written name"))
            continue
        if text_of(written) in rule.skip_names:
            continue
        if "untyped_member" in rule.receivers and _declared_type(
            match, text_of(written), DECLARING_RECEIVERS, holders, grammar, parsed, typed
        ):
            continue
        # An edge whose from end is a template needs no enclosing declaration.
        needed = any(spec.from_template is None for spec in rule.edges)
        source = _enclosing(match, declared, holders, rule_set, grammar, parsed) if needed else ""
        if source is None:
            skipped.append((file, line, rule.name, "no enclosing declaration is mapped"))
            continue
        bindings = parsed.imports.get(parsed.block_at(match.start_byte), {})
        known = {"namespace": parsed.namespace_at(match)}
        values = _receiver_values(match, written, member, holders, rule_set, grammar, parsed)
        names, reasons, starts = [], [], []
        for spec in rule.edges:
            separator = spec.separator or grammar.separator
            reason = (
                f"{rule.member_child} is not a typed parameter"
                if "assigned_parameter" in rule.receivers
                else f"{rule.name_child} has no declared type"
                if rule.receivers
                else f"no resolution step holds for {rule.name_child}"
            )
            start = source if spec.from_template is None else _fill(spec.from_template, values)
            if spec.template is not None or start is None:
                name = _fill(spec.template, values) if start is not None else None
                reason = "no enclosing type is mapped"
            elif spec.key:
                holder = _holder(match, holders, rule_set, grammar, parsed)
                enclosing = holder[0] if holder else None
                _, name, row = _argument(match, spec.key, grammar, parsed, enclosing, call=True)
                name = name or None
                reason = reason if name is not None else row
            else:
                name = (
                    _parameter_type(match, member, grammar, parsed)
                    if "assigned_parameter" in rule.receivers
                    else _declared_type(
                        match, text_of(written), rule.receivers, holders, grammar, parsed, typed
                    )
                    if rule.receivers
                    else parsed.resolve(written, grammar)
                )
                if (
                    name is not None
                    and member is not None
                    and "assigned_parameter" not in rule.receivers
                ):
                    name = separator.join((name, text_of(member)))
            if name is not None and spec.resolve:
                name = resolve_name(name, spec.resolve, separator, bindings, known, tables=tables)
            names.append(name)
            reasons.append(reason)
            starts.append(start)
        if names and not any(names):
            for reason in dict.fromkeys(reasons):
                skipped.append((file, line, rule.name, reason))
            continue
        fired += 1
        for spec, name, reason, start in zip(rule.edges, names, reasons, starts, strict=True):
            if not name or start is None:
                skipped.append((file, line, rule.name, f"edge {spec.kind}: {reason}"))
                continue
            kind = rule_set.edge_kinds[spec.kind]
            candidates = () if spec.full_id else _candidates(spec, rule_set.types, name)
            far = next(iter(namespaces(rule_set.types, kind.to_types)), None)
            if spec.from_template is not None:
                start = f"{next(iter(namespaces(rule_set.types, kind.from_types)))}::{start}"
            edges.append(
                FoundEdge(
                    kind=spec.kind,
                    source=start,
                    target=name
                    if spec.full_id
                    else candidates[0]
                    if candidates
                    else f"{far}::{name}",
                    file=file,
                    line=line,
                    pack=rule.pack,
                    rule=rule.name,
                    confidence=rule.confidence,
                    target_type=spec.to_type,
                    on_miss="target" if spec.on_miss else "",
                    searched_for=name,
                    candidates=candidates,
                    types_tried=spec.types,
                )
            )
    return fired


def _property(node: Node | None, grammar: Grammar) -> Node | None:
    """The name of the property the node reads on the enclosing object, or ``None`` when it is no
    such read."""
    if node is None or node.type not in grammar.property_access:
        return None
    owner = node.child_by_field_name(grammar.property_object)
    name = node.child_by_field_name(grammar.property_name)
    if owner is None or text_of(owner) != grammar.property_self or name is None:
        return None
    return name


def _declared_type(
    node: Node,
    name: str,
    kinds: Sequence[str],
    holders: Mapping[str, tuple[Rule, ...]],
    grammar: Grammar,
    parsed: ParsedFile,
    typed: dict[int, dict[str, str]],
) -> str | None:
    """The full name of the type the nearest enclosing type declaration declares for its property
    ``name``, or ``None``; ``typed`` holds each declaration's types already read, by node id.

    The receiver kinds are read in order, and the first declaration of a kind that gives a
    type wins. A nearer node that holds a body but no rule maps, an anonymous class, gives none.
    """
    bodies = {r.body_child for rules in holders.values() for r in rules}
    holder = node.parent
    while holder is not None and not any(c.type in bodies for c in holder.children):
        holder = holder.parent
    if holder is None or holder.type not in holders:
        return None
    if holder.id not in typed:
        typed[holder.id] = _property_types(holder, kinds, bodies, grammar, parsed)
    return typed[holder.id].get(name)


def _property_types(
    holder: Node, kinds: Sequence[str], bodies: set[str], grammar: Grammar, parsed: ParsedFile
) -> dict[str, str]:
    """The full name of each property's declared type in the type declaration ``holder``, by the
    property's name, a nested declaration with a body left out."""
    found: list[Node] = []
    pending = [holder]
    while pending:
        node = pending.pop()
        found.append(node)
        if node is holder or not any(c.type in bodies for c in node.children):
            pending.extend(reversed(node.named_children))
    declarations = dict(grammar.property_declarations)
    types: dict[str, str] = {}
    for kind in kinds:
        for node in (n for n in found if n.type == declarations.get(kind)):
            name = _bare(node.child_by_field_name(grammar.property_name), grammar)
            if name is None or name in types:
                continue
            if kind == "var_annotation":
                full = _annotated(node, holder, grammar, parsed)
            else:
                written = _typed(node, holder, grammar)
                full = parsed.resolve(written, grammar) if written is not None else None
            if full:
                types[name] = full
    return types


def _receiver_values(
    node: Node,
    written: Node,
    member: Node | None,
    holders: Mapping[str, tuple[Rule, ...]],
    rule_set: RuleSet,
    grammar: Grammar,
    parsed: ParsedFile,
) -> dict[str, str]:
    """The values a receiver rule's templates read at the node: ``member``, the property's name;
    ``method``, the second name child's text; ``enclosing_type``, the full name of the nearest
    enclosing type declaration. A value the node lacks is left out."""
    values = {"member": text_of(written)}
    if member is not None:
        values["method"] = text_of(member)
    holder = _holder(node, holders, rule_set, grammar, parsed)
    if holder is not None:
        values["enclosing_type"] = holder[0]
    return values


def _parameter_type(
    node: Node, written: Node | None, grammar: Grammar, parsed: ParsedFile
) -> str | None:
    """The full name of the type declared for the parameter that ``written`` names, in the nearest
    enclosing node holding a parameter of that name, or ``None``.

    A parameter is a node of the grammar's ``assigned_parameter`` type that is a child or a
    grandchild of an ancestor of the node, outside the branch that holds the node.
    """
    kind = dict(grammar.property_declarations).get("assigned_parameter")
    name = _bare(written, grammar)
    below, at = node, node.parent
    while kind and name and at is not None:
        for child in at.named_children:
            if child.id == below.id:
                continue
            for found in (child, *child.named_children):
                named = _bare(found.child_by_field_name(grammar.property_name), grammar)
                if found.type == kind and named == name:
                    typed = _typed(found, at, grammar)
                    return parsed.resolve(typed, grammar) if typed is not None else None
        below, at = at, at.parent
    return None


def _bare(node: Node | None, grammar: Grammar) -> str | None:
    """The text of the written name at or last below the node, or ``None``: ``$box`` gives
    ``box``."""
    while node is not None and node.type not in grammar.written and node.named_children:
        node = node.named_children[-1]
    return text_of(node) if node is not None and node.type in grammar.written else None


def _typed(node: Node, holder: Node, grammar: Grammar) -> Node | None:
    """The written name of the type field on the node or its nearest ancestor below ``holder``,
    reached through only children; ``None`` for a type of several names or none."""
    at: Node | None = node
    while at is not None and at is not holder:
        found = at.child_by_field_name(grammar.property_type)
        if found is not None:
            while found.type not in grammar.written and len(found.named_children) == 1:
                found = found.named_children[0]
            return found if found.type in grammar.written else None
        at = at.parent
    return None


def _annotated(node: Node, holder: Node, grammar: Grammar, parsed: ParsedFile) -> str | None:
    """The full name the annotation pattern's ``type`` capture gives in the comment just before
    the node or its nearest ancestor below ``holder`` that has one, or ``None``."""
    at: Node | None = node
    while at is not None and at is not holder and grammar.property_annotation is not None:
        before = at.prev_named_sibling
        if before is not None and before.type == grammar.comment:
            found = grammar.property_annotation.search(text_of(before))
            if found is None or not found.group("type"):
                return None
            return resolve_name(
                found.group("type"),
                grammar.resolve or (("as_written", ""),),
                grammar.separator,
                parsed.imports.get(parsed.block_at(before.start_byte), {}),
                {"namespace": parsed.namespace_at(before)},
                tables={},
            )
        at = at.parent
    return None


def _all_written(node: Node, written: frozenset[str]) -> bool:
    """Whether every named node below the node has a type among the written names."""
    return all(c.type in written and _all_written(c, written) for c in node.named_children)


def _allows(rule_set: RuleSet, name: str, allowed: Sequence[str]) -> bool:
    """Whether the type or one of its ancestors is among the allowed types."""
    seen: set[str] = set()
    while name not in allowed and name in rule_set.types and name not in seen:
        seen.add(name)
        name = rule_set.types[name].parent or ""
    return name in allowed


def _child(node: Node, name: str) -> Node | None:
    """The node's child in the field ``name``, else its first named child of that type."""
    found = node.child_by_field_name(name)
    return found or next((c for c in node.named_children if c.type == name), None)


def _enclosing(
    node: Node,
    declared: Mapping[str, Sequence[Rule]],
    holders: Mapping[str, tuple[Rule, ...]],
    rule_set: RuleSet,
    grammar: Grammar,
    parsed: ParsedFile,
) -> str | None:
    """The id the nearest enclosing tree node a declaration rule maps was given, or ``None``.

    The id is minted as the first declaration rule that fires on the node mints it; an ancestor it
    mints no id for is passed.
    """
    parent = node.parent
    while parent is not None:
        rule = next((r for r in declared.get(parent.type, ()) if _fires(r, parent)), None)
        values = _names(parent, rule, grammar, parsed) if rule is not None else None
        if rule is not None and values is not None:
            holder = _holder(parent, holders, rule_set, grammar, parsed)
            if holder is not None:
                values["enclosing_type"] = holder[0]
            node_id = _node_id(rule, values)
            if node_id is not None:
                return f"{namespace_of(rule_set.types, rule.node_type)}::{node_id}"
        parent = parent.parent
    return None


def _same(left: Any, right: Any) -> bool:
    return type(left) is type(right) and bool(left == right)


def _holds(data: dict[str, Entry], source: str, mapping: bool, condition: Condition) -> bool:
    """Whether one condition holds; ``source`` is what ``id_matches`` searches and ``mapping``
    what ``is_mapping`` compares."""
    if isinstance(condition, IsMapping):
        return mapping is condition.value
    if isinstance(condition, IdMatches):
        return condition.pattern.search(source) is not None
    hits = resolve_path(data, condition.path)
    if isinstance(condition, HasKey):
        return bool(hits)
    equal = any(_same(hit.value, condition.value) for hit in hits) or (
        condition.value is None and not hits
    )
    return equal is not condition.negate


def _attribute(data: dict[str, Entry], name: str, path: str) -> tuple[str, Any, int] | None:
    hits = resolve_path(data, path)
    return (name, plain(hits[0].value), hits[0].line) if hits else None


def _text(value: Any) -> str | None:
    if value is None or isinstance(value, (dict, list)):
        return None
    return str(value).lower() if isinstance(value, bool) else str(value)


def _ends(
    spec: EdgeSpec, data: dict[str, Entry], entry: tuple[str | None, int], paths: Mapping[str, str]
) -> list[tuple[str, int]]:
    """Each end value the edge names, with the line of the key or item that states it. A template
    may also name the file's path values."""
    if spec.parts:
        return _composed(spec, data, entry, paths)
    ends = []
    for hit in resolve_path(data, spec.key):
        items = hit.value if spec.each and isinstance(hit.value, list) else None
        if spec.each and isinstance(hit.value, dict):
            items = list(hit.value.values())
        for item in [Hit(i.value, i.line, None) for i in items] if items else [hit]:
            raw = _text(item.value)
            if raw is None or (spec.matches is not None and not fnmatchcase(raw, spec.matches)):
                continue
            name = spec.key.rsplit(".", 1)[-1]
            if spec.pattern is None:
                matches = [{name: raw}]
            else:
                found = spec.pattern.finditer(raw) if spec.each else [spec.pattern.search(raw)]
                matches = [
                    {name: raw, **{k: v for k, v in m.groupdict().items() if v is not None}}
                    for m in found
                    if m is not None
                ]
            for values in matches:
                end = (
                    _fill(spec.template, {**paths, **values}) if spec.template is not None else raw
                )
                if end is not None:
                    ends.append((end, item.line))
    return ends


def _composed(
    spec: EdgeSpec, data: dict[str, Entry], entry: tuple[str | None, int], paths: Mapping[str, str]
) -> list[tuple[str, int]]:
    """The list form: one template over several key sources, one edge per matched each entry.

    An ``entry`` part is the fire's own key, at its line; a whole-file fire has none. With
    ``listed_at``, an end that is not an item of the list at that key path gives no edge.
    """
    fixed: dict[str, str] = {}
    each: list[Hit] | None = None
    line = 0
    for mode, path in spec.parts:
        if mode == "file":
            line = entry[1]
            continue
        if mode == "entry":
            if entry[0] is None:
                return []
            fixed["key"], line = entry[0], line or entry[1]
            continue
        hits = resolve_path(data, path)
        if mode == "each":
            each = hits
        elif hits and _text(hits[0].value) is not None:
            fixed[path.rsplit(".", 1)[-1]] = str(_text(hits[0].value))
            line = line or hits[0].line
        else:
            return []
    listed = None
    if spec.listed_at is not None:
        listed = {_text(item.value) for item in resolve_path(data, f"{spec.listed_at}.*")}
    ends = []
    for hit in each if each is not None else [Hit(None, line, None)]:
        values = {**paths, **fixed}
        if each is not None:
            values["key"] = hit.key if hit.key is not None else str(_text(hit.value))
            if (spec.matches is not None and not fnmatchcase(values["key"], spec.matches)) or any(
                fnmatchcase(values["key"], glob) for glob in spec.not_matches
            ):
                continue
        end = _fill(spec.template, values)
        if end is not None and (listed is None or end in listed):
            ends.append((end, hit.line))
    return ends


def _fill(template: str | None, values: Mapping[str, str]) -> str | None:
    """The template with each ``{name}`` replaced; ``None`` when a name has no value."""
    if template is None or any(name not in values for name in PLACEHOLDER.findall(template)):
        return None
    return PLACEHOLDER.sub(lambda found: values[found.group(1)], template)


def _node_id(rule: Rule, values: Mapping[str, str], *, empty_ok: bool = False) -> str | None:
    """The rule's bare id: its template filled from ``values``, then each normalize step applied.

    ``None`` when the template names a key ``values`` lacks, or when the filled text is empty and
    ``empty_ok`` is false; the empty test comes before any normalize step. An id pattern runs
    first: searched in the text of its source, its named captures join ``values``; ``None`` when
    the source or a value the pattern names is absent, or the pattern does not fit.
    """
    if rule.id_pattern:
        pattern, source = _id_pattern(rule, values), values.get(rule.id_source)
        found = pattern.search(source) if pattern is not None and source is not None else None
        if found is None:
            return None
        values = {**values, **{k: v for k, v in found.groupdict().items() if v is not None}}
    filled = _fill(rule.id_template, values)
    if filled is None or not (filled or empty_ok):
        return None
    return _reshape(filled, rule.normalize)


def _id_pattern(rule: Rule, values: Mapping[str, str]) -> re.Pattern[str] | None:
    """The rule's id pattern, each ``{name}`` filled with that value as literal text; ``None`` when
    a value it names is absent."""
    if any(name not in values for name in PATTERN_VALUE.findall(rule.id_pattern)):
        return None
    filled = PATTERN_VALUE.sub(lambda found: re.escape(values[found.group(1)]), rule.id_pattern)
    return compile_pattern(filled)


def _matches(
    root: Path,
    rule: Rule,
    packs: Sequence[LoadedPack],
    folders: Mapping[str, tuple[str, ...]],
    selection: Selection,
    read: set[str],
    removed: set[str],
) -> list[tuple[str, str, frozenset[str]]]:
    types = FileTypes.build(packs, selection.extensions)
    directories = sorted({path for name in rule.folders for path in folders[name]})
    kept, dropped = select_files(root, directories, rule.filetype, types, selection)
    read.update(kept)
    removed.update(dropped)
    matched = []
    for file in kept:
        claimed = types.claim(posixpath.basename(file))
        names, stem = claimed if claimed is not None else (frozenset(), "")
        ending = posixpath.basename(file)[len(stem) + 1 :]
        if fnmatchcase(stem, rule.glob) and (not rule.endings or ending in rule.endings):
            matched.append((file, stem, names))
    return matched
