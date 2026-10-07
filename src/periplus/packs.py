"""Pack resolution: where packs are looked for, what directories are there, and what a pin matches.

Three questions and one fact. Where — ``resolve_pack_roots``. What is there —
``discover_candidates``. Which of them a ``packs:`` pin names — ``match_pins``. The fact is
``bundled_digest``, a hash of the bundled pack files, which tells two installs apart.

**No file inside a pack directory is opened, except by ``bundled_digest``.** It is the one
function here that opens pack files, and it only hashes their bytes. Not a manifest, not
``pack.yaml``, not anything else. That
is a deliberate limit and the reason this module is small: resolving a pin, detecting a
duplicate and refusing a version mismatch are judgments about pack *validity*, and a harness making
them would have to know what a ``folders`` block is before anything knows what a pack is. A pack
directory is named ``<pack>@<version>``, so a pin can be matched against directory names alone. The
validator later confirms the manifest inside agrees with the name outside — a check this module
could never make.

The only ``Traversable`` operations this module calls are ``is_dir``, ``is_file``, ``iterdir`` and
``name``, plus the one ``joinpath`` that reaches the bundled root itself. Apart from
``bundled_digest``'s ``read_bytes``, it never calls ``open`` or ``read_text``, and it never
calls ``builtins.open``.

Nothing here is rendered. A directory name is attacker-influenced text and is stored exactly as it
is on disk; escaping it is ``report.py``'s work, and escaping in the producer would make the escaped
form the value and let two escapes be applied.

This module ships no ``HarnessError`` subclass. ``match_pins`` returns ``Problem`` records rather
than raising, because one call has to report every unmatched pin and an exception carries one —
three unmatched pins produce three problems in a single run.

A note on the name, because the collision is deliberate and easy to misread. ``periplus.packs`` is
this module *and* the bundled pack data at ``src/periplus/packs/``. A regular module wins over a
namespace-package portion in the import system, so ``import periplus.packs`` reaches this file;
nothing imports the data directory as a package, and ``importlib.resources`` reaches it as a
resource rather than as a module.
"""

from __future__ import annotations

import hashlib
import importlib.resources
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from importlib.resources.abc import Traversable
from pathlib import Path
from typing import Literal

from periplus.errors import ExitCode, Problem
from periplus.layout import PACKS_DIRECTORY as PACKS_DIRECTORY
from periplus.settings import PROJECT_MARKER, ResolvedSetting, SourceRef

__all__ = [
    "PACKS_DIRECTORY",
    "MatchedPack",
    "PackCandidate",
    "PackName",
    "PackRoot",
    "bundled_digest",
    "discover_candidates",
    "match_pins",
    "resolve_pack_roots",
]

#: The directory segment that holds packs, at the project root, at the user level and inside the
#: install. One name because it is one convention: a person who knows where their packs go at one
#: level knows it at all three.

# The four kinds of root and the three statuses an entry can have are written out at every
# annotation rather than named once as a module-level alias. `settings.py` records why: mypy
# normalises a `Literal` alias into a union of literals while the runtime object is not a union, so
# a tool that compares the declared types against the imported module reports the module as broken
# when it is correct.


@dataclass(frozen=True, slots=True)
class PackRoot:
    """One directory on the pack search path, whether or not it is there.

    ``display`` is ``str(traversable)`` for every root, with no special case. ``Traversable`` does
    not guarantee a meaningful ``str()``, and that is accepted: the value is only ever rendered,
    every implementation in the standard library produces something a person can read, and a branch
    here would be a second place for the bundled root's name to be decided.

    ``exists`` is ``traversable.is_dir()``. ``Traversable`` declares no ``exists()`` at all.

    ``source`` names the settings file that added a configured root, and is ``None`` for the three
    fixed ones — including a fixed root a settings file also named, which the file did not add.
    """

    kind: Literal["project", "user", "bundled", "configured"]
    display: str
    traversable: Traversable
    exists: bool
    source: SourceRef | None


@dataclass(frozen=True, slots=True)
class PackName:
    """A directory name split at its single ``@``. Parsed from the name, never read from a file.

    Neither half is checked further. The version is not required to be a version and the pack name
    is not required to be anything, because checking either is validation and validation is the
    next task's whole subject.
    """

    pack: str
    version: str


