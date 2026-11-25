"""``periplus fresh``: whether ``periplus map`` run now would write the map as it is.

``map`` writes an inputs record beside the map: a digest of each file the rules read, of the
effective settings, of each loaded rutter's files, the tool version, and the map's own digest.
This command selects the files as ``map`` does, with no rule run, and compares.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import periplus
from periplus.engine.rules import file_rule_matches
from periplus.errors import ExitCode, HarnessError, Problem
from periplus.layout import PROJECT_MARKER, SETTINGS_FILENAME
from periplus.map import Prepared, inputs_of, inputs_path, prepare, short_digest
from periplus.navigate.mapfile import _locate
from periplus.preflight import DependencyStatus
from periplus.report import _escape, _json_problem, amount

__all__ = ["RENDERERS", "FreshReport", "render_json", "render_text", "run"]

#: Each set of changes as the changed, the added and the removed names, each sorted.
Changes = tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]

_NONE: Changes = ((), (), ())

#: What to do when the state is unknown.
_UNKNOWN = (
    "for the project's map, run periplus map to build it with its record",
    "for a map file that another command wrote, run periplus fresh on the map it came from",
)


@dataclass(frozen=True, slots=True)
class FreshReport:
    """One ``fresh`` run.

    ``state`` is ``fresh``, ``stale`` or ``unknown``, and ``reason`` says why a state is unknown.
    ``made_by`` is the tool the record names, ``None`` with no record. ``counts`` holds the number
    of files and of rutters the record holds. ``remedy`` says what to do when the state is unknown.
    """

    map_path: str | None
    state: str
    reason: str = ""
    made_by: str | None = None
    settings_changed: bool = False
    packs: Changes = _NONE
    files: Changes = _NONE
    counts: tuple[int, int] = (0, 0)
    problems: tuple[Problem, ...] = ()
    remedy: tuple[str, ...] = _UNKNOWN

    @property
    def tool(self) -> str:
        """The tool that runs now."""
        return f"periplus {periplus.__version__}"

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems; else ``MAP_STALE`` unless the map is fresh."""
        if self.problems:
            return min(problem.code for problem in self.problems)
        return ExitCode.OK if self.state == "fresh" else ExitCode.MAP_STALE


def run(
    start: Path,
    env: Mapping[str, str],
    dependencies: tuple[DependencyStatus, ...],
    map_path: Path | None,
    settings_path: Path | None = None,
) -> FreshReport:
    """Compare the record beside the map at ``map_path``, or the project's map, with the project
    as it is now, read with the settings file at ``settings_path`` when one is given, as ``map``
    reads it."""
    try:
        path = _locate(start, map_path)
    except HarnessError as error:
        return FreshReport(None, "unknown", problems=(error.problem(),))
    try:
        own = short_digest(path.read_bytes())
    except OSError as error:
        message = (
            f"no map at {path}; run periplus map"
            if isinstance(error, FileNotFoundError)
            else f"cannot read {path}: {error}"
        )
        problem = Problem(ExitCode.MAP_NOT_FOUND, message, {"path": str(path)})
        return FreshReport(str(path), "unknown", problems=(problem,))
    record_path = inputs_path(path)
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        reason = (
            f"no inputs record at {record_path}: the map was built by a Periplus older than this "
            "command, or it is a map file that slice --out, extract, join, common or minus wrote, "
            "and those carry none"
        )
        return FreshReport(str(path), "unknown", reason)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        return FreshReport(str(path), "unknown", f"cannot read {record_path}: {error}")
    keys = {
        "files",
        "generated_by",
        "map",
        "packs",
        "periplus_inputs_version",
        "settings",
        "settings_file",
    }
    if (
        not isinstance(record, dict)
        or set(record) != keys
        or record["periplus_inputs_version"] != 0
        or not isinstance(record["files"], dict)
        or not isinstance(record["packs"], dict)
    ):
        return FreshReport(str(path), "unknown", f"{record_path} is not an inputs record")
    made_by = str(record["generated_by"])
    if record["map"] != own:
        reason = (
            f"the inputs record at {record_path} is of another map: the map was written after "
            "it, by an older Periplus, by hand, or by a command that writes map files"
        )
        return FreshReport(str(path), "unknown", reason, made_by)
    prepared = prepare(start, env, dependencies, settings_path)
    if not isinstance(prepared, Prepared):
        return FreshReport(str(path), "unknown", made_by=made_by, problems=prepared)
    built_with = str(record["settings_file"])
    if built_with != prepared.settings_file:
        reason = (
            f"the map was built with the settings file {built_with}, and this run read "
            f"{prepared.settings_file}"
        )
        default = built_with == f"{PROJECT_MARKER}/{SETTINGS_FILENAME}"
        remedy = "run periplus fresh" if default else f"run periplus fresh --settings {built_with}"
        return FreshReport(str(path), "unknown", reason, made_by, remedy=(remedy,))
    try:
        matched = file_rule_matches(
            prepared.listings,
            prepared.rule_set,
            prepared.packs,
            prepared.folders,
            prepared.selection,
        )
        now = inputs_of(prepared, matched)
    except HarnessError as error:
        return FreshReport(str(path), "unknown", made_by=made_by, problems=(error.problem(),))
    files, packs = (
        _compared(record["files"], now["files"]),
        _compared(record["packs"], now["packs"]),
    )
    settings_changed = record["settings"] != now["settings"]
    same = files == _NONE and packs == _NONE and not settings_changed
    return FreshReport(
        str(path),
        "fresh" if same and made_by == f"periplus {periplus.__version__}" else "stale",
        made_by=made_by,
        settings_changed=settings_changed,
        packs=packs,
        files=files,
        counts=(len(record["files"]), len(record["packs"])),
    )


