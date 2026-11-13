"""``periplus slice``: the items around a start set, printed as rows or cut into a map file."""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Collection, Mapping
from dataclasses import dataclass, replace
from fractions import Fraction
from pathlib import Path
from typing import Any

from periplus.engine.emit import counts, hierarchy
from periplus.errors import ExitCode, HarnessError, Problem
from periplus.map import write_document
from periplus.navigate import find
from periplus.navigate.ids import resolve
from periplus.navigate.listing import (
    NONE,
    Listing,
    first_location,
    footer,
    kind_warnings,
    payload,
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
from periplus.navigate.show import node_descriptions
from periplus.navigate.source import SourceLines, description_line, located, source_line, where
from periplus.navigate.walk import walk
from periplus.report import _escape, _json_problem

__all__ = [
    "PRINT_DEPTH",
    "ROW_LIMIT",
    "START_LIMIT",
    "RENDERERS",
    "PieceRow",
    "SliceReport",
    "Start",
    "render_json",
    "render_text",
    "run",
]

#: The most start nodes the words pick in all, unless ``starts`` says otherwise.
START_LIMIT = 8
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
    container end of a grouping edge, which the walk does not go on from.
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


@dataclass(frozen=True, slots=True)
class Members:
    """The members of a start that is a container: how many, how many of each type, rarest type
    first, and the rows shown."""

    container: str
    total: int
    by_type: Mapping[str, int]
    rows: tuple[PieceRow, ...]


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
) -> SliceReport:
    """Write ``ids``, the nodes under each of ``prefixes`` and what they reach to ``out``.

    Without ``out``, print the piece instead: see ``_piece``. ``direction`` is ``out``, ``in`` or
    ``both``. A limit of 0 keeps every item. ``depth`` and ``limit`` of ``None`` take the mode's
    default. ``types`` and ``starts`` narrow words, which only the printed piece takes.
    """
    if out is None:
        return _piece(
            start,
            env,
            ids,
            prefixes,
            direction,
            PRINT_DEPTH if depth is None else depth,
            kinds,
            ROW_LIMIT if limit is None else limit,
            map_path,
            types,
            START_LIMIT if starts is None else starts,
        )
    if types or starts is not None:
        message = "--type and --starts pick start nodes from words, which --out does not take"
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
    depth: int,
    kinds: Collection[str],
    limit: int,
    map_path: Path | None,
    types: Collection[str],
    most: int,
) -> SliceReport:
    """The piece around the start nodes, as rows to print.

    An argument that names a node starts there. The rest is searched as ``find`` searches, as a
    whole and word by word; see ``_starts``. ``types`` and, when there are words, ``prefixes``
    narrow those starts. Without words, each prefix adds the nodes under it.
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
            notes: list[str] = []
            for word in words:
                hits = find.search(index, word, None, (), described)
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
                )
                for node_id, chosen in found.items():
                    picked.setdefault(node_id, chosen)
                lone = found and queries[0] == whole and len(queries) > 1
                if lone and not find.search(index, whole, wanted, narrowed, described):
                    notes.append(f"no node matches {whole!r} as a whole; started from its words")
            elif prefixes:
                for node_id in sorted(_under(document, prefixes)):
                    picked.setdefault(node_id, Start(_row(index, node_id, described)))
            elif not picked:
                message = "give some words, an id or a path prefix"
                return SliceReport(printed=True, problems=(Problem(ExitCode.USAGE, message, {}),))
            order = list(picked)
            grouping = {as_text(k) for k in document.get("grouping_kinds", ())} - set(kinds)
            alone = bool(types) and not queries
            only = find.narrowing(index, types, ())[0] if alone else None
            share = max(1, limit // len(order)) if limit and order else 0
            found_members = (_members(index, s, grouping, only, share, standing) for s in order)
            members = [m for m in found_members if m is not None]
            rows: list[PieceRow] = []
            deeper, folded = False, Counter[str]()
            if not (alone and members):
                rows, deeper, folded = _grow(index, order, direction, depth, set(kinds), grouping)
            left_over = limit - sum(len(m.rows) for m in members) if limit else 0
            kept = (
                []
                if limit and left_over <= 0
                else _keep(rows, picked, matched, left_over, standing)
            )
            held = {edge["kind"] for edge in index.edges}
    except HarnessError as error:
        return SliceReport(printed=True, problems=(error.problem(),))
    lines = SourceLines(start, map_path)
    begun = tuple(
        replace(s, row=replace(s.row, source=lines.at(s.row.location))) for s in picked.values()
    )
    items = tuple(
        replace(rows[i], source=lines.at(rows[i].location), description=described.get(rows[i].id))
        for i in kept
    )
    left = [row for i, row in enumerate(rows) if i not in set(kept)]
    members = [
        replace(
            m,
            rows=tuple(
                replace(r, source=lines.at(r.location), description=described.get(r.id))
                for r in m.rows
            ),
        )
        for m in members
    ]
    return SliceReport(
        nodes=len({r.id for r in rows} | set(order)),
        edges=len(rows),
        warnings=tuple(warnings) + kind_warnings(kinds, held),
        problems=problems,
        printed=True,
        starts=begun,
        rows=Listing(items, len(rows), len(items), len(items) < len(rows)),
        left_by_hop=dict(sorted(Counter(r.hop for r in left).items())),
        left_by_kind=dict(sorted(Counter(r.kind for r in left).items())),
        kinds=tuple(sorted({r.kind for r in rows})),
        deeper=deeper,
        depth=depth,
        direction=direction,
        searched=bool(queries),
        folded=dict(sorted(folded.items())),
        notes=tuple(notes),
        members=tuple(members),
    )


def _members(
    index: MapIndex,
    container: str,
    grouping: Collection[str],
    only: set[str] | None,
    most: int,
    standing: _Standing,
) -> Members | None:
    """The members of ``container`` by its incoming grouping edges, or ``None`` when it has none.

    Types go rarest first; inside a type, the member more other files depend on comes first,
    then the id. Rows are taken one type at a time in turn, up to ``most`` (0 takes them all).
    ``only`` keeps the members of those types.
    """
    if not any(edge["kind"] in grouping for edge in index.incoming(container)):
        return None
    by_type: dict[str, list[tuple[Mapping[str, Any], str]]] = {}
    for edge in index.incoming(container):
        member = as_text(edge["from"])
        kind = as_text(index.nodes[member]["type"])
        if edge["kind"] in grouping and (only is None or kind in only):
            by_type.setdefault(kind, []).append((edge, member))
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


class _Standing:
    """What the map alone says about a node: how many nodes share its type, and how many other
    files hold nodes with an edge into it. Each is counted once per run."""

    def __init__(self, index: MapIndex) -> None:
        self._index = index
        self._types = Counter(as_text(node["type"]) for node in index.nodes.values())
        self._files: dict[str, int] = {}

    def rarity(self, node_id: str) -> int:
        """How many nodes of the map share ``node_id``'s type; fewer is rarer."""
        return self._types[as_text(self._index.nodes[node_id]["type"])]

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
    then the id.
    """
    wanted, prefixes = narrowing
    scores, owned, rarest = weighed
    said: dict[str, list[tuple[str, str, str | None]]] = {}
    nearest: dict[str, find.Match] = {}
    for query in queries:
        for match in find.search(index, query, wanted, prefixes, described):
            place = _place(match[0])
            said.setdefault(match[1], []).append((query, place, match[3][0] if match[3] else None))
            if match[1] not in nearest or match[0] < nearest[match[1]][0]:
                nearest[match[1]] = match

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
    starts: list[str],
    direction: str,
    depth: int,
    kinds: Collection[str],
    grouping: Collection[str] = (),
) -> tuple[list[PieceRow], bool, Counter[str]]:
    """Every row breadth-first, hop by hop across all starts, whether an edge leads on, and the
    nodes folded into the node above, counted by type.

    Each edge is one row at most. A node first reached is a full row and is followed at the next
    hop; one reached again is a back-reference. A node all of whose edges join it to the node
    above, two edges or more, is folded: it makes no row and costs no hop. Edges go in (kind,
    other end, end) order, so the rows are the same on every run. An edge of a ``grouping``
    kind is followed only from its member to its container: the container is a row once per
    start, marked, and the walk does not go on from it.
    """
    ways = {"out": (("to", index.outgoing),), "in": (("from", index.incoming),)}.get(
        direction, (("to", index.outgoing), ("from", index.incoming))
    )
    seen = set(starts)
    used: set[tuple[str, str, str]] = set()
    frontiers = {s: [s] for s in starts}
    rows: list[PieceRow] = []
    folded: Counter[str] = Counter()
    boxed: set[tuple[str, str]] = set()

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

    for hop in range(1, depth + 1):
        for begun in starts:
            reached = []
            for item in frontiers[begun]:
                for edge, end in edges(item):
                    key = (edge["from"], edge["kind"], edge["to"])
                    if key in used:
                        continue
                    target = as_text(edge[end])
                    node = index.nodes[target]
                    if target not in seen and _satellite(index, target) == item:
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
            frontiers[begun] = reached
    deeper = any(edges(item) for items in frontiers.values() for item in items)
    return rows, deeper, folded


def _why(start: Start) -> str:
    if start.given is not None:
        return f"given as {start.given!r}"
    said = [
        f"{word!r} in {'attribute ' + (name or '') if matched == 'attribute' else matched}"
        for word, matched, name in start.words
    ]
    return "words: " + ", ".join(said)


def _tree(report: SliceReport) -> list[str]:
    """The rows under each start, each row indented under the node it was reached from."""
    below: dict[str, list[PieceRow]] = {}
    for row in report.rows.items:
        below.setdefault(row.parent, []).append(row)
    lines: list[str] = []
    files = {start.row.id: _file(start.row.location) for start in report.starts}

    def at(row: PieceRow) -> str:
        """The row's ``file:line``, or ``:line`` when the file is that of the node above."""
        place = located(row.location)
        file = _file(row.location)
        return place[len(file) :] if file is not None and file == files.get(row.parent) else place

    def grow(node_id: str) -> None:
        for row in below.get(node_id, ()):
            pad = "  " * row.hop
            arrow = f"--{_escape(row.kind)}-->" if row.outward else f"<--{_escape(row.kind)}--"
            if row.again:
                lines.append(
                    f"{pad}{row.hop} {arrow} {_escape(row.id)}  (again)  {_escape(at(row))}"
                )
                continue
            files[row.id] = _file(row.location)
            marker = (
                "  (container; list its members with periplus slice ID)" if row.container else ""
            )
            lines.append(
                f"{pad}{row.hop} {arrow} {_escape(row.id)}  {_escape(row.type)}"
                f"  {_escape(row.state)}  {_escape(at(row))}{marker}"
            )
            lines.extend(pad + line for line in source_line(row.source))
            lines.extend(pad + line for line in description_line(row.description))
            grow(row.id)

    for start in report.starts:
        if start.row.id in below:
            lines += ["", f"around {_escape(start.row.id)}"]
            grow(start.row.id)
    return lines


