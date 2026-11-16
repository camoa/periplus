"""``periplus slice``: the items around a start set, printed as rows or cut into a map file."""

from __future__ import annotations

import math
import os
import re
from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from fractions import Fraction
from pathlib import Path
from typing import Any

from periplus.engine.emit import counts, hierarchy
from periplus.errors import ExitCode, HarnessError, Problem
from periplus.map import write_document
from periplus.navigate import find
from periplus.navigate import grouping as grouping_
from periplus.navigate.ids import resolve
from periplus.navigate.listing import (
    NONE,
    Listing,
    first_location,
    footer,
    kind_warnings,
    mark_text,
    payload,
    place,
    problem_lines,
)
from periplus.navigate.mapfile import (
    MapIndex,
    NodeNotFound,
    as_json,
    as_text,
    load_document,
    reading_fields,
)
from periplus.navigate.names import Names
from periplus.navigate.show import node_descriptions
from periplus.navigate.source import SourceLines, description_line, source_line, where
from periplus.navigate.walk import stand_in_line, walk
from periplus.report import _escape, _json_problem

__all__ = [
    "DEEP_STARTS",
    "PRINT_DEPTH",
    "ROW_LIMIT",
    "START_LIMIT",
    "RENDERERS",
    "Piece",
    "PieceRow",
    "SliceReport",
    "Start",
    "render_json",
    "render_text",
    "run",
]

#: The most start nodes the words pick in all, unless ``starts`` says otherwise.
START_LIMIT = 12
#: How many starts, the first by rank, walk ``PRINT_DEPTH`` hops; the rest walk one, unless
#: ``depth`` says otherwise.
DEEP_STARTS = 8
#: The most start nodes the words pick of any one node type.
TYPE_STARTS = 2
#: The share of the start budget the first pass gives to the words, one start each in turn from
#: the rarest word down; it gives every word one start while the budget lasts.
WORD_SHARE = Fraction(1, 2)
#: The decimal places a word's weight keeps, so equal scores are equal on every machine.
WEIGHT_PLACES = 6
#: The fewest characters a word needs to be searched; a shorter one matches too much.
MIN_WORD = 3
#: The most rows a printed piece shows, unless ``limit`` says otherwise.
ROW_LIMIT = 50
#: How many edges a printed piece follows, unless ``depth`` says otherwise.
PRINT_DEPTH = 2
#: The bytes the default printed piece aims at; an explicit ``limit`` caps rows alone instead.
BYTE_LIMIT = 8 * 1024
#: The most far-end names one link clause prints before it counts the rest.
LINK_NAMES = 5
#: The most names of nodes outside the project one link clause prints.
OUTSIDE_NAMES = 3
#: The most edge kinds a footer line names, those with the most rows left out first.
FOOTER_KINDS = 6
#: Far ends of one clause that share an owner, at least this many, print as the owner and a count.
OWNER_FOLD = 3
#: The bytes the legend at the end of a printed piece may take; past them it counts the rest.
LEGEND_BYTES = 640
#: The depth and the item limit of a slice written to a file, as before the printed piece.
FILE_DEPTH = 1
FILE_LIMIT = 500


@dataclass(frozen=True, slots=True)
class Start:
    """A start node of a printed piece, as ``find`` shows it, and why it was picked.

    ``given`` is the argument that named it; ``words`` each word, or the whole text, that found
    it, with where it matched (``id``, ``attribute`` or ``description``) and the attribute's name.
    """

    row: find.FindRow
    given: str | None = None
    words: tuple[tuple[str, str, str | None], ...] = ()


@dataclass(frozen=True, slots=True)
class PieceRow:
    """One row of a printed piece: the edge from the node above, ``parent``, to the node ``id``.

    ``outward`` is true when the edge runs from ``parent`` to ``id``. ``again`` marks a node
    printed in full elsewhere in the piece; its row is a back-reference. ``container`` marks the
    container end of a grouping edge, which the walk does not go on from. ``marks`` holds the
    mark texts of ``id``.
    """

    start: str
    hop: int
    parent: str
    kind: str
    outward: bool
    id: str
    type: str
    state: str
    again: bool
    location: str | None = None
    source: str | None = None
    description: str | None = None
    container: bool = False
    marks: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Members:
    """The members of a start that is a container: how many, how many of each type, rarest type
    first, and the rows shown."""

    container: str
    total: int
    by_type: Mapping[str, int]
    rows: tuple[PieceRow, ...]


@dataclass(frozen=True, slots=True)
class Link:
    """A subject's edges of one kind and direction to other nodes of the piece, by short name.

    ``owners`` are far ends folded into their owner, with a count; ``more`` counts the mapped far
    ends past the names shown; ``outside`` names the first far ends not mapped, of
    ``outside_count``. ``realized`` marks far ends at the concrete end of a realizing kind: the
    forms of this node.
    """

    kind: str
    outward: bool
    names: tuple[str, ...]
    more: int
    owners: tuple[tuple[str, int], ...]
    outside: tuple[str, ...]
    outside_count: int
    realized: bool = False


@dataclass(frozen=True, slots=True)
class Subject:
    """A mapped node of the piece under its file: line, short name, type, source line, its links
    in the piece, its edges the piece does not show, as (kind, outward, count), how many nodes
    stand for it past the cap, and its mark texts."""

    id: str
    short: str
    type: str
    line: int | float | None
    source: str | None
    description: str | None
    links: tuple[Link, ...]
    unwalked: tuple[tuple[str, bool, int], ...]
    more_forms: int = 0
    marks: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class FileGroup:
    """One file of the piece, the containers its nodes belong to, and its nodes in line order."""

    file: str | None
    containers: tuple[str, ...]
    subjects: tuple[Subject, ...]
    piece: int = 1


