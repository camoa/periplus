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
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

import periplus
from periplus.engine.check import checked
from periplus.engine.emit import LeftOut, build_document, render
from periplus.engine.packload import RuleSet
from periplus.engine.rules import MapPass, run_file_rules, run_map_rules, withhold_found
from periplus.engine.select import (
    FileTypes,
    Selection,
    base_folders,
    files_in,
    folder_problems,
    optional_folders,
    resolve_folders,
)
from periplus.errors import ExitCode, HarnessError, Problem
from periplus.layout import PROJECT_MARKER, SETTINGS_FILENAME
from periplus.manifest import LoadedPack, resolve_pack_order
from periplus.mapshared import _DEFAULT_MAP as _DEFAULT_MAP
from periplus.mapshared import MAP_SCHEMA as MAP_SCHEMA
from periplus.mapshared import _section as _section
from periplus.mapshared import first_error
from periplus.preflight import DependencyStatus
from periplus.report import _escape, _json_problem, amount
from periplus.resolution import folder_overrides, resolve, settings_values
from periplus.settings import ResolvedSettings
from periplus.validate import _schema

__all__ = ["RENDERERS", "MapReport", "render_json", "render_text", "run", "write_document"]


def write_document(document: Mapping[str, object], target: Path) -> tuple[Problem, ...]:
    """Check ``document`` against the map schema and write it; the problems found, if any."""
    invalid = first_error(Draft202012Validator(_schema(MAP_SCHEMA)).iter_errors(document))
    if invalid is not None:
        message = f"the map does not match its schema: {invalid.message}"
        return (Problem(ExitCode.MAP_INVALID, message, {}),)
    try:
        target.write_bytes(render(document).encode("utf-8"))
    except OSError as error:
        message = f"the map cannot be written to {target}: {error.strerror or error}"
        return (Problem(ExitCode.OUTPUT_UNWRITABLE, message, {"path": str(target)}),)
    return ()


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
    #: Each pass of the map rules, the last one adding nothing; empty when no map rule runs.
    map_passes: tuple[MapPass, ...] = ()
    #: The nodes and the edges of an internal type the written map leaves out.
    internal: LeftOut = LeftOut()
    #: Each boundary node and the number of edges into it, most first, then by id.
    boundaries: tuple[tuple[str, int], ...] = ()
    #: Each unknown boundary node as the pack whose rule set the mark and the reason.
    unknown: tuple[tuple[str, str], ...] = ()
    #: Each node of conflicting types and its candidates, by id.
    conflicts: tuple[tuple[str, tuple[str, ...]], ...] = ()
    #: Each pinned pack whose file rules selected no file, with each base folder its rules reach:
    #: the folder, its value as written, and the number of directories it resolved to.
    empty_packs: tuple[tuple[str, tuple[tuple[str, str, int], ...]], ...] = ()

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
    values, origins = settings_values(resolution.settings)
    rule_set, refused = checked(packs, values, origins)
    try:
        if rule_set is None or refused:
            return _failed(refused)
        wanted = sorted(
            {name for rule in rule_set.rules if rule.supported for name in rule.folders}
        )
        # A path value relative to a folder needs its directories; the unread walk stays on rules.
        relative = {v.relative_to for i in rule_set.files.values() for v in i.path_values}
        overrides = folder_overrides(resolution.settings)
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
        refused = list(folder_problems(rule_set, packs, overrides))
        if refused:
            return _failed(refused)
        folders = resolve_folders(
            sorted({*wanted, *relative} - {""}), packs, overrides, root, selection
        )
        found_nodes, found_edges, fires, opened, read, removed, broken, skipped = run_file_rules(
            root, rule_set, packs, folders, selection
        )
        pinned = {matched.name.pack for matched in resolution.packs}
        empty = _empty_packs(root, rule_set, packs, pinned, folders, read, overrides, selection)
        directories = sorted({path for name in wanted for path in folders[name]})
        listed, unlisted = files_in(root, directories, selection)
        unread = sorted(set(listed) - read)
        if not read:
            message = (
                "no file was selected, so no map was written and any existing map was left as it "
                "was: every pinned pack looked only in folders that hold none of its files; "
                f"declare where the code is under folders in {PROJECT_MARKER}/{SETTINGS_FILENAME}"
            )
            return replace(
                _failed([Problem(ExitCode.NOTHING_SELECTED, message, {"setting": "folders"})]),
                packs=tuple(sorted((p.name.pack, p.name.version) for p in packs)),
                excluded=len(removed),
                unread=tuple(unread),
                unlisted=tuple(unlisted),
                empty_packs=empty,
            )
        found_nodes, found_edges, withheld = withhold_found(rule_set, found_nodes, found_edges)
        fires.update(withheld)
        map_nodes, map_edges, map_fires, map_passes, unread_by_map = run_map_rules(
            rule_set, found_nodes, found_edges
        )
        skipped.extend(unread_by_map)
        fires.update(map_fires)
        document, left_out = build_document(
            [*found_nodes, *map_nodes],
            [*found_edges, *map_edges],
            rule_set.types,
            rule_set.edge_kinds,
            packs,
            periplus.__version__,
            Path(os.path.relpath(project.path, root)).as_posix(),
            boundary=rule_set.boundary,
            skipped=skipped,
            supporting=_supporting_paths(packs, settings),
            attributes=rule_set.attributes,
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
    target = start / output if output is not None else root / PROJECT_MARKER / _DEFAULT_MAP
    unwritten = write_document(document, target)
    if unwritten:
        return _failed(unwritten)
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
        map_passes=tuple(map_passes),
        internal=left_out,
        boundaries=_boundaries(document),
        unknown=_unknown(document),
        conflicts=tuple(
            (n["id"], tuple(n["attributes"]["type_conflict"]))
            for n in document["nodes"]
            if "type_conflict" in n.get("attributes", {})
        ),
        empty_packs=empty,
    )


