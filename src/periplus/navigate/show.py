"""``periplus show``: one node and every edge arriving at it or leaving it, grouped by kind."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from importlib.resources import files
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from ruamel.yaml.error import YAMLError

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.layout import PROJECT_MARKER
from periplus.mapshared import first_error
from periplus.navigate.ids import resolve
from periplus.navigate.listing import (
    NONE,
    Listing,
    attribute_text,
    cut,
    edge_attributes,
    footer,
    mark_text,
    payload,
    place,
    problem_lines,
)
from periplus.navigate.mapfile import (
    MapIndex,
    _locate,
    as_json,
    as_text,
    is_whole,
    load_map,
    reading_fields,
)
from periplus.navigate.source import SourceLines, located, source_line, where
from periplus.report import _escape, _json_problem
from periplus.settings import find_project_root
from periplus.skills_install import SKILLS_DIRECTORY
from periplus.yamlread import load

__all__ = [
    "RENDERERS",
    "Description",
    "MANY_RENDERERS",
    "EdgeRow",
    "Location",
    "ShowReport",
    "ShowReports",
    "descriptions_path",
    "listed",
    "node_descriptions",
    "read_descriptions",
    "render_json",
    "render_text",
    "run",
    "run_many",
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
    """One edge at the shown node: its kind, the other end, where it is, and why it is there.

    ``location`` is the edge's first location, or the other end's when the edge has none, and
    ``source`` the line of code there. ``supporting`` marks an other end in supporting code,
    ``other_marks`` holds the other end's mark texts, and ``attributes`` the edge's own.
    ``other_description`` is the other end's entry in the descriptions file, when it has one.
    """

    kind: str
    other: str
    other_type: str
    other_state: str
    locations: tuple[Location, ...]
    occurrences: int | float | None
    confidences: tuple[str, ...]
    rules: tuple[str, ...]
    description: Description | None = None
    location: str | None = None
    source: str | None = None
    supporting: bool = False
    other_marks: tuple[str, ...] = ()
    attributes: Mapping[str, Any] = field(default_factory=dict)
    other_description: Description | None = None


@dataclass(frozen=True, slots=True)
class ShowReport:
    """One node, and its ``outgoing`` and ``incoming`` edge rows as a ``Listing`` each.

    ``forms`` are the nodes that stand for it across realizing edges, as (id, type, kind, the node
    each stands for), and ``more_forms`` how many more there are past the cap. ``marks`` holds the
    node's mark texts."""

    id: str = ""
    type: str = ""
    state: str = ""
    marks: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()
    attributes: Mapping[str, Any] | None = None
    locations: tuple[Mapping[str, Any], ...] = ()
    provenance: tuple[Mapping[str, Any], ...] = ()
    description: Description | None = None
    outgoing: Listing[EdgeRow] = NONE
    incoming: Listing[EdgeRow] = NONE
    forms: tuple[tuple[str, str, str, str], ...] = ()
    more_forms: int = 0
    warnings: tuple[str, ...] = ()
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
    entries: Mapping[str, Any],
) -> list[EdgeRow]:
    """Edge rows sorted by kind, then other-end id, then first location; those whose other end is
    supporting code after the rest."""
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
                where(edge, other),
                supporting=index.supporting(edge[end]) is not None,
                other_marks=index.marks(edge[end]),
                attributes=edge_attributes(edge),
                other_description=_entry(entries[edge[end]]) if edge[end] in entries else None,
            )
        )
    return sorted(rows, key=lambda r: (r.supporting, r.kind, r.other, _first(r.locations)))


@dataclass(frozen=True, slots=True)
class ShowReports:
    """One ``ShowReport`` for each id asked, in the order asked."""

    reports: tuple[ShowReport, ...]

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code any report stopped with, or ``OK`` when none did."""
        return min((r.exit_code for r in self.reports if r.exit_code), default=ExitCode.OK)

    @property
    def warnings(self) -> tuple[str, ...]:
        """Every report's warnings, in order."""
        return tuple(w for r in self.reports for w in r.warnings)

    @property
    def problems(self) -> tuple[Problem, ...]:
        """Every report's problems, in order."""
        return tuple(p for r in self.reports for p in r.problems)


def run(
    start: Path,
    env: Mapping[str, str],
    node_id: str,
    limit: int,
    map_path: Path | None,
) -> ShowReport:
    """Show the node ``node_id``; a missing map or node is a problem, not a raise."""
    return run_many(start, env, [node_id], limit, map_path).reports[0]