@dataclass(frozen=True, slots=True)
class Piece:
    """Nodes the output names that edges other than grouping edges join: its starts, in pick
    order, how many things the output names in it, and how many nodes in supporting code its
    walk left out, with the patterns they match."""

    starts: tuple[str, ...]
    things: int
    supporting: int = 0
    patterns: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SliceReport:
    """One slice run. ``out`` is ``None`` when nothing was written.

    A printed piece (``printed``) holds its ``starts`` and ``rows``, what the row cap left out by
    hop and by kind, the kinds its rows hold, whether an edge leads on past ``depth``, the nodes
    folded into the node above by type, and ``notes`` on how the words were read.
    """

    out: str | None = None
    nodes: int = 0
    edges: int = 0
    warnings: tuple[str, ...] = ()
    problems: tuple[Problem, ...] = ()
    printed: bool = False
    starts: tuple[Start, ...] = ()
    rows: Listing[PieceRow] = NONE
    left_by_hop: Mapping[int, int] | None = None
    left_by_kind: Mapping[str, int] | None = None
    kinds: tuple[str, ...] = ()
    deeper: bool = False
    depth: int = PRINT_DEPTH
    direction: str = "both"
    searched: bool = False
    folded: Mapping[str, int] | None = None
    notes: tuple[str, ...] = ()
    members: tuple[Members, ...] = ()
    files: tuple[FileGroup, ...] = ()
    inventory: tuple[tuple[str, tuple[tuple[str, int], ...]], ...] = ()
    shorts: Mapping[str, str] | None = None
    cuts: tuple[str, ...] = ()
    legend: tuple[tuple[str, str], ...] = ()
    pieces: tuple[Piece, ...] = ()
    piece_of: Mapping[str, int] | None = None

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def run(
    start: Path,
    env: Mapping[str, str],
    ids: Collection[str],
    prefixes: Collection[str],
    direction: str,
    depth: int | None,
    kinds: Collection[str],
    limit: int | None,
    out: Path | None,
    map_path: Path | None,
    types: Collection[str] = (),
    starts: int | None = None,
    support: bool = False,
) -> SliceReport:
    """Write ``ids``, the nodes under each of ``prefixes`` and what they reach to ``out``.

    Without ``out``, print the piece instead: see ``_piece``. ``direction`` is ``out``, ``in`` or
    ``both``. A limit of 0 keeps every item. ``depth`` and ``limit`` of ``None`` take the mode's
    default. ``types`` and ``starts`` narrow words, which only the printed piece takes, and
    ``support`` prints its supporting code.
    """
    if out is None:
        return _piece(
            start,
            env,
            ids,
            prefixes,
            direction,
            depth,
            kinds,
            ROW_LIMIT if limit is None else limit,
            map_path,
            types,
            START_LIMIT if starts is None else starts,
            limit is None,
            support,
        )
    if types or starts is not None or support:
        message = (
            "--type, --starts and --support shape the printed piece, which --out does not take"
        )
        return SliceReport(problems=(Problem(ExitCode.USAGE, message, {}),))
    depth = FILE_DEPTH if depth is None else depth
    limit = FILE_LIMIT if limit is None else limit
    try:
        if not ids and not prefixes:
            return SliceReport(
                problems=(Problem(ExitCode.USAGE, "give at least one id or a path prefix", {}),)
            )
        path, document = load_document(start, env, map_path)
        target = start / out
        if target.resolve() == path.resolve():
            message = f"--out {target} is the map being read; choose another file"
            return SliceReport(
                problems=(Problem(ExitCode.OUTPUT_UNWRITABLE, message, {"path": str(target)}),)
            )
        with reading_fields(start, map_path):
            index = MapIndex(document)
            resolved = [resolve(index, text) for text in ids]
            begun = {node_id for node_id, _ in resolved}
            begun |= _under(document, prefixes)
            kept = set(begun)
            for item in sorted(begun):
                kept.update(row.id for row in walk(index, item, direction, depth, set(kinds)))
            held = {edge["kind"] for edge in index.edges}
            if limit and len(kept) > limit:
                message = f"the slice reaches {len(kept)} items, over the limit of {limit}"
                return SliceReport(problems=(Problem(ExitCode.SLICE_TOO_LARGE, message, {}),))
            nodes = [node for node in document["nodes"] if node["id"] in kept]
            edges = [e for e in document["edges"] if e["from"] in kept and e["to"] in kept]
            piece: dict[str, Any] = {
                **document,
                "counts": counts(nodes, edges),
                "nodes": nodes,
                "edges": edges,
                "type_hierarchy": hierarchy({str(node["type"]) for node in nodes}, index.parent),
            }
            texts = piece.pop("legend", {})
            held_names = {
                "edge_kinds": {edge["kind"] for edge in edges},
                "node_types": {node["type"] for node in nodes},
            }
            legend = {
                section: given
                for section, names in held_names.items()
                if (given := {k: v for k, v in texts.get(section, {}).items() if k in names})
            }
            if legend:
                piece["legend"] = legend
    except HarnessError as error:
        return SliceReport(problems=(error.problem(),))
    problems = write_document(piece, target)
    if problems:
        return SliceReport(problems=problems)
    warnings = tuple(w for _, said in resolved for w in said) + kind_warnings(kinds, held)
    return SliceReport(str(target), len(nodes), len(edges), warnings)


def _under(document: Mapping[str, Any], prefixes: Collection[str]) -> set[str]:
    """The nodes whose first location's file starts with one of ``prefixes``; each must hold one."""
    starts: set[str] = set()
    for prefix in prefixes:
        under = {
            node["id"]
            for node in document["nodes"]
            if (loc := first_location(node)) and loc["file"].startswith(prefix)
        }
        if not under:
            raise NodeNotFound(f"no node's first location starts with {prefix!r}", {})
        starts |= under
    return starts


#: A word: a run of letters, digits and underscores.
_WORD = re.compile(r"\w+")
#: ``find``'s rank for a word found in the id but not in its last ``::`` segment.
_OUTSIDE_NAME = 4
#: Where a match was found, by ``find``'s rank: 0 to 4 the id, 5 an attribute, 6 a description.
_PLACES = ("id", "attribute", "description")


def _place(rank: int) -> str:
    return _PLACES[max(rank - 4, 0)]