def _empty_packs(
    root: Path,
    rule_set: RuleSet,
    packs: Sequence[LoadedPack],
    pinned: set[str],
    folders: Mapping[str, tuple[str, ...]],
    read: set[str],
    overrides: Mapping[str, str | Sequence[str]],
    selection: Selection,
) -> tuple[tuple[str, tuple[tuple[str, str, int], ...]], ...]:
    """Each pinned pack with file rules none of whose rules selected a file, with the base folders
    those rules reach. A file is a rule's when it sits directly in one of the rule's directories
    and a type of the rule's file type claims it, as ``select_files`` decides. An optional folder
    that finds no directory is left out of the row, and a pack left with none is not listed."""
    types = FileTypes.build(packs, selection.extensions)
    optional = optional_folders(packs)
    found = []
    for pack in sorted(pinned):
        rules = [r for r in rule_set.rules if r.pack == pack and r.supported and not r.matches_type]
        wanted = {(d, r.filetype) for r in rules for name in r.folders for d in folders[name]}
        if not rules or any(
            (posixpath.dirname(file), filetype) in wanted
            for file in read
            for filetype in types.names_of(posixpath.basename(file))
        ):
            continue
        bases = base_folders(sorted({n for rule in rules for n in rule.folders}), packs, overrides)
        resolved = resolve_folders([name for name, _ in bases], packs, overrides, root, selection)
        listed = tuple(
            (name, value, len(resolved[name]))
            for name, value in bases
            if resolved[name] or name not in optional
        )
        if listed:
            found.append((pack, listed))
    return tuple(found)


def _boundaries(document: Mapping[str, Any]) -> tuple[tuple[str, int], ...]:
    """Each boundary node and the number of edges into it, most first, then by id."""
    into = Counter(str(edge["to"]) for edge in document["edges"])
    found = [(n["id"], into[n["id"]]) for n in document["nodes"] if n["state"] == "boundary"]
    return tuple(sorted(found, key=lambda row: (-row[1], row[0])))