def _compared(then: Mapping[str, object], now: Mapping[str, object]) -> Changes:
    """The names whose digest differs, those only ``now`` holds and those only ``then`` holds."""
    return (
        tuple(sorted(name for name in then.keys() & now.keys() if then[name] != now[name])),
        tuple(sorted(now.keys() - then.keys())),
        tuple(sorted(then.keys() - now.keys())),
    )


def _summary(noun: str, changes: Changes) -> str:
    """``files same``, or the counts of the changes, the first one with its noun."""
    parts = [
        (len(names), verb)
        for names, verb in zip(changes, ("changed", "added", "removed"), strict=True)
        if names
    ]
    if not parts:
        return f"{noun}s same"
    (first, verb), *rest = parts
    return ", ".join([f"{amount(first, noun)} {verb}", *(f"{n} {v}" for n, v in rest)])


def render_text(report: FreshReport) -> str:
    """The report as lines a person reads. Every outside string goes through ``_escape``."""
    lines = ["periplus fresh"]
    if report.map_path is not None:
        lines.append(f"map: {_escape(report.map_path)}")
    lines += [_escape(problem.message) for problem in report.problems]
    if report.problems:
        return "\n".join(lines) + "\n"
    if report.state == "unknown":
        lines += [f"unknown: {_escape(report.reason)}", *map(_escape, report.remedy)]
        return "\n".join(lines) + "\n"
    files, packs = report.counts
    if report.state == "fresh":
        lines.append(
            f"fresh: {amount(files, 'file')}, the settings, {amount(packs, 'rutter')} and the "
            "tool match the map"
        )
        return "\n".join(lines) + "\n"
    tool = (
        "tool same"
        if report.made_by == report.tool
        else f"tool changed: {_escape(report.made_by or '')} then, {report.tool} now"
    )
    settings = "settings changed" if report.settings_changed else "settings same"
    lines.append(
        f"stale: {_summary('file', report.files)}; {settings}; "
        f"{_summary('rutter', report.packs)}; {tool}"
    )
    for noun, changes in (("files", report.files), ("rutters", report.packs)):
        for names, verb in zip(changes, ("changed", "added", "removed"), strict=True):
            if names:
                lines.append(f"{noun} {verb}:")
                lines += [f"  {_escape(name)}" for name in names]
    lines.append("run periplus map to rebuild")
    return "\n".join(lines) + "\n"


def render_json(report: FreshReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    known = report.state != "unknown"

    def listed(changes: Changes) -> dict[str, list[str]] | None:
        names = dict(zip(("changed", "added", "removed"), changes, strict=True))
        return {verb: list(found) for verb, found in names.items()} if known else None

    payload = {
        "command": "fresh",
        "state": report.state,
        "reason": report.reason or None,
        "map": report.map_path,
        "made_by": report.made_by,
        "tool": {"then": report.made_by, "now": report.tool},
        "settings": ("changed" if report.settings_changed else "same") if known else None,
        "packs": listed(report.packs),
        "files": listed(report.files),
        "problems": [_json_problem(p) for p in report.problems],
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


#: The formats ``fresh --format`` offers. ``cli.build_parser`` writes the same two names as a
#: literal, because ``cli`` may not import this module.
RENDERERS: Mapping[str, Callable[[FreshReport], str]] = {
    "text": render_text,
    "json": render_json,
}
