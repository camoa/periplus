"""``periplus members``: what a container holds, by the map's grouping kinds."""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.navigate import find
from periplus.navigate.grouping import members
from periplus.navigate.ids import resolve_all
from periplus.navigate.listing import first_location, marked_text, place, problem_lines
from periplus.navigate.mapfile import MapIndex, as_json, as_text, load_map, reading_fields
from periplus.navigate.names import Names
from periplus.navigate.source import place_key, places
from periplus.report import _escape, _json_problem

__all__ = [
    "RENDERERS",
    "Held",
    "Member",
    "MembersReport",
    "listed",
    "render_json",
    "render_text",
    "run",
]


@dataclass(frozen=True, slots=True)
class Member:
    """One member: its id, the short name it prints, type, state, its own first ``file:line``,
    the grouping kind that joins it to the container, its marks and whether it is in supporting
    code."""

    id: str
    name: str
    type: str
    state: str
    location: str | None
    kind: str
    marks: tuple[str, ...] = ()
    supporting: bool = False


@dataclass(frozen=True, slots=True)
class Held:
    """A container, the short name it prints, its members by type, most first, then by type
    name, and its members in that type order, each type by place, then id."""

    container: str
    name: str
    by_type: tuple[tuple[str, int], ...]
    members: tuple[Member, ...]


@dataclass(frozen=True, slots=True)
class MembersReport:
    """The members of each container asked, in the order asked."""

    held: tuple[Held, ...] = ()
    warnings: tuple[str, ...] = ()
    problems: tuple[Problem, ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def run(
    start: Path,
    env: Mapping[str, str],
    ids: Sequence[str],
    types: Collection[str],
    map_path: Path | None,
) -> MembersReport:
    """The members of each of ``ids``: the from ends of the edges of a grouping kind that arrive
    at it, each member once; ``types`` keeps those types and their subtypes."""
    try:
        index = load_map(start, env, map_path)
        with reading_fields(start, map_path):
            containers, notes = resolve_all(index, ids)
            wanted, _, said = find.narrowing(index, types, ())
            names = Names(index)
            held = tuple(_held(index, names, c, wanted) for c in containers)
    except HarnessError as error:
        return MembersReport(problems=(error.problem(),))
    return MembersReport(held, (*notes, *said))


def _held(index: MapIndex, names: Names, container: str, wanted: set[str] | None) -> Held:
    first: dict[str, Member] = {}
    for edge, member in members(index, container, index.grouping, wanted):
        if member not in first:
            node = index.nodes[member]
            loc = first_location(node)
            first[member] = Member(
                member,
                names.short(member),
                as_text(node["type"]),
                as_text(node["state"]),
                place(loc) if loc else None,
                as_text(edge["kind"]),
                index.marks(member),
                index.supporting(member) is not None,
            )
    counted = Counter(m.type for m in first.values())
    by_type = tuple(sorted(counted.items(), key=lambda p: (-p[1], p[0])))
    rank = {t: n for n, (t, _) in enumerate(by_type)}
    ordered = sorted(
        first.values(),
        key=lambda m: (rank[m.type], place_key(m.location), m.id),
    )
    return Held(container, names.short(container), by_type, tuple(ordered))


def render_text(report: MembersReport) -> str:
    """For each container: its count line by type, then one row a member: name, type, state
    and its own place."""
    lines = ["periplus members"]
    for held in report.held:
        counted = ", ".join(f"{_escape(t)} {n}" for t, n in held.by_type)
        total = len(held.members)
        lines.append(
            f"members of {_escape(held.name)}: {total}" + (f" ({counted})" if total else "")
        )
        at = places([m.location for m in held.members])
        lines += [
            f"  {_escape(m.name)}  {_escape(m.type)}  {_escape(m.state)}  {_escape(where)}"
            f"{marked_text(m.marks, m.supporting)}"
            for m, where in zip(held.members, at, strict=True)
        ]
    lines += [f"warning: {_escape(w)}" for w in report.warnings]
    lines += problem_lines(report.problems)
    return "\n".join(lines) + "\n"


def _json_member(member: Member) -> dict[str, Any]:
    return {
        "id": member.id,
        "type": member.type,
        "state": member.state,
        "location": member.location,
        "kind": member.kind,
        "marks": list(member.marks),
        "supporting": member.supporting,
    }


def render_json(report: MembersReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    return as_json(
        {
            "command": "members",
            "containers": [
                {
                    "container": h.container,
                    "total": len(h.members),
                    "by_type": dict(h.by_type),
                    "members": [_json_member(m) for m in h.members],
                }
                for h in report.held
            ],
            "warnings": list(report.warnings),
            "problems": [_json_problem(p) for p in report.problems],
        }
    )


def listed(report: MembersReport) -> tuple[str, ...]:
    """The ids ``--ids`` prints: every member, container by container, in the text's order."""
    return tuple(dict.fromkeys(m.id for h in report.held for m in h.members))


RENDERERS = {"text": render_text, "json": render_json}
