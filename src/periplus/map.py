"""``periplus map``: extract the map of a project and write it.

The shape follows ``validate`` and ``spec``: frozen records, an ``exit_code`` property, and a
``RENDERERS`` table keyed by ``--format``'s two choices. All extraction lives in the
``periplus.engine`` package. This module links settings, packs, the engine and the write.

It names no stack. Every folder, type and rule comes from a loaded pack.
"""

from __future__ import annotations

import json
import os
import posixpath
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

import periplus
from periplus.engine.check import checked
from periplus.engine.emit import build_document, render
from periplus.engine.rules import run_file_rules
from periplus.engine.select import Selection, files_in, holds_double_star, resolve_folders
from periplus.errors import ExitCode, HarnessError, Problem
from periplus.layout import PROJECT_MARKER, SETTINGS_FILENAME
from periplus.manifest import resolve_pack_order
from periplus.preflight import DependencyStatus
from periplus.report import _escape
from periplus.resolution import resolve
from periplus.validate import _schema

__all__ = ["RENDERERS", "MapReport", "render_json", "render_text", "run"]

#: The shipped schema the built document is checked against before anything is written.
MAP_SCHEMA = "schema/map.schema.json"

#: The map's default home, under the project root.
_DEFAULT_MAP = "map.json"


@dataclass(frozen=True, slots=True)
class MapReport:
    """One ``map`` run. ``map_path`` is ``None`` when nothing was written."""

    map_path: str | None
    nodes: int
    edges: int
    packs: tuple[tuple[str, str], ...]
    executed: tuple[tuple[str, str, int], ...]
    not_executed: tuple[tuple[str, str, str], ...]
    problems: tuple[Problem, ...]
    opened: tuple[str, ...] = ()
    differing: tuple[tuple[str, str], ...] = ()
    selected: int = 0
    excluded: int = 0
    parse_errors: tuple[str, ...] = ()
    skipped: tuple[tuple[str, int, str, str], ...] = ()
    #: The files below the rules' folders, after excludes, that no executed rule selected.
    unread: tuple[str, ...] = ()
    #: The folders below the rules' folders that the unread walk could not list.
    unlisted: tuple[str, ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)

    @property
    def idle(self) -> tuple[tuple[str, str], ...]:
        """The executed rules that fired zero times."""
        return tuple((pack, rule) for pack, rule, fires in self.executed if fires == 0)


