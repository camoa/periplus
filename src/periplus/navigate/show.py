"""``periplus show``: one node and every edge arriving at it or leaving it, grouped by kind."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.layout import PROJECT_MARKER
from periplus.mapshared import first_error
from periplus.navigate.ids import resolve
from periplus.navigate.listing import NONE, Listing, cut, footer, payload, place
from periplus.navigate.mapfile import (
    MapIndex,
    _locate,
    as_json,
    as_text,
    is_whole,
    load_map,
    reading_fields,
)
from periplus.report import _escape, _json_problem
from periplus.settings import find_project_root
from periplus.skills_install import SKILLS_DIRECTORY

__all__ = [
    "RENDERERS",
    "Description",
    "EdgeRow",
    "Location",
    "ShowReport",
    "render_json",
    "render_text",
    "run",
]

#: The hand-written file that says what a node or edge does: the project's
#: ``.periplus/descriptions.yaml``, found by walking up from the map file's folder, or the one
#: beside the map file when no project is found.
DESCRIPTIONS = "descriptions.yaml"
#: Below the skills folder, one segment each: ``joinpath`` need not accept a separator.
_DESCRIPTIONS_SCHEMA = ("periplus-map", "references", "descriptions.schema.json")


@dataclass(frozen=True, slots=True)
class Description:
    """A descriptions entry as show reports it: its text, and the file and line it names."""

    text: str
    file: str
    line: int


@dataclass(frozen=True, slots=True)
class Location:
    """A file and the line in it."""

    file: str
    line: int | float


@dataclass(frozen=True, slots=True)
class EdgeRow:
    """One edge at the shown node: its kind, the other end, where it is, and why it is there."""

    kind: str
    other: str
    other_type: str
    other_state: str
    locations: tuple[Location, ...]
    occurrences: int | float | None
    confidences: tuple[str, ...]
    rules: tuple[str, ...]
    description: Description | None = None


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
    description: Description | None = None
    outgoing: Listing[EdgeRow] = NONE
    incoming: Listing[EdgeRow] = NONE
    problems: tuple[Problem, ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def _first(locations: tuple[Location, ...]) -> tuple[str, int | float]:
    return (locations[0].file, locations[0].line) if locations else ("", 0)


def _whole(value: Any) -> int | float:
    """``value``, which a report prints as a count or line; a ``TypeError`` when it is not whole."""
    if not is_whole(value):
        raise TypeError(f"expected a whole number, got {type(value).__name__} {value!r}")
    return value


def _rows(
    index: MapIndex,
    edges: list[dict[str, Any]],
    end: str,
    described: Mapping[tuple[str, str, str], Description],
) -> list[EdgeRow]:
    """Edge rows sorted by kind, then other-end id, then first location."""
    rows = []
    for edge in edges:
        other = index.nodes[edge[end]]
        confidences = {as_text(p["confidence"]) for p in edge["provenance"] if "confidence" in p}
        occurrences = edge.get("occurrences")
        rows.append(
            EdgeRow(
                as_text(edge["kind"]),
                as_text(other["id"]),
                as_text(other["type"]),
                as_text(other["state"]),
                tuple(
                    Location(as_text(loc["file"]), _whole(loc["line"])) for loc in edge["locations"]
                ),
                None if occurrences is None else _whole(occurrences),
                tuple(sorted(confidences)),
                tuple(sorted({f"{p['pack']}:{p['rule']}" for p in edge["provenance"]})),
                described.get((edge["from"], edge["kind"], edge["to"])),
            )
        )
    return sorted(rows, key=lambda r: (r.kind, r.other, _first(r.locations)))


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
        document, problems = _descriptions(_locate(start, map_path))
        nodes = document.get("nodes", {})
        edges = {(e["from"], e["kind"], e["to"]): _entry(e) for e in document.get("edges", [])}
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
                description=_entry(nodes[node_id]) if node_id in nodes else None,
                outgoing=cut(_rows(index, index.outgoing(node_id), "to", edges), limit),
                incoming=cut(_rows(index, index.incoming(node_id), "from", edges), limit),
                problems=problems,
            )
    except HarnessError as error:
        return ShowReport(problems=(error.problem(),))


def _descriptions(map_file: Path) -> tuple[Mapping[str, Any], tuple[Problem, ...]]:
    """The project's descriptions file: empty when absent, a problem when unreadable.

    Found from the folder of ``map_file``, so a slice at the project root and another
    project's map each read their own; beside ``map_file`` only when no project is found.
    """
    folder = map_file.absolute().parent
    root = find_project_root(folder)
    path = root / PROJECT_MARKER / DESCRIPTIONS if root else folder / DESCRIPTIONS
    if not path.is_file():
        return {}, ()
    try:
        document = YAML(typ="safe", pure=True).load(path.read_text(encoding="utf-8"))
    except (YAMLError, OSError, UnicodeDecodeError) as error:
        detail = {"path": str(path), "detail": str(error)}
        return {}, (Problem(ExitCode.NOT_A_MAP, f"{path} is not readable YAML", detail),)
    node = files("periplus") / SKILLS_DIRECTORY
    for segment in _DESCRIPTIONS_SCHEMA:
        node = node / segment
    schema = json.loads(node.read_text(encoding="utf-8"))
    invalid = first_error(Draft202012Validator(schema).iter_errors(document))
    if invalid is None:
        return document, ()
    message = f"{path} does not match the descriptions schema: {invalid.message}"
    return {}, (Problem(ExitCode.NOT_A_MAP, message, {"path": str(path)}),)


def _entry(entry: Mapping[str, Any]) -> Description:
    """A descriptions entry as show reports it: its text, file and line."""
    return Description(entry["text"], entry["file"], entry["line"])


def _described(entry: Description | None) -> str:
    if entry is None:
        return "none"
    return f"{_escape(entry.text)} ({_escape(entry.file)}:{entry.line})"


def _json_description(entry: Description | None) -> dict[str, Any] | None:
    return None if entry is None else {"text": entry.text, "file": entry.file, "line": entry.line}


def _placed(locations: Any) -> Any:
    """``locations`` unchanged, once each has the file and line the text report prints."""
    for location in locations:
        place(location)
    return locations


def _json_location(location: Location) -> dict[str, Any]:
    return {"file": location.file, "line": location.line}


def _json_row(row: EdgeRow) -> dict[str, Any]:
    return {
        "kind": row.kind,
        "other": row.other,
        "other_type": row.other_type,
        "other_state": row.other_state,
        "locations": [_json_location(loc) for loc in row.locations],
        "occurrences": row.occurrences,
        "confidences": list(row.confidences),
        "rules": list(row.rules),
        "description": _json_description(row.description),
    }


def _edge_lines(listing: Listing[EdgeRow]) -> list[str]:
    lines = []
    kind = None
    for row in listing.items:
        if row.kind != kind:
            kind = row.kind
            lines.append(f"  {_escape(kind)}:")
        where = ", ".join(place(_json_location(loc)) for loc in row.locations) or "no location"
        count = f"  x{row.occurrences}" if row.occurrences else ""
        confidences = ",".join(_escape(c) for c in row.confidences) or "no confidence"
        lines.append(
            f"    {_escape(row.other)}  {_escape(row.other_type)}"
            f"  {_escape(row.other_state)}"
            f"  {_escape(where)}{count}  {confidences}"
            f"  {_escape(', '.join(row.rules))}"
        )
        if row.description is not None:
            lines.append(f"      description: {_described(row.description)}")
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
        lines += [f"location: {_escape(place(loc))}" for loc in report.locations]
        for p in report.provenance:
            lines.append(
                f"provenance: {_escape(p['pack'])}:{_escape(p['rule'])}"
                f"  {_escape(p.get('confidence', 'no confidence'))}"
            )
        lines.append(f"description: {_described(report.description)}")
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
        "description": _json_description(report.description),
        "outgoing": payload(report.outgoing, _json_row),
        "incoming": payload(report.incoming, _json_row),
        "problems": [_json_problem(p) for p in report.problems],
    }
    return as_json(document)


RENDERERS = {"text": render_text, "json": render_json}
