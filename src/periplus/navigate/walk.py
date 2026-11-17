"""``periplus neighbors`` and ``periplus affected``: the items reached along edges."""

from __future__ import annotations

import shlex
from collections import Counter, defaultdict
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.navigate.ids import resolve
from periplus.navigate.listing import (
    NONE,
    Listing,
    cut,
    footer,
    kind_warnings,
    mark_text,
    payload,
    problem_lines,
)
from periplus.navigate.mapfile import (
    STAND_INS,
    MapIndex,
    as_json,
    as_text,
    load_map,
    map_flag,
    reading_fields,
)
from periplus.navigate.names import Names
from periplus.navigate.show import node_descriptions
from periplus.navigate.source import (
    SourceLines,
    description_line,
    located,
    places,
    source_line,
    where,
)
from periplus.report import _escape, _json_problem, amount

__all__ = [
    "BUDGET",
    "HUB",
    "PIPED",
    "RENDERERS",
    "CauseReport",
    "CauseRow",
    "CauseWalk",
    "WalkReport",
    "WalkRow",
    "cause_report",
    "cause_walk",
    "head_line",
    "listed",
    "render_json",
    "render_text",
    "run",
    "run_cause",
    "stand_in_line",
    "start_args",
    "summary",
    "ways",
]


@dataclass(frozen=True, slots=True)
class WalkRow:
    """One item reached: its id, type and state, the depth, and the edge kind and end it came by.

    ``location`` is where that edge is written, or the item's own place when the edge has none,
    and ``source`` the line of code there. ``description`` is the item's descriptions entry.
    ``stands_for`` marks an item added because it stands for ``via`` across a realizing edge,
    at ``via``'s depth: a form of a declaration, or with ``in`` the declaration of a form.
    ``supporting`` marks an item in supporting code, and ``marks`` holds its mark texts.
    """

    id: str
    type: str
    state: str
    depth: int
    kind: str
    via: str
    location: str | None = None
    source: str | None = None
    description: str | None = None
    stands_for: bool = False
    supporting: bool = False
    marks: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WalkReport:
    """The items reached from ``start``, as a ``Listing`` of rows, with warnings and problems.

    ``more`` counts, for each node, the nodes that stand for it past ``STAND_INS``."""

    start: str = ""
    direction: str = "out"
    rows: Listing[WalkRow] = NONE
    warnings: tuple[str, ...] = ()
    problems: tuple[Problem, ...] = ()
    more: tuple[tuple[str, int], ...] = ()
    map_path: Path | None = None

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def walk(
    index: MapIndex,
    start: str,
    direction: str,
    depth: int,
    kinds: Collection[str],
    more: dict[str, int] | None = None,
) -> list[WalkRow]:
    """Breadth-first rows, each item once at its nearest depth with the first edge that reached it,
    along edges (``direction`` ``out``) or against them (``in``).

    A layer's items are expanded in id order and each item's edges in (kind, other end) order, so
    the edge that wins a tie is the same on every run. The start and each item reached are
    followed by the nodes that stand for them (``MapIndex.stand_ins``) at their own depth, whatever
    ``kinds`` says, but for an item reached along a realizing edge: the other forms of a
    declaration reached from one of them are siblings, not the code behind it. ``more`` gathers
    the count past the cap by node.
    """
    ways = {"out": (("to", index.outgoing),), "in": (("from", index.incoming),)}[direction]
    seen = {start}
    rows: list[WalkRow] = []

    def stand(item: str, level: int) -> list[str]:
        found, left = index.stand_ins(item, direction == "in")
        if left and more is not None:
            more[item] = left
        added = []
        for other, edge, via in found:
            if other in seen:
                continue
            seen.add(other)
            added.append(other)
            node = index.nodes[other]
            rows.append(
                WalkRow(
                    other,
                    as_text(node["type"]),
                    as_text(node["state"]),
                    level,
                    as_text(edge["kind"]),
                    via,
                    where(edge, node),
                    stands_for=True,
                )
            )
        return added

    frontier = [start, *stand(start, 0)]
    for level in range(1, depth + 1):
        reached: list[str] = []
        for item in sorted(frontier):
            edges = [
                (e, end)
                for end, follow in ways
                for e in follow(item)
                if not kinds or e["kind"] in kinds
            ]
            for edge, end in sorted(edges, key=lambda p: (p[0]["kind"], p[0][p[1]])):
                target = edge[end]
                if target in seen:
                    continue
                seen.add(target)
                reached.append(target)
                # Indexed, not index.node: a dangling end is a damaged map, not an unknown id.
                node = index.nodes[target]
                rows.append(
                    WalkRow(
                        as_text(target),
                        as_text(node["type"]),
                        as_text(node["state"]),
                        level,
                        as_text(edge["kind"]),
                        as_text(edge["from" if end == "to" else "to"]),
                        where(edge, node),
                    )
                )
                if edge["kind"] not in index.realizing:
                    reached += stand(as_text(target), level)
        frontier = reached
        if not frontier:
            break
    return sorted(rows, key=lambda r: (r.depth, r.id))


