"""``periplus slice``: the things around some starts, printed under their files or written to a map.

A macro. It picks the starts from words, as ``find`` ranks them, or takes them as ids; adds the
members of a container start, as ``members`` lists them; then walks by cause from them, as
``neighbors`` and ``affected`` do, to ``--depth`` hops. What it adds is the content of each thing
of the result: its file, source line, description, marks and links among the result, the legend
of the kinds met and an inventory. The ids ``--ids`` prints are the starts, the members and what
``neighbors --ids`` and ``affected --ids`` list from them, so the result is reproducible with the
small commands; a part the text cuts names the small command that prints it in full.
"""

from __future__ import annotations

import math
import os
import re
import shlex
from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field, replace
from fractions import Fraction
from pathlib import Path
from typing import Any

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.map import write_document
from periplus.navigate import find
from periplus.navigate import grouping as grouping_
from periplus.navigate import members as members_
from periplus.navigate.ids import resolve
from periplus.navigate.listing import (
    NONE,
    Listing,
    attribute_text,
    edge_attributes,
    first_location,
    footer,
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
    map_flag,
    reading_fields,
)
from periplus.navigate.names import Names
from periplus.navigate.reach import DIRECTIONS
from periplus.navigate.sets import sub_document
from periplus.navigate.show import node_descriptions
from periplus.navigate.source import SourceLines, description_line, source_line
from periplus.navigate.walk import (
    HUB,
    NO_CAUSES,
    CauseRow,
    cause_report,
    start_args,
    summary,
    walk,
)
from periplus.report import _escape, _json_problem, amount

__all__ = [
    "PRINT_DEPTH",
    "ROW_LIMIT",
    "START_LIMIT",
    "RENDERERS",
    "Piece",
    "PieceRow",
    "SliceReport",
    "Start",
    "Walked",
    "listed",
    "render_json",
    "render_text",
    "run",
]

#: The most start nodes the words pick in all, unless ``starts`` says otherwise.
START_LIMIT = 12
#: The most start nodes the words pick of any one node type.
TYPE_STARTS = 2
#: The share of the start budget the first pass gives to the words, one start each in turn from
#: the rarest word down; it gives every word one start while the budget lasts.
WORD_SHARE = Fraction(1, 2)
#: The decimal places a word's weight keeps, so equal scores are equal on every machine.
WEIGHT_PLACES = 6
#: The fewest characters a word needs to be searched; a shorter one matches too much.
MIN_WORD = 3
#: The most things past the starts a printed slice shows, unless ``limit`` says otherwise.
ROW_LIMIT = 50
#: The things past the starts the byte aim never cuts, so a slice of many starts still shows what
#: its walks reached.
ROW_FLOOR = 10
#: The start lines a printed slice shows in full; the rest are counted, with the command that
#: lists them.
START_LINES = 4
#: The hops each walk by cause goes, unless ``depth`` says otherwise. On a real map a start's walk
#: off held 15% of its things within 2 hops and 40% within 3, so 2 keeps one start's slice near the
#: byte aim and leaves the rest to ``--depth``.
PRINT_DEPTH = 2
#: The bytes the default printed slice aims at; an explicit ``limit`` caps things alone instead.
BYTE_LIMIT = 8 * 1024
#: The most far-end names one link clause prints before it counts the rest.
LINK_NAMES = 5
#: The most names of nodes outside the project one link clause prints.
OUTSIDE_NAMES = 3
#: The most edge kinds a footer line names, those with the most rows left out first.
FOOTER_KINDS = 6
#: Far ends of one clause that share an owner, at least this many, print as the owner and a count.
OWNER_FOLD = 3
#: The bytes the legend at the end of a printed slice may take; past them it counts the rest.
LEGEND_BYTES = 640
#: The most things a slice written to a file may hold, unless ``limit`` says otherwise.
FILE_LIMIT = 500
#: What each walk is called in the text, and the small command that prints it.
_WALKS = {"off": ("sets off:", "neighbors"), "by": ("set off by:", "affected")}


@dataclass(frozen=True, slots=True)
class Start:
    """A start node of a slice, as ``find`` shows it, and why it was picked.

    ``given`` is the argument that named it; ``words`` each word, or the whole text, that found
    it, with where it matched (``id``, ``attribute`` or ``description``) and the attribute's name.
    """

    row: find.FindRow
    given: str | None = None
    words: tuple[tuple[str, str, str | None], ...] = ()


@dataclass(frozen=True, slots=True)
class PieceRow:
    """One thing of the result past the starts: ``id``, reached from ``parent`` by an edge of
    ``kind`` at ``hop``, by the walk from the start ``start``.

    ``walk`` names the part that found it: ``off`` (as ``neighbors``), ``by`` (as ``affected``)
    or ``members``. ``outward`` is true when the edge runs from ``parent`` to ``id``. ``hub`` is
    the fan of a thing the walk did not go on from; ``touch`` marks a thing only pointed at.
    ``attributes`` are the edge's.
    """

    start: str
    hop: int
    parent: str
    kind: str
    outward: bool
    id: str
    type: str
    state: str
    walk: str
    location: str | None = None
    source: str | None = None
    description: str | None = None
    marks: tuple[str, ...] = ()
    hub: int | None = None
    touch: bool = False
    attributes: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Members:
    """The members of a start that is a container: how many, how many of each type, most first,
    as ``members`` counts them, and the rows of the slice."""

    container: str
    total: int
    by_type: tuple[tuple[str, int], ...]
    rows: tuple[PieceRow, ...]


