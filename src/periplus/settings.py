"""Settings resolution: finding the two files, reading one, and merging them key by key.

Three separable questions, and they are three functions because they fail independently.
``locate_settings`` decides *which files apply* and opens nothing, so a file that exists and will
not parse can be reported as skipped rather than silently becoming absent.
``load_settings_document`` decides *what is in one file* and knows nothing about layers.
``resolve_settings`` decides *what wins* and reads no filesystem — it takes documents and
sources as arguments, which is what lets the whole cascade be tested against constructed values.

This is the first module in the package to import a runtime distribution. ``ruamel.yaml`` and
``platformdirs`` are both imported at module level here, deliberately and visibly: nothing on
``cli``'s module-level import path may reach this file, which is the property
``tests/test_console_script.py`` asserts by importing ``periplus.cli`` with both distributions
blocked. Before this module existed that test could only fail if somebody imported a distribution
for no reason. From here on it protects something real, because ``cli`` importing ``settings`` at
module level would break the startup check that names a missing dependency.

What this module does not do, because a later component does it:

* It does not substitute a brace in a folder value, join a folder to a root, or check that any path
  exists. A ``folders`` value leaves here as written: one template string, or a tuple of them
  for a list. That is the input of a later folder resolver, which is not built yet.
* It does not parse a ``packs:`` pin into a name and a version, list a directory, or decide whether
  a pack root exists. Pins leave here as the strings the file wrote. That is ``packs.py``.
* It does not decide whether a failure ends the run, and it does not catch its own exception.
  ``resolution.py`` catches ``SettingsUnreadable`` and turns it into a ``Problem`` and a skipped
  source; the "neither file exists" condition is invisible here, because this module is handed
  documents rather than finding them.
* It validates nothing, by design. What it does do is refuse to *lie*
  about a type: a value whose shape does not match the key's declared type is dropped rather than
  coerced into a tuple of characters. See ``MERGE_RULES``.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, Literal, TypeVar

import platformdirs
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from periplus.errors import ExitCode, HarnessError

# Re-exported, so every caller that imported these from here still can. The redundant alias is
# the explicit re-export form, and it is what tells the linter the names are deliberate.
from periplus.layout import PACKS_DIRECTORY as PACKS_DIRECTORY
from periplus.layout import PROJECT_MARKER as PROJECT_MARKER
from periplus.layout import SETTINGS_FILENAME as SETTINGS_FILENAME

__all__ = [
    "MERGE_RULES",
    "FirstParty",
    "ResolvedSetting",
    "ResolvedSettings",
    "SettingsSource",
    "SettingsUnreadable",
    "SourceRef",
    "find_project_root",
    "load_settings_document",
    "locate_settings",
    "resolve_settings",
    "user_config_dir",
]

T = TypeVar("T")

# Three vocabularies are written out at every annotation rather than named once as a module-level
# alias, which is not the arrangement anyone would choose. A `Literal` alias cannot be verified in
# an inline-typed package: mypy normalises `Literal["user", "project"]` into a union of two
# literals, the runtime object is one `_LiteralGenericAlias` and not a union, so a tool that
# compares the declared types against the imported module reports `SourceKind is not a Union` on a
# module that is correct. Measured with `mypy.stubtest` on 2026-08-30 — that run was the evidence
# for this shape, not a check holding it in place; nothing in this project runs stubtest. A leading
# underscore does not exempt the alias.
#
#   the two layers that are settings files  Literal["user", "project"]
#     A third — a `folders` block inside a pack manifest — would arrive as one more member.
#   what happened to one layer's file       Literal["used", "absent", "skipped"]
#     `skipped` is set by the caller that catches a parse failure, never here: the difference
#     between "there is no file" and "there is a file I could not read" is the whole reason
#     locating and loading are two functions.
#   how one settings key merges             Literal["replace", "union", "accumulate", "per_key",
#                                                   "paired"]


#: The environment variable that replaces the user configuration directory outright.
CONFIG_DIR_VARIABLE = "PERIPLUS_CONFIG_DIR"


@dataclass(frozen=True, slots=True)
class SourceRef:
    """Which settings file an effective value came from, as it is printed beside that value."""

    kind: Literal["user", "project"]
    name: str


@dataclass(frozen=True, slots=True)
class SettingsSource:
    """One layer's file: where it is, what a relative path in it means, and what happened to it.

    ``root`` carries the anchor rather than leaving it to be derived, which is what makes "a
    relative path resolves against the root of the file that declared it" structural instead of a
    rule the merge has to remember. The two layers do not derive it the same way — the project
    file's root is its grandparent, because the file is ``<root>/.periplus/settings.yml``, and the
    user file's root is its parent — and an explicit ``--settings PATH`` breaks both derivations.
    Computing it once where the file is located removes the question from every later reader.
    """

    kind: Literal["user", "project"]
    path: Path
    root: Path
    status: Literal["used", "absent", "skipped"]
    reason: str | None

    def ref(self) -> SourceRef:
        """This source as the reference an effective value carries.

        The one place a ``SourceRef.name`` is built from a path, so the two cannot drift.
        """
        return SourceRef(kind=self.kind, name=str(self.path))


@dataclass(frozen=True, slots=True)
class ResolvedSetting(Generic[T]):
    """An effective value and every file that had a say in it.

    There is no way to hold a value without holding where it came from, which is what makes
    research's visibility requirement structural rather than a convention.

    ``sources`` is in cascade order — user first, then project. A key merged by replacement carries
    exactly one entry, the file that won. A key merged by accumulation carries one entry per file
    that declared it, including a file that declared it empty: presence is what makes a file a
    source, not whether its contribution changed the answer.

    ``sources`` attributes the *key* and not the *entries in it*, and for a key that accumulates
    those are different facts. Given a ``pack_paths`` of ``(pathA, pathB)`` and a ``sources`` of
    ``(user, project)``, nothing says which file added which path — so ``packs.py``'s
    ``PackRoot.source``, "which settings file added a configured root", would have to guess, and
    would guess plausibly and silently. ``entry_sources`` is that missing fact: one ``SourceRef``
    per element of ``value``, in the same order, for the keys that accumulate. It is ``None`` for
    every other key, which says "there is nothing per-entry to say here" rather than repeating one
    file N times — a replace key's entries all came from the one file ``sources`` already names.

    One reference per entry, in the same order, holds by construction rather than by a check.
    ``_merge_sequence`` is the only code that builds a non-``None`` ``entry_sources``, and it
    appends to ``values`` and to ``entry_sources`` in one loop body, so the two cannot come out of
    step. A later builder that does not append in lockstep carries that check itself: the defect is
    an ``entry_sources`` short by one, which type-checks, reads correctly, and reaches a report as
    a misattribution rather than as a crash.

    One gap this does not close, stated so it is not mistaken for closed: ``first_party``
    accumulates two lists inside one ``FirstParty`` value, so a flat tuple of the same length as
    ``value`` cannot describe it. Its ``entry_sources`` is ``None``, and per-entry attribution for
    its two lists is unavailable. ``pack_paths`` is the key that needs it.
    """

    value: T
    sources: tuple[SourceRef, ...]
    entry_sources: tuple[SourceRef, ...] | None = None


@dataclass(frozen=True, slots=True)
class FirstParty:
    """The two path-pattern lists that decide where the codebase ends and its dependencies begin.

    Both accumulate across layers, so this is one setting holding two lists rather than two
    settings — ``ResolvedSetting[FirstParty]`` — and it means the sources are the files that
    contributed to either list.
    """

    include: tuple[str, ...]
    exclude: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResolvedSettings:
    """Every settings key, merged, with its sources. A key no file declared is ``None``.

    ``None`` rather than an empty tuple or a machine default, because a key that fell through to
    nothing is exactly the case the output has to make visible: the cascade deliberately does not
    forbid it, and a fabricated default would print as though somebody had chosen it.

    ``folders`` and ``extensions`` are mappings rather than optionals for the same reason in the
    opposite direction — an empty mapping already says "no folder was declared anywhere", and
    wrapping it in an optional would give two ways to write the same fact.
    """

    periplus_version: ResolvedSetting[int] | None
    packs: ResolvedSetting[tuple[str, ...]] | None
    pack_paths: ResolvedSetting[tuple[Path, ...]] | None
    folders: Mapping[str, ResolvedSetting[str | tuple[str, ...]]]
    extensions: Mapping[str, ResolvedSetting[str]]
    first_party: ResolvedSetting[FirstParty] | None
    exclude: ResolvedSetting[tuple[str, ...]] | None
    re_include: ResolvedSetting[tuple[str, ...]] | None
    accepted_unknowns: ResolvedSetting[tuple[Mapping[str, object], ...]] | None
    #: The named text values every template of every pack may name, merged as ``extensions`` is.
    values: Mapping[str, ResolvedSetting[str]]


class SettingsUnreadable(HarnessError):
    """A settings file exists and could not be turned into a mapping.

    One class for four causes — the bytes could not be read, they could not be decoded, the parser
    refused them, or the document parsed into something that is not a mapping — because they are one
    thing to do about it: open the file and fix it. ``detail`` names which one it was.

    This is the only ``HarnessError`` subclass this module ships. There is deliberately no
    ``SettingsNotFound``: this module never sees the "neither file exists" condition, because it
    takes documents and sources as arguments. That detection belongs to ``resolution.py``.
    """

    code = ExitCode.UNREADABLE_SETTINGS


def find_project_root(start: Path) -> Path | None:
    """The nearest directory at or above ``start`` that holds a ``.periplus/`` directory.

    Lexical, and never ``resolve()``d. Following a symlink here would report a project root the
    person never wrote and never navigated through, and the walk would leave the tree it was asked
    about. ``Path.parents`` is a lexical sequence, so a symlinked parent cannot send the walk
    somewhere unrelated; it stops at the filesystem root and returns ``None``.

    The marker is a directory, not a file, for the reason ``git`` looks for ``.git`` — the same
    directory holds the settings file and the project's own packs, so one marker answers both.
    """
    for directory in (start, *start.parents):
        if (directory / PROJECT_MARKER).is_dir():
            return directory
    return None


def user_config_dir(env: Mapping[str, str]) -> Path:
    """Periplus' own configuration directory — ``~/.config/periplus`` on Linux, not ``~/.config``.

    One function returns one level whichever branch produced it, which is what
    ``PERIPLUS_CONFIG_DIR`` forces: a variable named for this tool cannot sensibly point at the
    directory holding every tool's configuration. So the user settings file is
    ``<user config dir>/settings.yml`` and the user pack root is ``<user config dir>/packs/``, with
    no ``periplus`` segment appended by us.

    The environment is an argument rather than something this function reads, so a test moves the
    user layer without monkeypatching a module — and what it reads out of that argument is
    ``PERIPLUS_CONFIG_DIR`` alone. Everything else is ``platformdirs``, which reads the process
    environment itself: ``XDG_CONFIG_HOME`` on POSIX, ``%APPDATA%`` on Windows,
    ``~/Library/Application Support`` on macOS. Verified 2026-08-30 against platformdirs 4.11.5 that
    ``user_config_dir()`` accepts no environment argument and reads ``os.environ`` at
    ``unix.py:326``, so an ``XDG_CONFIG_HOME`` passed through this mapping would be read by nothing
    and offering it would be a decoration on the one variable that matters.

    ``appauthor=False`` is load-bearing on Windows and inert everywhere else: left at ``None``,
    platformdirs uses the app name as the author directory and returns
    ``%APPDATA%\\periplus\\periplus``.
    """
    override = env.get(CONFIG_DIR_VARIABLE)
    if override:
        return Path(override)
    return Path(platformdirs.user_config_dir("periplus", appauthor=False))


def locate_settings(
    project_root: Path | None,
    user_config_dir: Path | None,
    settings_path: Path | None = None,
) -> tuple[SettingsSource, ...]:
    """One record per layer whose file location is knowable, in cascade order: user, then project.

    Opens nothing. A layer whose file is not there comes back ``absent`` rather than being left out,
    because the report has to name the file it did not find.

    A layer appears at all only when its location can be named. ``user_config_dir=None`` means the
    user layer was not consulted, and a project layer with neither a root nor an explicit file has
    no path to report as absent.

    The project source's root is ``project_root`` when one is given, and otherwise derived from
    ``settings_path`` by one rule: a file at ``X/.periplus/settings.yml`` anchors to ``X``,
    and any other file anchors to its own directory. So the contract for the caller is one line —
    pass the root when something decided it, and pass ``settings_path`` with ``project_root=None``
    to get the ``--settings`` rule. Deciding between ``--project-root``, ``--settings`` and the walk
    is the caller's, because only it knows which flag the person typed.
    """
    sources: list[SettingsSource] = []

    if user_config_dir is not None:
        sources.append(_source("user", user_config_dir / SETTINGS_FILENAME, user_config_dir))

    if settings_path is not None:
        sources.append(_source("project", settings_path, project_root or _anchor_of(settings_path)))
    elif project_root is not None:
        path = project_root / PROJECT_MARKER / SETTINGS_FILENAME
        sources.append(_source("project", path, project_root))

    return tuple(sources)


def _anchor_of(settings_path: Path) -> Path:
    """The project root an explicitly named settings file implies.

    A file at ``X/.periplus/settings.yml`` fixes the root at ``X``, so a person pointing
    at a real project's file gets that project's root and the two can never disagree. Any other file
    anchors to its own directory, which is the only answer available and the one that keeps a
    relative ``pack_paths`` entry beside the file that wrote it.
    """
    parent = settings_path.parent
    return parent.parent if parent.name == PROJECT_MARKER else parent


def _source(kind: Literal["user", "project"], path: Path, root: Path) -> SettingsSource:
    """One located layer. ``is_file()`` is the only filesystem call; the file is not opened."""
    return SettingsSource(
        kind=kind,
        path=path,
        root=root,
        status="used" if path.is_file() else "absent",
        reason=None,
    )


def load_settings_document(path: Path) -> Mapping[str, object]:
    """Read one settings file into a mapping, or raise ``SettingsUnreadable``.

    ``YAML(typ='safe', pure=True)``. ``safe`` refuses arbitrary object construction and is YAML 1.2,
    which is the whole reason ruamel is here rather than PyYAML: verified 2026-08-30 on 0.19.1, a
    duplicate key raises where PyYAML keeps the last value silently, and ``12:30``, ``on``, ``yes``
    and ``no`` stay the strings they were written as, where PyYAML makes the first of those the
    integer 750. ``pure`` pins the pure-Python parser, which ruamel would otherwise swap for the C
    one whenever the optional ``ruamel.yaml.clib`` extension happens to be importable — an
    environment-dependent branch in a tool that promises output that is byte-identical
    across machines.

    One ``except`` covers every parser refusal, because ``DuplicateKeyError``, ``ParserError`` and
    ``ScannerError`` all subclass ``YAMLError``; the parser's own message, marks and all, goes into
    ``detail`` rather than into the one line a person reads.

    ``OSError`` and ``UnicodeDecodeError`` are caught for the same exit code, because exit 4
    means "a settings file could not be read **or** parsed", and a person gets a named
    failure rather than a traceback. A settings file that is a directory, or unreadable, or holds
    bytes that are not UTF-8, reaches a person as a line naming the file.

    An empty file loads as ``None`` and a scalar or a list document loads as a ``str`` or a
    ``list``. All three are valid YAML that is not a settings file, and all three are exit 4 — the
    check is here rather than in the parser because no parser has an opinion about it.

    Keys are not checked. A key the settings schema does not name is ignored by the merge without
    comment, whatever its type, because this module validates nothing.
    """
    yaml = YAML(typ="safe", pure=True)
    try:
        with path.open("r", encoding="utf-8") as stream:
            document = yaml.load(stream)
    except YAMLError as error:
        raise SettingsUnreadable(
            f"the settings file could not be parsed: {path}",
            {"path": str(path), "cause": "parser", "detail": str(error)},
        ) from error
    except UnicodeDecodeError as error:
        raise SettingsUnreadable(
            f"the settings file is not valid UTF-8: {path}",
            {"path": str(path), "cause": "encoding", "detail": str(error)},
        ) from error
    except OSError as error:
        raise SettingsUnreadable(
            f"the settings file could not be read: {path}",
            {"path": str(path), "cause": "read", "detail": str(error)},
        ) from error

    if not isinstance(document, Mapping):
        raise SettingsUnreadable(
            f"the settings file is not a mapping: {path}",
            {"path": str(path), "cause": "shape", "detail": type(document).__name__},
        )
    return document


def _as_int(value: object) -> int | None:
    """An integer, and not a ``bool`` wearing one. ``periplus_version: true`` is not version 1."""
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _as_strings(value: object) -> tuple[str, ...] | None:
    """A list of strings, all of them, or nothing at all."""
    if isinstance(value, list | tuple) and all(isinstance(item, str) for item in value):
        return tuple(value)
    return None


def _as_string_mapping(value: object) -> Mapping[str, str] | None:
    """A mapping of string to string, all of them, or nothing at all."""
    if isinstance(value, Mapping) and all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    ):
        return dict(value)
    return None


def _as_folder_mapping(value: object) -> Mapping[str, str | tuple[str, ...]] | None:
    """A mapping of string to a string or a non-empty list of strings, all of them, or nothing."""
    if isinstance(value, Mapping) and all(
        isinstance(key, str)
        and (
            isinstance(item, str)
            or (isinstance(item, list) and item and _as_strings(item) is not None)
        )
        for key, item in value.items()
    ):
        return {key: item if isinstance(item, str) else tuple(item) for key, item in value.items()}
    return None


def _as_mappings(value: object) -> tuple[Mapping[str, object], ...] | None:
    """A list of string-keyed mappings, whatever their values are.

    The values are deliberately not required to be strings. An ``accepted_unknowns`` entry's
    ``accepted_on`` is a date, and an unquoted ``2026-08-28`` loads as a ``datetime.date`` under
    ``typ='safe'`` — measured, not assumed. Requiring ``str`` here would silently delete a
    legitimate entry from a person's file to satisfy a type annotation.
    """
    if isinstance(value, list | tuple) and all(
        isinstance(item, Mapping) and all(isinstance(key, str) for key in item) for item in value
    ):
        return tuple(dict(item) for item in value)
    return None


def _as_first_party(value: object) -> FirstParty | None:
    """A ``first_party`` block. A missing or malformed half is an empty list, not a refusal."""
    if not isinstance(value, Mapping):
        return None
    return FirstParty(
        include=_as_strings(value.get("include", [])) or (),
        exclude=_as_strings(value.get("exclude", [])) or (),
    )


@dataclass(frozen=True, slots=True)
class _Rule:
    """How one settings key merges across layers, and what shape its value has to be.

    ``coerce`` is part of the rule rather than a step beside it, because the two are one decision:
    the behaviour says which contributions combine and the coercion says which ones count. A
    contribution the coercion rejects is dropped exactly like a key the schema does not name.
    """

    behaviour: Literal["replace", "union", "accumulate", "per_key", "paired"]
    coerce: Callable[[object], Any]
    anchor: bool = False


#: The merge rule for every key the settings schema names, keyed by the name. Data, not branches:
#: a new key in the settings schema is a row here and a field on ``ResolvedSettings``, never a
#: condition inside the merge.
#:
#: "Scalars — last wins" and "``packs`` — replace" are
#: one operation: take the last file that declared the key. One row kind, two names in prose.
#:
#: Only ``pack_paths`` sets ``anchor``, which turns each relative string into a path under the root
#: of the file that declared it. ``folders`` values are templates that a later folder resolver will
#: join to the project root, so they are stored exactly as written, braces intact.
MERGE_RULES: Mapping[str, _Rule] = {
    "periplus_version": _Rule("replace", _as_int),
    "packs": _Rule("replace", _as_strings),
    "pack_paths": _Rule("union", _as_strings, anchor=True),
    "folders": _Rule("per_key", _as_folder_mapping),
    "extensions": _Rule("per_key", _as_string_mapping),
    "first_party": _Rule("paired", _as_first_party),
    "exclude": _Rule("accumulate", _as_strings),
    "re_include": _Rule("accumulate", _as_strings),
    "accepted_unknowns": _Rule("accumulate", _as_mappings),
    "values": _Rule("per_key", _as_string_mapping),
}


def _anchor_path(root: Path, value: str) -> Path:
    """``value`` as an absolute path under ``root``, normalised lexically and never resolved.

    An absolute entry is kept exactly as written. A relative one is joined and normalised with
    ``os.path.normpath``, which collapses ``..`` textually; ``Path.resolve()`` would follow a
    symlink and print a directory the person never named.
    """
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate
    return Path(os.path.normpath(root / candidate))


def _merge_key(
    name: str, rule: _Rule, layers: Sequence[tuple[SettingsSource, Mapping[str, object]]]
) -> Any:  # noqa: ANN401 - the return type is the field's, and the field declares it
    """Merge one key across every layer that declared it, in cascade order.

    Returns ``None`` for a key no layer declared, except under ``per_key``, where the empty mapping
    already says it.
    """
    contributions = [
        (source, coerced)
        for source, document in layers
        if name in document and (coerced := rule.coerce(document[name])) is not None
    ]

    if rule.behaviour == "per_key":
        return _merge_per_key(contributions)
    if not contributions:
        return None
    if rule.behaviour == "replace":
        source, value = contributions[-1]
        return ResolvedSetting(value=value, sources=(source.ref(),))
    if rule.behaviour == "paired":
        return ResolvedSetting(
            value=FirstParty(
                include=tuple(item for _, value in contributions for item in value.include),
                exclude=tuple(item for _, value in contributions for item in value.exclude),
            ),
            sources=tuple(source.ref() for source, _ in contributions),
        )
    return _merge_sequence(contributions, rule)


def _merge_per_key(
    contributions: Sequence[tuple[SettingsSource, Mapping[str, str]]],
) -> Mapping[str, ResolvedSetting[str]]:
    """A mapping merged entry by entry: for each name, the last layer that declared *that name*.

    Each entry carries the one file that won it, which is what makes the fell-through case visible —
    a name only the user file declares survives into the result carrying the user file as its
    source, beside a name the project file overrode carrying the project file.

    Sorted by name. ``report.py`` sorts everything it prints, but this mapping is a value a second
    consumer can hold, and a mapping that reaches anyone in the order a YAML file happened to be
    written in is a determinism defect waiting for a consumer that does not sort.
    """
    merged: dict[str, ResolvedSetting[str]] = {}
    for source, mapping in contributions:
        for name, value in mapping.items():
            merged[name] = ResolvedSetting(value=value, sources=(source.ref(),))
    return dict(sorted(merged.items()))


def _merge_sequence(
    contributions: Sequence[tuple[SettingsSource, tuple[Any, ...]]], rule: _Rule
) -> ResolvedSetting[tuple[Any, ...]]:
    """Concatenate every layer's list in cascade order.

    ``union`` drops a repeat and ``accumulate`` keeps it, and the difference is not cosmetic.
    ``pack_paths`` names directories to search: the same directory reached from two files is one
    place to look, and listing it twice would make one pack directory match a pin under two roots
    and fail the run at exit 6 for a duplicate that does not exist. ``exclude`` and ``re_include``
    are ordered patterns where a repeat costs nothing and removing one would quietly reorder the
    rest.

    De-duplication keeps the first occurrence, so the earliest layer that named a path fixes its
    position, and every layer that named it stays in ``sources``. It is also the layer the surviving
    entry is attributed to: a directory both files name was added by the earlier one, and the later
    one changed nothing about where it sits in the search order.

    ``entry_sources`` is built here, in the loop, and not derived afterwards. The declaring source
    is in hand at the moment each item is appended and nowhere else; once the values are
    concatenated the fact is gone. That is why per-entry attribution cannot be added to a merge
    that did not collect it.
    """
    values: list[Any] = []
    entry_sources: list[SourceRef] = []
    for source, value in contributions:
        for item in value:
            item = _anchor_path(source.root, item) if rule.anchor else item
            if rule.behaviour == "union" and item in values:
                continue
            values.append(item)
            entry_sources.append(source.ref())
    return ResolvedSetting(
        value=tuple(values),
        sources=tuple(source.ref() for source, _ in contributions),
        entry_sources=tuple(entry_sources),
    )


def resolve_settings(
    user: Mapping[str, object] | None,
    project: Mapping[str, object] | None,
    sources: Sequence[SettingsSource],
) -> ResolvedSettings:
    """Merge the layers into one record where every effective value names the files behind it.

    The cascade is ``sources``' own order rather than a hardcoded user-then-project, so the order
    ``locate_settings`` returns is the order that applies and can be tested by reordering it.

    A document is paired with the source of its own ``kind``, which is where a relative path in it
    gets its anchor from. A layer contributes only when both halves are present: a ``used`` source
    with no document, and a document for a layer that has no ``used`` source, are each skipped.
    Neither can come from a person's input — only from wiring — and ``resolution.py``, the one
    caller, builds this mapping from the same ``sources`` tuple it passes in.
    """
    documents: dict[str, Mapping[str, object] | None] = {"user": user, "project": project}
    layers = [
        (source, document)
        for source in sources
        if source.status == "used" and (document := documents[source.kind]) is not None
    ]
    merged = {name: _merge_key(name, rule, layers) for name, rule in MERGE_RULES.items()}
    return ResolvedSettings(
        periplus_version=merged["periplus_version"],
        packs=merged["packs"],
        pack_paths=merged["pack_paths"],
        folders=merged["folders"],
        extensions=merged["extensions"],
        first_party=merged["first_party"],
        exclude=merged["exclude"],
        re_include=merged["re_include"],
        accepted_unknowns=merged["accepted_unknowns"],
        values=merged["values"],
    )
