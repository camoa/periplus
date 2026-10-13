"""``periplus show``: one node and every edge arriving at it or leaving it, grouped by kind."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.navigate.ids import resolve
from periplus.navigate.listing import Listing, cut, footer, payload
from periplus.navigate.mapfile import MapIndex, as_text, load_map, reading_fields
from periplus.report import _escape

__all__ = ["RENDERERS", "ShowReport", "render_json", "render_text", "run"]

_NONE = Listing((), 0, 0, False)


@dataclass(frozen=True, slots=True)
class ShowReport:
    """One node, and its ``outgoing`` and ``incoming`` edge rows as a ``Listing`` each."""

    id: str = ""
    type: str = ""
    state: str = ""
    roles: tuple[str, ...] = ()
    attributes: Mapping[str, Any] | None = None
    locations: tuple[Mapping[str, Any], ...] = ()
    provenance: tuple[Mapping[str, Any], ...] = ()
    outgoing: Listing = _NONE
    incoming: Listing = _NONE
    problems: tuple[Problem, ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def _first(locations: list[dict[str, Any]]) -> tuple[str, int]:
    return (locations[0]["file"], locations[0]["line"]) if locations else ("", 0)


def _rows(index: MapIndex, edges: list[dict[str, Any]], end: str) -> list[dict[str, Any]]:
    """Edge rows sorted by kind, then other-end id, then first location."""
    rows = []
    for edge in edges:
        other = index.nodes[edge[end]]
        confidences = {as_text(p["confidence"]) for p in edge["provenance"] if "confidence" in p}
        rows.append(
            {
                "kind": as_text(edge["kind"]),
                "other": as_text(other["id"]),
                "other_type": as_text(other["type"]),
                "other_state": as_text(other["state"]),
                "locations": _placed(edge["locations"]),
                "occurrences": edge.get("occurrences"),
                "confidences": sorted(confidences),
                "rules": sorted({f"{p['pack']}:{p['rule']}" for p in edge["provenance"]}),
            }
        )
    return sorted(rows, key=lambda r: (r["kind"], r["other"], _first(r["locations"])))


def run(
    start: Path,
    env: Mapping[str, str],
    node_id: str,
    limit: int,
    map_path: Path | None,
) -> ShowReport:
    """Show the node ``node_id``; a missing map or node is a problem, not a raise."""
    try:
        index = load_map(start, env, map_path)
        node_id = resolve(index, node_id)
        with reading_fields(start, map_path):
            node = index.node(node_id)
            attributes = node.get("attributes", {})
            if not isinstance(attributes, dict):
                raise TypeError(f"attributes is a {type(attributes).__name__}, not an object")
            for p in node["provenance"]:
                as_text(p["pack"])
                as_text(p["rule"])
                as_text(p.get("confidence", ""))
            return ShowReport(
                id=node["id"],
                type=as_text(node["type"]),
                state=as_text(node["state"]),
                roles=tuple(as_text(role) for role in node.get("roles", ())),
                attributes=attributes,
                locations=tuple(_placed(node["locations"])),
                provenance=tuple(node["provenance"]),
                outgoing=cut(_rows(index, index.outgoing(node_id), "to"), limit),
                incoming=cut(_rows(index, index.incoming(node_id), "from"), limit),
            )
    except HarnessError as error:
        return ShowReport(problems=(error.problem(),))


def _place(location: Mapping[str, Any]) -> str:
    return f"{location['file']}:{location['line']}"


def _placed(locations: Any) -> Any:
    """``locations`` unchanged, once each has the file and line the text report prints."""
    for location in locations:
        _place(location)
    return locations


def _edge_lines(listing: Listing) -> list[str]:
    lines = []
    kind = None
    for row in listing.items:
        if row["kind"] != kind:
            kind = row["kind"]
            lines.append(f"  {_escape(kind)}:")
        where = ", ".join(_place(loc) for loc in row["locations"]) or "no location"
        count = f"  x{row['occurrences']}" if row["occurrences"] else ""
        confidences = ",".join(_escape(c) for c in row["confidences"]) or "no confidence"
        lines.append(
            f"    {_escape(row['other'])}  {_escape(row['other_type'])}"
            f"  {_escape(row['other_state'])}"
            f"  {_escape(where)}{count}  {confidences}"
            f"  {_escape(', '.join(row['rules']))}"
        )
    note = footer(listing)
    return lines + ([f"  {note}"] if note else []) or ["  none"]


def render_text(report: ShowReport) -> str:
    """The report as lines a person reads. Every outside string goes through ``_escape``."""
    lines = [f"periplus show {_escape(report.id)}" if report.id else "periplus show"]
    if report.id:
        lines += [f"type: {_escape(report.type)}", f"state: {_escape(report.state)}"]
        if report.roles:
            lines.append(f"roles: {_escape(', '.join(report.roles))}")
        for key, value in sorted((report.attributes or {}).items()):
            lines.append(f"attribute {_escape(key)}: {_escape(json.dumps(value, sort_keys=True))}")
        lines += [f"location: {_escape(_place(loc))}" for loc in report.locations]
        for p in report.provenance:
            lines.append(
                f"provenance: {_escape(p['pack'])}:{_escape(p['rule'])}"
                f"  {_escape(p.get('confidence', 'no confidence'))}"
            )
        lines += ["", f"Outgoing ({report.outgoing.total}):", *_edge_lines(report.outgoing)]
        lines += ["", f"Incoming ({report.incoming.total}):", *_edge_lines(report.incoming)]
    lines += [f"{int(p.code)} {_escape(p.message)}" for p in report.problems]
    return "\n".join(lines) + "\n"


def render_json(report: ShowReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    document = {
        "id": report.id,
        "type": report.type,
        "state": report.state,
        "roles": list(report.roles),
        "attributes": dict(report.attributes or {}),
        "locations": list(report.locations),
        "provenance": list(report.provenance),
        "outgoing": payload(report.outgoing),
        "incoming": payload(report.incoming),
        "problems": [
            {"code": int(p.code), "message": p.message, "detail": dict(p.detail)}
            for p in report.problems
        ],
    }
    return json.dumps(document, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


RENDERERS = {"text": render_text, "json": render_json}
