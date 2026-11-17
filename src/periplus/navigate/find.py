"""``periplus find``: the things whose id, attributes or description hold some words, main things
first, and the edges whose description, kind meaning or code line holds them."""

from __future__ import annotations

import shlex
from collections import Counter
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from itertools import groupby
from pathlib import Path
from typing import Any

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.navigate.listing import (
    NONE,
    Listing,
    cut,
    first_location,
    mark_text,
    payload,
    place,
)
from periplus.navigate.mapfile import (
    MapIndex,
    as_json,
    as_text,
    load_document,
    map_flag,
    reading_fields,
)
from periplus.navigate.names import Names
from periplus.navigate.nesting import Places
from periplus.navigate.show import read_descriptions
from periplus.navigate.source import (
    SOURCE_WIDTH,
    SourceLines,
    description_line,
    place_key,
    source_line,
    where,
)
from periplus.navigate.undescribed import _key as _container
from periplus.navigate.walk import amount
from periplus.report import _escape, _json_problem

__all__ = [
    "BUDGET",
    "RENDERERS",
    "EdgeMatch",
    "FindReport",
    "FindRow",
    "Match",
    "found_row",
    "json_row",
    "listed",
    "narrowing",
    "render_json",
    "render_text",
    "row_lines",
    "run",
    "search",
]

#: The characters the text aims at: past them it folds what is not main into counts, then the
#: edges, then cuts the rows. ``cli.FIND_BUDGET``, which a test holds equal.
BUDGET = 12_000
#: The most types or containers a count line names.
_FOOTER_TYPES = 8
#: The most edges at one code line the text names one by one; past it, it counts them by kind.
_FOLDED_ENDS = 3
#: The most type names a warning about an unknown type suggests.
_SUGGESTED = 5
#: The groups of things in print order: main things, parts, things not mapped or with no
#: location, and things in supporting code; ``Places.why_not_main`` names all but ``main``.
_GROUPS = ("main", "part", "unplaced", "supporting")
#: Why an edge matched, in print order.
_REASONS = ("description", "source", "kind")
#: The rank of a word a thing does not hold, past every rank ``search`` gives.
_MISSING = 7


@dataclass(frozen=True, slots=True)
class FindRow:
    """One matching node: its id, type, state, first location as ``file:line``, and the line.

    ``matched`` is ``id``, ``attribute`` or ``description``, and ``description`` the node's
    descriptions entry. An attribute match names the attribute and holds the string that matched.
    ``supporting`` marks a node in supporting code, by the map's ``supporting_paths``, and
    ``marks`` holds its mark texts, by ``MapIndex.marks``. ``group`` is one of ``_GROUPS``.
    """

    id: str
    type: str
    state: str
    location: str | None
    source: str | None = None
    matched: str = "id"
    description: str | None = None
    matched_attribute: str | None = None
    attribute_value: str | None = None
    supporting: bool = False
    marks: tuple[str, ...] = ()
    group: str = "main"


@dataclass(frozen=True, slots=True)
class EdgeMatch:
    """One matching edge: its kind, its ends with their short names, its place, why it matched
    (one of ``_REASONS``), its descriptions entry's text and the code line at its place."""

    kind: str
    source: str
    target: str
    source_name: str
    target_name: str
    location: str | None
    matched: str
    description: str | None = None
    code: str | None = None