def _file(location: str | None) -> str | None:
    """The file of a ``file:line`` location, or ``None`` when there is none."""
    return None if location is None else location.rpartition(":")[0]


def _member_lines(members: Members) -> list[str]:
    """A container's members under its type, each type with its count, then how to list one."""
    lines = ["", f"members of {_escape(members.container)}: {members.total}"]
    for kind, count in members.by_type.items():
        lines.append(f"  {_escape(kind)} {count}")
        for row in (r for r in members.rows if r.type == kind):
            lines.append(
                f"    <--{_escape(row.kind)}-- {_escape(row.id)}  {_escape(row.type)}"
                f"  {_escape(row.state)}  {_escape(located(row.location))}"
            )
            lines.extend("  " + line for line in source_line(row.source))
            lines.extend("  " + line for line in description_line(row.description))
    command = f"periplus slice {_escape(members.container)} --type T --limit 0"
    return [*lines, f"list one type in full: {command}"]


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
    kinds = ", ".join(f"{_escape(k)} {n}" for k, n in (report.left_by_kind or {}).items())
    ways = [f"--kind K (kinds here: {', '.join(_escape(k) for k in report.kinds)})"]
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


def render_text(report: SliceReport) -> str:
    """The report as lines a person reads. Every outside string goes through ``_escape``."""
    lines = ["periplus slice"]
    if report.printed and not report.problems:
        lines += [_escape(note) for note in report.notes]
        if not report.starts:
            lines.append("no matches")
        for number, start in enumerate(report.starts, 1):
            lines.append(f"start {number} ({_escape(_why(start))})")
            lines += find.row_lines(start.row)
        for members in report.members:
            lines += _member_lines(members)
        lines += _tree(report)
        lines += _left_out(report)
    if report.out is not None:
        lines.append(f"wrote {_escape(report.out)}: {report.nodes} nodes, {report.edges} edges")
    lines += [f"warning: {_escape(w)}" for w in report.warnings]
    lines += problem_lines(report.problems)
    return "\n".join(lines) + "\n"


