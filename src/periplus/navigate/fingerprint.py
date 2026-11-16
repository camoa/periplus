"""``periplus stamp`` and ``periplus stale``: a fingerprint of the code a node entry describes.

A fingerprint is the first 16 hex digits of the SHA-256 of the lines ``Places.span`` gives, blank
lines at the end left off, joined by line feeds. The map never reads the descriptions file, so
its bytes do not depend on it.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.navigate.listing import problem_lines
from periplus.navigate.mapfile import MapIndex, as_json, load_map, reading_fields
from periplus.navigate.names import Names
from periplus.navigate.nesting import Places, Thing, json_thing, thing, thing_line
from periplus.navigate.show import read_descriptions
from periplus.navigate.source import SourceLines
from periplus.report import _escape, _json_problem

__all__ = [
    "STALE_RENDERERS",
    "STAMP_RENDERERS",
    "StaleReport",
    "StampReport",
    "listed",
    "render_stale_json",
    "render_stale_text",
    "render_stamp_json",
    "render_stamp_text",
    "stale",
    "stamp",
]

#: The hex digits of a fingerprint.
DIGITS = 16
_TOKEN = re.compile(r"\S+")


@dataclass(frozen=True, slots=True)
class StampReport:
    """How many node entries got a fingerprint, how many kept the one they had, and each entry
    skipped with why. ``found`` is false when there is no descriptions file."""

    found: bool = True
    stamped: int = 0
    kept: int = 0
    skipped: tuple[tuple[str, str], ...] = ()
    problems: tuple[Problem, ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


@dataclass(frozen=True, slots=True)
class StaleReport:
    """The node entries: how many, how many match their code, those whose code changed, the ids
    the map no longer holds, those whose code cannot be read, and how many have no fingerprint.
    ``found`` is false when there is no descriptions file."""

    found: bool = True
    entries: int = 0
    fresh: int = 0
    changed: tuple[Thing, ...] = ()
    gone: tuple[str, ...] = ()
    unreadable: tuple[Thing, ...] = ()
    unstamped: int = 0
    warnings: tuple[str, ...] = ()
    problems: tuple[Problem, ...] = ()

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among the problems, or ``OK`` when there were none."""
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def _fingerprint(places: Places, source: SourceLines, node_id: str) -> str | None:
    """The fingerprint of ``node_id``'s code, or ``None`` when it has no location or the lines
    cannot be read."""
    span = places.span(node_id)
    if span is None:
        return None
    file, first, last = span
    lines = source.lines(file)
    if lines is None or first > len(lines):
        return None
    chunk = lines[first - 1 : len(lines) if last is None else last]
    while len(chunk) > 1 and not chunk[-1].strip():
        chunk.pop()
    return hashlib.sha256("\n".join(chunk).encode("utf-8")).hexdigest()[:DIGITS]


def _setup(start: Path, env: Mapping[str, str], map_path: Path | None) -> tuple[Any, ...]:
    index = load_map(start, env, map_path)
    path, document, problems = read_descriptions(start, map_path)
    places = Places(index, Names(index))
    return index, path, document, problems, places, SourceLines(start, map_path)


def stamp(start: Path, env: Mapping[str, str], every: bool, map_path: Path | None) -> StampReport:
    """Write a fingerprint into each node entry that has none, or into all with ``every``.

    Each fingerprint is a line ``fingerprint: '<digits>'``, quoted so that digits alone stay a
    string, after the entry's ``line`` key, at its
    indent, or the value of the entry's ``fingerprint`` key replaced; no other byte changes. An
    entry written inline, as ``{text: ...}``, is skipped. Nothing is written when the result read
    back is not the old file with the fingerprints set.
    """
    try:
        index, path, document, problems, places, source = _setup(start, env, map_path)
    except HarnessError as error:
        return StampReport(problems=(error.problem(),))
    if problems:
        return StampReport(problems=problems)
    if not path.is_file():
        return StampReport(found=False)
    if not document.get("nodes"):
        return StampReport()
    try:
        with reading_fields(start, map_path):
            raw = path.read_bytes().decode("utf-8")
            entries = YAML().load(raw)["nodes"]
            lines = raw.splitlines(keepends=True)
            stamped = kept = 0
            skipped: list[tuple[str, str]] = []
            expected = {i: dict(e) for i, e in document["nodes"].items()}
            for node_id, entry in entries.items():
                if "fingerprint" in entry and not every:
                    kept += 1
                    continue
                said = _stamp_one(index, places, source, lines, node_id, entry)
                if said is None:
                    stamped += 1
                    expected[node_id]["fingerprint"] = entry["fingerprint"]
                else:
                    skipped.append((node_id, said))
    except HarnessError as error:
        return StampReport(problems=(error.problem(),))
    except (YAMLError, UnicodeDecodeError, OSError) as error:
        return StampReport(problems=(_problem(error, path),))
    written = "".join(lines)
    if YAML(typ="safe", pure=True).load(written) != {**document, "nodes": expected}:
        message = (
            f"{path}: the fingerprints cannot be set without changing other text; nothing written"
        )
        return StampReport(problems=(Problem(ExitCode.NOT_A_MAP, message, {"path": str(path)}),))
    if written != raw:
        try:
            path.write_bytes(written.encode("utf-8"))
        except OSError as error:
            return StampReport(problems=(_problem(error, path),))
    return StampReport(True, stamped, kept, tuple(skipped))