def _unknown(document: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    """Each unknown boundary node as its marking pack and reason, sorted. A run-time call site's
    pack is the first that set its ``resolution``; another node's is its detail's rule's."""
    found = []
    for node in document["nodes"]:
        if node["state"] != "unknown_boundary":
            continue
        if "unresolved_detail" in node:
            found.append((node["unresolved_detail"]["rule"].partition("/")[0], "no rule"))
        else:
            packs = sorted(p["pack"] for p in node["provenance"] if "resolution" in p["sets"])
            found.append((packs[0], "run-time"))
    return tuple(sorted(found))


def _counted(rows: Sequence[str]) -> str:
    """Each distinct row and how many times it occurs, by row."""
    return ", ".join(f"{_escape(row)} {n}" for row, n in sorted(Counter(rows).items()))


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


def _empty_pack_advice(pack: str, bases: Sequence[tuple[str, str, int]]) -> str:
    """What to do about a pack that selected no file: a missing folder may be declared elsewhere;
    when every folder was found, the pack simply reads nothing they hold."""
    if all(n for _, _, n in bases):
        holds = "it holds" if len(bases) == 1 else "they hold"
        return f"; {holds} no file the rules of {_escape(pack)} read"
    return (
        "; if the code is elsewhere, declare the folder under folders in "
        f"{PROJECT_MARKER}/{SETTINGS_FILENAME}"
    )


def render_text(report: MapReport) -> str:
    """The report as lines a person reads. Every outside string goes through ``_escape``. Packs
    that selected no file come first, and only when there are some."""
    lines = ["periplus map"]
    if report.empty_packs:
        lines += _section(
            "Packs that selected no file",
            [
                f"{_escape(pack)}: "
                + "; ".join(
                    f"{_escape(name)} = {_escape(value)}, "
                    + (f"{n} folder{'' if n == 1 else 's'} found" if n else "no such folder")
                    for name, value, n in bases
                )
                + _empty_pack_advice(pack, bases)
                for pack, bases in report.empty_packs
            ],
        )
    lines += _section(
        "Map",
        [
            f"{'path':<8}{_escape(report.map_path or 'not written')}",
            f"{'nodes':<8}{report.nodes}",
            f"{'edges':<8}{report.edges}",
            *(
                [
                    f"internal: {amount(report.internal.nodes, 'node')} and "
                    f"{amount(report.internal.edges, 'edge')} left out"
                ]
                if report.internal.nodes or report.internal.edges
                else []
            ),
        ],
    )
    shown_boundaries = [f"{_escape(node)} {n}" for node, n in report.boundaries[:10]]
    if len(report.boundaries) > 10:
        shown_boundaries.append(
            f"and {len(report.boundaries) - 10} more; the JSON report lists them all"
        )
    lines += _section("Boundaries", [f"total {len(report.boundaries)}", *shown_boundaries])
    lines += _section(
        "Unknown boundaries",
        [
            f"total {len(report.unknown)}",
            *(
                [
                    f"by pack: {_counted([p for p, _ in report.unknown])}",
                    f"by reason: {_counted([r for _, r in report.unknown])}",
                ]
                if report.unknown
                else []
            ),
        ],
    )
    shown_conflicts = [f"{_escape(n)}: {_escape('; '.join(c))}" for n, c in report.conflicts[:10]]
    if len(report.conflicts) > 10:
        shown_conflicts.append(
            f"and {len(report.conflicts) - 10} more; the JSON report lists them all"
        )
    lines += _section(
        "Type conflicts",
        [
            f"total {len(report.conflicts)}",
            f"edges left out {report.internal.unclear_edges}",
            *shown_conflicts,
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
        "Map rule passes",
        [
            f"pass {n}: "
            + (", ".join(f"{_escape(p)} {_escape(r)} fired {k}" for p, r, k in rows) or "none")
            for n, rows in report.map_passes
        ],
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
        "internal": {"nodes": report.internal.nodes, "edges": report.internal.edges},
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
        "map_passes": [
            {"pass": n, "fired": [{"pack": p, "rule": r, "fires": k} for p, r, k in rows]}
            for n, rows in report.map_passes
        ],
        "boundaries": {
            "total": len(report.boundaries),
            "by_node": [{"node": node, "edges": n} for node, n in report.boundaries],
        },
        "unknown_boundaries": {
            "total": len(report.unknown),
            "by_pack": dict(Counter(p for p, _ in report.unknown)),
            "by_reason": dict(Counter(r for _, r in report.unknown)),
        },
        "type_conflicts": {
            "total": len(report.conflicts),
            "edges_left_out": report.internal.unclear_edges,
            "by_node": [{"node": n, "candidates": list(c)} for n, c in report.conflicts],
        },
        "problems": [_json_problem(p) for p in report.problems],
        "empty_packs": [
            {
                "pack": pack,
                "folders": [{"folder": f, "value": v, "found": n} for f, v, n in bases],
            }
            for pack, bases in report.empty_packs
        ],
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


#: The formats ``map --format`` offers. ``cli.build_parser`` writes the same two names as a
#: literal because ``cli`` may not import this module; a test asserts the two agree.
RENDERERS: Mapping[str, Callable[[MapReport], str]] = {
    "text": render_text,
    "json": render_json,
}


def _supporting_paths(packs: Sequence[LoadedPack], settings: ResolvedSettings) -> list[str]:
    """The packs' ``files.supporting`` patterns, unless the settings set ``supporting_from_packs``
    to false, and the settings' ``supporting``."""
    found: list[str] = []
    keep = settings.supporting_from_packs is None or settings.supporting_from_packs.value
    for pack in packs if keep else ():
        files = pack.manifest.document.get("files")
        listed = files.get("supporting") if isinstance(files, dict) else None
        found += [p for p in listed if isinstance(p, str)] if isinstance(listed, list) else []
    return found + list(settings.supporting.value if settings.supporting else ())