def _json_start(start: Start) -> dict[str, Any]:
    words = [{"word": w, "matched": m, "matched_attribute": a} for w, m, a in start.words]
    return {**find.json_row(start.row), "given": start.given, "words": words}


def _json_row(row: PieceRow) -> dict[str, Any]:
    return {
        "start": row.start,
        "hop": row.hop,
        "from": row.parent,
        "kind": row.kind,
        "direction": "out" if row.outward else "in",
        "id": row.id,
        "type": row.type,
        "state": row.state,
        "again": row.again,
        "location": row.location,
        "source": row.source,
        "description": row.description,
        "container": row.container,
    }


def _json_members(members: Members) -> dict[str, Any]:
    return {
        "container": members.container,
        "total": members.total,
        "by_type": dict(members.by_type),
        "rows": [_json_row(row) for row in members.rows],
    }


def render_json(report: SliceReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    if report.printed:
        return as_json(
            {
                "starts": [_json_start(start) for start in report.starts],
                "rows": payload(report.rows, _json_row),
                "left_out": {
                    "by_hop": {str(h): n for h, n in (report.left_by_hop or {}).items()},
                    "by_kind": dict(report.left_by_kind or {}),
                },
                "deeper": report.deeper,
                "folded": dict(report.folded or {}),
                "notes": list(report.notes),
                "members": [_json_members(m) for m in report.members],
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