def _piece(
    start: Path,
    env: Mapping[str, str],
    given: Collection[str],
    prefixes: Collection[str],
    direction: str,
    depth: int | None,
    kinds: Collection[str],
    limit: int,
    map_path: Path | None,
    types: Collection[str],
    most: int,
    budgeted: bool = False,
    support: bool = False,
) -> SliceReport:
    """The piece around the start nodes, as rows to print; ``budgeted`` fits it to
    ``BYTE_LIMIT``, cutting far hops, then the unwalked counts, then names per link, then the
    nearest rows of the largest piece first.

    Without ``depth``, the first ``DEEP_STARTS`` starts walk ``PRINT_DEPTH`` hops and the rest
    one hop each.

    An argument that names a node starts there. The rest is searched as ``find`` searches, as a
    whole and word by word; see ``_starts``. ``types`` and, when there are words, ``prefixes``
    narrow those starts. Without words, each prefix adds the nodes under it.

    Unless ``support``, a node in supporting code is not a start, but for one named by its id or
    when every match is there, and the walk does not print or follow it: each piece counts them.
    """
    try:
        document = load_document(start, env, map_path)[1]
        described, problems = node_descriptions(start, map_path)
        with reading_fields(start, map_path):
            index = MapIndex(document)
            picked: dict[str, Start] = {}
            warnings: list[str] = []
            rest: list[str] = []
            several = len(_WORD.findall(" ".join(given))) > 1
            for text in given:
                try:
                    node_id, said = resolve(index, text)
                except NodeNotFound:
                    rest.append(text)
                    continue
                warnings += said
                picked.setdefault(node_id, Start(_row(index, node_id, described), given=text))
                if several and _WORD.fullmatch(text):
                    rest.append(text)
            words = list(dict.fromkeys(_WORD.findall(" ".join(rest).casefold())))
            words = [word for word in words if len(word) >= MIN_WORD]
            whole = " ".join(rest).casefold().strip()
            queries = list(dict.fromkeys(([whole] if whole and whole not in words else []) + words))
            matched: dict[str, set[str]] = {}
            # The words a node holds in its own name, an attribute or its description: a word
            # only in the id's type or in the owner part before its last ``::`` is not the node's.
            owned: dict[str, set[str]] = {}
            weights: dict[str, float] = {}
            scores: dict[str, float] = {}
            notes: list[str] = []
            search = _Search(index, described)
            for word in words:
                hits = search(word, None, ())
                for match in hits:
                    matched.setdefault(match[1], set()).add(word)
                    if match[0] != _OUTSIDE_NAME:
                        owned.setdefault(match[1], set()).add(word)
                if hits:
                    weights[word] = round(math.log(len(index.nodes) / len(hits)), WEIGHT_PLACES)
            standing = _Standing(index)
            if queries:
                wanted, narrowed, noted = find.narrowing(index, types, prefixes)
                warnings += noted
                scores = {
                    node_id: round(sum(weights[w] for w in found_), WEIGHT_PLACES)
                    for node_id, found_ in owned.items()
                }
                rarest = sorted(weights, key=lambda w: (-weights[w], w))
                found = _starts(
                    index,
                    queries,
                    (wanted, narrowed),
                    described,
                    (scores, owned, rarest),
                    most,
                    standing,
                    search,
                    support,
                )
                for node_id, chosen in found.items():
                    picked.setdefault(node_id, chosen)
                lone = found and queries[0] == whole and len(queries) > 1
                if lone and not search(whole, wanted, narrowed):
                    notes.append(f"no node matches {whole!r} as a whole; started from its words")
            elif prefixes:
                under = sorted(_under(document, prefixes))
                not_supporting = [n for n in under if support or index.supporting(n) is None]
                for node_id in not_supporting or under:
                    picked.setdefault(node_id, Start(_row(index, node_id, described)))
            elif not picked:
                message = "give some words, an id or a path prefix"
                return SliceReport(printed=True, problems=(Problem(ExitCode.USAGE, message, {}),))
            order = list(picked)
            depths = {
                s: depth if depth is not None else PRINT_DEPTH if n < DEEP_STARTS else 1
                for n, s in enumerate(order)
            }
            if len(set(depths.values())) > 1:
                notes.append(
                    f"walked {PRINT_DEPTH} hops from the first {DEEP_STARTS} starts"
                    f" and 1 hop from the other {len(order) - DEEP_STARTS}"
                )
            deepest = max(depths.values(), default=PRINT_DEPTH if depth is None else depth)
            grouping = {as_text(k) for k in document.get("grouping_kinds", ())} - set(kinds)
            alone = bool(types) and not queries
            only = find.narrowing(index, types, ())[0] if alone else None
            share = max(1, limit // len(order)) if limit and order else 0
            hidden: list[tuple[str, str, str]] = []
            found_members = (
                _members(index, s, grouping, only, share, standing, None if support else hidden)
                for s in order
            )
            members = [m for m in found_members if m is not None]
            rows: list[PieceRow] = []
            deeper, folded, more_forms = False, Counter[str](), dict[str, int]()
            if not (alone and members):
                rows, deeper, folded, more_forms = _grow(
                    index,
                    depths,
                    direction,
                    set(kinds),
                    standing,
                    grouping,
                    None if support else hidden,
                )
            left_over = limit - sum(len(m.rows) for m in members) if limit else 0
            kept = (
                []
                if limit and left_over <= 0
                else _keep(rows, picked, matched, left_over, standing)
            )
            held = {edge["kind"] for edge in index.edges}
            lines = SourceLines(start, map_path)
            names = Names(index)
            homes: dict[str, set[str]] = {}
            for edge in index.edges:
                if edge["kind"] in grouping and (loc := first_location(index.nodes[edge["from"]])):
                    homes.setdefault(as_text(loc["file"]), set()).add(as_text(edge["to"]))

            texts = document.get("legend", {}).get("edge_kinds", {})

            def assemble(
                chosen: Sequence[int], cap: int, more: bool, cuts: tuple[str, ...], told: bool
            ) -> SliceReport:
                shown = [rows[i] for i in chosen]
                files, inventory, pieces, piece_of = _layout(
                    index,
                    names,
                    standing,
                    (list(picked), shown, members, grouping, homes),
                    (lines, described),
                    (cap, more),
                    scores,
                    more_forms,
                )
                pieces = _with_supporting(pieces, piece_of, hidden)
                shorts = {i: names.short(i) for i in [*picked, *(m.container for m in members)]}
                shown_kinds = {k.kind for g in files for s in g.subjects for k in s.links}
                legend = tuple((k, as_text(texts[k])) for k in sorted(shown_kinds) if k in texts)
                left = [row for i, row in enumerate(rows) if i not in set(chosen)]
                return SliceReport(
                    nodes=len({r.id for r in rows} | set(order)),
                    edges=len(rows),
                    warnings=tuple(warnings) + kind_warnings(kinds, held),
                    problems=problems,
                    printed=True,
                    starts=begun,
                    rows=Listing(
                        tuple(
                            replace(
                                r,
                                source=lines.at(r.location),
                                description=described.get(r.id),
                                marks=index.marks(r.id),
                            )
                            for r in shown
                        ),
                        len(rows),
                        len(shown),
                        len(shown) < len(rows),
                    ),
                    left_by_hop=dict(sorted(Counter(r.hop for r in left).items())),
                    left_by_kind=dict(sorted(Counter(r.kind for r in left).items())),
                    kinds=tuple(sorted({r.kind for r in rows})),
                    deeper=deeper,
                    depth=deepest,
                    direction=direction,
                    searched=bool(queries),
                    folded=dict(sorted(folded.items())),
                    notes=tuple(notes),
                    members=tuple(members),
                    files=files,
                    inventory=inventory,
                    shorts=shorts,
                    cuts=cuts,
                    legend=legend if told else (),
                    pieces=pieces,
                    piece_of=piece_of,
                )

            begun = tuple(
                replace(
                    s,
                    row=replace(
                        s.row,
                        source=lines.at(s.row.location),
                        supporting=index.supporting(s.row.id) is not None,
                        marks=index.marks(s.row.id),
                    ),
                )
                for s in picked.values()
            )
            members = [
                replace(
                    m,
                    rows=tuple(
                        replace(
                            r,
                            source=lines.at(r.location),
                            description=described.get(r.id),
                            marks=index.marks(r.id),
                        )
                        for r in m.rows
                    ),
                )
                for m in members
            ]
            taking, cap, more, far_cut, near_cut = list(kept), LINK_NAMES, True, 0, 0
            told = True
            report = assemble(taking, cap, more, (), told)
            budget = BYTE_LIMIT if budgeted else 0
            while budget and len(render_text(report).encode()) > budget:
                far = [i for i in taking if rows[i].hop > 1]
                if told and report.legend:
                    told = False
                elif far:
                    taking.remove(max(far, key=lambda i: (rows[i].hop, i)))
                    far_cut += 1
                elif more:
                    more = False
                elif cap > 1:
                    cap //= 2
                elif (near := _near(report, rows, taking)) is not None:
                    taking.remove(near)
                    near_cut += 1
                else:
                    break
                parts = [] if told else ["legend left out"]
                parts += [f"{far_cut} rows past hop 1 left out"] if far_cut else []
                parts += [] if more else ["the +N more links lines dropped"]
                parts += [f"at most {cap} names per link"] if cap < LINK_NAMES else []
                if near_cut:
                    parts.append(f"{near_cut} hop-1 rows left out, largest piece first")
                cut_note = f"cut to fit {budget} bytes: {', '.join(parts)}; --limit N prints N rows"
                report = assemble(taking, cap, more, (cut_note,), told)
    except HarnessError as error:
        return SliceReport(printed=True, problems=(error.problem(),))
    return report


def _layout(
    index: MapIndex,
    names: Names,
    standing: _Standing,
    piece: tuple[list[str], list[PieceRow], list[Members], Collection[str], Mapping[str, set[str]]],
    reading: tuple[SourceLines, Mapping[str, str]],
    folding: tuple[int, bool],
    scores: Mapping[str, float],
    more_forms: Mapping[str, int],
) -> tuple[
    tuple[FileGroup, ...],
    tuple[tuple[str, tuple[tuple[str, int], ...]], ...],
    tuple[Piece, ...],
    dict[str, int],
]:
    """The piece's mapped nodes grouped by piece and file, the inventory of every node it names
    with its piece number, the pieces, and the piece number of each node.

    A piece is a set of the nodes the output names that edges join; see ``_joined``. Pieces go
    by the summed word score, ``scores``, of their starts, highest first,
    then by the things they name, most first, then by their smallest start id. Inside a piece,
    files go in the order the starts, the rows and the members first reach them; nodes inside a
    file by line. A file's header names the containers its nodes belong to by grouping edges,
    ``homes``. A node's links are its edges to other nodes of the piece, by kind and direction,
    a grouping edge from the node to its container left to the header. An edge between two nodes
    of one file prints only at its ``from`` end.
    ``folding`` gives the most names per link and whether to count the edges the piece leaves
    out. ``more_forms`` counts, by node, the nodes that stand for it past the cap.
    """
    starts, rows, members, grouping, homes = piece
    lines, described = reading
    cap, more = folding
    held = list(dict.fromkeys([*starts, *(i for r in rows for i in (r.parent, r.id))]))
    held += [r.id for m in members for r in m.rows if r.id not in held]
    inside = set(held)
    # Each node the output names, and the node it is printed under.
    named: dict[str, str] = {}
    owner = names.owner

    def link(kind: str, outward: bool, ends: list[str], here: str) -> Link:
        mapped = [e for e in ends if index.nodes[e]["state"] == "mapped"]
        outside = sorted(
            (e for e in ends if e not in mapped), key=lambda e: names.short(e).casefold()
        )
        by_owner: dict[str, list[str]] = {}
        for end in mapped:
            if (home := owner(end)) is not None:
                by_owner.setdefault(home, []).append(end)
        folded = {home: len(v) for home, v in by_owner.items() if len(v) >= OWNER_FOLD}
        loose = sorted(
            (e for e in mapped if owner(e) not in folded), key=lambda e: names.short(e).casefold()
        )
        for end in [*folded, *loose[:cap], *outside[:OUTSIDE_NAMES]]:
            named.setdefault(end, here)
        return Link(
            kind,
            outward,
            tuple(names.short(e) for e in loose[:cap]),
            max(0, len(loose) - cap),
            tuple(sorted((names.short(h), n) for h, n in folded.items())),
            tuple(names.short(e) for e in outside[:OUTSIDE_NAMES]),
            len(outside),
            index.realized(kind, outward),
        )

    found: list[tuple[str | None, Subject]] = []
    for node_id in held:
        node = index.nodes[node_id]
        if node["state"] != "mapped":
            continue
        named.setdefault(node_id, node_id)
        loc = first_location(node)
        ends: dict[tuple[str, bool], list[str]] = {}
        unwalked: Counter[tuple[str, bool]] = Counter()
        for outward, edges in ((True, index.outgoing(node_id)), (False, index.incoming(node_id))):
            for edge in edges:
                far = as_text(edge["to" if outward else "from"])
                kind = as_text(edge["kind"])
                if far == node_id or standing.satellite(far) == node_id:
                    continue
                if outward and kind in grouping:
                    continue
                if far in inside:
                    there = first_location(index.nodes[far])
                    same = there is not None and loc is not None and there["file"] == loc["file"]
                    if not (same and not outward and index.nodes[far]["state"] == "mapped"):
                        ends.setdefault((kind, outward), []).append(far)
                else:
                    unwalked[(kind, outward)] += 1
        found.append(
            (
                loc["file"] if loc else None,
                Subject(
                    node_id,
                    names.short(node_id),
                    as_text(node["type"]),
                    loc["line"] if loc else None,
                    lines.at(place(loc)) if loc else None,
                    described.get(node_id),
                    tuple(
                        link(k, o, sorted(set(v)), node_id)
                        for (k, o), v in sorted(ends.items(), key=lambda p: (p[0][0], not p[0][1]))
                    ),
                    tuple(
                        (k, o, n)
                        for (k, o), n in sorted(
                            unwalked.items(), key=lambda p: (-p[1], p[0][0], not p[0][1])
                        )
                    )
                    if more
                    else (),
                    more_forms.get(node_id, 0),
                    index.marks(node_id),
                ),
            )
        )
    for file, subject in found:
        for container in homes.get(file, ()) if file is not None else ():
            named.setdefault(container, subject.id)
    for start in starts:
        named.setdefault(start, start)
    joined = _joined(index, starts, [*rows, *(r for m in members for r in m.rows)], named, grouping)
    groups: dict[tuple[str, str | None], list[Subject]] = {}
    for file, subject in found:
        groups.setdefault((joined[subject.id], file), []).append(subject)
    things = Counter(joined.values())
    keys = list(dict.fromkeys(joined[s] for s in starts))
    held_by = {key: tuple(s for s in starts if joined[s] == key) for key in keys}
    keys.sort(
        key=lambda k: (
            -round(sum(scores.get(s, 0.0) for s in held_by[k]), WEIGHT_PLACES),
            -things[k],
            min(held_by[k]),
        )
    )
    number = {key: n for n, key in enumerate(keys, 1)}
    files = tuple(
        FileGroup(
            file,
            tuple(
                sorted(names.short(c) for c in (homes.get(file, ()) if file is not None else ()))
            ),
            tuple(sorted(subjects, key=lambda s: (s.line or 0, s.short))),
            number[here],
        )
        for (here, file), subjects in sorted(groups.items(), key=lambda g: number[g[0][0]])
    )
    by_type: dict[str, list[tuple[str, int]]] = {}
    for node_id in named:
        by_type.setdefault(as_text(index.nodes[node_id]["type"]), []).append(
            (names.short(node_id), number[joined[node_id]])
        )
    inventory = tuple(
        (kind, tuple(sorted(by_type[kind], key=lambda p: (p[0].casefold(), p[1]))))
        for kind in sorted(by_type, key=lambda t: (standing.rarity_of(t), t))
    )
    pieces = tuple(Piece(held_by[key], things[key]) for key in keys)
    piece_of = {n: number[k] for n, k in joined.items()}
    # A node a row reached that the output does not name goes to the piece of the node above.
    for row in [*rows, *(r for m in members for r in m.rows)]:
        piece_of.setdefault(row.id, piece_of.get(row.parent, piece_of[row.start]))
    return files, inventory, pieces, piece_of


def _with_supporting(
    pieces: tuple[Piece, ...], piece_of: Mapping[str, int], hidden: Sequence[tuple[str, str, str]]
) -> tuple[Piece, ...]:
    """``pieces`` with the nodes in supporting code each one's starts reached and left out,
    ``hidden`` as (start, node, pattern), counted once a piece."""
    nodes: dict[int, set[str]] = {}
    patterns: dict[int, set[str]] = {}
    for start, node, pattern in hidden:
        number = piece_of[start]
        nodes.setdefault(number, set()).add(node)
        patterns.setdefault(number, set()).add(pattern)
    return tuple(
        replace(p, supporting=len(nodes.get(n, ())), patterns=tuple(sorted(patterns.get(n, ()))))
        for n, p in enumerate(pieces, 1)
    )


def _joined(
    index: MapIndex,
    starts: list[str],
    rows: Sequence[PieceRow],
    named: Mapping[str, str],
    grouping: Collection[str],
) -> dict[str, str]:
    """Each node the output names, mapped to the first start of its piece.

    Two named nodes share a piece when an edge of the map joins them, whatever its kind, but
    for a grouping kind: two members of one container are not joined by it. A set of joined
    nodes that holds no start, such as the members of a container start, joins the piece of the
    start of the row that reached it, else the piece of the node it is printed under, ``named``.
    """
    top = grouping_.joined(index, named, grouping)
    first: dict[str, str] = {}
    for start in starts:
        first.setdefault(top[start], start)
    for row in rows:
        for node in (row.parent, row.id):
            if node in top:
                first.setdefault(top[node], first[top[row.start]])
    for node, under in named.items():
        first.setdefault(top[node], first[top[under]])
    return {n: first[top[n]] for n in named}


def _near(report: SliceReport, rows: list[PieceRow], taking: list[int]) -> int | None:
    """The last row kept of the piece that names the most things, the later piece on a tie,
    or ``None`` when no row is kept."""
    piece_of = report.piece_of or {}
    sizes = sorted(enumerate(report.pieces, 1), key=lambda p: (-p[1].things, -p[0]))
    for number, _ in sizes:
        mine = [i for i in taking if piece_of.get(rows[i].id) == number]
        if mine:
            return max(mine)
    return None


def _members(
    index: MapIndex,
    container: str,
    grouping: Collection[str],
    only: set[str] | None,
    most: int,
    standing: _Standing,
    hidden: list[tuple[str, str, str]] | None = None,
) -> Members | None:
    """The members of ``container`` by its incoming grouping edges, or ``None`` when it has none.

    With ``hidden``, a member in supporting code is left out and added to it as (container,
    member, pattern).

    Types go rarest first; inside a type, the member more other files depend on comes first,
    then the id. Rows are taken one type at a time in turn, up to ``most`` (0 takes them all).
    ``only`` keeps the members of those types.
    """
    if not any(edge["kind"] in grouping for edge in index.incoming(container)):
        return None
    by_type: dict[str, list[tuple[Mapping[str, Any], str]]] = {}
    for edge, member in grouping_.members(index, container, grouping, only):
        pattern = index.supporting(member) if hidden is not None else None
        if pattern is not None and hidden is not None:
            hidden.append((container, member, pattern))
            continue
        by_type.setdefault(as_text(index.nodes[member]["type"]), []).append((edge, member))
    ordered = sorted(by_type, key=lambda t: (standing.rarity(by_type[t][0][1]), t))
    for kind in ordered:
        by_type[kind].sort(key=lambda pair: (-standing.depended(pair[1]), pair[1]))
    rows: list[PieceRow] = []
    depth = max((len(v) for v in by_type.values()), default=0)
    for turn in range(depth):
        for kind in ordered:
            if turn < len(by_type[kind]) and (not most or len(rows) < most):
                link, member = by_type[kind][turn]
                node = index.nodes[member]
                rows.append(
                    PieceRow(
                        container,
                        1,
                        container,
                        as_text(link["kind"]),
                        False,
                        member,
                        kind,
                        as_text(node["state"]),
                        False,
                        where(link, node),
                    )
                )
    counted = {kind: len(by_type[kind]) for kind in ordered}
    return Members(container, sum(counted.values()), counted, tuple(rows))


def _row(index: MapIndex, node_id: str, described: Mapping[str, str]) -> find.FindRow:
    """A start named by its id, as ``find`` shows a row matched by its id."""
    return find.found_row((0, node_id, index.nodes[node_id], None), described)


def _satellite(index: MapIndex, node_id: str) -> str | None:
    """The one other node all of ``node_id``'s edges join it to, when it has two edges or more."""
    edges = index.outgoing(node_id) + index.incoming(node_id)
    others = {e["to"] if e["from"] == node_id else e["from"] for e in edges}
    return others.pop() if len(edges) > 1 and len(others) == 1 and node_id not in others else None


class _Search:
    """``find.search`` over one map, each text, type set and prefix list searched once a run."""

    def __init__(self, index: MapIndex, described: Mapping[str, str]) -> None:
        self._index = index
        self._described = described
        self._found: dict[tuple[str, frozenset[str] | None, tuple[str, ...]], list[find.Match]] = {}

    def __call__(
        self, text: str, wanted: set[str] | None, prefixes: Collection[str]
    ) -> list[find.Match]:
        key = (text, None if wanted is None else frozenset(wanted), tuple(prefixes))
        if key not in self._found:
            self._found[key] = find.search(self._index, text, wanted, prefixes, self._described)
        return self._found[key]


class _Standing:
    """What the map alone says about a node: how many nodes share its type, how many other
    files hold nodes with an edge into it, and the node it is a satellite of. Each is counted
    once per run."""

    def __init__(self, index: MapIndex) -> None:
        self._index = index
        self._types = Counter(as_text(node["type"]) for node in index.nodes.values())
        self._files: dict[str, int] = {}
        self._satellites: dict[str, str | None] = {}

    def satellite(self, node_id: str) -> str | None:
        """``_satellite`` of the node."""
        if node_id not in self._satellites:
            self._satellites[node_id] = _satellite(self._index, node_id)
        return self._satellites[node_id]

    def rarity(self, node_id: str) -> int:
        """How many nodes of the map share ``node_id``'s type; fewer is rarer."""
        return self.rarity_of(as_text(self._index.nodes[node_id]["type"]))

    def rarity_of(self, type_name: str) -> int:
        """How many nodes of the map are of ``type_name``."""
        return self._types[type_name]

    def depended(self, node_id: str) -> int:
        """How many files, other than the node's own, hold a node with an edge into it."""
        if node_id not in self._files:
            nodes = self._index.nodes
            own = {loc["file"] for loc in nodes[node_id]["locations"]}
            files = {
                loc["file"]
                for edge in self._index.incoming(node_id)
                if (loc := first_location(nodes[edge["from"]])) is not None
            }
            self._files[node_id] = len(files - own)
        return self._files[node_id]


def _starts(
    index: MapIndex,
    queries: list[str],
    narrowing: tuple[set[str] | None, Collection[str]],
    described: Mapping[str, str],
    weighed: tuple[Mapping[str, float], Mapping[str, set[str]], list[str]],
    most: int,
    standing: _Standing,
    search: _Search,
    support: bool = False,
) -> dict[str, Start]:
    """Up to ``most`` start nodes that the queries find, in two passes.

    The first pass covers the words: in turn from the rarest word down, it takes the best node
    that holds the word and is not yet taken, until it holds ``WORD_SHARE`` of ``most``, or one
    start per word when that is more. The second fills the rest by score, as follows.

    A query is the whole text or one word. A node's score is the sum of the weights of the words
    it holds in its own name, an attribute or its description, a word weighing the log of the
    map's node count over the nodes it matches, so a rare word outweighs a common one. A start
    of a lower score never comes before one of a higher score. Among equal scores, rarer types
    come first, and at most ``TYPE_STARTS`` of a type, counted over all the starts, are taken
    before the rest of that score; inside a type, a mapped node comes first, then the node more
    other files depend on, then the one whose id the words cover most, then ``find``'s rank,
    then the id. Unless ``support``, a node in supporting code is taken only when every match is.
    """
    wanted, prefixes = narrowing
    scores, owned, rarest = weighed
    said: dict[str, list[tuple[str, str, str | None]]] = {}
    nearest: dict[str, find.Match] = {}
    for query in queries:
        for match in search(query, wanted, prefixes):
            place = _place(match[0])
            said.setdefault(match[1], []).append((query, place, match[3][0] if match[3] else None))
            if match[1] not in nearest or match[0] < nearest[match[1]][0]:
                nearest[match[1]] = match
    if not support:
        nearest = {n: m for n, m in nearest.items() if index.supporting(n) is None} or nearest

    def key(node_id: str) -> tuple[float, int, str, bool, int, Fraction, int, str]:
        node = index.nodes[node_id]
        words = {q for q, _, _ in said[node_id]}
        folded = node_id.casefold()
        share = Fraction(sum(len(w) for w in words if w in folded), len(node_id) or 1)
        return (
            -scores.get(node_id, 0.0),
            standing.rarity(node_id),
            as_text(node["type"]),
            node["state"] != "mapped",
            -standing.depended(node_id),
            -share,
            nearest[node_id][0],
            node_id,
        )

    ranked = sorted(nearest, key=key)
    first = min(most, max(math.ceil(most * WORD_SHARE), len(rarest)))
    order: list[str] = []
    while len(order) < first:
        before = len(order)
        for word in rarest:
            best = next((n for n in ranked if word in owned.get(n, ()) and n not in order), None)
            if best is not None and len(order) < first:
                order.append(best)
        if len(order) == before:
            break
    taken = Counter(as_text(index.nodes[node_id]["type"]) for node_id in order)
    for score in dict.fromkeys(-key(node_id)[0] for node_id in ranked):
        level = [
            node_id
            for node_id in ranked
            if scores.get(node_id, 0.0) == score and node_id not in order
        ]
        spread: list[str] = []
        rest: list[str] = []
        for node_id in level:
            kind = as_text(index.nodes[node_id]["type"])
            (spread if taken[kind] < TYPE_STARTS else rest).append(node_id)
            taken[kind] += 1
        order += spread + rest
    return {
        node_id: Start(find.found_row(nearest[node_id], described), words=tuple(said[node_id]))
        for node_id in order[:most]
    }


def _keep(
    rows: list[PieceRow],
    picked: Mapping[str, Start],
    matched: Mapping[str, set[str]],
    limit: int,
    standing: _Standing,
) -> list[int]:
    """The indexes of the rows the cap keeps, in walk order; a limit of 0 keeps them all.

    Rows are taken best first: full rows before back-references, then a node more starts reach,
    then one reached from starts of more words, then one whose own id, attributes or description
    more words match, then a rarer type, then a node more other files depend on, then the
    nearer hop, then the id. A first pass takes rows in that order while each start holds no
    more than an even share of the cap; a second pass fills the cap with the best rows left.
    Each row brings the rows above it, and a back-reference the full row it points to; a row
    whose rows do not fit is passed over.
    """
    if not limit or len(rows) <= limit:
        return list(range(len(rows)))
    reach: dict[str, set[str]] = {}
    for row in rows:
        reach.setdefault(row.id, set()).add(row.start)
    groups = {
        node_id: {q for s in starts for q in _queries(picked[s])}
        for node_id, starts in reach.items()
    }
    full = {row.id: i for i, row in enumerate(rows) if not row.again}

    def needs(i: int) -> set[int]:
        chain: set[int] = set()
        todo = [i]
        while todo:
            j = todo.pop()
            if j in chain:
                continue
            chain.add(j)
            row = rows[j]
            todo += [full[n] for n in (row.parent, row.id if row.again else None) if n in full]
        return chain

    def rank(i: int) -> tuple[bool, int, int, int, int, int, int, str, int]:
        row = rows[i]
        return (
            row.again,
            -len(reach[row.id]),
            -len(groups[row.id]),
            -len(matched.get(row.id, ())),
            standing.rarity(row.id),
            -standing.depended(row.id),
            row.hop,
            row.id,
            i,
        )

    ranked = sorted(range(len(rows)), key=rank)
    starts = list(dict.fromkeys(row.start for row in rows))
    share = max(1, limit // len(starts))
    kept: set[int] = set()
    taken: Counter[str] = Counter()
    for i in ranked:
        new = needs(i) - kept
        if taken[rows[i].start] + len(new) <= share and len(kept) + len(new) <= limit:
            taken[rows[i].start] += len(new)
            kept |= new
    for i in ranked:
        new = needs(i) - kept
        if len(kept) + len(new) <= limit:
            kept |= new
    return sorted(kept)


def _queries(start: Start) -> set[str]:
    """The words, or the argument, that picked ``start``."""
    return {start.given} if start.given is not None else {q for q, _, _ in start.words}


def _grow(
    index: MapIndex,
    depths: Mapping[str, int],
    direction: str,
    kinds: Collection[str],
    standing: _Standing,
    grouping: Collection[str] = (),
    hidden: list[tuple[str, str, str]] | None = None,
) -> tuple[list[PieceRow], bool, Counter[str], dict[str, int]]:
    """Every row breadth-first, hop by hop across all starts, each start to its own depth in
    ``depths``, whether an edge leads on, and the nodes folded into the node above, counted by
    type.

    Each edge is one row at most. A node first reached is a full row and is followed at the next
    hop; one reached again is a back-reference. A node all of whose edges join it to the node
    above, two edges or more, is folded: it makes no row and costs no hop. Edges go in (kind,
    other end, end) order, so the rows are the same on every run. An edge of a ``grouping``
    kind is followed only from its member to its container: the container is a row once per
    start, marked, and the walk does not go on from it. A start, and a node first reached by an
    edge of a kind that does not realize, brings the nodes that stand for it as rows at its own
    hop, as ``walk`` does; the last value counts those past the cap, by node. With ``hidden``, a
    node in supporting code makes no row and is not followed: it is added to ``hidden`` as
    (start, node, pattern).
    """
    ways = {"out": (("to", index.outgoing),), "in": (("from", index.incoming),)}.get(
        direction, (("to", index.outgoing), ("from", index.incoming))
    )
    starts = list(depths)
    seen = set(starts)
    used: set[tuple[str, str, str]] = set()
    rows: list[PieceRow] = []
    folded: Counter[str] = Counter()
    boxed: set[tuple[str, str]] = set()
    more: dict[str, int] = {}

    def hide(begun: str, node: str) -> bool:
        pattern = index.supporting(node) if hidden is not None else None
        if pattern is not None and hidden is not None:
            hidden.append((begun, node, pattern))
        return pattern is not None

    def stand(begun: str, item: str, hop: int) -> list[str]:
        found, left = index.stand_ins(item, direction == "in")
        if left:
            more[item] = left
        added = []
        for other, edge, via in found:
            if other in seen or hide(begun, other):
                continue
            seen.add(other)
            used.add((edge["from"], edge["kind"], edge["to"]))
            added.append(other)
            node = index.nodes[other]
            rows.append(
                PieceRow(
                    begun,
                    hop,
                    via,
                    as_text(edge["kind"]),
                    edge["from"] == via,
                    other,
                    as_text(node["type"]),
                    as_text(node["state"]),
                    False,
                    where(edge, node),
                )
            )
        return added

    frontiers = {s: [s, *stand(s, s, 0)] for s in starts}

    def edges(item: str) -> list[tuple[Mapping[str, Any], str]]:
        found = [
            (e, end)
            for end, follow in ways
            for e in follow(item)
            if (not kinds or e["kind"] in kinds)
            and (e["from"], e["kind"], e["to"]) not in used
            and not (end == "from" and e["kind"] in grouping)
        ]
        return sorted(found, key=lambda p: (p[0]["kind"], p[0][p[1]], p[1]))

    for hop in range(1, max(depths.values(), default=0) + 1):
        for begun in starts:
            if hop > depths[begun]:
                continue
            reached = []
            for item in frontiers[begun]:
                for edge, end in edges(item):
                    key = (edge["from"], edge["kind"], edge["to"])
                    if key in used:
                        continue
                    target = as_text(edge[end])
                    node = index.nodes[target]
                    if target not in seen and hide(begun, target):
                        continue
                    if target not in seen and standing.satellite(target) == item:
                        seen.add(target)
                        folded[as_text(node["type"])] += 1
                        used.update(
                            (e["from"], e["kind"], e["to"])
                            for e in index.outgoing(target) + index.incoming(target)
                        )
                        continue
                    used.add(key)
                    container = edge["kind"] in grouping
                    if container and (begun, target) in boxed:
                        continue
                    if container:
                        boxed.add((begun, target))
                    again = target in seen
                    rows.append(
                        PieceRow(
                            begun,
                            hop,
                            item,
                            as_text(edge["kind"]),
                            end == "to",
                            target,
                            as_text(node["type"]),
                            as_text(node["state"]),
                            again,
                            where(edge, node),
                            container=container,
                        )
                    )
                    if not again:
                        seen.add(target)
                        if not container:
                            reached.append(target)
                            if edge["kind"] not in index.realizing:
                                reached += stand(begun, target, hop)
            frontiers[begun] = reached
    deeper = any(edges(item) for items in frontiers.values() for item in items)
    return rows, deeper, folded, more


def _why(start: Start) -> str:
    if start.given is not None:
        return f"given as {start.given!r}"
    said = [
        f"{word!r} in {'attribute ' + (name or '') if matched == 'attribute' else matched}"
        for word, matched, name in start.words
    ]
    return "words: " + ", ".join(said)


def _clause(link: Link) -> str:
    """One link as ``kind -> a, b, Owner (3) (+2 more) (+1 outside the project: x)``."""
    arrow = "->" if link.outward else "<-"
    parts = [f"{_escape(name)} ({count})" for name, count in link.owners]
    parts += [_escape(name) for name in link.names]
    head = (
        f"realized by ({_escape(link.kind)}) ->"
        if link.realized
        else f"{_escape(link.kind)} {arrow}"
    )
    text = f"{head} {', '.join(parts)}".rstrip()
    text += f" (+{link.more} more)" if link.more else ""
    if link.outside_count:
        listed = ", ".join(_escape(name) for name in link.outside)
        text += f" (+{link.outside_count} outside the project: {listed})"
    return text


def _file_lines(group: FileGroup, under: str) -> list[str]:
    """A file's header, its path below ``under``, then each of its nodes: line, short name,
    type, source, description, links, and the count of edges the piece leaves out."""
    header = _escape(group.file[len(under) :]) if group.file is not None else "no file"
    if group.containers:
        header += f"  in {', '.join(_escape(c) for c in group.containers)}"
    lines = ["", header]
    for subject in group.subjects:
        line = "" if subject.line is None else subject.line
        lines.append(
            f"  :{line}  {_escape(subject.short)}  {_escape(subject.type)}"
            f"{mark_text(subject.marks)}"
        )
        lines += source_line(subject.source)
        lines += description_line(subject.description)
        lines += [f"      {_clause(link)}" for link in subject.links]
        if subject.more_forms:
            lines.append(f"    {stand_in_line(subject.short, subject.more_forms)}")
        if subject.unwalked:
            total = sum(n for _, _, n in subject.unwalked)
            counted = ", ".join(
                f"{_escape(kind)} {'->' if outward else '<-'} {n}"
                for kind, outward, n in subject.unwalked
            )
            lines.append(
                f"      +{total} more links: {counted}; see periplus slice {_escape(subject.short)}"
            )
    return lines


def _folder(files: Sequence[FileGroup]) -> str:
    """The longest folder, ending in ``/``, that holds every printed file; empty when none."""
    paths = [group.file for group in files if group.file is not None]
    common = os.path.commonprefix(paths) if paths else ""
    return common[: common.rfind("/") + 1]


def _piece_lines(report: SliceReport, shorts: Mapping[str, str], under: str) -> list[str]:
    """Each piece: its header, then its files; after the last of several, the line that says
    no mapped edge joins them as printed, and the command that tests two."""
    lines: list[str] = []
    total = len(report.pieces)
    for number, piece in enumerate(report.pieces, 1):
        starts = ", ".join(_escape(shorts.get(s, s)) for s in piece.starts)
        things = f"{piece.things} thing{'' if piece.things == 1 else 's'}"
        lines += ["", f"piece {number} of {total}: {things}, starts: {starts}"]
        for group in report.files:
            if group.piece == number:
                lines += _file_lines(group, under)
        if piece.supporting:
            patterns = ", ".join(_escape(p) for p in piece.patterns)
            lines += [
                "",
                f"+{piece.supporting} in supporting code ({patterns}): show with --support",
            ]
    if total > 1:
        one, two = (_escape(shorts.get(p.starts[0], p.starts[0])) for p in report.pieces[:2])
        lines += [
            "",
            f"no edge of the map joins these {total} pieces as printed; they may still meet"
            " through nodes not printed, or relate in ways the map does not hold;"
            f" test two with periplus path {one} {two}",
        ]
    return lines


def _member_line(members: Members, short: str) -> str:
    """A container start's member count by type, and the command that lists one type."""
    counted = ", ".join(f"{_escape(t)} {n}" for t, n in members.by_type.items())
    return (
        f"members of {_escape(short)}: {members.total} ({counted});"
        f" list one type: periplus slice {_escape(short)} --type T --limit 0"
    )


def _left_out(report: SliceReport) -> list[str]:
    """The folded nodes, what the row cap left out, by hop and by kind, and the flags that narrow
    or deepen."""
    lines = []
    if report.folded:
        counted = ", ".join(f"{_escape(t)} {n}" for t, n in report.folded.items())
        lines.append(f"folded into the node above, all their edges joining it: {counted}")
    note = footer(report.rows)
    if note is None:
        return lines + ([f"go deeper with --depth {report.depth + 1}"] if report.deeper else [])
    hops = ", ".join(f"{hop}: {n}" for hop, n in (report.left_by_hop or {}).items())
    left = report.left_by_kind or {}
    first = sorted(left, key=lambda k: (-left[k], k))[:FOOTER_KINDS]
    kinds = ", ".join(f"{_escape(k)} {left[k]}" for k in first)
    kinds += f", and {len(left) - len(first)} more kinds" if len(left) > len(first) else ""
    here = sorted(report.kinds, key=lambda k: (-left.get(k, 0), k))
    named = ", ".join(_escape(k) for k in here[:FOOTER_KINDS])
    named += f", and {len(here) - FOOTER_KINDS} more" if len(here) > FOOTER_KINDS else ""
    ways = [f"--kind K (kinds here: {named})"]
    if report.direction == "both":
        ways += ["--direction out", "--direction in"]
    if report.depth > 1:
        ways.append(f"--depth {report.depth - 1}")
    lines += [
        f"{note} rows",
        f"left out by hop: {hops}",
        f"left out by kind: {kinds}",
        f"narrow with {', '.join(ways[:-1])} or {ways[-1]}"
        if len(ways) > 1
        else f"narrow with {ways[0]}",
    ]
    if report.searched:
        lines.append("pick other starts with --type T, --path P or --starts N")
    return [*lines, "show all with --limit 0"]


def _legend_lines(legend: Sequence[tuple[str, str]]) -> list[str]:
    """The description of each kind the piece's links show, within ``LEGEND_BYTES``, then a
    count of the rest."""
    if not legend:
        return []
    lines, size = ["", "legend:"], 0
    for at, (kind, text) in enumerate(legend):
        line = f"  {_escape(kind)}: {_escape(text)}"
        size += len(line.encode()) + 1
        if size > LEGEND_BYTES:
            return [*lines, f"  +{len(legend) - at} more: periplus legend --kind K"]
        lines.append(line)
    return lines


def render_text(report: SliceReport) -> str:
    """The report as lines a person reads. Every outside string goes through ``_escape``."""
    lines = ["periplus slice"]
    if report.printed and not report.problems:
        shorts = report.shorts or {}
        lines += [_escape(note) for note in report.notes]
        if not report.starts:
            lines.append("no matches")
        for start in report.starts:
            short = _escape(shorts.get(start.row.id, start.row.id))
            lines.append(
                f"start {short}  {_escape(start.row.type)}  ({_escape(_why(start))})"
                f"{mark_text(start.row.marks)}"
            )
        lines += [_member_line(m, shorts.get(m.container, m.container)) for m in report.members]
        under = _folder(report.files)
        lines += [f"paths under: {_escape(under)}"] if under else []
        lines += _piece_lines(report, shorts, under)
        if report.inventory:
            count = sum(len(names) for _, names in report.inventory)
            lines += ["", f"inventory: {count} nodes"]
            several = len(report.pieces) > 1
            lines += [
                f"  {_escape(kind)} {len(names)}: "
                + ", ".join(_escape(n) + (f" [{piece}]" if several else "") for n, piece in names)
                for kind, names in report.inventory
            ]
        lines += _left_out(report)
        lines += [_escape(cut) for cut in report.cuts]
        lines += _legend_lines(report.legend)
    if report.out is not None:
        lines.append(f"wrote {_escape(report.out)}: {report.nodes} nodes, {report.edges} edges")
    lines += [f"warning: {_escape(w)}" for w in report.warnings]
    lines += problem_lines(report.problems)
    return "\n".join(lines) + "\n"


def _json_start(start: Start, piece_of: Mapping[str, int]) -> dict[str, Any]:
    words = [{"word": w, "matched": m, "matched_attribute": a} for w, m, a in start.words]
    return {
        **find.json_row(start.row),
        "given": start.given,
        "words": words,
        "piece": piece_of[start.row.id],
    }


def _json_row(row: PieceRow, piece_of: Mapping[str, int]) -> dict[str, Any]:
    return {
        "piece": piece_of[row.id],
        "start": row.start,
        "hop": row.hop,
        "from": row.parent,
        "kind": row.kind,
        "direction": "out" if row.outward else "in",
        "id": row.id,
        "type": row.type,
        "state": row.state,
        "marks": list(row.marks),
        "again": row.again,
        "location": row.location,
        "source": row.source,
        "description": row.description,
        "container": row.container,
    }


def _json_members(members: Members, piece_of: Mapping[str, int]) -> dict[str, Any]:
    return {
        "container": members.container,
        "total": members.total,
        "by_type": dict(members.by_type),
        "rows": [_json_row(row, piece_of) for row in members.rows],
    }


def render_json(report: SliceReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    if report.printed:
        piece_of = report.piece_of or {}
        return as_json(
            {
                "starts": [_json_start(start, piece_of) for start in report.starts],
                "pieces": [
                    {
                        "piece": n,
                        "starts": list(p.starts),
                        "things": p.things,
                        "supporting": p.supporting,
                    }
                    for n, p in enumerate(report.pieces, 1)
                ],
                "rows": payload(report.rows, lambda row: _json_row(row, piece_of)),
                "left_out": {
                    "by_hop": {str(h): n for h, n in (report.left_by_hop or {}).items()},
                    "by_kind": dict(report.left_by_kind or {}),
                },
                "deeper": report.deeper,
                "folded": dict(report.folded or {}),
                "notes": list(report.notes),
                "members": [_json_members(m, piece_of) for m in report.members],
                "depth": report.depth,
                "direction": report.direction,
                "warnings": list(report.warnings),
                "problems": [_json_problem(p) for p in report.problems],
            }
        )
    document = {
        "out": report.out,
        "nodes": report.nodes,
        "edges": report.edges,
        "warnings": list(report.warnings),
        "problems": [_json_problem(p) for p in report.problems],
    }
    return as_json(document)


RENDERERS = {"text": render_text, "json": render_json}