@dataclass(frozen=True, slots=True)
class PackCandidate:
    """One entry directly under one root, and what its name makes of it.

    Every entry is a candidate whatever its type. The type decides the ``status``, not whether the
    entry appears — every candidate directory is reported, and the whole
    point of ``unnamed`` is the difference between "there is nothing there" and "there is something
    there that no pin can ever match".

    ``not_a_directory`` is kept because a ``pack.yaml`` or a
    ``README.md`` sitting loose under a pack root is a thing a person put there: reporting it
    costs one enum member on a branch that already exists, and dropping it silently would hide the
    one case where a name a pin could match is not a directory.

    ``indeterminate`` is what ``is_dir()`` and ``is_file()`` both denying looks like: a broken
    symlink, a socket or a device node, or an entry under a root that can be listed and not
    traversed — a directory at mode ``0o444`` lists its entries and refuses to stat any of them, so
    a real pack directory under it answers ``False`` to both questions. The status is defined by
    what was observed and not by a cause the harness would have to guess at. It exists because
    ``not_a_directory`` is an assertion, and asserting that a directory is not a directory is a
    report that lies; "I could not tell" is the true answer and is a different thing for a person
    to do about it.
    """

    root: PackRoot
    entry: str
    name: PackName | None
    status: Literal["named", "unnamed", "not_a_directory", "indeterminate"]


@dataclass(frozen=True, slots=True)
class MatchedPack:
    """A pin and the directory whose name it matched, under the root that held it.

    ``path`` is a ``str`` and not a ``Path`` because a pack matched under the bundled root has no
    ``Path`` — it has a ``Traversable``, which is not guaranteed to be one. One type for all four
    roots is worth more than a ``Path`` for three of them, and the value is only ever rendered.
    """

    pin: str
    name: PackName
    root: PackRoot
    path: str


def resolve_pack_roots(
    project_root: Path | None,
    user_config_dir: Path,
    configured: ResolvedSetting[tuple[Path, ...]] | None,
) -> tuple[PackRoot, ...]:
    """The pack search path, in fixed order, de-duplicated, with every root reported present or not.

    Four sources in one order that never decides an outcome: the project's own
    ``<root>/.periplus/packs``, the person's ``<user config dir>/packs``, the install's own
    ``periplus/packs`` through ``importlib.resources``, then every ``pack_paths`` entry from either
    settings file. A pin matching under two roots is a problem naming both, not a first-wins pick,
    so the order is there to make the output stable and for nothing else.

    A ``project_root`` of ``None`` produces no project record. ``absent`` is for a directory
    that has a path and is not there; a root with no path has nothing to report, and printing one
    would name a directory nothing ever intended to search. The user root and the bundled root are
    still returned, because both are knowable with no project and no settings at all.

    A ``configured`` of ``None`` is the ordinary case, not an error: a key no settings file declared
    merges to ``None`` rather than to an empty value, and the three fixed roots come back alone.

    The four are de-duplicated in order, first occurrence winning, so a ``pack_paths`` entry
    naming a directory already on the fixed list changes nothing — it was already going to be
    searched, in that position. The surviving root keeps its fixed ``kind`` and its ``source``
    stays ``None``. Without this, every directory under that path is discovered twice and every pin
    matching one of them fails the run for a duplicate that does not exist, which is the same
    hazard ``settings.py`` records as the reason ``pack_paths`` merges by union.

    Comparison is equality between the lexically normalised paths ``settings.py`` produced — no
    ``resolve()``, no symlink following. Two spellings of one directory that differ after
    normalisation are two roots here, and a pin matching under both reports a duplicate. That is
    what the harness can see without resolving a path, and resolving one would print a directory the
    person never named.

    A root that is not a ``Path`` at all cannot be compared with one and is never de-duplicated. On
    every install this project has seen, the bundled root *is* a ``Path`` and de-duplicates like the
    others; the branch exists for the installs where it is not.
    """
    found: list[PackRoot] = []
    if project_root is not None:
        found.append(_root("project", project_root / PROJECT_MARKER / PACKS_DIRECTORY, None))
    found.append(_root("user", user_config_dir / PACKS_DIRECTORY, None))
    found.append(_root("bundled", _bundled_root(), None))
    if configured is not None:
        # `entry_sources` is one reference per entry of `value`, in the same order, because
        # `settings._merge_sequence` appends to both in one loop body — so indexing it positionally
        # is safe by construction. Never zip against `sources`, which is
        # one reference per contributing *file*: the two can have the same length and different
        # content, and zipping produces a plausible, silent misattribution.
        entry_sources = configured.entry_sources
        for index, path in enumerate(configured.value):
            source = entry_sources[index] if entry_sources is not None else None
            found.append(_root("configured", path, source))

    roots: list[PackRoot] = []
    seen: set[Path] = set()
    for root in found:
        key = root.traversable
        if isinstance(key, Path):
            if key in seen:
                continue
            seen.add(key)
        roots.append(root)
    return tuple(roots)