@dataclass(frozen=True, slots=True)
class Walked:
    """One walk of the slice, ``off`` or ``by``: every thing it reached to its end (empty for the
    raw walk), how many the slice holds within its depth, the kinds it followed undeclared, and the
    commands that print the part the slice holds and the whole walk."""

    toward: str
    rows: tuple[CauseRow, ...]
    held: int
    undeclared: tuple[str, ...]
    command: str
    whole: str
    raw: bool = False


@dataclass(frozen=True, slots=True)
class Link:
    """A subject's edges of one kind and direction to other nodes of the slice, by short name.

    ``owners`` are far ends folded into their owner, with a count; ``more`` counts the mapped far
    ends past the names shown; ``outside`` names the first far ends not mapped, of
    ``outside_count``. ``realized`` marks far ends at the concrete end of a realizing kind: the
    forms of this node. ``tags`` and ``outside_tags`` hold, for each of ``names`` and
    ``outside``, the attributes of its edge as a row prints them.
    """

    kind: str
    outward: bool
    names: tuple[str, ...]
    more: int
    owners: tuple[tuple[str, int], ...]
    outside: tuple[str, ...]
    outside_count: int
    realized: bool = False
    tags: tuple[str, ...] = ()
    outside_tags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Subject:
    """A mapped node of the slice under its file: line, short name, type, source line, its links
    in the slice, its edges the slice does not show, as (kind, outward, count), its mark texts,
    whether a link names fewer ends than it has, and its fan when the walk stopped at it."""

    id: str
    short: str
    type: str
    line: int | float | None
    source: str | None
    description: str | None
    links: tuple[Link, ...]
    unwalked: tuple[tuple[str, bool, int], ...]
    marks: tuple[str, ...] = ()
    cut_links: bool = False
    hub: int | None = None


@dataclass(frozen=True, slots=True)
class FileGroup:
    """One file of the slice, the containers its nodes belong to, and its nodes in line order."""

    file: str | None
    containers: tuple[str, ...]
    subjects: tuple[Subject, ...]
    piece: int = 1


