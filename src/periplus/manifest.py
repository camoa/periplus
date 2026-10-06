"""Pack manifests: reading one ``pack.yaml``, and walking ``depends`` into an ordered list.

Two questions, and they are two functions because they fail differently. What is in one manifest —
``load_manifest``, which raises, because one file has one failure. What order a pinned pack and
everything beneath it load in — ``resolve_pack_order``, which returns ``Problem`` records and never
raises, because one call has to report every unresolvable name, every duplicate and every cycle,
and an exception carries one. That is the same split ``settings.py`` and ``packs.py`` already
draw, for the same reason, and it is why this module ships one ``HarnessError`` subclass and also
returns problems.

**This module opens files inside pack directories. ``packs.py`` still does not.** The contract it
states is not amended and not weakened: resolving a pin, detecting a duplicate directory and
refusing a version mismatch remain judgments made from directory names alone, so that nothing has
to know what a ``folders`` block is before it knows what a pack is. This is the peer module that
runs *after* that, on the directories that stage produced. It is a consumer of ``PackCandidate``
and ``MatchedPack``, never an extension of the module that produces them, and nothing here is
imported by ``packs.py``.

What it does **not** do, because the validator does it:

* It does not check that the ``pack:`` inside a directory agrees with the ``<pack>@<version>``
  outside. ``packs.py`` assigns that to the validator by name, and doing it here would put one
  judgment in two places. What this module does instead is refuse to pick between them silently:
  ``LoadedPack`` carries the directory's ``PackName`` and the manifest's own ``pack`` side by side,
  both unresolved, and the one rule that decides anything — *a ``depends`` entry resolves against
  the pack half of a directory name* — is written down rather than inferred. A manifest that names
  itself something else therefore loads under its directory's name and is refused later, which is
  a report that is incomplete rather than one that lies.
* It enforces no line of ``pack-manifest.schema.json``. ``required: ["pack", "version"]`` is line 9
  of that file and it is the validator's to enforce; a manifest missing either key loads here with
  that field ``None``. A key whose value is not the declared shape — a ``depends`` that is a string
  rather than a list of them — is dropped exactly as ``settings.py`` drops a mistyped settings
  value, rather than coerced into a tuple of characters. Dropped and not warned about, because a
  warning here is the validator's whole job arriving early and half-built.

The one thing a document *must* be is a mapping. That is not schema enforcement but the difference
between a file that can be read and one that cannot: an empty ``pack.yaml``, a list document and a
bare scalar are all valid YAML and none of them is a manifest, and there is no field to put them
in. They are ``ManifestUnreadable``, the same as bytes that will not decode.

Determinism, which is a stated property of the whole project and not a nicety here. Two runs over
one tree return the same order, and so do two runs whose inputs arrive in different order:
``depends`` entries are walked sorted and de-duplicated, pinned packs are walked sorted by name,
and nothing iterates a set or a directory in filesystem order. Sorting ``depends`` rather than
keeping the author's order costs nothing the engine spec would miss — contributions merge
additively and must not depend on load order — and buys an order that is a function of the graph
instead of a function of how somebody typed a list.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from importlib.resources.abc import Traversable
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError

from periplus.errors import ExitCode, HarnessError, Problem
from periplus.packs import MatchedPack, PackCandidate, PackName

__all__ = [
    "MANIFEST_FILENAME",
    "LoadedPack",
    "ManifestUnreadable",
    "PackManifest",
    "load_manifest",
    "resolve_pack_order",
]

#: The manifest's filename, one per pack directory. Declared here rather than in ``layout.py``,
#: which holds the three names a *project* is laid out by and exists because three modules read
#: them. This is a pack's own layout and one module reads it; the validator, when it wants it,
#: imports it from here the way ``packs.py`` re-exports ``PACKS_DIRECTORY``.
MANIFEST_FILENAME = "pack.yaml"


@dataclass(frozen=True, slots=True)
class PackManifest:
    """One ``pack.yaml``, as the fields this module reads plus everything else it did not.

    ``pack`` and ``version`` are optional although the schema requires both, because the schema is
    a promise a validator keeps and this module is not that validator. A manifest that omits one,
    or writes something that is not a string, carries ``None`` here — a fact, where a fabricated
    empty string would be a value nobody wrote.

    ``depends`` is the only field this module acts on. It is ``()`` for a manifest that declares
    none and for one whose ``depends`` is not a list of strings, which are two different files and
    one behaviour: neither contributes an edge, and the validator separates them.

    ``document`` is the whole parsed mapping, carried rather than discarded so that the consumers
    this reader exists for — ``periplus spec`` and framework detection — read ``folders``,
    ``files``, ``grammar`` and ``boundary`` without this module growing a field per block and
    without a second parse of the same bytes. It is the parse result itself, not a forecast of what
    somebody might want.
    """

    pack: str | None
    version: str | None
    depends: tuple[str, ...]
    document: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class LoadedPack:
    """One pack directory and the manifest inside it, with both names left unresolved.

    ``name`` is parsed from the directory name and ``manifest.pack`` is what the file says it is.
    They are both here and neither wins, for the reason the module docstring gives: choosing is the
    validator's, and choosing silently is the failure this package refuses everywhere.

    ``directory`` is the ``Traversable`` for the pack directory, which is the thing a consumer
    needs and the thing ``MatchedPack`` cannot give it — that record carries a ``str`` path,
    deliberately, because ``packs.py`` never joins past a root. Rule files live under this
    directory and a consumer opens them through this handle, so it works under an install where the
    bundled root is not a ``Path``.

    ``path`` is the printable form, joined lexically from the root's own display exactly as
    ``MatchedPack.path`` is, so a pack named in this module's output and in a resolution report
    reads the same in both.
    """

    name: PackName
    directory: Traversable
    path: str
    manifest: PackManifest


class ManifestUnreadable(HarnessError):
    """A pack manifest could not be turned into a mapping.

    One class for five causes — the file is not there, the bytes could not be read, they could not
    be decoded, the parser refused them, or the document is not a mapping — because they are one
    thing to do about it: open the named file and fix it. ``detail`` names which one it was, so the
    five stay separable for anyone reading ``--format json`` without becoming five exit codes that
    mean the same remedy.

    "Not there" is one of the five rather than a class of its own. A pack directory with no
    ``pack.yaml`` in it is not a pack, and the remedy is the same sentence: look at that path.
    """

    code = ExitCode.UNREADABLE_MANIFEST


def load_manifest(directory: Traversable) -> PackManifest:
    """Read the ``pack.yaml`` in one pack directory, or raise ``ManifestUnreadable``.

    ``YAML(typ='safe', pure=True)``, the same parser configuration ``settings.py`` uses and for the
    same three reasons: ``safe`` refuses arbitrary object construction, ``safe`` is YAML 1.2 so a
    duplicate key is refused rather than silently keeping the last value and a bare ``on`` stays the
    string it was written as, and ``pure`` pins the pure-Python parser rather than letting an
    optional C extension decide which one runs — an environment-dependent branch in a tool that
    promises byte-identical output across machines.

    ``FileNotFoundError`` is caught before ``OSError``, which it subclasses, because the two have
    different remedies and folding them would print "could not be read" about a file that was never
    written. Everything else an ``OSError`` can be — a directory where the manifest belongs, a
    permission refusal, a dangling symlink — is one message naming the path.

    Nothing is validated. See the module docstring for which lines of the schema this deliberately
    does not enforce and why.
    """
    manifest = directory / MANIFEST_FILENAME
    display = str(manifest)
    yaml = YAML(typ="safe", pure=True)
    try:
        with manifest.open("r", encoding="utf-8") as stream:
            document = yaml.load(stream)
    except FileNotFoundError as error:
        raise ManifestUnreadable(
            f"the pack directory has no {MANIFEST_FILENAME}: {display}",
            {"path": display, "cause": "missing", "detail": str(error)},
        ) from error
    except YAMLError as error:
        raise ManifestUnreadable(
            f"the pack manifest could not be parsed: {display}",
            {"path": display, "cause": "parser", "detail": str(error)},
        ) from error
    except UnicodeDecodeError as error:
        raise ManifestUnreadable(
            f"the pack manifest is not valid UTF-8: {display}",
            {"path": display, "cause": "encoding", "detail": str(error)},
        ) from error
    except OSError as error:
        raise ManifestUnreadable(
            f"the pack manifest could not be read: {display}",
            {"path": display, "cause": "read", "detail": str(error)},
        ) from error

    if not isinstance(document, Mapping):
        raise ManifestUnreadable(
            f"the pack manifest is not a mapping: {display}",
            {"path": display, "cause": "shape", "detail": type(document).__name__},
        )
    return PackManifest(
        pack=_as_string(document.get("pack")),
        version=_as_string(document.get("version")),
        depends=_as_strings(document.get("depends")),
        document=document,
    )


def _as_string(value: object) -> str | None:
    """A string, or nothing. A ``version:`` written unquoted as ``0.1`` is a float, not a
    version."""
    return value if isinstance(value, str) else None


def _as_strings(value: object) -> tuple[str, ...]:
    """A list of strings, all of them, or nothing at all — never a tuple of characters."""
    if isinstance(value, list | tuple) and all(isinstance(item, str) for item in value):
        return tuple(value)
    return ()


@dataclass(frozen=True, slots=True)
class _Directory:
    """One pack directory, reached the same way whether a pin named it or a ``depends`` found it.

    It exists so that the two are one code path. A ``PackCandidate`` carries an optional
    ``PackName`` because most entries under a pack root are not packs; every directory that gets
    this far has a name, and saying so in the type is what keeps a ``None`` from having to be
    checked for on a branch that cannot happen and cannot be tested.
    """

    name: PackName
    directory: Traversable
    path: str


def resolve_pack_order(
    pinned: Sequence[MatchedPack],
    candidates: Sequence[PackCandidate],
) -> tuple[tuple[LoadedPack, ...], tuple[Problem, ...]]:
    """Every pinned pack and everything beneath it, dependencies first. Never raises.

    The order is a depth-first post-order over the ``depends`` graph, entered at the pinned packs in
    sorted name order and descending into each pack's dependencies in sorted, de-duplicated name
    order. Dependencies therefore come out before the packs that declare them, every pack appears
    exactly once however many packs reach it, and the whole sequence is a function of the graph
    rather than of the order the arguments arrived in.

    How a name becomes a directory, which is the one rule this module decides and so is written
    here rather than left to be inferred:

    * A **pinned** pack is the directory its pin matched. A pin names ``<pack>@<version>`` outright,
      so it settles its own version and no search is made for it. Two pins carrying the same pack
      half — ``php@0.1.0`` and ``php@0.2.0`` both pinned — are ``DEPENDS_DUPLICATED``, because the
      graph is keyed by pack name and a name cannot be two packs at once.
    * A **``depends``** entry is the one ``named`` candidate directory whose pack half equals it.
      None is ``DEPENDS_UNMATCHED``; more than one is ``DEPENDS_DUPLICATED``, reported rather than
      resolved, because the entry carries no version and nothing in the manifest says which was
      meant.

    A name that is also pinned resolves to the pinned directory. That falls out of the pins being
    walked first and is kept deliberately: an explicit pin is a version somebody chose, and a
    ``depends`` entry is not, so the pin is the only stated preference in the room.

    Each name is resolved once and its outcome remembered, failures included, so a pack five other
    packs depend on produces one problem rather than five. What is reported is a fact about the
    name, and a fact repeated per referrer is the same fact printed five times.

    A failure never empties the result. A pack whose dependency did not resolve is still returned —
    its own manifest was read — and a cycle is reported with the offending edge dropped, so what
    comes back is the order of the graph without that edge. Both follow ``match_pins``, which
    returns both halves of a duplicated pin and reports it: withholding the result would resolve by
    omission the thing the problem exists to leave open.
    """
    problems: list[Problem] = []
    pinned_directories = _pinned_directories(pinned)
    discovered = _discovered_directories(candidates)
    resolved: dict[str, LoadedPack | None] = {}
    order: list[LoadedPack] = []
    for name in sorted(pinned_directories):
        _walk(name, pinned_directories, discovered, resolved, order, problems)
    return tuple(order), tuple(problems)


def _pinned_directories(pinned: Sequence[MatchedPack]) -> dict[str, tuple[_Directory, ...]]:
    """The pinned packs grouped by the pack half of their name, each group in directory order.

    A pin needs no search: ``match_pins`` matches a candidate when ``candidate.entry == pin`` and
    only when its status is ``named``, so the pin *is* the entry, the parsed name comes with the
    record, and the directory is that entry under the root the match names.

    A group holds more than one entry when two pins share a pack half, and also when one pin
    matched under two roots — which ``match_pins`` has already reported at ``PIN_DUPLICATED``. The
    second report this produces is not that one restated: it says the pack *name* resolves to two
    directories, which is what stops the graph, and it would be true of two different pins as well.
    """
    grouped: dict[str, list[_Directory]] = {}
    for match in pinned:
        grouped.setdefault(match.name.pack, []).append(
            _directory(match.root.traversable, match.root.display, match.pin, match.name)
        )
    return {name: _sorted_directories(group) for name, group in grouped.items()}


def _discovered_directories(
    candidates: Sequence[PackCandidate],
) -> dict[str, tuple[_Directory, ...]]:
    """Every ``named`` candidate grouped by its pack half, each group in directory order.

    Only ``named`` candidates are here. An ``unnamed`` entry has no pack half for a ``depends`` to
    equal, and a ``not_a_directory`` or ``indeterminate`` one is not a pack directory whatever it is
    called — all three are already reported by discovery, and admitting one here would let a
    ``README.md`` under a pack root satisfy a dependency.
    """
    grouped: dict[str, list[_Directory]] = {}
    for candidate in candidates:
        if candidate.status == "named" and candidate.name is not None:
            grouped.setdefault(candidate.name.pack, []).append(
                _directory(
                    candidate.root.traversable,
                    candidate.root.display,
                    candidate.entry,
                    candidate.name,
                )
            )
    return {name: _sorted_directories(group) for name, group in grouped.items()}


def _directory(root: Traversable, display: str, entry: str, name: PackName) -> _Directory:
    """One pack directory: the handle it is opened through and the path it is printed as.

    The handle is ``Traversable.joinpath``, which is how a bundled pack is reached on an install
    where the root is not a ``Path``. The printed path is joined lexically from the root's own
    display, the same join ``packs.py`` makes for ``MatchedPack.path``, so one directory reads
    identically in a resolution report and here.
    """
    return _Directory(name=name, directory=root / entry, path=str(Path(display) / entry))


def _sorted_directories(group: Sequence[_Directory]) -> tuple[_Directory, ...]:
    """One group of directories, de-duplicated by printable path and sorted by it.

    Sorted so that the directory a duplicate problem names first does not depend on which root was
    listed first, and de-duplicated because two pins naming one directory are one directory: the
    same pin appearing twice in a ``packs:`` list must not turn into a duplicate that does not
    exist.
    """
    by_path = {entry.path: entry for entry in group}
    return tuple(by_path[path] for path in sorted(by_path))


def _walk(
    start: str,
    pinned_directories: Mapping[str, tuple[_Directory, ...]],
    discovered: Mapping[str, tuple[_Directory, ...]],
    resolved: dict[str, LoadedPack | None],
    order: list[LoadedPack],
    problems: list[Problem],
) -> None:
    """Depth-first from one name, appending each pack to ``order`` after all of its dependencies.

    Iterative rather than recursive. The depth is a codebase's dependency depth and nothing here
    would plausibly reach the interpreter's limit, but this function's contract is that it never
    raises for anything a person's input can cause, and a hand-written chain of a thousand packs is
    a person's input.

    ``on_path`` maps a name being expanded to its position on the stack, which is what turns a back
    edge into a nameable cycle rather than a bare "there was one": the slice from that position is
    the cycle, in the order it was entered. The edge is then dropped and the walk continues, so one
    cycle produces one problem and the packs around it still come back ordered.

    ``on_path`` is tested before ``resolved``, and the order is load-bearing. A name enters
    ``resolved`` when it is expanded and reaches ``order`` when it is popped, so every name
    currently on the path is already in ``resolved`` — testing that first would read a back edge as
    a pack that is simply finished, and no cycle would ever be found.
    """
    if start in resolved:
        return
    first = _resolve(start, pinned_directories, discovered, resolved, problems)
    stack: list[tuple[str, tuple[str, ...], int]] = [(start, _dependencies_of(first), 0)]
    on_path: dict[str, int] = {start: 0}
    while stack:
        name, dependencies, index = stack[-1]
        if index == len(dependencies):
            stack.pop()
            del on_path[name]
            finished = resolved[name]
            if finished is not None:
                order.append(finished)
            continue
        stack[-1] = (name, dependencies, index + 1)
        child = dependencies[index]
        if child in on_path:
            problems.append(_cycle(entry for entry, _, _ in stack[on_path[child] :]))
            continue
        if child in resolved:
            continue
        loaded = _resolve(child, pinned_directories, discovered, resolved, problems)
        on_path[child] = len(stack)
        stack.append((child, _dependencies_of(loaded), 0))


def _dependencies_of(pack: LoadedPack | None) -> tuple[str, ...]:
    """One pack's dependencies, sorted and de-duplicated. A pack that did not load has none.

    Sorted so the emitted order is a function of the graph and not of how the list was typed;
    de-duplicated because ``depends: [php, php]`` is one edge, and the schema does not say
    otherwise — it sets no ``uniqueItems`` on the array.
    """
    if pack is None:
        return ()
    return tuple(sorted(set(pack.manifest.depends)))


def _resolve(
    name: str,
    pinned_directories: Mapping[str, tuple[_Directory, ...]],
    discovered: Mapping[str, tuple[_Directory, ...]],
    resolved: dict[str, LoadedPack | None],
    problems: list[Problem],
) -> LoadedPack | None:
    """One name to one loaded pack, or to ``None`` and one problem. Answered once and remembered.

    ``None`` is cached exactly as a success is, which is what makes "one problem per name" hold: a
    name that resolves to nothing is a settled answer, not an unanswered question to be retried by
    the next pack that depends on it.
    """
    if name in resolved:
        return resolved[name]
    directories = pinned_directories.get(name) or discovered.get(name) or ()
    if not directories:
        resolved[name] = None
        problems.append(_unmatched(name, discovered))
        return None
    if len(directories) > 1:
        resolved[name] = None
        problems.append(_duplicated(name, directories))
        return None
    loaded = _load(directories[0], problems)
    resolved[name] = loaded
    return loaded


def _load(entry: _Directory, problems: list[Problem]) -> LoadedPack | None:
    """One directory read into a ``LoadedPack``, or ``None`` and the read failure as a problem.

    This is the one place ``ManifestUnreadable`` is caught, and it is caught for the reason
    ``resolution.py`` catches ``SettingsUnreadable``: the exception is the right shape for one file
    and the wrong shape for a walk that has to finish and report everything it found.
    """
    try:
        manifest = load_manifest(entry.directory)
    except ManifestUnreadable as error:
        problems.append(error.problem())
        return None
    return LoadedPack(
        name=entry.name,
        directory=entry.directory,
        path=entry.path,
        manifest=manifest,
    )


def _unmatched(name: str, discovered: Mapping[str, tuple[_Directory, ...]]) -> Problem:
    """A ``depends`` entry no pack directory carries, with the names that were on the path.

    ``available`` is every pack name discovery found, sorted, rather than a guess at which one was
    meant. A near-miss list would need a distance rule, and a rule that decides ``twig`` was meant
    by ``twigg`` will one day decide it was meant by ``php``.
    """
    return Problem(
        code=ExitCode.DEPENDS_UNMATCHED,
        message=f"no pack directory on the search path is named {name!r}",
        detail={"pack": name, "available": ", ".join(sorted(discovered))},
    )


def _duplicated(name: str, directories: Sequence[_Directory]) -> Problem:
    """One pack name carried by two directories. Both are named and neither is chosen."""
    return Problem(
        code=ExitCode.DEPENDS_DUPLICATED,
        message=f"the pack name {name!r} is carried by more than one directory",
        detail={
            "pack": name,
            "directories": ", ".join(entry.path for entry in directories),
        },
    )


def _cycle(names: Iterable[str]) -> Problem:
    """A ``depends`` chain that reaches back into itself, named in the order it was entered.

    A one-name cycle is a pack that depends on itself. It needs no separate guard and gets no
    separate code: it is the shortest back edge there is, the detector finds it the same way, and
    the remedy is the same sentence.
    """
    cycle = tuple(names)
    written = " -> ".join((*cycle, cycle[0]))
    return Problem(
        code=ExitCode.DEPENDS_CYCLE,
        message=f"the pack dependencies form a cycle: {written}",
        detail={"cycle": written, "packs": ", ".join(sorted(cycle))},
    )