def run(
    start: Path,
    env: Mapping[str, str],
    dependencies: tuple[DependencyStatus, ...],
    settings_path: Path | None = None,
    output: Path | None = None,
) -> MapReport:
    """Resolve the project, run its rules, validate the document and write it.

    A problem the resolution already carries ends the run with its code before any file is
    selected. A project with no settings file is ``NO_SETTINGS``. A pack that fails its schema
    does not hide the problems of the packs that do not depend on it. Nothing is written on any
    failure.
    """
    resolution = resolve(
        start=start, env=env, dependencies=dependencies, settings_path=settings_path
    )
    problems = list(resolution.problems)
    project = next(
        (s for s in resolution.settings_sources if s.kind == "project" and s.status == "used"),
        None,
    )
    if not problems and (project is None or resolution.settings is None):
        problems.append(
            Problem(
                ExitCode.NO_SETTINGS,
                f"no {PROJECT_MARKER}/{SETTINGS_FILENAME} found for this project",
                {},
            )
        )
    if problems or project is None or resolution.settings is None:
        return _failed(problems)
    if not resolution.packs:
        message = (
            f"no rutter is pinned: list one under packs in {PROJECT_MARKER}/{SETTINGS_FILENAME}; "
            "periplus status shows the bundled rutters"
        )
        return _failed([Problem(ExitCode.MAP_INVALID, message, {"setting": "packs"})])

    packs, pack_problems = resolve_pack_order(resolution.packs, resolution.candidates)
    if pack_problems:
        return _failed(pack_problems)
    root = project.root
    given = resolution.settings.values
    values = {name: setting.value for name, setting in given.items()}
    origins = {name: setting.sources[-1].name for name, setting in given.items()}
    rule_set, refused = checked(packs, values, origins)
    try:
        if rule_set is None or refused:
            return _failed(refused)
        wanted = sorted(
            {name for rule in rule_set.rules if rule.supported for name in rule.folders}
        )
        # A path value relative to a folder needs its directories; the unread walk stays on rules.
        relative = {v.relative_to for i in rule_set.files.values() for v in i.path_values}
        overrides = {n: setting.value for n, setting in resolution.settings.folders.items()}
        settings = resolution.settings
        first_party = settings.first_party.value if settings.first_party else None
        selection = Selection.build(
            packs,
            {name: setting.value for name, setting in settings.extensions.items()},
            first_party.include if first_party else (),
            first_party.exclude if first_party else (),
            settings.exclude.value if settings.exclude else (),
            settings.re_include.value if settings.re_include else (),
        )
        deep = sorted(name for name in relative - {""} if holds_double_star(name, packs, overrides))
        if deep:
            message = (
                f"the folder {deep[0]}, which a path value is relative_to, holds ** in its value"
            )
            return _failed([Problem(ExitCode.FOLDER_UNRESOLVED, message, {"folder": deep[0]})])
        folders = resolve_folders(
            sorted({*wanted, *relative} - {""}), packs, overrides, root, selection
        )
        found_nodes, found_edges, fires, opened, read, removed, broken, skipped = run_file_rules(
            root, rule_set, packs, folders, selection
        )
        directories = sorted({path for name in wanted for path in folders[name]})
        listed, unlisted = files_in(root, directories, selection)
        unread = sorted(set(listed) - read)
        document = build_document(
            found_nodes,
            found_edges,
            rule_set.types,
            rule_set.edge_kinds,
            packs,
            periplus.__version__,
            Path(os.path.relpath(project.path, root)).as_posix(),
            boundary=rule_set.boundary,
            skipped=skipped,
        )
    except HarnessError as error:
        return _failed([error.problem()])
    declared = {info.id_namespace for info in rule_set.types.values() if info.id_namespace}
    undeclared = sorted(
        node["id"] for node in document["nodes"] if node["id"].partition("::")[0] not in declared
    )
    if undeclared:
        more = f", and {len(undeclared) - 1} more" if len(undeclared) > 1 else ""
        message = (
            "the built map holds an id whose namespace no loaded pack declares "
            f"(UNDECLARED_ID_NAMESPACE): {undeclared[0]}{more}"
        )
        detail = {"problem": "UNDECLARED_ID_NAMESPACE", "id": undeclared[0]}
        return _failed([Problem(ExitCode.MAP_INVALID, message, detail)])
    invalid = sorted(
        Draft202012Validator(_schema(MAP_SCHEMA)).iter_errors(document),
        key=lambda found: (list(map(str, found.absolute_path)), found.message),
    )
    if invalid:
        message = f"the built map does not match its schema: {invalid[0].message}"
        return _failed([Problem(ExitCode.MAP_INVALID, message, {})])

    target = start / output if output is not None else root / PROJECT_MARKER / _DEFAULT_MAP
    try:
        target.write_bytes(render(document).encode("utf-8"))
    except OSError as error:
        message = f"the map cannot be written to {target}: {error.strerror or error}"
        return _failed([Problem(ExitCode.OUTPUT_UNWRITABLE, message, {"path": str(target)})])
    return MapReport(
        map_path=str(target),
        nodes=len(document["nodes"]),
        edges=len(document["edges"]),
        packs=tuple(sorted((p.name.pack, p.name.version) for p in packs)),
        executed=tuple(sorted((pack, rule, count) for (pack, rule), count in fires.items())),
        not_executed=tuple(
            sorted(
                (rule.pack, rule.name, rule.reason) for rule in rule_set.rules if not rule.supported
            )
        ),
        problems=(),
        opened=tuple(opened),
        differing=_differing(document),
        selected=len(read),
        excluded=len(removed),
        parse_errors=tuple(broken),
        skipped=tuple(sorted(skipped)),
        unread=tuple(unread),
        unlisted=tuple(unlisted),
    )