def _bundled_root() -> Traversable:
    # The import package's own name, not the distribution's. `importlib.resources` reaches the
    # bundled data directory as a resource; the module you are reading shadows it as a module.
    return importlib.resources.files("periplus") / PACKS_DIRECTORY


def bundled_digest() -> str:
    """The sha256 of every file under the bundled packs, in sorted path order.

    Each file contributes its path relative to the bundled root, then its bytes, so a renamed file
    changes the digest as a changed one does. Two installs carry the same rutters exactly when this
    string is equal.
    """
    files: dict[str, Traversable] = {}
    pending: list[tuple[str, Traversable]] = [("", _bundled_root())]
    while pending:
        prefix, folder = pending.pop()
        try:
            entries = tuple(folder.iterdir())
        except OSError:
            # An absent or unreadable folder contributes nothing, as `discover_candidates` treats it.
            continue
        for entry in entries:
            name = f"{prefix}{entry.name}"
            if entry.is_dir():
                pending.append((f"{name}/", entry))
            else:
                files[name] = entry
    digest = hashlib.sha256()
    for name in sorted(files):
        digest.update(name.encode("utf-8") + b"\0" + files[name].read_bytes() + b"\0")
    return digest.hexdigest()


def _root(
    kind: Literal["project", "user", "bundled", "configured"],
    traversable: Traversable,
    source: SourceRef | None,
) -> PackRoot:
    """One root record. ``is_dir()`` is the only filesystem call, and nothing is opened."""
    return PackRoot(
        kind=kind,
        display=str(traversable),
        traversable=traversable,
        exists=traversable.is_dir(),
        source=source,
    )


def discover_candidates(roots: Sequence[PackRoot]) -> tuple[PackCandidate, ...]:
    """Every entry directly under every root that is there, in root order then name order.

    One ``iterdir()`` per existing root. One level: no recursion, no second ``iterdir``, no
    ``joinpath`` past the root — so a symlinked directory under a root cannot walk anywhere, and a
    pack's contents are never reached.

    Sorted by root order, then by entry name, by code point. Nothing iterates a directory in
    filesystem order: on ext4 with hashed directories that order is arbitrary, and output that
    agreed with it would differ between two machines holding the same tree.

    A root that exists and cannot be listed contributes no candidates. ``iterdir`` raises
    ``OSError`` on a directory with no read permission and it is caught; the root stays in the
    report with ``exists`` true. It is not a failure on its own — a pin that needed one of its
    directories fails when it is matched, and that message names the roots that were searched.
    """
    candidates: list[PackCandidate] = []
    for root in roots:
        if not root.exists:
            continue
        try:
            # The sort is inside the `try` because that is where `Path.iterdir` raises on the
            # declared floor and it is not the same place on every version. On 3.11 it is a
            # generator function and a `PermissionError` surfaces when the result is walked; on
            # 3.14 it raises at the call. Verified on both, by running the closed-directory case
            # with the sort moved out: 3.14 still catches it and 3.11 lets it escape. So this is a
            # 3.11 requirement that the machine this was written on cannot demonstrate.
            entries = sorted(root.traversable.iterdir(), key=lambda entry: entry.name)
        except OSError:
            continue
        candidates.extend(_candidate(root, entry) for entry in entries)
    return tuple(candidates)


def _candidate(root: PackRoot, entry: Traversable) -> PackCandidate:
    """One entry classified by its type and then by its name.

    ``is_file()`` is asked only when ``is_dir()`` has already said no, so a pack directory — the
    ordinary case — pays for one probe and not two. The answer separates an entry that is a file
    from an entry neither question would claim, which is the whole of ``indeterminate``.
    """
    if not entry.is_dir():
        status: Literal["not_a_directory", "indeterminate"] = (
            "not_a_directory" if entry.is_file() else "indeterminate"
        )
        return PackCandidate(root=root, entry=entry.name, name=None, status=status)
    name = parse_pack_name(entry.name)
    if name is None:
        return PackCandidate(root=root, entry=entry.name, name=None, status="unnamed")
    return PackCandidate(root=root, entry=entry.name, name=name, status="named")


def parse_pack_name(entry: str) -> PackName | None:
    """``<pack>@<version>`` split at its single ``@``, or ``None`` when the name is not that shape.

    Exactly one ``@`` and both sides non-empty. Nothing further is checked, so ``drupal``,
    ``a@b@c``, ``@1.0.0`` and ``drupal@`` are all unnamed. Whether the version is a version and
    whether the pack name is a pack name are questions about validity, and this module answers none.
    """
    if entry.count("@") != 1:
        return None
    pack, _, version = entry.partition("@")
    if not pack or not version:
        return None
    return PackName(pack=pack, version=version)


