"""``periplus update``: move a project's pins to the rutter versions that are installed.

The installed version of a name is read off the same roots and candidates ``resolve`` builds, so
what this command writes is what ``map`` loads. When more than one root ships the name, the first
root in ``resolve_pack_roots`` order that holds it supplies the version: project, user config,
bundled, then ``pack_paths``. That is this module's rule, stated here; the resolver's order never
decides an outcome. A name the project root holds is kept, because the project copy is what is
installed for that project. A pin moves downward as well as upward, and the report says so, because
a pin nothing on the search path ships cannot be mapped at all.

``resolve`` reports a stale pin as ``PIN_UNMATCHED`` and two copies as ``PIN_DUPLICATED``. Both are
the cases this command serves, so neither is carried into its report. Every other resolution
problem is, and ends the run before the file is touched.

The file is read and written through ruamel's round-trip loader so its comments survive. That is
the one thing the safe loader in ``settings.py`` cannot do.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from periplus.errors import ExitCode, Problem
from periplus.layout import PROJECT_MARKER, SETTINGS_FILENAME
from periplus.packs import parse_pack_name
from periplus.preflight import DependencyStatus
from periplus.report import _escape
from periplus.resolution import resolve

__all__ = [
    "RENDERERS",
    "Change",
    "Kept",
    "UpdateReport",
    "render_json",
    "render_text",
    "update_pins",
]

#: Where in the file the pin list sits, read off the text so the rewrite keeps the file's own
#: indentation of ``- `` rather than imposing one.
_FIRST_ITEM = re.compile(r"^packs:[^\n]*\n(?:[ \t]*(?:#[^\n]*)?\n)*?( *)- ", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class Change:
    """A pin moved: the rutter's name, the version it was pinned at, and the version now."""

    name: str
    old: str
    new: str
    also_available: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class Kept:
    """A pin left as it was, and why."""

    pin: str
    reason: str


@dataclass(frozen=True, slots=True)
class UpdateReport:
    changed: tuple[Change, ...]
    kept: tuple[Kept, ...]
    problems: tuple[Problem, ...]

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def update_pins(
    start: Path, env: Mapping[str, str], dependencies: tuple[DependencyStatus, ...]
) -> UpdateReport:
    """Rewrite each pin whose name an installed rutter ships, and report every pin either way."""
    resolution = resolve(start=start, env=env, dependencies=dependencies)
    carried = tuple(
        problem
        for problem in resolution.problems
        if problem.code not in (ExitCode.PIN_UNMATCHED, ExitCode.PIN_DUPLICATED)
    )
    path = (
        resolution.project_root / PROJECT_MARKER / SETTINGS_FILENAME
        if resolution.project_root is not None
        else None
    )
    if carried:
        return UpdateReport((), (), carried)
    if path is None or not path.is_file():
        message = f"no {PROJECT_MARKER}/{SETTINGS_FILENAME} found for this project"
        return UpdateReport((), (), (Problem(ExitCode.NO_SETTINGS, message, {}),))

    text = path.read_text(encoding="utf-8")
    yaml = YAML(typ="rt")
    yaml.preserve_quotes = True
    match = _FIRST_ITEM.search(text)
    offset = len(match.group(1)) if match else 0
    yaml.indent(mapping=2, sequence=offset + 2, offset=offset)
    try:
        document = yaml.load(text)
    except YAMLError as error:
        problem = Problem(ExitCode.UNREADABLE_SETTINGS, f"{path} is not valid YAML: {error}", {})
        return UpdateReport((), (), (problem,))
    pins = document.get("packs") if hasattr(document, "get") else None
    if not isinstance(pins, list):
        return UpdateReport((), (), ())

    changed: list[Change] = []
    kept: list[Kept] = []
    for index, item in enumerate(pins):
        name = parse_pack_name(str(item))
        holders = [
            (candidate.root.kind, candidate.name.version)
            for candidate in resolution.candidates
            if candidate.status == "named"
            and candidate.name is not None
            and name is not None
            and candidate.name.pack == name.pack
        ]
        if name is None or not holders:
            kept.append(Kept(str(item), "not shipped by any rutter on the search path"))
        elif holders[0][0] in ("project", "configured"):
            where = "the project's own packs" if holders[0][0] == "project" else "a pack_paths root"
            kept.append(Kept(str(item), f"shipped from {where}"))
        elif holders[0][1] == name.version:
            kept.append(Kept(str(item), "already current"))
        else:
            new = holders[0][1]
            pins[index] = type(item)(f"{name.pack}@{new}")
            others = tuple(sorted({version for _, version in holders[1:] if version != new}))
            changed.append(Change(name.pack, name.version, new, others))
    if changed:
        with path.open("w", encoding="utf-8") as handle:
            yaml.dump(document, handle)
    return UpdateReport(tuple(changed), tuple(kept), ())


def _newer(change: Change) -> bool:
    def numbers(version: str) -> tuple[int, ...]:
        return tuple(int(part) for part in re.findall(r"\d+", version))

    return numbers(change.new) >= numbers(change.old)


def render_text(report: UpdateReport) -> str:
    """One line per changed pin as ``name: old -> new``, one per kept pin with its reason."""
    lines: list[str] = []
    for change in report.changed:
        line = f"{_escape(change.name)}: {_escape(change.old)} -> {_escape(change.new)}"
        if not _newer(change):
            line += " (a lower version than the pin)"
        if change.also_available:
            line += f" (also available: {_escape(', '.join(change.also_available))})"
        lines.append(line)
    lines += [f"kept {_escape(kept.pin)}: {_escape(kept.reason)}" for kept in report.kept]
    lines += [_escape(problem.message) for problem in report.problems]
    return "\n".join(lines) + "\n" if lines else ""


def render_json(report: UpdateReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    payload = {
        "changed": [
            {
                "name": change.name,
                "old": change.old,
                "new": change.new,
                "downward": not _newer(change),
                "also_available": list(change.also_available),
            }
            for change in report.changed
        ],
        "kept": [{"pin": kept.pin, "reason": kept.reason} for kept in report.kept],
        "problems": [
            {"code": int(p.code), "message": p.message, "detail": dict(p.detail)}
            for p in report.problems
        ],
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


#: The formats ``update --format`` offers. ``cli.build_parser`` writes the same two names as a
#: literal, because ``cli`` may not import this module.
RENDERERS: Mapping[str, Callable[[UpdateReport], str]] = {
    "text": render_text,
    "json": render_json,
}