def run_many(
    start: Path,
    env: Mapping[str, str],
    ids: Sequence[str],
    limit: int,
    map_path: Path | None,
) -> ShowReports:
    """Show each of ``ids`` from one load of the map, as ``run`` shows one. The descriptions
    file's problems go with the first report."""
    try:
        index = load_map(start, env, map_path)
        document, problems = _descriptions(_locate(start, map_path))
        nodes = document.get("nodes", {})
        edges = {(e["from"], e["kind"], e["to"]): _entry(e) for e in document.get("edges", [])}
        lines = SourceLines(start, map_path)
    except HarnessError as error:
        return ShowReports((ShowReport(problems=(error.problem(),)),))
    told = (nodes, edges)
    return ShowReports(
        tuple(
            _one(start, map_path, index, told, lines, node_id, limit, () if n else problems)
            for n, node_id in enumerate(ids)
        )
    )


def _one(
    start: Path,
    map_path: Path | None,
    index: MapIndex,
    described: tuple[Mapping[str, Any], Mapping[tuple[str, str, str], Description]],
    lines: SourceLines,
    node_id: str,
    limit: int,
    problems: tuple[Problem, ...],
) -> ShowReport:
    """The report of one node; a missing node is a problem, not a raise."""
    nodes, edges = described
    try:
        with reading_fields(start, map_path):
            node_id, resolved = resolve(index, node_id)
            node = index.node(node_id)
            attributes = node.get("attributes", {})
            if not isinstance(attributes, dict):
                raise TypeError(f"attributes is a {type(attributes).__name__}, not an object")
            found, more_forms = index.stand_ins(node_id)
            forms = tuple(
                (other, as_text(index.nodes[other]["type"]), as_text(edge["kind"]), via)
                for other, edge, via in found
            )
            for p in node["provenance"]:
                as_text(p["pack"])
                as_text(p["rule"])
                as_text(p.get("confidence", ""))
            return ShowReport(
                id=node["id"],
                type=as_text(node["type"]),
                state=as_text(node["state"]),
                marks=index.marks(node_id),
                roles=tuple(as_text(role) for role in node.get("roles", ())),
                attributes=attributes,
                locations=tuple(_placed(node["locations"])),
                provenance=tuple(node["provenance"]),
                description=_entry(nodes[node_id]) if node_id in nodes else None,
                outgoing=_shown(
                    _rows(index, index.outgoing(node_id), "to", edges, nodes), limit, lines
                ),
                incoming=_shown(
                    _rows(index, index.incoming(node_id), "from", edges, nodes), limit, lines
                ),
                forms=forms,
                more_forms=more_forms,
                warnings=resolved,
                problems=problems,
            )
    except HarnessError as error:
        return ShowReport(problems=(error.problem(),))


def _shown(rows: list[EdgeRow], limit: int, lines: SourceLines) -> Listing[EdgeRow]:
    """The first ``limit`` rows, each with its source line read."""
    listing = cut(rows, limit)
    items = tuple(replace(row, source=lines.at(row.location)) for row in listing.items)
    return replace(listing, items=items)


def _descriptions(map_file: Path) -> tuple[Mapping[str, Any], tuple[Problem, ...]]:
    """The project's descriptions file: empty when absent, a problem when unreadable.

    Found as ``descriptions_path`` finds it.
    """
    path = descriptions_path(map_file)
    if not path.is_file():
        return {}, ()
    try:
        document = load(path.read_text(encoding="utf-8"))
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


def descriptions_path(map_file: Path) -> Path:
    """Where the descriptions file of ``map_file`` is: found from the folder of ``map_file``, so a
    slice at the project root and another project's map each read their own; beside ``map_file``
    only when no project is found."""
    folder = map_file.absolute().parent
    root = find_project_root(folder)
    return root / PROJECT_MARKER / DESCRIPTIONS if root else folder / DESCRIPTIONS


def read_descriptions(
    start: Path, map_path: Path | None
) -> tuple[Path, Mapping[str, Any], tuple[Problem, ...]]:
    """The descriptions file's path, its document as ``_descriptions`` reads it, and the
    problems."""
    map_file = _locate(start, map_path)
    return (descriptions_path(map_file), *_descriptions(map_file))


def node_descriptions(
    start: Path, map_path: Path | None
) -> tuple[dict[str, str], tuple[Problem, ...]]:
    """Each described node's text by id, and the problems ``_descriptions`` found."""
    document, problems = _descriptions(_locate(start, map_path))
    return {i: entry["text"] for i, entry in document.get("nodes", {}).items()}, problems


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
        "other_marks": list(row.other_marks),
        "attributes": dict(row.attributes),
        "locations": [_json_location(loc) for loc in row.locations],
        "occurrences": row.occurrences,
        "confidences": list(row.confidences),
        "rules": list(row.rules),
        "description": _json_description(row.description),
        "other_description": _json_description(row.other_description),
        "location": row.location,
        "source": row.source,
        "supporting": row.supporting,
    }