@dataclass(frozen=True, slots=True)
class FindReport:
    """Every matching thing as a row, counted by type, the matching edges, and what went wrong.

    ``limit`` is the text budget in characters (0: none); ``fold`` says the things that are not
    main may print as counts; ``containers`` holds the short name of the container of each such
    thing, ``None`` for none; ``again`` and ``map_args`` make the command that lists more.
    """

    matches: Listing[FindRow] = NONE
    by_type: Mapping[str, int] | None = None
    edges: tuple[EdgeMatch, ...] = ()
    limit: int = 0
    fold: bool = False
    containers: Mapping[str, str | None] | None = None
    again: tuple[str, ...] = ()
    map_args: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    problems: tuple[Problem, ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def _rank(node_id: str, text: str) -> int | None:
    """0 the id is the text, 1 the name is, 2 it starts with it, 3 holds it, 4 the id holds it."""
    whole = node_id.casefold()
    name = whole.rsplit("::", 1)[-1]
    if whole == text:
        return 0
    if name == text:
        return 1
    if name.startswith(text):
        return 2
    if text in name:
        return 3
    return 4 if text in whole else None


def _attribute(attributes: Mapping[str, Any], text: str) -> tuple[str, str] | None:
    """The first attribute, by name, whose string value or string list item holds ``text``."""
    for name, value in sorted(attributes.items()):
        for item in value if isinstance(value, list) else [value]:
            if isinstance(item, str) and text in item.casefold():
                return name, item
    return None


def _with_subtypes(index: MapIndex, type_name: str) -> set[str]:
    """``type_name`` and every type below it in the map's hierarchy."""
    found = {type_name}
    pending = [type_name]
    while pending:
        for child in index.subtypes(pending.pop()):
            if child not in found:
                found.add(child)
                pending.append(child)
    return found


def _location(node: Mapping[str, Any]) -> str | None:
    """The node's first location as ``file:line``, or ``None`` when it has none."""
    loc = first_location(node)
    return place(loc) if loc else None


def _suggestions(index: MapIndex, type_name: str) -> list[str]:
    """Node types near ``type_name``: those of ids starting ``type_name::``, then by name."""
    held = sorted({as_text(node["type"]) for node in index.nodes.values()})
    prefixed = sorted(
        {as_text(n["type"]) for i, n in index.nodes.items() if i.startswith(f"{type_name}::")}
    )
    folded = type_name.casefold()
    near = [t for t in held if folded in t.casefold() or t.casefold() in folded]
    return list(dict.fromkeys(prefixed + near))[:_SUGGESTED]


def _unknown(index: MapIndex, type_name: str) -> str:
    """The warning for a type the map does not hold, with the types it may have meant."""
    types = f"periplus types{map_flag(index.given)}"
    warning = f"no type named {type_name!r} is in the map; {types} lists them"
    suggested = _suggestions(index, type_name)
    return f"{warning}; did you mean: {', '.join(suggested)}" if suggested else warning


def _strip(file: str) -> str:
    return file.removeprefix("./")


def run(
    start: Path,
    env: Mapping[str, str],
    text: str,
    types: Collection[str],
    limit: int,
    map_path: Path | None,
    paths: Collection[str] = (),
    marks: Collection[str] = (),
    *,
    any_word: bool = False,
    parts: bool = False,
    edges: bool = True,
    kinds: bool = False,
    source: bool = True,
) -> FindReport:
    """Find the things and edges that hold the words of ``text``; a load failure is a problem.

    Each word, split at white space, must match a thing's id, attributes or description, or
    with ``any_word`` one word must. ``types`` keeps a node of any of them or their subtypes,
    ``paths`` a node with a location whose file starts with any of them, and ``marks`` a node
    that carries any of these mark texts; empty keeps every node. ``parts`` keeps the things
    that are not main. An edge is kept when one of its ends would be, and matches by its
    description, by its code line unless ``source`` is off, or by its kind's meaning with
    ``kinds`` or when no thing matched. ``limit`` is the text budget in characters, 0 for none.
    """
    words = list(dict.fromkeys(text.casefold().split())) or [text.casefold()]
    try:
        document = load_document(start, env, map_path)[1]
        _, told, problems = read_descriptions(start, map_path)
        with reading_fields(start, map_path):
            index = MapIndex(document, map_path)
            lines = SourceLines(start, map_path)
            names = Names(index)
            places = Places(index, names)
            report = _things(index, places, words, any_word, types, paths, marks, told, parts)
            rows = tuple(replace(r, source=lines.at(r.location)) for r in report.matches.items)
            report = replace(report, matches=cut(rows, 0))
            if edges and text.strip():
                wanted, prefixes, _ = narrowing(index, types, paths)

                def kept(node_id: str) -> bool:
                    return _kept(index, node_id, wanted, prefixes, marks)

                legend = document.get("legend", {}).get("edge_kinds", {})
                meanings = legend if kinds or not rows else {}
                found = _edges(index, names, told, meanings, kept, words, any_word, source, lines)
                report = replace(report, edges=found)
    except HarnessError as error:
        return FindReport(problems=(error.problem(),))
    again = ["periplus", "find", *([text] if text else [])]
    for flag, values in (("--type", types), ("--path", paths), ("--mark", marks)):
        again += [part for value in values for part in (flag, value)]
    for flag, on in (("--any", any_word), ("--kinds", kinds)):
        again += [flag] if on else []
    again += [] if edges else ["--no-edges"]
    again += [] if source else ["--no-source"]
    return replace(
        report,
        limit=limit,
        fold=not parts and not types,
        again=tuple(again),
        map_args=("--map", str(map_path)) if map_path is not None else (),
        problems=problems,
    )


def _kept(
    index: MapIndex,
    node_id: str,
    wanted: set[str] | None,
    prefixes: Collection[str],
    marks: Collection[str],
) -> bool:
    """Whether the node fits the types, the path prefixes and the marks, as a thing must."""
    node = index.nodes[node_id]
    if wanted is not None and node["type"] not in wanted:
        return False
    files = [_strip(as_text(loc["file"])) for loc in node["locations"]]
    if prefixes and not any(file.startswith(p) for file in files for p in prefixes):
        return False
    return not marks or bool(set(marks) & set(index.marks(node_id)))


def _things(
    index: MapIndex,
    places: Places,
    words: Sequence[str],
    any_word: bool,
    types: Collection[str],
    paths: Collection[str],
    marks: Collection[str],
    told: Mapping[str, Any],
    parts: bool,
) -> FindReport:
    """The matching things in print order: by group, then for each word from the rarest, the
    one that matches fewest things, a name before a description alone, then ``search``'s rank,
    then the id."""
    wanted, prefixes, warnings = narrowing(index, types, paths)
    held = sorted(set(index.mark_texts.values()))
    for mark in sorted(set(marks) - set(held)):
        known = f"the map's marks: {', '.join(held)}" if held else "the map holds no marks"
        warnings.append(f"no node carries the mark {mark!r}; {known}")
    described = {i: entry["text"] for i, entry in (told.get("nodes") or {}).items()}
    found = {w: {m[1]: m for m in search(index, w, wanted, prefixes, described)} for w in words}
    rarest = sorted(words, key=lambda w: (len(found[w]), w))
    hits = [set(found[w]) for w in rarest]
    ids = set.union(*hits) if any_word else set.intersection(*hits)
    keyed = []
    for node_id in ids:
        ranks = tuple(found[w][node_id][0] if node_id in found[w] else _MISSING for w in rarest)
        first = next(found[w][node_id] for w in rarest if node_id in found[w])
        group = places.why_not_main(node_id) or "main"
        row = replace(
            found_row(first, described),
            supporting=index.supporting(node_id) is not None,
            marks=index.marks(node_id),
            group=group,
        )
        if (marks and not set(marks) & set(row.marks)) or (parts and group == "main"):
            continue
        tiers = tuple(0 if r < 6 else 1 if r == 6 else 2 for r in ranks)
        keyed.append(((_GROUPS.index(group), tiers, ranks, node_id), row))
    rows = [row for _, row in sorted(keyed, key=lambda pair: pair[0])]
    containers: dict[str, str | None] = {}
    for row in rows:
        if row.group != "main":
            held_by = _container(index, places, row.id, "container")
            containers[row.id] = None if held_by is None else places.names.short(held_by)
    by_type = dict(sorted(Counter(row.type for row in rows).items()))
    return FindReport(cut(rows, 0), by_type, containers=containers, warnings=tuple(warnings))


def _edges(
    index: MapIndex,
    names: Names,
    told: Mapping[str, Any],
    meanings: Mapping[str, Any],
    kept: Callable[[str], bool],
    words: Sequence[str],
    any_word: bool,
    source: bool,
    lines: SourceLines,
) -> tuple[EdgeMatch, ...]:
    """The edges with an end ``kept`` keeps whose description, code line (unless ``source`` is
    off) or kind meaning (each kind in ``meanings``) holds the words; by reason, place, kind and
    ends."""
    hold = any if any_word else all

    def holds(text: str) -> bool:
        folded = text.casefold()
        return hold(w in folded for w in words)

    entries = {(e["from"], e["kind"], e["to"]): e["text"] for e in told.get("edges") or []}
    kinds = {kind for kind, said in meanings.items() if isinstance(said, str) and holds(said)}
    found = []
    for edge in index.edges:
        if not (kept(edge["from"]) or kept(edge["to"])):
            continue
        key = (edge["from"], edge["kind"], edge["to"])
        entry = entries.get(key)
        at = where(edge, index.nodes[edge["from"]])
        if entry is not None and holds(entry):
            matched = "description"
        elif source and (line := _code(edge, lines, holds)) is not None:
            matched, at = "source", line
        elif edge["kind"] in kinds:
            matched = "kind"
        else:
            continue
        found.append(
            EdgeMatch(
                as_text(edge["kind"]),
                as_text(edge["from"]),
                as_text(edge["to"]),
                names.short(edge["from"]),
                names.short(edge["to"]),
                at,
                matched,
                entry,
                lines.at(at),
            )
        )
    found.sort(
        key=lambda e: (_REASONS.index(e.matched), place_key(e.location), e.kind, e.source, e.target)
    )
    return tuple(found)


def _code(edge: Mapping[str, Any], lines: SourceLines, holds: Callable[[str], bool]) -> str | None:
    """The first of the edge's places whose whole code line holds the words, as ``file:line``."""
    for loc in edge["locations"]:
        text = lines.lines(as_text(loc["file"]))
        line = loc["line"]
        if text is not None and 1 <= line <= len(text) and holds(text[line - 1]):
            return place(loc)
    return None


def narrowing(
    index: MapIndex, types: Collection[str], paths: Collection[str]
) -> tuple[set[str] | None, list[str], list[str]]:
    """The node types ``types`` keeps (``None`` keeps all), the path prefixes, and the warnings
    for a type or a path the map does not hold."""
    warnings: list[str] = []
    wanted: set[str] | None = None
    if types:
        wanted = set()
        for type_name in sorted(set(types)):
            below = _with_subtypes(index, type_name)
            wanted |= below
            if not any(node["type"] in below for node in index.nodes.values()) and not (
                index.parent(type_name) or index.subtypes(type_name)
            ):
                warnings.append(_unknown(index, type_name))
    prefixes = sorted({_strip(p) for p in paths})
    files = {_strip(as_text(loc["file"])) for n in index.nodes.values() for loc in n["locations"]}
    for prefix in prefixes:
        if not any(file.startswith(prefix) for file in files):
            warnings.append(f"no file in the map starts with {prefix!r}")
    return wanted, prefixes, warnings


#: One match: its rank (0 to 4 by id, 5 attribute, 6 description), id, node, and the attribute
#: name and value that matched.
Match = tuple[int, str, Mapping[str, Any], tuple[str, str] | None]


def search(
    index: MapIndex,
    text: str,
    wanted: set[str] | None,
    prefixes: Collection[str],
    described: Mapping[str, str],
) -> list[Match]:
    """The nodes whose id, attributes or description hold ``text``, by rank and then id."""
    needle = text.casefold()
    ranked: list[Match] = []
    for node_id, node in index.nodes.items():
        if wanted is not None and node["type"] not in wanted:
            continue
        held = [_strip(as_text(loc["file"])) for loc in node["locations"]]
        if prefixes and not any(file.startswith(p) for file in held for p in prefixes):
            continue
        rank = _rank(as_text(node_id), needle)
        attribute = None if rank is not None else _attribute(node.get("attributes", {}), needle)
        if attribute is not None:
            rank = 5
        elif rank is None and needle in described.get(node_id, "").casefold():
            rank = 6
        if rank is not None:
            ranked.append((rank, node_id, node, attribute))
    ranked.sort(key=lambda row: (row[0], row[1]))
    return ranked


def found_row(match: Match, described: Mapping[str, str]) -> FindRow:
    """One match as a row, its source line not yet read."""
    rank, node_id, node, attribute = match
    return FindRow(
        node_id,
        as_text(node["type"]),
        as_text(node["state"]),
        _location(node),
        matched={5: "attribute", 6: "description"}.get(rank, "id"),
        description=described.get(node_id),
        matched_attribute=attribute[0] if attribute else None,
        attribute_value=attribute[1] if attribute else None,
    )


def row_lines(row: FindRow) -> list[str]:
    """One row as text: the node, its place and what matched, then its source, attribute and
    description lines."""
    where = row.location or "no location"
    marked = {
        "attribute": f"  [attribute {_escape(row.matched_attribute or '')}]",
        "description": "  [description]",
    }.get(row.matched, "")
    marked += mark_text(row.marks)
    marked += "  [supporting code]" if row.supporting else ""
    lines = [
        f"{_escape(row.id)}  {_escape(row.type)}  {_escape(row.state)}  {_escape(where)}" + marked
    ]
    lines += source_line(row.source)
    if row.attribute_value is not None:
        value = row.attribute_value.strip().partition("\n")[0].strip()[:SOURCE_WIDTH]
        lines.append(f"      @ {_escape(row.matched_attribute or '')}: {_escape(value)}")
    return lines + description_line(row.description)


def _edge_lines(edge: EdgeMatch) -> list[str]:
    """One edge as text: kind, both ends' short names, place and why, then its code line and
    description."""
    lines = [
        f"  {_escape(edge.kind)}  {_escape(edge.source_name)} -> {_escape(edge.target_name)}"
        f"  {_escape(edge.location or 'no location')}  [{edge.matched}]"
    ]
    return lines + source_line(edge.code) + description_line(edge.description)


def _edge_rows(edges: Sequence[EdgeMatch]) -> list[str]:
    """The edges as text, those matched by ``[source]`` at one place with no description folded
    into one row: the place once, then each edge's kind and ends, or past ``_FOLDED_ENDS`` the
    count by kind, then the code line once."""
    lines: list[str] = []
    for at, grouped in groupby(
        edges, lambda e: e.location if e.matched == "source" and e.description is None else e
    ):
        group = list(grouped)
        if len(group) == 1 or not isinstance(at, str):
            lines += [line for edge in group for line in _edge_lines(edge)]
            continue
        if len(group) > _FOLDED_ENDS:
            said = f"{len(group)} edges: {_counted(Counter(e.kind for e in group), 'kinds')}"
        else:
            said = "; ".join(
                f"{_escape(e.kind)} {_escape(e.source_name)} -> {_escape(e.target_name)}"
                for e in group
            )
        lines += [f"  {_escape(at)}  [source]  {said}", *source_line(group[0].code)]
    return lines


def _counted(counts: Counter[Any], noun: str) -> str:
    """The counts, most first, then by name (``None`` as ``(no container)`` last), the first
    ``_FOOTER_TYPES`` named and the rest counted."""
    ranked = sorted(counts.items(), key=lambda p: (-p[1], p[0] is None, p[0] or ""))
    named = ", ".join(
        f"{_escape(k) if k is not None else '(no container)'} {n}"
        for k, n in ranked[:_FOOTER_TYPES]
    )
    more = len(ranked) - _FOOTER_TYPES
    return named + (f", and {more} more {noun}" if more > 0 else "")


def _command(report: FindReport, *extra: str) -> str:
    return " ".join(shlex.quote(part) for part in (*report.again, *extra, *report.map_args))


def _head(report: FindReport) -> list[str]:
    """The count line, then the things by type in each of the two groups, then the edges by kind."""
    rows = report.matches.items
    groups = Counter(row.group for row in rows)
    said = [
        f"{groups['main']} main" if groups["main"] else "",
        amount(groups["part"], "part") if groups["part"] else "",
        f"{groups['supporting']} in supporting code" if groups["supporting"] else "",
        f"{groups['unplaced']} not mapped or with no location" if groups["unplaced"] else "",
    ]
    split = ", ".join(part for part in said if part)
    things = amount(len(rows), "thing") + (f" ({split})" if split else "")
    lines = [f"periplus find: {things}, {amount(len(report.edges), 'edge')}"]
    main = Counter(row.type for row in rows if row.group == "main")
    rest = Counter(row.type for row in rows if row.group != "main")
    lines += [f"main by type: {_counted(main, 'types')}"] if main else []
    lines += [f"not main by type: {_counted(rest, 'types')}"] if rest else []
    kinds = Counter(edge.kind for edge in report.edges)
    return lines + ([f"edges by kind: {_counted(kinds, 'kinds')}"] if kinds else [])


def _text(report: FindReport, fold: bool, fold_edges: bool, keep: int | None) -> str:
    """The text with what is not main folded or not, the edges folded or not, and the first
    ``keep`` listed rows (``None``: all)."""
    rows = report.matches.items
    main = [row for row in rows if row.group == "main"]
    rest = [row for row in rows if row.group != "main"]
    listed = main if fold else list(rows)
    head = _head(report)
    if keep is not None and keep < len(listed):
        noun = "main things" if fold else "things"
        head.append(
            f"showing {keep} of {len(listed)} {noun}; all: "
            f"{_escape(_command(report, '--limit', '0'))}"
        )
        listed = listed[:keep]
    body: list[str] = []
    for n, row in enumerate(listed):
        if row.group != "main" and n and listed[n - 1].group == "main":
            body.append("not main:")
        body += row_lines(row)
    if fold and rest:
        containers = Counter((report.containers or {}).get(row.id) for row in rest)
        body += [
            f"not main, not listed: {len(rest)}",
            f"  by container: {_counted(containers, 'containers')}",
            f"  list them: {_escape(_command(report, '--parts'))}",
        ]
    body += [""] if body and report.edges else []
    if report.edges and fold_edges:
        body += [
            f"edges, not listed: {len(report.edges)}",
            f"  by kind: {_counted(Counter(e.kind for e in report.edges), 'kinds')}",
            f"  list them: {_escape(_command(report, '--limit', '0'))}",
        ]
    elif report.edges:
        body.append("edges:")
        body += _edge_rows(report.edges)
    notes = [f"warning: {_escape(w)}" for w in report.warnings]
    notes += [f"{int(p.code)} {_escape(p.message)}" for p in report.problems]
    return "\n".join([*head, "", *(body or ["no matches"]), *notes]) + "\n"


def render_text(report: FindReport) -> str:
    """The report as lines a person reads, in at most ``limit`` characters when it can be: past
    them the things that are not main become counts (unless ``fold`` is off), then the edges,
    then the listed rows are cut, keeping one. Every outside string goes through ``_escape``."""
    rows = report.matches.items
    levels = [(False, False), (report.fold, False), (report.fold, True)]
    for fold, fold_edges in dict.fromkeys(levels):
        text = _text(report, fold, fold_edges, None)
        if not report.limit or len(text) <= report.limit:
            return text
    listed = sum(row.group == "main" for row in rows) if report.fold else len(rows)
    low, high = 1, max(listed, 1)
    while low < high:
        middle = (low + high + 1) // 2
        if len(_text(report, report.fold, True, middle)) <= report.limit:
            low = middle
        else:
            high = middle - 1
    return _text(report, report.fold, True, low)


def json_row(row: FindRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "type": row.type,
        "state": row.state,
        "location": row.location,
        "source": row.source,
        "matched": row.matched,
        "matched_attribute": row.matched_attribute,
        "description": row.description,
        "supporting": row.supporting,
        "marks": list(row.marks),
    }


def _json_edge(edge: EdgeMatch) -> dict[str, Any]:
    return {
        "kind": edge.kind,
        "from": edge.source,
        "to": edge.target,
        "location": edge.location,
        "source": edge.code,
        "matched": edge.matched,
        "description": edge.description,
    }


def render_json(report: FindReport) -> str:
    """The report as one JSON document, every match and edge, keys sorted, ``ensure_ascii=True``."""
    document = {
        **payload(report.matches, lambda row: {**json_row(row), "group": row.group}),
        "by_type": dict(report.by_type or {}),
        "edges": [_json_edge(edge) for edge in report.edges],
        "warnings": list(report.warnings),
        "problems": [_json_problem(p) for p in report.problems],
    }
    return as_json(document)


def listed(report: FindReport) -> list[str]:
    """The ids ``--ids`` prints: every matching thing, then both ends of each matching edge,
    each once."""
    ends = (end for edge in report.edges for end in (edge.source, edge.target))
    return list(dict.fromkeys([*(row.id for row in report.matches.items), *ends]))


RENDERERS = {"text": render_text, "json": render_json}
