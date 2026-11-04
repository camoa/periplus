"""``periplus export``: print a map as GraphML, DOT or Mermaid text."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.navigate.listing import first_location
from periplus.navigate.mapfile import load_document, reading_fields
from periplus.report import _escape

__all__ = ["WRITERS", "ExportReport", "render_text", "run"]

_MERMAID_EDGES = 500
_MERMAID_CHARS = 50_000


@dataclass(frozen=True, slots=True)
class ExportReport:
    """The exported text, with warnings and problems; ``text`` is empty after a problem."""

    format: str = ""
    text: str = ""
    warnings: tuple[str, ...] = ()
    problems: tuple[Problem, ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def _attr(value: str) -> str:
    return escape(value, {'"': "&quot;"})


def _graphml(document: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    keys = (
        ("node", "type", "string"),
        ("node", "state", "string"),
        ("node", "file", "string"),
        ("node", "line", "int"),
        ("edge", "kind", "string"),
        ("edge", "file", "string"),
        ("edge", "line", "int"),
    )
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
    ]
    lines += [
        f'  <key id="{scope}_{name}" for="{scope}" attr.name="{name}" attr.type="{kind}"/>'
        for scope, name, kind in keys
    ]
    lines.append('  <graph id="G" edgedefault="directed">')

    def data(scope: str, values: list[tuple[str, str]]) -> list[str]:
        return [f'      <data key="{scope}_{n}">{escape(v)}</data>' for n, v in values]

    for node in document["nodes"]:
        values = [("type", node["type"]), ("state", node["state"])]
        where = first_location(node)
        if where:
            values += [("file", where["file"]), ("line", str(where["line"]))]
        lines.append(f'    <node id="{_attr(node["id"])}">')
        lines += data("node", values)
        lines.append("    </node>")
    for edge in document["edges"]:
        values = [("kind", edge["kind"])]
        where = first_location(edge)
        if where:
            values += [("file", where["file"]), ("line", str(where["line"]))]
        lines.append(f'    <edge source="{_attr(edge["from"])}" target="{_attr(edge["to"])}">')
        lines += data("edge", values)
        lines.append("    </edge>")
    lines += ["  </graph>", "</graphml>"]
    return "\n".join(lines) + "\n", ()


# The lexer keeps `\\` as two characters and reads `\"` as a quote, so a name holding a
# backslash cannot be written as itself. Doubling every backslash keeps every id a distinct
# name that always parses, and the label carries the id as written.
def _dot_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _dot(document: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    lines = ["digraph periplus {"]
    for node in document["nodes"]:
        label = _dot_quote(node["id"])[1:-1] + "\\n" + _dot_quote(node["type"])[1:-1]
        lines.append(f'  {_dot_quote(node["id"])} [label="{label}"];')
    for edge in document["edges"]:
        ends = f"{_dot_quote(edge['from'])} -> {_dot_quote(edge['to'])}"
        lines.append(f"  {ends} [label={_dot_quote(edge['kind'])}];")
    lines.append("}")
    return "\n".join(lines) + "\n", ()


def _mermaid_text(value: str) -> str:
    return value.replace("#", "#35;").replace('"', "#quot;")


def _mermaid(document: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    token = {node["id"]: f"n{n}" for n, node in enumerate(document["nodes"])}
    lines = ["flowchart LR"]
    for node in document["nodes"]:
        label = _mermaid_text(f"{node['id']} ({node['type']})")
        lines.append(f'  {token[node["id"]]}["{label}"]')
    for edge in document["edges"]:
        kind = _mermaid_text(edge["kind"])
        lines.append(f'  {token[edge["from"]]} -- "{kind}" --> {token[edge["to"]]}')
    text = "\n".join(lines) + "\n"
    warnings = []
    if len(document["edges"]) > _MERMAID_EDGES:
        warnings.append(
            f"{len(document['edges'])} edges is above Mermaid's default limit of "
            f"{_MERMAID_EDGES}; it may not render"
        )
    if len(text) > _MERMAID_CHARS:
        warnings.append(
            f"{len(text)} characters is above Mermaid's default limit of "
            f"{_MERMAID_CHARS:,}; it may not render"
        )
    return text, tuple(warnings)


WRITERS: dict[str, Callable[[Mapping[str, Any]], tuple[str, tuple[str, ...]]]] = {
    "graphml": _graphml,
    "dot": _dot,
    "mermaid": _mermaid,
}


def run(start: Path, env: Mapping[str, str], format: str, map_path: Path | None) -> ExportReport:
    """Write the map found from ``start`` in ``format``, one of the keys of ``WRITERS``."""
    try:
        writer = WRITERS[format]
        _, document = load_document(start, env, map_path)
        with reading_fields(start, map_path):
            text, warnings = writer(document)
    except HarnessError as error:
        return ExportReport(format, problems=(error.problem(),))
    return ExportReport(format, text, warnings)


def render_text(report: ExportReport) -> str:
    """The warnings and problems as lines a person reads. Every outside string is escaped."""
    lines = [f"warning: {_escape(w)}\n" for w in report.warnings]
    lines += [f"{int(p.code)} {_escape(p.message)}\n" for p in report.problems]
    return "".join(lines)