def _differing(document: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    """Each node id and attribute name whose value is written with ``differs``."""
    return tuple(
        sorted(
            (node["id"], name)
            for node in document["nodes"]
            for name, value in node.get("attributes", {}).items()
            if isinstance(value, dict) and set(value) == {"differs"}
        )
    )


def _failed(problems: Sequence[Problem]) -> MapReport:
    return MapReport(
        None, 0, 0, (), (), (), tuple(sorted(problems, key=lambda p: (p.code, p.message)))
    )


def _section(heading: str, rows: Sequence[str]) -> list[str]:
    """A blank line, a heading, and the rows indented under it; ``none`` when there are none."""
    return ["", f"{heading}:", *[f"  {row}".rstrip() for row in rows or ["none"]]]


def render_text(report: MapReport) -> str:
    """The report as lines a person reads. Every outside string goes through ``_escape``."""
    lines = ["periplus map"]
    lines += _section(
        "Map",
        [
            f"{'path':<8}{_escape(report.map_path or 'not written')}",
            f"{'nodes':<8}{report.nodes}",
            f"{'edges':<8}{report.edges}",
        ],
    )
    lines += _section(
        "Files",
        [
            f"{'selected':<10}{report.selected}",
            f"{'excluded':<10}{report.excluded}",
            f"{'unread':<10}{len(report.unread)}",
            f"{'unlisted':<10}{len(report.unlisted)}",
        ],
    )
    endings = Counter(
        posixpath.splitext(posixpath.basename(path))[1].lstrip(".") for path in report.unread
    )
    lines += _section(
        "Files no rule read, by ending",
        [
            f"{_escape(ending or 'none')} {count}"
            for ending, count in sorted(endings.items(), key=lambda item: (-item[1], item[0]))
        ],
    )
    shown = [_escape(path) for path in report.unread[:20]]
    if len(report.unread) > 20:
        shown.append(f"and {len(report.unread) - 20} more; the JSON report lists them all")
    lines += _section("Files no rule read", shown)
    listed = [_escape(path) for path in report.unlisted[:20]]
    if len(report.unlisted) > 20:
        listed.append(f"and {len(report.unlisted) - 20} more; the JSON report lists them all")
    lines += _section("Folders that could not be listed", listed)
    lines += _section("Files that did not parse cleanly", [_escape(f) for f in report.parse_errors])
    lines += _section("Packs", [f"{_escape(p)} {_escape(v)}" for p, v in report.packs])
    lines += _section(
        "Rules executed",
        [f"{_escape(p)} {_escape(r)} fired {n}" for p, r, n in report.executed],
    )
    lines += _section(
        "Rules that fired zero times", [f"{_escape(p)} {_escape(r)}" for p, r in report.idle]
    )
    lines += _section(
        "Rules not executed",
        [f"{_escape(p)} {_escape(r)} {_escape(why)}" for p, r, why in report.not_executed],
    )
    lines += _section(
        "Matches skipped",
        [f"{_escape(f)}:{n} {_escape(r)} {_escape(why)}" for f, n, r, why in report.skipped],
    )
    lines += _section(
        "Attributes that differ between files",
        [f"{_escape(node)} {_escape(name)}" for node, name in report.differing],
    )
    lines += _section(
        "Problems",
        [f"{int(p.code)} {_escape(p.message)}" for p in report.problems],
    )
    return "\n".join(lines) + "\n"


def render_json(report: MapReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    payload = {
        "map": report.map_path,
        "nodes": report.nodes,
        "edges": report.edges,
        "packs": [{"pack": p, "version": v} for p, v in report.packs],
        "executed": [{"pack": p, "rule": r, "fires": n} for p, r, n in report.executed],
        "zero_fires": [{"pack": p, "rule": r} for p, r in report.idle],
        "not_executed": [
            {"pack": p, "rule": r, "reason": why} for p, r, why in report.not_executed
        ],
        "opened": list(report.opened),
        "parse_errors": list(report.parse_errors),
        "skipped": [
            {"file": f, "line": n, "rule": r, "reason": why} for f, n, r, why in report.skipped
        ],
        "differing": [{"node": n, "attribute": a} for n, a in report.differing],
        "selected": report.selected,
        "excluded": report.excluded,
        "unread": list(report.unread),
        "unlisted": list(report.unlisted),
        "problems": [
            {"code": int(p.code), "message": p.message, "detail": dict(p.detail)}
            for p in report.problems
        ],
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


#: The formats ``map --format`` offers. ``cli.build_parser`` writes the same two names as a
#: literal because ``cli`` may not import this module; a test asserts the two agree.
RENDERERS: Mapping[str, Callable[[MapReport], str]] = {
    "text": render_text,
    "json": render_json,
}