def match_pins(
    pins: Sequence[str],
    candidates: Sequence[PackCandidate],
) -> tuple[tuple[MatchedPack, ...], tuple[Problem, ...]]:
    """Match each pin against directory names alone. Returns matches and problems, and never raises.

    A name matches a pin when the candidate's status is ``named`` and its entry string equals the
    pin, byte for byte — no case folding, no Unicode normalisation, no whitespace stripping, no
    version comparison. ``drupal@0.1.0`` matches ``drupal@0.1.0`` and nothing else.

    Three outcomes and no fourth:

    * Matched once — one ``MatchedPack``, no problem.
    * Matched nowhere — one problem at ``PIN_UNMATCHED``, naming the roots that were searched and
      every near miss. A pin that does not itself parse falls here with an empty near-miss list; it
      is not a new failure class, because "matched nowhere" is already true of it.
    * Matched under two roots — one problem at ``PIN_DUPLICATED`` naming both roots, **and both
      matches are still returned**. The name is reported twice rather than
      resolved, so dropping either match would report it once and resolve it by omission.

    A near miss is a ``named`` candidate whose *parsed pack name* equals the pin's, and whose entry
    is not the pin. Parsed rather than a prefix: under a prefix comparison a pin of ``php@0.1.0``
    would near-miss ``phpstan@1.0.0``, which is a different pack.

    A directory on the path that no pin names is reported present and unmatched, and is not a
    problem. This function never decides whether it is called at all — matching is skipped when
    settings gave no pins, and that is ``resolution.py``'s call.

    The exit status is not decided here. ``PIN_UNMATCHED`` and ``PIN_DUPLICATED`` are set on the
    ``Problem``, and ``ResolutionReport.exit_code`` takes the lowest code among every problem found.
    """
    matches: list[MatchedPack] = []
    problems: list[Problem] = []
    for pin in pins:
        # The walrus binds the parsed name the candidate already carries, so a match never
        # re-parses a directory name that discovery has parsed once. A candidate carries a name
        # exactly when its status is `named`, which is how `_candidate` builds it.
        found = [
            (candidate, name)
            for candidate in candidates
            if (name := candidate.name) is not None and candidate.entry == pin
        ]
        matches.extend(_matched(pin, candidate, name) for candidate, name in found)
        if not found:
            problems.append(_unmatched(pin, candidates))
        elif len(found) > 1:
            problems.append(_duplicated(pin, [candidate for candidate, _ in found]))
    return tuple(matches), tuple(problems)


def _matched(pin: str, candidate: PackCandidate, name: PackName) -> MatchedPack:
    """One matched pin, under the root that held it."""
    return MatchedPack(
        pin=pin,
        name=name,
        root=candidate.root,
        # Joined lexically from the root's printable name. `Traversable.joinpath` is deliberately
        # not used: this module joins nothing past a root, and the value is only ever rendered.
        path=str(Path(candidate.root.display) / candidate.entry),
    )


def _unmatched(pin: str, candidates: Sequence[PackCandidate]) -> Problem:
    """A pin no directory name matched, with the near misses and the roots that were listed.

    ``searched`` names the roots the candidates came from rather than every root on the path,
    because this function is given candidates and not roots. A root that exists and holds nothing —
    or one that could not be listed — contributes no candidate and so is not named here. The report
    as a whole still carries every root with its own ``exists``, which is where a person reads the
    full list; this detail is the near-at-hand half of it.
    """
    pack = parse_pack_name(pin)
    near = [
        candidate.entry
        for candidate in candidates
        if candidate.status == "named"
        and pack is not None
        and candidate.name is not None
        and candidate.name.pack == pack.pack
        and candidate.entry != pin
    ]
    return Problem(
        code=ExitCode.PIN_UNMATCHED,
        message=f"no pack directory is named {pin!r} on the pack search path",
        detail={
            "pin": pin,
            "searched": _joined(dict.fromkeys(c.root.display for c in candidates)),
            "near_misses": _joined(dict.fromkeys(near)),
        },
    )


def _duplicated(pin: str, found: Sequence[PackCandidate]) -> Problem:
    """One name under two roots. Both roots are named; both matches are returned by the caller."""
    return Problem(
        code=ExitCode.PIN_DUPLICATED,
        message=f"the pack directory {pin!r} was found under more than one root",
        detail={
            "pin": pin,
            "roots": _joined(candidate.root.display for candidate in found),
        },
    )


def _joined(values: Iterable[str]) -> str:
    """Directory names and root names as one string, because ``Problem.detail`` maps names to text.

    ``, `` rather than a newline: a name holding a separator is ambiguous either way, and a newline
    would let a directory name forge a line of the text report before ``report.py`` ever sees it.
    An empty string means none, which is a fact rather than a missing key.
    """
    return ", ".join(values)