@dataclass(frozen=True, slots=True)
class Piece:
    """Nodes the output names that edges other than grouping edges join: its starts, in pick
    order, how many things the output names in it, and how many nodes in supporting code it
    left out, with the patterns they match."""

    starts: tuple[str, ...]
    things: int
    supporting: int = 0
    patterns: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SliceReport:
    """One slice run. ``out`` is ``None`` when nothing was written.

    A printed slice (``printed``) holds its ``starts``, the ``members`` of its container starts,
    its ``walks``, and ``rows``: the things past the starts it prints, with what the cap left out
    by hop and by kind, the kinds and the farthest hop of all of them. ``held`` is every id of the
    result, never cut. ``notes`` say how the words
    were read; ``unpicked`` counts the nodes the ``words`` matched that the start cap left out;
    ``piped`` says the starts came from standard input.
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
    deepest: int = 0
    depth: int | None = PRINT_DEPTH
    direction: str = "both"
    searched: bool = False
    notes: tuple[str, ...] = ()
    members: tuple[Members, ...] = ()
    walks: tuple[Walked, ...] = ()
    listing: str = ""
    files: tuple[FileGroup, ...] = ()
    inventory: tuple[tuple[str, tuple[tuple[str, int], ...]], ...] = ()
    shorts: Mapping[str, str] | None = None
    cuts: tuple[str, ...] = ()
    legend: tuple[tuple[str, str], ...] = ()
    pieces: tuple[Piece, ...] = ()
    piece_of: Mapping[str, int] | None = None
    unpicked: int = 0
    words: tuple[str, ...] = ()
    piped: bool = False
    map_path: Path | None = None
    held: tuple[str, ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


@dataclass(frozen=True, slots=True)
class _Walking:
    """How the slice walks: which ways, how many hops (``None``: all), the kinds kept, the hub
    limit, the hubs walked all the same and whether to add touching things."""

    direction: str = "both"
    depth: int | None = PRINT_DEPTH
    kinds: Collection[str] = ()
    hub: int = HUB
    through: Sequence[str] = ()
    touch: bool = False


def run(
    start: Path,
    env: Mapping[str, str],
    ids: Collection[str],
    prefixes: Collection[str],
    direction: str = "both",
    depth: int | None = PRINT_DEPTH,
    kinds: Collection[str] = (),
    limit: int | None = None,
    out: Path | None = None,
    map_path: Path | None = None,
    types: Collection[str] = (),
    starts: int | None = None,
    support: bool = False,
    from_ids: Sequence[str] = (),
    piped: bool = False,
    hub: int = HUB,
    through: Sequence[str] = (),
    touch: bool = False,
) -> SliceReport:
    """Pick the starts, add the members of a container start, walk by cause from them and print
    the result; with ``out``, write it to that map file instead.

    ``ids`` are words or ids; ``from_ids`` are ids alone, with no word searched, and ``piped``
    says they came from standard input. ``direction`` is ``off``, ``by`` or ``both``; ``depth``
    ``None`` walks to the end. ``limit`` of ``None`` takes the mode's default and 0 keeps every
    thing: printed, the most things past the starts, with a byte aim when not given; written, the
    most things the file may hold.
    """
    walking = _Walking(direction, depth, tuple(kinds), hub, tuple(through), touch)
    printed = out is None
    try:
        path, document = load_document(start, env, map_path)
        target = None if out is None else start / out
        if target is not None and target.resolve() == path.resolve():
            message = f"--out {target} is the map being read; choose another file"
            return SliceReport(
                problems=(Problem(ExitCode.OUTPUT_UNWRITABLE, message, {"path": str(target)}),)
            )
        with reading_fields(start, map_path):
            index = MapIndex(document, map_path)
            report = _piece(
                start,
                index,
                document.get("legend", {}).get("edge_kinds", {}),
                from_ids or ids,
                prefixes,
                walking,
                (ROW_LIMIT if limit is None else limit) if printed else 0,
                map_path,
                types,
                START_LIMIT if starts is None else starts,
                printed and limit is None,
                support,
                not from_ids,
                piped,
            )
            if target is None or report.problems:
                return report if printed else replace(report, printed=False)
            cap = FILE_LIMIT if limit is None else limit
            if not report.held:
                message = "no node matches the words; nothing written"
                return SliceReport(problems=(Problem(ExitCode.NODE_NOT_FOUND, message, {}),))
            if cap and len(report.held) > cap:
                message = f"the slice holds {len(report.held)} items, over the limit of {cap}"
                return SliceReport(problems=(Problem(ExitCode.SLICE_TOO_LARGE, message, {}),))
            kept = set(report.held)
            nodes = [node for node in document["nodes"] if node["id"] in kept]
            edges = [e for e in document["edges"] if e["from"] in kept and e["to"] in kept]
            piece = sub_document(document, nodes, edges, index.parent)
    except HarnessError as error:
        return SliceReport(printed=printed, problems=(error.problem(),))
    problems = write_document(piece, target)
    if problems:
        return SliceReport(problems=problems)
    return SliceReport(str(target), len(nodes), len(edges), report.warnings)


def _under(nodes: Mapping[str, Any], prefixes: Collection[str]) -> set[str]:
    """The nodes whose first location's file starts with one of ``prefixes``; each must hold one."""
    starts: set[str] = set()
    for prefix in prefixes:
        under = {
            node_id
            for node_id, node in nodes.items()
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
    index: MapIndex,
    texts: Mapping[str, Any],
    given: Collection[str],
    prefixes: Collection[str],
    walking: _Walking,
    limit: int,
    map_path: Path | None,
    types: Collection[str],
    most: int,
    budgeted: bool = False,
    support: bool = False,
    searching: bool = True,
    piped: bool = False,
) -> SliceReport:
    """The slice around the start nodes; ``budgeted`` fits its text to ``BYTE_LIMIT``, leaving
    out the legend, then the unwalked counts, then names per link, then the farthest things.
    ``texts`` are the map's edge kind descriptions.

    An argument that names a node starts there. The rest is searched as ``find`` searches, as a
    whole and word by word; see ``_starts``. ``types`` and, when there are words, ``prefixes``
    narrow those starts. Without words, each prefix adds the nodes under it.

    Unless ``support``, a node in supporting code is not a start, but for one named by its id or
    when every match is there, and it is not printed: each piece counts them.

    Without ``searching``, each of ``given`` must name a node, and no word is searched.
    """
    described, problems = node_descriptions(start, map_path)
    picked: dict[str, Start] = {}
    warnings: list[str] = []
    rest: list[str] = []
    several = len(_WORD.findall(" ".join(given))) > 1
    for text in given:
        try:
            node_id, said = resolve(index, text, prefer_main=not searching)
        except NodeNotFound:
            if not searching:
                raise
            rest.append(text)
            continue
        warnings += said
        picked.setdefault(node_id, Start(_row(index, node_id, described), given=text))
        if searching and several and _WORD.fullmatch(text):
            rest.append(text)
    words = list(dict.fromkeys(_WORD.findall(" ".join(rest).casefold())))
    words = [word for word in words if len(word) >= MIN_WORD]
    whole = " ".join(rest).casefold().strip()
    queries = list(dict.fromkeys(([whole] if whole and whole not in words else []) + words))
    # The words a node holds in its own name, an attribute or its description: a word only in
    # the id's type or in the owner part before its last ``::`` is not the node's.
    owned: dict[str, set[str]] = {}
    weights: dict[str, float] = {}
    notes: list[str] = []
    unpicked = 0
    search = _Search(index, described)
    for word in words:
        hits = search(word, None, ())
        for match in hits:
            if match[0] != _OUTSIDE_NAME:
                owned.setdefault(match[1], set()).add(word)
        if hits:
            weights[word] = round(math.log(len(index.nodes) / len(hits)), WEIGHT_PLACES)
    standing = _Standing(index)
    scores: dict[str, float] = {}
    if queries:
        wanted, narrowed, noted = find.narrowing(index, types, prefixes)
        warnings += noted
        scores = {
            node_id: round(sum(weights[w] for w in found_), WEIGHT_PLACES)
            for node_id, found_ in owned.items()
        }
        rarest = sorted(weights, key=lambda w: (-weights[w], w))
        found, matches = _starts(
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
        unpicked = len(set(matches) - set(picked))
        lone = found and queries[0] == whole and len(queries) > 1
        if lone and not search(whole, wanted, narrowed):
            notes.append(f"no node matches {whole!r} as a whole; started from its words")
    elif prefixes:
        under = sorted(_under(index.nodes, prefixes))
        not_supporting = [n for n in under if support or index.supporting(n) is None]
        for node_id in not_supporting or under:
            picked.setdefault(node_id, Start(_row(index, node_id, described)))
    elif not picked:
        message = "give some words, an id or a path prefix"
        return SliceReport(printed=True, problems=(Problem(ExitCode.USAGE, message, {}),))
    order = list(picked)
    names = Names(index)
    only = find.narrowing(index, types, ())[0] if types and not queries else None
    roots = {s: s for s in order}
    hidden: list[tuple[str, str, str]] = []

    def shown(begun: str, node: str) -> bool:
        """Whether ``node`` prints; one in supporting code is added to ``hidden`` instead."""
        pattern = None if support or node in picked else index.supporting(node)
        if pattern is not None:
            hidden.append((begun, node, pattern))
        return pattern is None

    members: list[Members] = []
    for container in order:
        if not any(edge["kind"] in index.grouping for edge in index.incoming(container)):
            continue
        holding = members_.held(index, names, container, only)
        rows = []
        for member in holding.members:
            roots.setdefault(member.id, container)
            if member.id not in picked and shown(container, member.id):
                rows.append(
                    PieceRow(
                        container,
                        0,
                        container,
                        member.kind,
                        False,
                        member.id,
                        member.type,
                        member.state,
                        "members",
                        member.location,
                    )
                )
        members.append(Members(container, len(holding.members), holding.by_type, tuple(rows)))
    walk_from = list(roots)
    on = map_flag(map_path)
    listing = _starts_command(given, searching, prefixes, types, most, support, piped) + on
    named, _ = start_args([names.short(i) for i in walk_from], piped)
    reached, walks, walked = _walk(start, index, walk_from, roots, walking, map_path, named)
    if isinstance(reached, tuple):
        return SliceReport(printed=True, problems=reached)
    warnings += walked
    raw_note = f" (for each of the {len(walk_from)} ids it walks from)"
    piped_note = " (with the same ids piped into the first command)" if piped else ""

    def runnable(command: str, raw: bool) -> str:
        """``command`` with the map, after the command that lists its ids when it reads ``-``."""
        if raw:
            return command + on + raw_note
        if named == ["-"]:
            return f"{listing} | {command}{on}{piped_note}"
        return command + on

    walks = [
        replace(w, command=runnable(w.command, w.raw), whole=runnable(w.whole, w.raw))
        for w in walks
    ]
    held = list(dict.fromkeys([*walk_from, *(r.id for r in reached)]))
    rows = [r for m in members for r in m.rows] + [r for r in reached if shown(r.start, r.id)]
    hubs = {r.id: r.hub for r in reached if r.hub is not None}
    lines = SourceLines(start, map_path)
    homes: dict[str, set[str]] = {}
    for edge in index.edges:
        if edge["kind"] in index.grouping and (loc := first_location(index.nodes[edge["from"]])):
            homes.setdefault(as_text(loc["file"]), set()).add(as_text(edge["to"]))
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
    shown_members = tuple(
        replace(m, rows=tuple(_filled(r, lines, described, index) for r in m.rows)) for m in members
    )

    def assemble(
        taking: int, cap: int, more: bool, cuts: tuple[str, ...], told: bool
    ) -> SliceReport:
        kept = rows[:taking]
        files, inventory, pieces, piece_of = _layout(
            index,
            names,
            standing,
            (order, kept, index.grouping, homes),
            (lines, described),
            (cap, more),
            scores,
            hubs,
        )
        pieces = _with_supporting(pieces, piece_of, hidden)
        shorts = {i: names.short(i) for i in [*picked, *(m.container for m in members)]}
        shown_kinds = {k.kind for g in files for s in g.subjects for k in s.links}
        legend = tuple((k, as_text(texts[k])) for k in sorted(shown_kinds) if k in texts)
        left = rows[taking:]
        return SliceReport(
            nodes=len(held),
            edges=len(reached),
            warnings=tuple(dict.fromkeys(warnings)),
            problems=problems,
            printed=True,
            starts=begun,
            rows=Listing(
                tuple(_filled(r, lines, described, index) for r in kept),
                len(rows),
                len(kept),
                len(kept) < len(rows),
            ),
            left_by_hop=dict(sorted(Counter(r.hop for r in left).items())),
            left_by_kind=dict(sorted(Counter(r.kind for r in left).items())),
            kinds=tuple(sorted({r.kind for r in rows})),
            deepest=max((r.hop for r in rows), default=0),
            depth=walking.depth,
            direction=walking.direction,
            searched=bool(queries),
            notes=tuple(notes),
            members=shown_members,
            walks=tuple(walks),
            listing=listing,
            files=files,
            inventory=inventory,
            shorts=shorts,
            cuts=cuts,
            legend=legend if told else (),
            pieces=pieces,
            piece_of=piece_of,
            unpicked=unpicked,
            words=tuple(words or [whole]) if queries else (),
            piped=piped,
            map_path=map_path,
            held=tuple(held),
        )

    taking = min(len(rows), limit) if limit else len(rows)
    floor = min(taking, ROW_FLOOR)
    cap, more, told, cut, over = LINK_NAMES, True, True, 0, False
    report = assemble(taking, cap, more, (), told)
    budget = BYTE_LIMIT if budgeted else 0
    while budget and not over and len(render_text(report).encode()) > budget:
        if told and report.legend:
            told = False
        elif more:
            more = False
        elif cap > 1:
            cap //= 2
        elif taking > floor:
            taking -= 1
            cut += 1
        else:
            over = True
        parts = [] if told else ["legend left out"]
        parts += [] if more else ["the +N more links lines dropped"]
        parts += [f"at most {cap} names per link"] if cap < LINK_NAMES else []
        parts += [f"{amount(cut, 'thing')} left out, farthest hop first"] if cut else []
        parts += (
            [f"the first {amount(taking, 'thing')} past the starts kept over it"] if over else []
        )
        cut_note = f"cut to fit {budget} bytes: {', '.join(parts)}; --limit N prints N things"
        if not told:
            cut_note += f"; what a kind means: periplus legend --kind K{on}"
        if not more or cap < LINK_NAMES:
            cut_note += f"; a node's links in full: periplus show NAME --limit 0{on}"
        report = assemble(taking, cap, more, (cut_note,), told)
    return report


def _starts_command(
    given: Collection[str],
    searching: bool,
    prefixes: Collection[str],
    types: Collection[str],
    most: int,
    support: bool,
    piped: bool,
) -> str:
    """The ``slice --depth 0 --ids`` command that prints this slice's starts and their members,
    without the map."""
    words = ["periplus", "slice"]
    words += [*given] if searching else ["--from", *(["-"] if piped else given)]
    words += [f for prefix in prefixes for f in ("--path", prefix)]
    words += [f for kind in types for f in ("--type", kind)]
    words += ["--starts", str(most)] if most != START_LIMIT else []
    words += ["--support"] if support else []
    return " ".join(shlex.quote(word) for word in [*words, "--depth", "0", "--ids"])


def _filled(
    row: PieceRow, lines: SourceLines, described: Mapping[str, str], index: MapIndex
) -> PieceRow:
    """``row`` with its source line, description and marks."""
    return replace(
        row,
        source=lines.at(row.location),
        description=described.get(row.id),
        marks=index.marks(row.id),
    )


def _walk(
    start: Path,
    index: MapIndex,
    walk_from: Sequence[str],
    roots: dict[str, str],
    walking: _Walking,
    map_path: Path | None,
    named: Sequence[str],
) -> tuple[list[PieceRow] | tuple[Problem, ...], list[Walked], list[str]]:
    """The things the walks of ``walking`` reach from ``walk_from`` within its depth, each once,
    by hop, the walk off before the walk by; each walk; and their warnings. Each row hangs under
    the start whose walk reached it, by ``roots``, which it extends. ``named`` are the ids a
    command the walk names takes.

    On a map that lists causes, each walk is ``cause_report``'s, as ``neighbors`` and
    ``affected`` take it. On one that lists none, it is the raw walk those commands fall back
    to, from each id in turn, and a warning says so. The problems of a walk come back in place
    of the rows.
    """
    if not walk_from:
        return [], [], []
    rows: list[PieceRow] = []
    walks: list[Walked] = []
    warnings: list[str] = []
    seen = set(walk_from)
    for toward in DIRECTIONS[walking.direction]:
        verb = _WALKS[toward][1]
        found: list[PieceRow] = []
        if index.declares_causes:
            report = cause_report(
                start,
                index,
                walk_from,
                toward,
                walking.depth,
                walking.kinds,
                0,
                map_path,
                walking.hub,
                walking.through,
                walking.touch,
            )
            if report.problems:
                return report.problems, [], []
            warnings += report.warnings
            last = max((r.hop for r in report.walked), default=0)
            hops = last if walking.depth is None else min(walking.depth, last)
            inside = [r for r in report.walked if r.hop <= hops]
            inside += list(report.touching) if walking.depth != 0 else []
            for r in sorted(inside, key=lambda r: (r.hop, r.touch, r.id)):
                root = roots.setdefault(r.id, roots[r.via])
                if r.id not in seen:
                    seen.add(r.id)
                    found.append(
                        PieceRow(
                            root,
                            r.hop,
                            r.via,
                            r.kind,
                            not r.backward,
                            r.id,
                            r.type,
                            r.state,
                            toward,
                            r.location,
                            hub=r.hub,
                            touch=r.touch,
                            attributes=r.attributes,
                        )
                    )
            walks.append(
                Walked(
                    toward,
                    report.walked,
                    len(inside),
                    report.undeclared,
                    _command(verb, named, walking.depth, walking),
                    _command(verb, named, None, walking),
                )
            )
        else:
            levels = len(index.nodes) if walking.depth is None else walking.depth
            for item in walk_from if levels else ():
                raw = walk(index, item, "out" if toward == "off" else "in", levels, walking.kinds)
                for w in raw:
                    root = roots.setdefault(w.id, roots.get(w.via, roots[item]))
                    if w.id not in seen:
                        seen.add(w.id)
                        found.append(
                            PieceRow(
                                root,
                                w.depth,
                                w.via,
                                w.kind,
                                toward == "off" and not w.stands_for,
                                w.id,
                                w.type,
                                w.state,
                                toward,
                                w.location,
                                attributes=w.attributes,
                            )
                        )
            raw_command = _command(verb, ["ID"], walking.depth, walking, raw=True)
            walks.append(Walked(toward, (), len(found), (), raw_command, raw_command, raw=True))
            warnings.append(NO_CAUSES)
        rows += found
    rows.sort(key=lambda r: (r.hop, r.walk != "off", r.touch, r.id))
    return rows, walks, warnings


def _command(
    verb: str, named: Sequence[str], depth: int | None, walking: _Walking, raw: bool = False
) -> str:
    """The ``neighbors`` or ``affected`` command, ``verb``, that prints a walk of the slice from
    ``named`` to ``depth`` hops (``None``: all), with the slice's walk options and ``--limit 0``;
    ``raw`` names the raw walk."""
    words = ["periplus", verb, *named, *(["--raw"] if raw else [])]
    words += ["--depth", "all" if depth is None else str(depth)]
    words += [f for kind in walking.kinds for f in ("--kind", kind)]
    if not raw:
        words += ["--hub", str(walking.hub)] if walking.hub != HUB else []
        words += [f for item in walking.through for f in ("--through", item)]
        words += ["--touch"] if walking.touch else []
    words += ["--limit", "0"]
    return " ".join(shlex.quote(word) for word in words)


def _layout(
    index: MapIndex,
    names: Names,
    standing: _Standing,
    piece: tuple[list[str], list[PieceRow], Collection[str], Mapping[str, set[str]]],
    reading: tuple[SourceLines, Mapping[str, str]],
    folding: tuple[int, bool],
    scores: Mapping[str, float],
    hubs: Mapping[str, int],
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
    files go in the order the starts and the rows first reach them; nodes inside a
    file by line. A file's header names the containers its nodes belong to by grouping edges,
    ``homes``. A node's links are its edges to other nodes of the piece, by kind and direction,
    a grouping edge from the node to its container left to the header. An edge between two nodes
    of one file prints only at its ``from`` end.
    ``folding`` gives the most names per link and whether to count the edges the piece leaves
    out. ``hubs`` holds the fan of each node the walk did not go on from.
    """
    starts, rows, grouping, homes = piece
    lines, described = reading
    cap, more = folding
    held = list(dict.fromkeys([*starts, *(r.id for r in rows)]))
    inside = set(held)
    # Each node the output names, and the node it is printed under.
    named: dict[str, str] = {}
    owner = names.owner

    def link(
        kind: str, outward: bool, ends: list[str], here: str, said: Mapping[str, str]
    ) -> Link:
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
            tuple(said.get(e, "") for e in loose[:cap]),
            tuple(said.get(e, "") for e in outside[:OUTSIDE_NAMES]),
        )

    found: list[tuple[str | None, Subject]] = []
    for node_id in held:
        node = index.nodes[node_id]
        if node["state"] != "mapped":
            continue
        named.setdefault(node_id, node_id)
        loc = first_location(node)
        ends: dict[tuple[str, bool], list[str]] = {}
        said: dict[tuple[str, bool], dict[str, str]] = {}
        unwalked: Counter[tuple[str, bool]] = Counter()
        for outward, edges in ((True, index.outgoing(node_id)), (False, index.incoming(node_id))):
            for edge in edges:
                far = as_text(edge["to" if outward else "from"])
                kind = as_text(edge["kind"])
                if far == node_id:
                    continue
                if outward and kind in grouping:
                    continue
                if far in inside:
                    there = first_location(index.nodes[far])
                    same = there is not None and loc is not None and there["file"] == loc["file"]
                    if not (same and not outward and index.nodes[far]["state"] == "mapped"):
                        ends.setdefault((kind, outward), []).append(far)
                        text = attribute_text(edge_attributes(edge))
                        said.setdefault((kind, outward), {})[far] = text
                else:
                    unwalked[(kind, outward)] += 1
        links = tuple(
            link(k, o, sorted(set(v)), node_id, said[(k, o)])
            for (k, o), v in sorted(ends.items(), key=lambda p: (p[0][0], not p[0][1]))
        )
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
                    links,
                    tuple(
                        (k, o, n)
                        for (k, o), n in sorted(
                            unwalked.items(), key=lambda p: (-p[1], p[0][0], not p[0][1])
                        )
                    )
                    if more
                    else (),
                    index.marks(node_id),
                    more
                    and any(k.more or k.owners or k.outside_count > len(k.outside) for k in links),
                    hubs.get(node_id),
                ),
            )
        )
    for file, subject in found:
        for container in homes.get(file, ()) if file is not None else ():
            named.setdefault(container, subject.id)
    for start in starts:
        named.setdefault(start, start)
    joined = _joined(index, starts, rows, named, grouping)
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
    for row in rows:
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


def _row(index: MapIndex, node_id: str, described: Mapping[str, str]) -> find.FindRow:
    """A start named by its id, as ``find`` shows a row matched by its id."""
    return find.found_row((0, node_id, index.nodes[node_id], None), described)


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
    """What the map alone says about a node: how many nodes share its type, and how many other
    files hold nodes with an edge into it. Each is counted once per run."""

    def __init__(self, index: MapIndex) -> None:
        self._index = index
        self._types = Counter(as_text(node["type"]) for node in index.nodes.values())
        self._files: dict[str, int] = {}

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
) -> tuple[dict[str, Start], list[str]]:
    """Up to ``most`` start nodes that the queries find, in two passes, and every node the
    queries found that may be a start.

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
    }, ranked


def _why(start: Start) -> str:
    if start.given is not None:
        return f"given as '{start.given}'"
    said = [
        f"'{word}' in {'attribute ' + (name or '') if matched == 'attribute' else matched}"
        for word, matched, name in start.words
    ]
    return "words: " + ", ".join(said)


def _tags(link: Link, outside: bool = False) -> tuple[str, ...]:
    """The attribute text of each name the link shows, or of each outside name; none given, none
    printed."""
    names, tags = (link.outside, link.outside_tags) if outside else (link.names, link.tags)
    return tags or ("",) * len(names)


def _clause(link: Link) -> str:
    """One link as ``kind -> a, b, Owner (3) (+2 more) (+1 outside the project: x)``."""
    arrow = "->" if link.outward else "<-"
    parts = [f"{_escape(name)} ({count})" for name, count in link.owners]
    parts += [_escape(name) + tag for name, tag in zip(link.names, _tags(link), strict=True)]
    head = (
        f"realized by ({_escape(link.kind)}) ->"
        if link.realized
        else f"{_escape(link.kind)} {arrow}"
    )
    text = f"{head} {', '.join(parts)}".rstrip()
    text += f" (+{link.more} more)" if link.more else ""
    if link.outside_count:
        listed = ", ".join(
            _escape(name) + tag
            for name, tag in zip(link.outside, _tags(link, outside=True), strict=True)
        )
        text += f" (+{link.outside_count} outside the project: {listed})"
    return text


def _file_lines(group: FileGroup, under: str, on: str) -> list[str]:
    """A file's header, its path below ``under``, then each of its nodes: line, short name,
    type, marks, hub fan, source, description, links, and the count of edges the slice leaves
    out."""
    header = _escape(group.file[len(under) :]) if group.file is not None else "no file"
    if group.containers:
        header += f"  in {', '.join(_escape(c) for c in group.containers)}"
    lines = ["", header]
    for subject in group.subjects:
        line = "" if subject.line is None else subject.line
        hub = "" if subject.hub is None else f"  [hub: {subject.hub} links not walked]"
        lines.append(
            f"  :{line}  {_escape(subject.short)}  {_escape(subject.type)}"
            f"{mark_text(subject.marks)}{hub}"
        )
        lines += source_line(subject.source)
        lines += description_line(subject.description)
        lines += [f"      {_clause(link)}" for link in subject.links]
        if subject.unwalked:
            total = sum(n for _, _, n in subject.unwalked)
            counted = ", ".join(
                f"{_escape(kind)} {'->' if outward else '<-'} {n}"
                for kind, outward, n in subject.unwalked
            )
            lines.append(
                f"      +{amount(total, 'more link')}: {counted};"
                f" see periplus show {_escape(subject.short)} --limit 0{_escape(on)}"
            )
        elif subject.cut_links:
            lines.append(
                f"      all links: periplus show {_escape(subject.short)} --limit 0{_escape(on)}"
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
                lines += _file_lines(group, under, map_flag(report.map_path))
        if piece.supporting:
            patterns = ", ".join(_escape(p) for p in piece.patterns)
            lines += [
                "",
                f"+{piece.supporting} in supporting code ({patterns}): show with --support,"
                " or with the in-full commands at the end",
            ]
    if total > 1:
        one, two = (_escape(shorts.get(p.starts[0], p.starts[0])) for p in report.pieces[:2])
        lines += [
            "",
            f"no edge of the map joins these {total} pieces as printed; they may still meet"
            " through nodes not printed, or relate in ways the map does not hold;"
            f" test two with periplus path {one} {two}{_escape(map_flag(report.map_path))}",
        ]
    return lines


def _member_line(members: Members, short: str, on: str) -> str:
    """A container start's member count by type, and the command that lists them."""
    counted = ", ".join(f"{_escape(t)} {n}" for t, n in members.by_type)
    return (
        f"members of {_escape(short)}: {members.total} ({counted});"
        f" all: periplus members {_escape(short)}{_escape(on)} (--type T for one type)"
    )


def _walk_lines(report: SliceReport) -> list[str]:
    """Each walk in a line, as ``neighbors`` and ``affected`` sum theirs up; when the slice holds
    part of it, how much and the command that prints the whole walk; then the kinds it followed
    undeclared."""
    lines = []
    for walked in report.walks:
        label, _ = _WALKS[walked.toward]
        if walked.raw:
            lines.append(
                f"{label:<12}{amount(walked.held, 'thing')} by the raw walk, as the map lists"
                f" no cause; each: {_escape(walked.command)}"
            )
            continue
        line = summary(label, walked.rows, False)
        if walked.held < len(walked.rows):
            hops = (
                "no hop"
                if report.depth == 0
                else "hop 1"
                if report.depth == 1
                else (f"hops 1-{report.depth}")
            )
            line += f"; this slice holds {hops}: {walked.held}; all: {_escape(walked.whole)}"
        lines.append(line)
    undeclared = sorted({k for w in report.walks for k in w.undeclared})
    if undeclared:
        named = ", ".join(_escape(k) for k in undeclared)
        lines.append(f"undeclared kinds, walked by raw direction: {named}")
    return lines


def _left_out(report: SliceReport) -> list[str]:
    """What the cap left out, by hop and by kind, and the flags that narrow."""
    note = footer(report.rows)
    if note is None:
        return []
    hops = ", ".join(f"{hop}: {n}" for hop, n in (report.left_by_hop or {}).items())
    left = report.left_by_kind or {}
    first = sorted(left, key=lambda k: (-left[k], k))[:FOOTER_KINDS]
    kinds = ", ".join(f"{_escape(k)} {left[k]}" for k in first)
    kinds += (
        f", and {amount(len(left) - len(first), 'more kind')}" if len(left) > len(first) else ""
    )
    here = sorted(report.kinds, key=lambda k: (-left.get(k, 0), k))
    named = ", ".join(_escape(k) for k in here[:FOOTER_KINDS])
    named += f", and {len(here) - FOOTER_KINDS} more" if len(here) > FOOTER_KINDS else ""
    ways = [f"--kind K (kinds here: {named})"]
    if report.direction == "both":
        ways += ["--direction off", "--direction by"]
    if report.deepest > 1:
        ways.append(f"--depth {report.deepest - 1}")
    lines = [
        f"showing {report.rows.shown} of {amount(report.rows.total, 'thing')} past the starts",
        f"left out by hop: {hops}",
        f"left out by kind: {kinds}",
        f"narrow with {', '.join(ways[:-1])} or {ways[-1]}"
        if len(ways) > 1
        else f"narrow with {ways[0]}",
    ]
    if report.searched:
        lines.append("pick other starts with --type T, --path P or --starts N")
    return lines


def _in_full(report: SliceReport) -> list[str]:
    """When the slice left things out, cut their links or left out supporting code, the
    commands that print each walk it holds in full; ``show`` prints a thing's links."""
    cut = footer(report.rows) is not None or bool(report.cuts)
    if not report.walks or not (cut or any(p.supporting for p in report.pieces)):
        return []
    return [
        "in full, each part this slice holds:",
        *(f"  {_WALKS[w.toward][0]} {_escape(w.command)}" for w in report.walks),
    ]


def _legend_lines(legend: Sequence[tuple[str, str]], on: str) -> list[str]:
    """The description of each kind the piece's links show, within ``LEGEND_BYTES``, then a
    count of the rest."""
    if not legend:
        return []
    lines, size = ["", "legend:"], 0
    for at, (kind, text) in enumerate(legend):
        line = f"  {_escape(kind)}: {_escape(text)}"
        size += len(line.encode()) + 1
        if size > LEGEND_BYTES:
            return [*lines, f"  +{len(legend) - at} more: periplus legend --kind K{_escape(on)}"]
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
        for start in report.starts[:START_LINES]:
            short = _escape(shorts.get(start.row.id, start.row.id))
            lines.append(
                f"start {short}  {_escape(start.row.type)}  ({_escape(_why(start))})"
                f"{mark_text(start.row.marks)}"
            )
        if len(report.starts) > START_LINES:
            lines.append(
                f"+{amount(len(report.starts) - START_LINES, 'more start')}; the starts and their"
                f" members: {_escape(report.listing)}"
            )
        if report.unpicked:
            words = ", ".join(_escape(w) for w in report.words)
            on = _escape(map_flag(report.map_path))
            lines.append(
                f"+{report.unpicked} more"
                f" {'node matches' if report.unpicked == 1 else 'nodes match'}"
                f" the words: periplus find WORD --limit 0{on} for"
                f" each of: {words}; start from any with periplus slice --from ID{on}"
            )
        lines += [
            _member_line(m, shorts.get(m.container, m.container), map_flag(report.map_path))
            for m in report.members
        ]
        lines += _walk_lines(report)
        under = _folder(report.files)
        lines += [f"paths under: {_escape(under)}"] if under else []
        lines += _piece_lines(report, shorts, under)
        if report.inventory:
            count = sum(len(names) for _, names in report.inventory)
            lines += ["", f"inventory: {amount(count, 'node')}"]
            several = len(report.pieces) > 1
            lines += [
                f"  {_escape(kind)} {len(names)}: "
                + ", ".join(_escape(n) + (f" [{piece}]" if several else "") for n, piece in names)
                for kind, names in report.inventory
            ]
        lines += _left_out(report)
        lines += [_escape(cut) for cut in report.cuts]
        lines += _in_full(report)
        lines += _legend_lines(report.legend, map_flag(report.map_path))
    if report.out is not None:
        lines.append(
            f"wrote {_escape(report.out)}: {amount(report.nodes, 'node')}, "
            f"{amount(report.edges, 'edge')}"
        )
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
        "attributes": dict(row.attributes),
        "direction": "out" if row.outward else "in",
        "walk": row.walk,
        "id": row.id,
        "type": row.type,
        "state": row.state,
        "marks": list(row.marks),
        "location": row.location,
        "source": row.source,
        "description": row.description,
        "hub": row.hub,
        "touch": row.touch,
    }


def _json_walk(walked: Walked) -> dict[str, Any]:
    return {
        "direction": walked.toward,
        "raw": walked.raw,
        "total": len(walked.rows) if not walked.raw else walked.held,
        "held": walked.held,
        "last_hop": max((r.hop for r in walked.rows), default=0),
        "hubs": [r.id for r in walked.rows if r.hub is not None],
        "undeclared": list(walked.undeclared),
        "command": walked.command,
        "all": walked.whole,
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
                "members": [
                    {
                        "container": m.container,
                        "total": m.total,
                        "by_type": dict(m.by_type),
                    }
                    for m in report.members
                ],
                "walks": [_json_walk(w) for w in report.walks],
                "rows": payload(report.rows, lambda row: _json_row(row, piece_of)),
                "left_out": {
                    "by_hop": {str(h): n for h, n in (report.left_by_hop or {}).items()},
                    "by_kind": dict(report.left_by_kind or {}),
                },
                "held": len(report.held),
                "notes": list(report.notes),
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


def listed(report: SliceReport) -> tuple[str, ...]:
    """The ids ``--ids`` prints: every thing of the result, never cut: the starts, the members of
    each container start, then what each walk reached within the depth, by hop."""
    return report.held


RENDERERS = {"text": render_text, "json": render_json}