def _edge_lines(listing: Listing[EdgeRow]) -> list[str]:
    lines = []
    kind = None
    supporting = False
    for row in listing.items:
        if row.supporting and not supporting:
            supporting, kind = True, None
            lines.append("  in supporting code:")
        if row.kind != kind:
            kind = row.kind
            lines.append(f"  {_escape(kind)}:")
        where = ", ".join(place(_json_location(loc)) for loc in row.locations) or located(
            row.location
        )
        count = f"  x{row.occurrences}" if row.occurrences else ""
        confidences = ",".join(_escape(c) for c in row.confidences) or "no confidence"
        lines.append(
            f"    {_escape(row.other)}  {_escape(row.other_type)}"
            f"  {_escape(row.other_state)}"
            f"  {_escape(where)}{count}  {confidences}"
            f"  {_escape(', '.join(row.rules))}{attribute_text(row.attributes)}"
            f"{mark_text(row.other_marks)}"
        )
        lines += source_line(row.source)
        if row.description is not None:
            lines.append(f"      description: {_described(row.description)}")
        if row.other_description is not None:
            lines.append(f"      other description: {_described(row.other_description)}")
    note = footer(listing)
    return lines + ([f"  {note}"] if note else []) or ["  none"]


def _form_lines(report: ShowReport) -> list[str]:
    """The nodes that stand for the shown node: each with its type, the realizing kind, and the
    node it stands for when that is not the shown node; none when there are none."""
    if not report.forms:
        return []
    lines = ["", f"Realized by ({len(report.forms) + report.more_forms}):"]
    for other, kind_of, kind, via in report.forms:
        through = f" from {_escape(via)}" if via != report.id else ""
        lines.append(f"  {_escape(other)}  {_escape(kind_of)}  by {_escape(kind)}{through}")
    return lines + ([f"  +{report.more_forms} more"] if report.more_forms else [])


def render_text(report: ShowReport) -> str:
    """The report as lines a person reads. Every outside string goes through ``_escape``."""
    lines = [
        f"periplus show {_escape(report.id)}{mark_text(report.marks)}"
        if report.id
        else "periplus show"
    ]
    if report.id:
        lines += [f"type: {_escape(report.type)}", f"state: {_escape(report.state)}"]
        if report.roles:
            lines.append(f"roles: {_escape(', '.join(report.roles))}")
        for key, value in sorted((report.attributes or {}).items()):
            # json.dumps prints one line of ASCII; _escape would double its backslashes.
            lines.append(f"attribute {_escape(key)}: {json.dumps(value, sort_keys=True)}")
        lines += [f"location: {_escape(place(loc))}" for loc in report.locations]
        for p in report.provenance:
            lines.append(
                f"provenance: {_escape(p['pack'])}:{_escape(p['rule'])}"
                f"  {_escape(p.get('confidence', 'no confidence'))}"
            )
        lines.append(f"description: {_described(report.description)}")
        lines += ["", f"Outgoing ({report.outgoing.total}):", *_edge_lines(report.outgoing)]
        lines += ["", f"Incoming ({report.incoming.total}):", *_edge_lines(report.incoming)]
        lines += _form_lines(report)
    lines += [f"warning: {_escape(w)}" for w in report.warnings]
    lines += problem_lines(report.problems)
    return "\n".join(lines) + "\n"


def render_json(report: ShowReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    document = {
        "id": report.id,
        "type": report.type,
        "state": report.state,
        "marks": list(report.marks),
        "roles": list(report.roles),
        "attributes": dict(report.attributes or {}),
        "locations": list(report.locations),
        "provenance": list(report.provenance),
        "description": _json_description(report.description),
        "outgoing": payload(report.outgoing, _json_row),
        "incoming": payload(report.incoming, _json_row),
        "realized_by": {
            "items": [
                {"id": other, "type": kind_of, "kind": kind, "stands_for": via}
                for other, kind_of, kind, via in report.forms
            ],
            "more": report.more_forms,
        },
        "warnings": list(report.warnings),
        "problems": [_json_problem(p) for p in report.problems],
    }
    return as_json(document)


def render_many_text(shown: ShowReports) -> str:
    """Each report as ``render_text`` prints it, a ``---`` line between two."""
    return "---\n".join(render_text(report) for report in shown.reports)


def render_many_json(shown: ShowReports) -> str:
    """One report as ``render_json`` prints it; several as ``{"shown": [...]}``, one each."""
    if len(shown.reports) == 1:
        return render_json(shown.reports[0])
    return as_json({"shown": [json.loads(render_json(report)) for report in shown.reports]})


def listed(shown: ShowReports) -> tuple[str, ...]:
    """The ids ``--ids`` prints: the other end of every edge row, outgoing then incoming, each
    once, report by report."""
    ends = (
        row.other
        for report in shown.reports
        for listing in (report.outgoing, report.incoming)
        for row in listing.items
    )
    return tuple(dict.fromkeys(ends))


RENDERERS = {"text": render_text, "json": render_json}
MANY_RENDERERS = {"text": render_many_text, "json": render_many_json}