def _stamp_one(
    index: MapIndex,
    places: Places,
    source: SourceLines,
    lines: list[str],
    node_id: str,
    entry: Any,
) -> str | None:
    """Set ``entry``'s fingerprint in ``lines`` and in ``entry``; ``None``, or why it is skipped."""
    if node_id not in index.nodes:
        return "not in the map"
    if entry.fa.flow_style():
        return "written inline"
    value = _fingerprint(places, source, node_id)
    if value is None:
        return "code unreadable"
    if "fingerprint" in entry:
        row, col = entry.lc.value("fingerprint")
        old = _TOKEN.match(lines[row], col)
        if old is None:
            return "fingerprint not on its key's line"
        lines[row] = lines[row][: old.start()] + f"'{value}'" + lines[row][old.end() :]
    else:
        row, col = entry.lc.key("line")
        if entry.lc.value("line")[0] != row:
            return "line not on its key's line"
        text = lines[row]
        ending = text[len(text.rstrip("\r\n")) :]
        if not ending:
            lines[row] = text + "\n"
        lines[row] += " " * col + f"fingerprint: '{value}'" + ending
    entry["fingerprint"] = value
    return None


def _problem(error: Exception, path: Path) -> Problem:
    if isinstance(error, OSError):
        message = f"{path} cannot be read or written: {error.strerror or error}"
        return Problem(ExitCode.OUTPUT_UNWRITABLE, message, {"path": str(path)})
    return Problem(ExitCode.NOT_A_MAP, f"{path} is not readable YAML", {"path": str(path)})


def stale(start: Path, env: Mapping[str, str], map_path: Path | None) -> StaleReport:
    """Compare each node entry's fingerprint with its code now."""
    try:
        index, path, document, problems, places, source = _setup(start, env, map_path)
        if problems:
            return StaleReport(problems=problems)
        if not path.is_file():
            return StaleReport(found=False)
        with reading_fields(start, map_path):
            entries = document.get("nodes") or {}
            changed: list[Thing] = []
            gone: list[str] = []
            unreadable: list[Thing] = []
            fresh = unstamped = 0
            for node_id in sorted(entries):
                if node_id not in index.nodes:
                    gone.append(node_id)
                    continue
                held = entries[node_id].get("fingerprint")
                if held is None:
                    unstamped += 1
                    continue
                now = _fingerprint(places, source, node_id)
                if now == held:
                    fresh += 1
                elif now is None:
                    unreadable.append(thing(index, places.names, node_id))
                else:
                    changed.append(thing(index, places.names, node_id))
    except HarnessError as error:
        return StaleReport(problems=(error.problem(),))
    return StaleReport(
        True, len(entries), fresh, tuple(changed), tuple(gone), tuple(unreadable), unstamped
    )


def _entries(count: int) -> str:
    return f"{count} node entr{'y' if count == 1 else 'ies'}"


def render_stamp_text(report: StampReport) -> str:
    """How many entries were stamped and kept, then each skipped entry with why."""
    lines = ["periplus stamp"]
    if not report.found:
        lines.append("no descriptions file")
    elif not report.problems:
        lines.append(
            f"stamped {_entries(report.stamped)}; {report.kept} kept the fingerprint they had"
        )
        if report.skipped:
            lines.append("skipped:")
            lines += [f"  {_escape(i)}  {why}" for i, why in report.skipped]
    lines += problem_lines(report.problems)
    return "\n".join(lines) + "\n"


def render_stamp_json(report: StampReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    return as_json(
        {
            "command": "stamp",
            "found": report.found,
            "stamped": report.stamped,
            "kept": report.kept,
            "skipped": [{"id": i, "reason": why} for i, why in report.skipped],
            "problems": [_json_problem(p) for p in report.problems],
        }
    )


def render_stale_text(report: StaleReport) -> str:
    """The count line, then the changed, gone and unreadable entries under a heading each."""
    lines = ["periplus stale"]
    if not report.found:
        lines.append("no descriptions file")
    elif not report.problems:
        lines.append(
            f"{_entries(report.entries)}: {report.fresh} fresh, {len(report.changed)} changed, "
            f"{len(report.gone)} gone, {len(report.unreadable)} unreadable, "
            f"{report.unstamped} not stamped"
        )
        for heading, rows in (("changed", report.changed), ("unreadable", report.unreadable)):
            if rows:
                lines.append(f"{heading}:")
                lines += [thing_line(row, row.location or "no location") for row in rows]
            if heading == "changed" and report.gone:
                lines.append("gone:")
                lines += [f"  {_escape(i)}" for i in report.gone]
    lines += problem_lines(report.problems)
    return "\n".join(lines) + "\n"


def render_stale_json(report: StaleReport) -> str:
    """The report as one JSON document, keys sorted, ``ensure_ascii=True``."""
    return as_json(
        {
            "command": "stale",
            "found": report.found,
            "entries": report.entries,
            "fresh": report.fresh,
            "changed": [json_thing(row) for row in report.changed],
            "gone": list(report.gone),
            "unreadable": [json_thing(row) for row in report.unreadable],
            "unstamped": report.unstamped,
            "problems": [_json_problem(p) for p in report.problems],
        }
    )


def listed(report: StaleReport) -> tuple[str, ...]:
    """The ids ``--ids`` prints: the changed entries, then the gone ones, then the unreadable."""
    return (
        *(row.id for row in report.changed),
        *report.gone,
        *(row.id for row in report.unreadable),
    )


STAMP_RENDERERS = {"text": render_stamp_text, "json": render_stamp_json}
STALE_RENDERERS = {"text": render_stale_text, "json": render_stale_json}