def run(
    start: Path,
    env: Mapping[str, str],
    node_id: str,
    direction: str,
    depth: int | None,
    kinds: Collection[str],
    limit: int,
    map_path: Path | None,
) -> WalkReport:
    """Walk from ``node_id`` along edges (``out``) or against them (``in``), ``depth`` levels, or
    to the end when ``depth`` is ``None``."""
    try:
        index = load_map(start, env, map_path)
    except HarnessError as error:
        return WalkReport(direction=direction, problems=(error.problem(),))
    return _raw(start, index, node_id, direction, depth, kinds, limit, map_path)


def _raw(
    start: Path,
    index: MapIndex,
    node_id: str,
    direction: str,
    depth: int | None,
    kinds: Collection[str],
    limit: int,
    map_path: Path | None,
) -> WalkReport:
    """``run`` on a map already loaded."""
    try:
        described, problems = node_descriptions(start, map_path)
        with reading_fields(start, map_path):
            node_id, resolved = resolve(index, node_id)
            more: dict[str, int] = {}
            levels = len(index.nodes) if depth is None else depth
            walked = walk(index, node_id, direction, levels, set(kinds), more)
            rows = [
                replace(r, supporting=index.supporting(r.id) is not None, marks=index.marks(r.id))
                for r in walked
            ]
            # Supporting code after the rest, each part by depth and id.
            rows.sort(key=lambda row: row.supporting)
            held = {edge["kind"] for edge in index.edges}
    except HarnessError as error:
        return WalkReport(direction=direction, problems=(error.problem(),))
    shown = cut(rows, limit)
    lines = SourceLines(start, map_path)
    items = tuple(
        replace(row, source=lines.at(row.location), description=described.get(row.id))
        for row in shown.items
    )
    shown = replace(shown, items=items)
    return WalkReport(
        node_id,
        direction,
        shown,
        resolved + kind_warnings(kinds, held),
        problems,
        tuple(sorted(more.items())),
        map_path,
    )


def render_text(report: WalkReport | CauseReport) -> str:
    """The report as lines a person reads. Every outside string goes through ``_escape``."""
    if isinstance(report, CauseReport):
        return _cause_text(report)
    verb = "neighbors" if report.direction == "out" else "affected"
    lines = [f"periplus {verb} {_escape(report.start)}" if report.start else f"periplus {verb}"]
    if report.start:
        lines.append(amount(report.rows.total, "item"))
    # An affected row's edge points to the item the walk came from.
    toward = "from" if report.direction == "out" else "to"
    supporting = False
    for row in report.rows.items:
        if row.supporting and not supporting:
            supporting = True
            lines.append("  in supporting code:")
        how = f"via {_escape(row.kind)} {toward} {_escape(row.via)}"
        if row.stands_for:
            relation = "realized by" if report.direction == "in" else "realizes"
            how = f"{relation} {_escape(row.via)} by {_escape(row.kind)}"
        lines.append(
            f"  {row.depth}  {_escape(row.id)}  {_escape(row.type)}"
            f"  {_escape(row.state)}  {how}  {_escape(located(row.location))}"
            f"{mark_text(row.marks)}"
        )
        lines += source_line(row.source)
        lines += description_line(row.description)
    on = _escape(map_flag(report.map_path))
    lines += [stand_in_line(node, n) + on for node, n in report.more]
    note = footer(report.rows)
    if note:
        lines.append(note)
    lines += [f"warning: {_escape(w)}" for w in report.warnings]
    lines += problem_lines(report.problems)
    return "\n".join(lines) + "\n"


