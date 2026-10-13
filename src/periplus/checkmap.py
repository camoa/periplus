"""``periplus check-map``: check a written map against the map schema.

The navigation commands check only a map's outline, so a deep schema error is reported here. The
map is found as ``load_map`` finds it, and the errors are sorted as ``periplus map`` sorts them.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from jsonschema import Draft202012Validator

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.navigate.mapfile import MAP_SCHEMA, _read
from periplus.report import _escape
from periplus.validate import _schema

__all__ = ["RENDERERS", "CheckReport", "render_json", "render_text", "run"]


@dataclass(frozen=True, slots=True)
class CheckReport:
    """The map checked, or ``None`` when none was found, and what is wrong with it."""

    map_path: str | None
    problems: tuple[Problem, ...]

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def run(start: Path, env: Mapping[str, str], map_path: Path | None) -> CheckReport:
    """Check the map at ``map_path``, or at ``<root>/.periplus/map.json`` when none is given."""
    try:
        path, document = _read(start, map_path)
    except HarnessError as error:
        found = error.detail.get("path")
        return CheckReport(str(found) if found is not None else None, (error.problem(),))
    invalid = sorted(
        Draft202012Validator(_schema(MAP_SCHEMA)).iter_errors(document),
        key=lambda found: (list(map(str, found.absolute_path)), found.message),
    )
    if invalid:
        message = f"{path} does not match the map schema: {invalid[0].message}"
        problem = Problem(ExitCode.NOT_A_MAP, message, {"path": str(path)})
        return CheckReport(str(path), (problem,))
    return CheckReport(str(path), ())


def render_text(report: CheckReport) -> str:
    """One line: the map matches the schema, or the problem."""
    if not report.problems and report.map_path is not None:
        return f"{_escape(report.map_path)} matches the map schema\n"
    return "".join(f"{_escape(problem.message)}\n" for problem in report.problems)


def render_json(report: CheckReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    payload = {
        "map": report.map_path,
        "valid": not report.problems,
        "problems": [
            {"code": int(p.code), "message": p.message, "detail": dict(p.detail)}
            for p in report.problems
        ],
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


#: The formats ``check-map --format`` offers. ``cli.build_parser`` writes the same two names as a
#: literal, because ``cli`` may not import this module.
RENDERERS: Mapping[str, Callable[[CheckReport], str]] = {
    "text": render_text,
    "json": render_json,
}
