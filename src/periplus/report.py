"""The two renderers. No resolution logic, no filesystem, no terminal.

This module receives a finished ``ResolutionReport`` and returns a string. It reads nothing, opens
nothing, and asks nothing about the stream it will be written to: no colour, no TTY detection, no
terminal-width probing. A pipe and a terminal receive the same bytes, which is half of the
determinism property and the half that is easiest to lose by accident.

The two renderers share one helper, ``_escape``, which is a pure string function that knows nothing
about the record. They share no "format a section" helper: a change to one renderer must not be
able to change the other, and a shared section formatter is exactly the edge that would let it.

Every mapping is emitted in name order, by ``sorted()`` here rather than by trusting the producer.
``settings.py`` already sorts ``folders`` and ``extensions``, and a second consumer may build a
``ResolvedSettings`` some other way.

Nothing in this module is on ``cli``'s module-level import path. ``cli`` imports it inside
``main()``, after the dependency check, so nothing it imports — ``json`` included — is paid by
``periplus --version`` or ``--help``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping, Sequence

from periplus.errors import Problem
from periplus.packs import MatchedPack, PackCandidate, PackName, PackRoot
from periplus.preflight import DependencyStatus
from periplus.resolution import ResolutionReport
from periplus.settings import (
    FirstParty,
    ResolvedSetting,
    ResolvedSettings,
    SettingsSource,
    SourceRef,
)

__all__ = ["RENDERERS", "render_json", "render_text"]

#: The settings keys, in the order the text form prints them. Written out rather than read off
#: `ResolvedSettings.__dataclass_fields__`, because the order a person reads is a choice and the
#: order the fields happen to be declared in is not one.
SETTINGS_KEYS = (
    "periplus_version",
    "packs",
    "pack_paths",
    "folders",
    "extensions",
    "first_party",
    "exclude",
    "re_include",
    "accepted_unknowns",
)


#: The two line boundaries ``str.splitlines()`` honours that are outside the ``Cc`` category.
#: Escaping every control character closed the newline hole and left these two: a name holding
#: U+2028 produced escaped output with no ``\n`` in it at all that ``splitlines()`` still read as
#: three lines, which is the line forging this function exists to prevent, two code points further
#: out. They are escaped in ``\uXXXX`` form because they do not fit two hex digits.
_LINE_BOUNDARIES = ("\u2028", "\u2029")


def _escaped(character: str) -> str:
    """One character, kept as itself or replaced by its ordinal.

    Three cases rather than a nested conditional, because an unreadable predicate is how the next
    range gets missed.
    """
    if character in _LINE_BOUNDARIES:
        return f"\\u{ord(character):04x}"
    if " " <= character < "\x7f" or character > "\x9f":
        return character
    return f"\\x{ord(character):02x}"


def _escape(text: str) -> str:
    """Attacker-influenced text as one line that always encodes. Never raises.

    A directory name on Linux is any byte sequence except ``/`` and NUL. Three things follow, and
    each is closed here:

    * A name can hold a **newline** and forge a line of this report.
    * A name can hold any **other control character**, and an ESC is the one that matters: a
      directory called ``evil\x1b[2K@1.0.0`` writes a raw ANSI erase-line into a report a person
      reads. That is the same class as forging a line, and it is why every code point in the
      Unicode ``Cc`` category is escaped by ordinal rather than left to a codec. ESC and BEL encode
      cleanly to both ASCII and UTF-8, so no ``errors="backslashreplace"`` will ever touch them —
      an earlier version of this function relied on exactly that and let them straight through.

      **``Cc`` is 0x00-0x1F *and* 0x7F-0x9F**, and both ranges are escaped. U+009B is CSI in a UTF-8
      xterm with ``allowC1Printable`` at its default, so a directory name carrying it would write a
      raw control sequence into the report — the same defect the paragraph above describes, one
      range further along.
    * A name that is **not valid UTF-8** arrives with surrogate escapes, which a UTF-8 stdout
      refuses to encode. The ``try`` is what narrows the last escape to the strings that genuinely
      would not encode.

    A **printable non-ASCII name is left alone**, rather than escaped to ``\\xc9mile@1.0.0``. That
    is the one place the two forms legitimately differ: JSON uses ``ensure_ascii=True`` because its
    output is a document a parser consumes and a lone surrogate breaks the encode, while this form
    is read by a person, who is better served by the directory name their filesystem actually
    holds.

    The backslash replacement comes first, so an escape sequence a real name contains cannot be
    confused with one this function produced.

    It happens here and never in a producer. ``packs.py`` records why: escaping where the value is
    read would make the escaped form the value, and a second renderer would escape it again.
    """
    for raw, escaped in (("\\", "\\\\"), ("\n", "\\n"), ("\r", "\\r"), ("\t", "\\t")):
        text = text.replace(raw, escaped)
    text = "".join(_escaped(character) for character in text)
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        text = text.encode("utf-8", "backslashreplace").decode("utf-8")
    return text


# ---------------------------------------------------------------------------------------------
# The text form
# ---------------------------------------------------------------------------------------------


def render_text(report: ResolutionReport) -> str:
    """The report as the lines a person reads, in the order the resolution happened.

    Sections in stage order — dependencies, project root, settings sources, effective settings with
    their sources, then pack roots, candidates, matched packs and problems. Reading top to bottom
    is reading what the tool did.

    Every section is printed even when it is empty, and a section whose stage did not run says so
    instead of being left out. A report that omits a section it could not fill reads as though the
    thing it describes does not exist.

    Provenance is printed inline against each value, in brackets, because a value whose source has
    to be looked up elsewhere will not get looked up.

    Everything this function writes encodes to UTF-8. Text taken from a filesystem or a settings
    file goes through ``_escape``, which escapes what would not encode and leaves a printable
    non-ASCII name as the name on disk; the words around it are ASCII literals. The stream is
    pinned to UTF-8 in ``cli``, which is what carries that name to a console whose default encoding
    is something else.
    """
    lines: list[str] = [f"periplus {_escape(report.tool_version)}"]
    lines.append(f"rutters: {report.rutters_digest}")
    lines += _block("Dependencies", _dependency_rows(report.dependencies))
    lines += _block(
        "Project root",
        [["not found - no .periplus directory at or above the starting directory"]]
        if report.project_root is None
        else [[_escape(str(report.project_root))]],
    )
    lines += _block(
        "Settings sources",
        [[f"user configuration directory from {report.user_config_from}"]]
        + _source_rows(report.settings_sources),
    )
    lines += _block("Effective settings", _settings_rows(report))
    lines += _block("Pack roots", _root_rows(report.pack_roots))
    lines += _block("Candidates", _candidate_rows(report.candidates))
    lines += _block("Matched packs", _match_rows(report, report.packs))
    lines += _block("Problems", _problem_rows(report.problems))
    return "\n".join(lines) + "\n"


def _block(heading: str, rows: Sequence[Sequence[str]]) -> list[str]:
    """One section: a blank line, its heading, and its rows aligned into columns.

    Alignment is computed from the content of this section alone and never from the terminal. The
    last populated cell in a row is not padded, so no line carries trailing whitespace.
    """
    widths: list[int] = []
    for row in rows:
        for index, cell in enumerate(row[:-1]):
            if index >= len(widths):
                widths.append(0)
            widths[index] = max(widths[index], len(cell))
    lines = ["", f"{heading}:"]
    for row in rows:
        cells = [
            cell.ljust(widths[index]) if index < len(row) - 1 else cell
            for index, cell in enumerate(row)
        ]
        lines.append(("  " + "  ".join(cells)).rstrip())
    return lines


def _dependency_rows(dependencies: Sequence[DependencyStatus]) -> list[list[str]]:
    """One row per required distribution: name, and the version found or that it is absent."""
    if not dependencies:
        return [["none required"]]
    return [
        [_escape(status.distribution), _escape(status.installed or "not installed")]
        for status in dependencies
    ]


def _source_rows(sources: Sequence[SettingsSource]) -> list[list[str]]:
    """One row per located settings file, with what happened to it and why, if there was a why."""
    if not sources:
        return [["no settings file location is knowable"]]
    return [
        [source.kind, source.status, _escape(str(source.path)), _escape(source.reason or "")]
        for source in sources
    ]


def _root_rows(roots: Sequence[PackRoot]) -> list[list[str]]:
    """One row per pack root, in the fixed root order, present or absent, never omitted.

    Not sorted, and that is the declared key: project, user, bundled, then the ``pack_paths``
    entries in the order they were merged. Sorting this would discard the search order.
    """
    if not roots:
        return [["none"]]
    return [
        [
            root.kind,
            "present" if root.exists else "absent",
            _escape(root.display),
            _ref(root.source) if root.source is not None else "",
        ]
        for root in roots
    ]


def _candidate_rows(candidates: Sequence[PackCandidate]) -> list[list[str]]:
    """One row per entry found under a root — exactly one, whatever the entry is named.

    ``discover_candidates`` has already sorted these by root order then entry name, by code point.
    The escape is what keeps the count honest: a directory named with an embedded newline would
    otherwise forge a row.
    """
    if not candidates:
        return [["none"]]
    return [
        [
            candidate.root.kind,
            candidate.status,
            _escape(candidate.entry),
            _name(candidate.name),
        ]
        for candidate in candidates
    ]


def _match_rows(report: ResolutionReport, matches: Sequence[MatchedPack]) -> list[list[str]]:
    """One row per matched pin, in the order the settings file wrote its pins.

    Not sorted: the declared key is the order the person chose, which is input and therefore stable
    across runs. A name matched under two roots appears twice, because reporting it once would
    resolve the duplicate by omission.
    """
    if "packs" in report.skipped:
        return [[f"skipped - {_escape(report.skipped['packs'])}"]]
    if not matches:
        return [["none"]]
    return [[_escape(match.pin), match.root.kind, _escape(match.path)] for match in matches]


def _problem_rows(problems: Sequence[Problem]) -> list[list[str]]:
    """One row per problem, lowest code first, with its named facts beside its one line."""
    if not problems:
        return [["none"]]
    rows: list[list[str]] = []
    for problem in problems:
        rows.append([str(int(problem.code)), _escape(problem.message)])
        for key in sorted(problem.detail):
            rows.append(["", f"  {_escape(key)}: {_escape(problem.detail[key])}"])
    return rows


def _settings_rows(report: ResolutionReport) -> list[list[str]]:
    """Every settings key with its effective value and the file that decided it.

    Two columns: the key, and the value with its provenance appended. Three columns were tried and
    the third had to be padded to the widest value in the whole section, which pushed the source of
    a one-character ``periplus_version`` out past column 120 because one ``first_party`` line is
    long. Ragged provenance reads better than an aligned column nobody can reach.

    A key no file declared reads "not declared", and a key a file declared empty reads "declared
    empty" and names that file. The two are different facts: presence is what makes a file a
    source, so a file writing ``re_include: []`` is a source of an empty value and not an absence.
    """
    settings = report.settings
    if settings is None:
        return [[f"skipped - {_escape(report.skipped.get('settings', 'not resolved'))}"]]
    rows: list[list[str]] = []
    for key in SETTINGS_KEYS:
        rows.extend(_setting_rows(key, getattr(settings, key)))
    return rows


def _joined_values(value: str | tuple[str, ...]) -> str:
    """One value escaped, or several each escaped and joined by a comma and a space."""
    return _escape(value) if isinstance(value, str) else ", ".join(_escape(v) for v in value)


def _setting_rows(key: str, value: object) -> list[list[str]]:
    """One key's rows. Five value shapes, each named rather than walked generically.

    The first row carries the key and every continuation row leaves it blank, so a multi-entry key
    reads as one block rather than as one key repeated.
    """
    if isinstance(value, Mapping):
        if not value:
            return [[key, "none declared"]]
        return _rows(
            key,
            [
                _with_refs(f"{_escape(name)} = {_joined_values(entry.value)}", entry.sources)
                for name, entry in sorted(value.items())
            ],
        )
    if value is None:
        return [[key, "not declared"]]
    assert isinstance(value, ResolvedSetting)  # noqa: S101 - the five shapes are exhaustive
    if key == "first_party":
        return _rows(
            key,
            [
                _with_refs(f"{half} = {_joined(getattr(value.value, half))}", value.sources)
                for half in ("include", "exclude")
            ],
        )
    if isinstance(value.value, tuple):
        return _rows(key, _entry_lines(value, _unknown if key == "accepted_unknowns" else str))
    return [[key, _with_refs(_escape(str(value.value)), value.sources)]]


def _rows(key: str, details: Sequence[str]) -> list[list[str]]:
    """One block: the key against its first line, and blank against every line after it."""
    return [[key if index == 0 else "", detail] for index, detail in enumerate(details)]


def _entry_lines(setting: ResolvedSetting[object], render: Callable[[object], str]) -> list[str]:
    """A sequence value as one line per entry, each naming the file that contributed *that* entry.

    ``entry_sources`` and not ``sources``: for a key that accumulates, the file that added one
    entry is a different fact from the files that had a say in the key, and zipping against
    ``sources`` produces a plausible, silent misattribution.
    """
    items = setting.value
    assert isinstance(items, tuple)  # noqa: S101 - every sequence rule produces a tuple
    if not items:
        return [_with_refs("declared empty", setting.sources)]
    per_entry = setting.entry_sources
    return [
        _with_refs(
            _escape(render(item)),
            (per_entry[index],) if per_entry is not None else setting.sources,
        )
        for index, item in enumerate(items)
    ]


def _with_refs(text: str, sources: Sequence[SourceRef]) -> str:
    """One value and the files behind it, on one line, with the provenance last."""
    return f"{text}  {_refs(sources)}".rstrip()


def _unknown(item: object) -> str:
    """One ``accepted_unknowns`` entry as its keys in name order.

    Its values are deliberately not all strings — an unquoted ``accepted_on: 2026-08-28`` loads as
    a ``datetime.date`` — so each is rendered through ``str`` here rather than assumed.
    """
    if not isinstance(item, Mapping):
        return str(item)
    return ", ".join(f"{key}={item[key]}" for key in sorted(item))


def _name(name: PackName | None) -> str:
    """A parsed directory name, or nothing when the name is not ``<pack>@<version>``."""
    return "" if name is None else f"{_escape(name.pack)} {_escape(name.version)}"


def _ref(source: SourceRef) -> str:
    """One settings file, as it is printed beside a value it decided."""
    return f"[{source.kind} {_escape(source.name)}]"


def _refs(sources: Sequence[SourceRef]) -> str:
    """Every settings file that had a say in one key, in cascade order."""
    return " ".join(_ref(source) for source in sources)


def _joined(values: Iterable[object]) -> str:
    """A sequence as one line. ``, `` because every element is already escaped to one line."""
    return ", ".join(_escape(str(value)) for value in values)


# ---------------------------------------------------------------------------------------------
# The JSON form
# ---------------------------------------------------------------------------------------------


def render_json(report: ResolutionReport) -> str:
    """The report as one JSON document, on one line per value, with sorted keys.

    An **explicit projection**, not a walk over the dataclasses. Four shipped values are not JSON
    primitives: ``PackRoot.traversable`` is a ``Traversable``, ``SettingsSource.path`` and ``.root``
    and each ``pack_paths`` entry are ``Path`` objects, an ``accepted_unknowns`` value may be a
    ``datetime.date``, and ``PackCandidate.root`` embeds a whole ``PackRoot`` that a walk would
    repeat once per candidate. ``dataclasses.asdict`` raises ``TypeError`` on the first three and
    silently duplicates the fourth, and ``default=str`` on ``json.dumps`` hides all four behind a
    stringification nobody chose and lets a fifth arrive unnoticed.

    So one private function per record type names the keys it emits and converts each value.
    Adding a field to a dataclass therefore does *not* silently add a key: it adds nothing until
    the projection names it, which is the safer of the two failure modes, because the alternative
    is a key whose type nobody chose.

    ``ensure_ascii=True`` rather than ``False``. A directory name on Linux is any byte sequence but
    ``/`` and NUL, so ``os.listdir`` returns a name that is not valid UTF-8 with surrogate escapes,
    and encoding one to UTF-8 raises ``UnicodeEncodeError: surrogates not allowed``. Under
    ``ensure_ascii`` the same name encodes cleanly as an escape. The trade is that a legitimate
    non-ASCII pack name renders escaped; for a tool whose job is to say where it looked, not
    crashing on a filesystem a person's machine can genuinely produce wins.

    Nothing here is passed through ``_escape``. That helper exists so a name cannot forge a *line*,
    and JSON has no lines to forge: the encoder escapes a newline and a surrogate itself, losslessly
    and reversibly, which is what the consumer of this form needs. Escaping first would hand that
    consumer a name that is not the name on disk.
    """
    payload = {
        "tool_version": report.tool_version,
        "rutters_digest": report.rutters_digest,
        "project_root": _text(report.project_root),
        "user_config_from": report.user_config_from,
        "settings_sources": [_json_source(source) for source in report.settings_sources],
        "settings": _json_settings(report.settings),
        "pack_roots": [_json_root(root) for root in report.pack_roots],
        "candidates": [_json_candidate(candidate) for candidate in report.candidates],
        "packs": [_json_match(match) for match in report.packs],
        "dependencies": [_json_dependency(status) for status in report.dependencies],
        "skipped": dict(report.skipped),
        "problems": [_json_problem(problem) for problem in report.problems],
    }
    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=True) + "\n"


def _text(value: object) -> str | None:
    """A ``Path`` or anything else printable as a string, and ``None`` as ``null``."""
    return None if value is None else str(value)


def _json_source(source: SettingsSource) -> dict[str, object]:
    """One located settings file. ``path`` and ``root`` are ``Path`` objects and become strings."""
    return {
        "kind": source.kind,
        "path": str(source.path),
        "root": str(source.root),
        "status": source.status,
        "reason": source.reason,
    }


def _json_root(root: PackRoot) -> dict[str, object]:
    """One pack root. ``traversable`` is never emitted — ``display`` is its rendered form, and a
    ``Traversable``'s ``repr`` is implementation-defined for a zip install or a multiplexed path."""
    return {
        "kind": root.kind,
        "display": root.display,
        "exists": root.exists,
        "source": _json_ref(root.source),
    }


def _json_root_ref(root: PackRoot) -> dict[str, object]:
    """A root as it appears *inside* a candidate or a match: which one it is, and nothing more.

    Embedding the whole record here is what makes a mechanical walk emit every root once per
    candidate — five copies of the bundled root on a run against this project's own repository.
    """
    return {"kind": root.kind, "display": root.display}


def _json_candidate(candidate: PackCandidate) -> dict[str, object]:
    """One entry under one root."""
    return {
        "root": _json_root_ref(candidate.root),
        "entry": candidate.entry,
        "name": _json_name(candidate.name),
        "status": candidate.status,
    }


def _json_match(match: MatchedPack) -> dict[str, object]:
    """One matched pin."""
    return {
        "pin": match.pin,
        "name": _json_name(match.name),
        "root": _json_root_ref(match.root),
        "path": match.path,
    }


def _json_name(name: PackName | None) -> dict[str, object] | None:
    """A parsed directory name, or ``null`` when the name is not ``<pack>@<version>``."""
    return None if name is None else {"pack": name.pack, "version": name.version}


def _json_ref(source: SourceRef | None) -> dict[str, object] | None:
    """One settings file reference."""
    return None if source is None else {"kind": source.kind, "name": source.name}


def _json_dependency(status: DependencyStatus) -> dict[str, object]:
    """One required distribution."""
    return {
        "distribution": status.distribution,
        "installed": status.installed,
        "present": status.present,
    }


def _json_problem(problem: Problem) -> dict[str, object]:
    """One failure. ``code`` is an ``IntEnum`` member, emitted as the integer it is."""
    return {
        "code": int(problem.code),
        "message": problem.message,
        "detail": dict(problem.detail),
    }


def _json_settings(settings: ResolvedSettings | None) -> dict[str, object] | None:
    """Every settings key, or ``null`` when the merge did not run.

    ``null`` and an object of nulls are different facts and both occur: the first means no file was
    read at all, the second means files were read and declared none of these keys.
    """
    if settings is None:
        return None
    return {key: _json_setting(key, getattr(settings, key)) for key in SETTINGS_KEYS}


def _json_setting(key: str, value: object) -> object:
    """One settings key: a mapping of settings, one setting, or ``null``."""
    if isinstance(value, Mapping):
        return {name: _json_one(entry) for name, entry in value.items()}
    if value is None:
        return None
    assert isinstance(value, ResolvedSetting)  # noqa: S101 - the five shapes are exhaustive
    return _json_one(value)


def _json_one(setting: ResolvedSetting[object]) -> dict[str, object]:
    """One effective value with every file behind it, and the per-entry attribution when there is
    one. ``entry_sources`` is ``null`` for a key where there is nothing per-entry to say."""
    return {
        "value": _json_value(setting.value),
        "sources": [_json_ref(source) for source in setting.sources],
        "entry_sources": (
            None
            if setting.entry_sources is None
            else [_json_ref(source) for source in setting.entry_sources]
        ),
    }


def _json_value(value: object) -> object:
    """One effective value as JSON. Five shapes, and a declared floor under the fifth."""
    if isinstance(value, FirstParty):
        return {"include": list(value.include), "exclude": list(value.exclude)}
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _json_scalar(item) for key, item in sorted(value.items(), key=str)}
    return _json_scalar(value)


def _json_scalar(value: object) -> object:
    """A JSON primitive, or its ``str`` when it is not one.

    The floor is declared rather than delegated to ``default=str``: ``accepted_unknowns`` values are
    deliberately not required to be strings, so a ``datetime.date`` reaches here and would raise
    ``TypeError`` from the encoder on a settings file that is entirely legal. Everything else in
    the record is already a primitive by the time it arrives, so this converts the one case the
    schema allows rather than blanketing the document.
    """
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


#: The formats ``--format`` offers, in the order they are offered. ``cli.build_parser`` writes the
#: same two names as a literal — it may not import this module, because that would put
#: ``ruamel.yaml`` on the console script's module-level import path — and a test asserts the two
#: agree.
RENDERERS: Mapping[str, Callable[[ResolutionReport], str]] = {
    "text": render_text,
    "json": render_json,
}