def stand_in_line(node: str, count: int) -> str:
    """The line that counts the nodes standing for ``node`` past the cap."""
    name = _escape(node)
    return f"  +{count} more stand for {name}, past the first {STAND_INS}; see periplus show {name}"


def _json_row(row: WalkRow) -> dict[str, Any]:
    return {
        "stands_for": row.stands_for,
        "supporting": row.supporting,
        "marks": list(row.marks),
        "id": row.id,
        "type": row.type,
        "state": row.state,
        "depth": row.depth,
        "kind": row.kind,
        "via": row.via,
        "location": row.location,
        "source": row.source,
        "description": row.description,
    }


def render_json(report: WalkReport | CauseReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    if isinstance(report, CauseReport):
        return as_json(_cause_json(report))
    document = {
        "start": report.start,
        "direction": report.direction,
        "rows": payload(report.rows, _json_row),
        "warnings": list(report.warnings),
        "problems": [_json_problem(p) for p in report.problems],
    }
    return as_json(document)


#: A node the walk by cause would follow more edges from than this is listed but not walked from.
HUB = 40
#: About how many characters the text of a walk by cause may hold before far hops become counts.
BUDGET = 20_000
#: The line a walk on a map without cause lists adds.
NO_CAUSES = "the map declares no cause directions; walked by raw direction, as --raw does"
#: The most starts a first line names; past them it counts the rest.
STARTS_NAMED = 3
#: The share of the things reached within these hops that ``summary`` prints.
SHARES = (2, 3, 5)
#: What a suggested command that reads its ids with ``-`` adds after it.
PIPED = " (with the same ids piped in)"


def start_args(starts: Sequence[str], piped: bool, note: str = PIPED) -> tuple[list[str], str]:
    """The starts a suggested command names, and what follows the command: the ids themselves, or
    ``-`` and ``note`` when they came from standard input or are more than ``STARTS_NAMED``."""
    if piped or len(starts) > STARTS_NAMED:
        return ["-"], note
    return list(starts), ""


@dataclass(frozen=True, slots=True)
class CauseRow:
    """One thing a walk by cause reached, ``hop`` edges from the starts, by an edge of ``kind``
    from ``via``; ``backward`` when that edge was followed from its to end to its from end.

    ``location`` is where that edge is written, else the thing's own place. ``hub`` is the fan
    of a thing the walk listed and did not walk from. ``touch`` marks a thing a reached node only
    points at, one hop out. A start is a row at hop 0 with the kind ``start``. ``only`` marks a
    thing ``periplus only`` returns, which ``periplus reach`` tags.
    """

    hop: int
    id: str
    type: str
    state: str
    kind: str
    backward: bool
    via: str
    location: str | None
    hub: int | None = None
    touch: bool = False
    supporting: bool = False
    marks: tuple[str, ...] = ()
    only: bool = False


@dataclass(frozen=True, slots=True)
class CauseWalk:
    """What a walk by cause reached, by hop and id, and the kinds it followed undeclared."""

    rows: tuple[CauseRow, ...]
    undeclared: tuple[str, ...]


def _tie(pair: tuple[dict[str, Any], str]) -> tuple[Any, Any]:
    """The order a node's edges are followed in: by kind, then by the end they lead to."""
    return (pair[0]["kind"], pair[0][pair[1]])


def ways(
    index: MapIndex, item: str, off: bool, kinds: Collection[str], touch: bool = False
) -> list[tuple[dict[str, Any], str]]:
    """The edges a walk by cause follows from ``item``, each with the end it leads to, in tie order.

    Walking ``off`` (what ``item`` sets off) follows a ``from`` kind forward and a ``to`` kind
    backward; walking ``by`` (what sets it off) the reverse. A kind under no cause list goes by its
    raw direction: forward ``off``, backward ``by``. ``none`` and ``touch`` kinds are never
    followed; ``touch`` gives the touching edges instead, forward ``off`` and backward ``by``.
    """
    pairs: list[tuple[dict[str, Any], str]]
    if touch:
        edges = index.outgoing(item) if off else index.incoming(item)
        pairs = [(e, "to" if off else "from") for e in edges if index.cause(e["kind"]) == "touch"]
    else:
        ahead, behind = ("from", "to") if off else ("to", "from")
        pairs = [
            (e, "to")
            for e in index.outgoing(item)
            if (cause := index.cause(e["kind"])) == ahead or (cause is None and off)
        ]
        pairs += [
            (e, "from")
            for e in index.incoming(item)
            if (cause := index.cause(e["kind"])) == behind or (cause is None and not off)
        ]
    return sorted([p for p in pairs if not kinds or p[0]["kind"] in kinds], key=_tie)


def cause_walk(
    index: MapIndex,
    starts: Collection[str],
    toward: str,
    kinds: Collection[str] = (),
    hub: int = HUB,
    through: Collection[str] = (),
) -> CauseWalk:
    """Breadth first from ``starts`` to the end, ``toward`` ``off`` or ``by``, each node once at
    its nearest hop with the first edge that reached it, in ``walk``'s tie order.

    A reached node with more than ``hub`` edges to follow (``hub`` 0: no limit) is listed with that
    fan and not walked from, unless ``through`` names it. A start is always walked from.
    """
    off = toward == "off"
    fans: dict[str, list[tuple[dict[str, Any], str]]] = {}

    def follow(item: str) -> list[tuple[dict[str, Any], str]]:
        if item not in fans:
            fans[item] = ways(index, item, off, kinds)
        return fans[item]

    seen = set(starts)
    rows: list[CauseRow] = []
    frontier = sorted(seen)
    hop = 0
    while frontier:
        hop += 1
        reached: list[str] = []
        for item in frontier:
            for edge, end in follow(item):
                target = as_text(edge[end])
                if target in seen:
                    continue
                seen.add(target)
                fan = len(follow(target))
                stop = 0 < hub < fan and target not in through
                node = index.nodes[target]
                rows.append(
                    CauseRow(
                        hop,
                        target,
                        as_text(node["type"]),
                        as_text(node["state"]),
                        as_text(edge["kind"]),
                        end == "from",
                        item,
                        where(edge, node),
                        fan if stop else None,
                    )
                )
                if not stop:
                    reached.append(target)
        frontier = sorted(reached)
    undeclared = sorted({r.kind for r in rows if index.cause(r.kind) is None})
    return CauseWalk(tuple(sorted(rows, key=lambda r: (r.hop, r.id))), tuple(undeclared))


def head_line(command: str, starts: Sequence[str]) -> str:
    """``periplus COMMAND`` and the starts, the first ``STARTS_NAMED`` by id and the rest counted,
    so ids read from standard input do not fill the line."""
    named = [_escape(s) for s in starts[:STARTS_NAMED]]
    left = len(starts) - STARTS_NAMED
    return " ".join(["periplus", command, *named, *([f"+{left} more"] if left > 0 else [])])


def head(index: MapIndex, node_id: str) -> CauseRow:
    """A start as the hop 0 row of a walk by cause."""
    node = index.nodes[node_id]
    return CauseRow(
        0,
        node_id,
        as_text(node["type"]),
        as_text(node["state"]),
        "start",
        False,
        "",
        where(None, node),
    )


def marked(index: MapIndex, row: CauseRow) -> CauseRow:
    """``row`` with its node's marks and whether it is supporting code."""
    return replace(row, supporting=index.supporting(row.id) is not None, marks=index.marks(row.id))


def summary(label: str, rows: Sequence[CauseRow], shares: bool) -> str:
    """One direction of a walk by cause in a line: hops to the end, things reached, the share
    within each of ``SHARES`` hops that the walk goes past when ``shares``, and the hubs."""
    last = max((r.hop for r in rows), default=0)
    line = f"{label:<12}{last:>3} {'hop' if last == 1 else 'hops'}, {amount(len(rows), 'thing')}"
    within = [
        f"{100 * sum(r.hop <= k for r in rows) // len(rows)}% within {k}"
        for k in SHARES
        if shares and last > k
    ]
    hubs = [_escape(r.id) for r in rows if r.hub is not None]
    named = ", ".join(hubs[:3]) + (f", +{len(hubs) - 3}" if len(hubs) > 3 else "")
    stopped = f"{amount(len(hubs), 'hub')} stopped" + (f" ({named})" if hubs else "")
    return "; ".join([line, *([", ".join(within)] if within else []), stopped])


@dataclass(frozen=True, slots=True)
class CauseReport:
    """A walk by cause for ``neighbors`` (``toward`` ``off``) or ``affected`` (``by``).

    ``walked`` holds every thing to the end of the walk, ``depth`` how many hops of it to show
    (``None``: all), ``touching`` the touching rows of the starts and the rows within ``depth``,
    ``limit`` the text budget in characters (0: none) and ``again`` the command that shows all,
    which the text follows with ``again_note``. ``names`` holds the short name a row prints for
    each id; ``None`` prints full ids and paths.
    """

    command: str
    toward: str = "off"
    starts: tuple[CauseRow, ...] = ()
    walked: tuple[CauseRow, ...] = ()
    touching: tuple[CauseRow, ...] = ()
    depth: int | None = 1
    limit: int = BUDGET
    again: str = ""
    undeclared: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    problems: tuple[Problem, ...] = ()
    names: Mapping[str, str] | None = None
    again_note: str = ""

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def run_cause(
    start: Path,
    env: Mapping[str, str],
    ids: Sequence[str],
    toward: str,
    depth: int | None,
    kinds: Collection[str],
    limit: int | None,
    map_path: Path | None,
    hub: int = HUB,
    through: Sequence[str] = (),
    touch: bool = False,
    full: bool = False,
    piped: bool = False,
) -> CauseReport | WalkReport:
    """Walk by cause from ``ids``, ``toward`` ``off`` or ``by``; show ``depth`` hops (``None``:
    all) in at most ``limit`` characters (``None``: ``BUDGET``; 0: no limit). Rows print short
    names, or with ``full`` full ids. ``piped`` says the ids came from standard input.

    On a map with no cause list the walk is ``run``'s, from one id, with ``limit`` rows (``None``:
    50), and a warning says so.
    """
    command = "neighbors" if toward == "off" else "affected"
    try:
        index = load_map(start, env, map_path)
    except HarnessError as error:
        return CauseReport(command, toward, problems=(error.problem(),))
    if not index.declares_causes:
        if len(ids) != 1:
            problem = Problem(
                ExitCode.USAGE,
                f"{NO_CAUSES}, which walks from one id; give one",
                {"ids": list(ids)},
            )
            return CauseReport(command, toward, problems=(problem,))
        direction = "out" if toward == "off" else "in"
        rows = 50 if limit is None else limit
        old = _raw(start, index, ids[0], direction, depth, kinds, rows, map_path)
        return replace(old, warnings=(*old.warnings, NO_CAUSES)) if old.start else old
    return cause_report(
        start, index, ids, toward, depth, kinds, limit, map_path, hub, through, touch, full, piped
    )


def cause_report(
    start: Path,
    index: MapIndex,
    ids: Sequence[str],
    toward: str,
    depth: int | None,
    kinds: Collection[str],
    limit: int | None,
    map_path: Path | None,
    hub: int = HUB,
    through: Sequence[str] = (),
    touch: bool = False,
    full: bool = False,
    piped: bool = False,
) -> CauseReport:
    """``run_cause``'s walk by cause on a map already loaded, whether or not it lists causes."""
    command = "neighbors" if toward == "off" else "affected"
    try:
        with reading_fields(start, map_path):
            notes: list[str] = []
            starts: list[str] = []
            passes: list[str] = []
            for text, into in [*((t, starts) for t in ids), *((t, passes) for t in through)]:
                found, note = resolve(index, text)
                into.append(found)
                notes += note
            starts = list(dict.fromkeys(starts))
            walked = cause_walk(index, starts, toward, set(kinds), hub, passes)
            reached = tuple(marked(index, r) for r in walked.rows)
            heads = tuple(marked(index, head(index, s)) for s in starts)
            touched = (
                _touching(index, heads, reached, toward, depth, set(kinds)) if touch else ()
            )
            held = {edge["kind"] for edge in index.edges}
            names = None if full else Names(index)
            shorts = (
                {r.id: names.short(r.id) for r in (*heads, *reached, *touched)}
                if names is not None
                else None
            )
            asked = [
                f"the kind {kind!r} is listed under cause {index.cause(kind)}, which the walk by "
                f"cause does not follow; --raw follows it"
                for kind in sorted(set(kinds) & held)
                if index.cause(kind) in ("none", "touch")
            ]
    except HarnessError as error:
        return CauseReport(command, toward, problems=(error.problem(),))
    named, piped_note = start_args(starts, piped)
    again = ["periplus", command, *named, "--depth", "all", "--limit", "0"]
    again += [f for kind in kinds for f in ("--kind", kind)]
    again += ["--hub", str(hub)] if hub != HUB else []
    again += [f for item in passes for f in ("--through", item)]
    again += ["--touch"] if touch else []
    again += ["--full"] if full else []
    again += ["--map", str(map_path)] if map_path is not None else []
    return CauseReport(
        command,
        toward,
        heads,
        reached,
        touched,
        depth,
        BUDGET if limit is None else limit,
        " ".join(shlex.quote(part) for part in again),
        walked.undeclared,
        (*notes, *kind_warnings(kinds, held), *asked),
        names=shorts,
        again_note=piped_note,
    )


def _touching(
    index: MapIndex,
    heads: Sequence[CauseRow],
    rows: Sequence[CauseRow],
    toward: str,
    depth: int | None,
    kinds: Collection[str],
) -> tuple[CauseRow, ...]:
    """The things the starts and the rows within ``depth`` touch, one hop out, each once, none
    the walk reached."""
    seen = {r.id for r in (*heads, *rows)}
    found: list[CauseRow] = []
    for at in [*heads, *(r for r in rows if r.hub is None and (depth is None or r.hop <= depth))]:
        for edge, end in ways(index, at.id, toward == "off", kinds, touch=True):
            target = as_text(edge[end])
            if target in seen:
                continue
            seen.add(target)
            node = index.nodes[target]
            row = CauseRow(
                at.hop + 1,
                target,
                as_text(node["type"]),
                as_text(node["state"]),
                as_text(edge["kind"]),
                end == "from",
                at.id,
                where(edge, node),
                touch=True,
            )
            found.append(marked(index, row))
    return tuple(found)


def _row_text(row: CauseRow, name: str, place: str) -> str:
    """A tree row: indent by hop, name, type, state, kind (``(rev)`` when followed backward),
    place, marks, then ``[supporting code]``, ``[hub: ...]`` or ``[touch]``."""
    tail = "  [supporting code]" if row.supporting else ""
    tail += f"  [hub: {row.hub} links not walked]" if row.hub is not None else ""
    tail += "  [touch]" if row.touch else ""
    tail += "  [only]" if row.only else ""
    return (
        f"{'  ' * row.hop}{_escape(name)}  {_escape(row.type)}  {_escape(row.state)}"
        f"  {_escape(row.kind)}{' (rev)' if row.backward else ''}  {_escape(place)}"
        f"{mark_text(row.marks)}{tail}"
    )


def _tree(report: CauseReport, hops: int) -> list[str]:
    """The starts, each with what it reached within ``hops`` under it, child under parent."""
    under: dict[str, list[CauseRow]] = defaultdict(list)
    for row in report.walked:
        if row.hop <= hops:
            under[row.via].append(row)
    for row in report.touching:
        if row.hop <= hops + 1:
            under[row.via].append(row)
    rows: list[CauseRow] = []

    def emit(row: CauseRow) -> None:
        rows.append(row)
        for child in sorted(under[row.id], key=lambda r: (r.touch, r.kind, r.id)):
            if child.touch:
                rows.append(child)
            else:
                emit(child)

    for start in report.starts:
        emit(start)
    if report.names is None:
        return [_row_text(r, r.id, located(r.location)) for r in rows]
    shown = places([r.location for r in rows])
    names = report.names
    return [_row_text(r, names.get(r.id, r.id), at) for r, at in zip(rows, shown, strict=True)]


def _hop_line(report: CauseReport, hop: int) -> str:
    """One hop not shown in rows: how many things, by type, most first, and its touching rows."""
    types = Counter(r.type for r in report.walked if r.hop == hop)
    counted = ", ".join(
        f"{_escape(t)} {n}" for t, n in sorted(types.items(), key=lambda p: (-p[1], p[0]))
    )
    touched = sum(r.hop == hop + 1 for r in report.touching)
    line = f"hop {hop}: {amount(types.total(), 'thing')} ({counted})"
    return line + (f"; {touched} touching" if touched else "")


def _cause_text(report: CauseReport) -> str:
    """A walk by cause as text: the cut line first when something is not shown, then the command,
    the summary, the tree, a count line for each hop not shown, and the notes."""
    lines = [head_line(report.command, [s.id for s in report.starts])]
    notes = [f"warning: {_escape(w)}" for w in report.warnings] + problem_lines(report.problems)
    if not report.starts:
        return "\n".join(lines + notes) + "\n"
    label = "sets off:" if report.toward == "off" else "set off by:"
    lines.append(summary(label, report.walked, False))
    if report.undeclared:
        undeclared = ", ".join(_escape(k) for k in report.undeclared)
        notes.insert(0, f"undeclared kinds, walked by raw direction: {undeclared}")
    last = max((r.hop for r in report.walked), default=0)
    hops = last if report.depth is None else min(report.depth, last)
    while True:
        body = _tree(report, hops) + [_hop_line(report, h) for h in range(hops + 1, last + 1)]
        shown = sum(r.hop <= hops for r in report.walked)
        cut_line = (
            [
                f"showing {shown} of {len(report.walked)} (hops 1-{hops} of {last}); "
                f"all: {_escape(report.again)}{report.again_note}"
            ]
            if shown < len(report.walked)
            else []
        )
        text = "\n".join(cut_line + lines + body + notes) + "\n"
        if not report.limit or len(text) <= report.limit or hops <= 1:
            return text
        hops -= 1


def _cause_json_row(row: CauseRow) -> dict[str, Any]:
    file, _, line = (row.location or "").rpartition(":")
    return {
        "hop": row.hop,
        "id": row.id,
        "type": row.type,
        "state": row.state,
        "via_kind": row.kind,
        "via_direction": "backward" if row.backward else "forward",
        "from": row.via,
        "file": file if row.location else None,
        "line": int(line) if row.location else None,
        "marks": list(row.marks),
        "supporting": row.supporting,
        "hub": row.hub,
        "touch": row.touch,
    }


def _cause_json(report: CauseReport) -> dict[str, Any]:
    """A walk by cause as one JSON document: every row within ``depth``, no text budget."""
    last = max((r.hop for r in report.walked), default=0)
    hops = last if report.depth is None else min(report.depth, last)
    rows = [r for r in report.walked if r.hop <= hops] + list(report.touching)
    return {
        "command": report.command,
        "direction": report.toward,
        "starts": [s.id for s in report.starts],
        "rows": [_cause_json_row(r) for r in sorted(rows, key=lambda r: (r.hop, r.touch, r.id))],
        "hops": [
            {
                "hop": hop,
                "things": sum(r.hop == hop for r in report.walked),
                "by_type": dict(Counter(r.type for r in report.walked if r.hop == hop)),
            }
            for hop in range(1, last + 1)
        ],
        "total": len(report.walked),
        "last_hop": last,
        "shown_hops": hops,
        "hubs": [
            {"id": r.id, "hop": r.hop, "fan": r.hub} for r in report.walked if r.hub is not None
        ],
        "undeclared": list(report.undeclared),
        "again": report.again,
        "warnings": list(report.warnings),
        "problems": [_json_problem(p) for p in report.problems],
    }


def listed(report: WalkReport | CauseReport) -> tuple[str, ...]:
    """The ids ``--ids`` prints: the starts, then every row within ``depth`` and, with
    ``--touch``, the touching rows, by hop and id; with ``--raw``, the start and its rows."""
    if isinstance(report, WalkReport):
        started = [report.start] if report.start else []
        return tuple(dict.fromkeys([*started, *(r.id for r in report.rows.items)]))
    last = max((r.hop for r in report.walked), default=0)
    hops = last if report.depth is None else min(report.depth, last)
    rows = [r for r in report.walked if r.hop <= hops] + list(report.touching)
    return (
        *(s.id for s in report.starts),
        *(r.id for r in sorted(rows, key=lambda r: (r.hop, r.touch, r.id))),
    )


RENDERERS = {"text": render_text, "json": render_json}
