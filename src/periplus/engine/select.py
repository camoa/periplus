"""Step two: turn folder names into directories, and directories into sorted file paths."""

from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from periplus.engine.source import SHORT_FORM_FORMAT, SourceUnreadable
from periplus.errors import ExitCode, HarnessError
from periplus.manifest import LoadedPack

__all__ = [
    "FileType",
    "FileTypes",
    "FolderUnresolved",
    "Selection",
    "extended",
    "files_in",
    "folder_values",
    "holds_double_star",
    "reachable",
    "resolve_folders",
    "select_files",
]

_REFERENCE = re.compile(r"\{([^{}]*)\}")


class FolderUnresolved(HarnessError):
    """A folder name is unknown, cyclic, in conflict between packs, or leaves the project root."""

    code = ExitCode.FOLDER_UNRESOLVED


def resolve_folders(
    names: Sequence[str],
    packs: Sequence[LoadedPack],
    overrides: Mapping[str, str | Sequence[str]],
    root: Path,
    selection: Selection | None = None,
) -> dict[str, tuple[str, ...]]:
    """Each folder name as the sorted repository-relative directories it stands for.

    The value comes from the settings overrides first, then from the pack manifests, where
    ``folder_values`` settles which pack's value is used. A value is one string or a list of them,
    and the folder stands for the union of their directories. A braced name inside a value is
    another folder, each of its values in turn, a star that is a whole path segment expands to the
    sorted directories present at that level, and a ``**`` segment to the directory and every
    directory below it, links followed. A directory that does not exist is left out. A directory
    reached through a link is named under the link's path. Only the names asked for, and those
    they reference, are resolved. A ``**`` walk does not enter a folder ``selection`` skips.
    """
    _, settled = folder_values(packs)
    return {
        name: tuple(
            sorted(
                {
                    directory
                    for pattern in _patterns(name, settled, overrides, ())
                    for directory in _expand(pattern, root, selection)
                }
            )
        )
        for name in names
    }


def holds_double_star(
    name: str, packs: Sequence[LoadedPack], overrides: Mapping[str, str | Sequence[str]]
) -> bool:
    """Whether the folder's value, with each folder it names, holds a ``**`` segment. Raises
    ``FolderUnresolved`` as ``resolve_folders`` does."""
    _, settled = folder_values(packs)
    return any("**" in pattern.split("/") for pattern in _patterns(name, settled, overrides, ()))


def reachable(pack: LoadedPack, packs: Sequence[LoadedPack]) -> set[str]:
    """The pack's own name and the names of every pack it depends on, directly or not."""
    manifests = {p.name.pack: p.manifest.document for p in packs}
    seen: set[str] = set()
    pending = [pack.name.pack]
    while pending:
        name = pending.pop()
        if name not in seen:
            seen.add(name)
            depends = manifests.get(name, {}).get("depends")
            pending.extend(depends if isinstance(depends, list) else [])
    return seen


def folder_values(
    packs: Sequence[LoadedPack],
) -> tuple[dict[str, dict[tuple[str, ...], set[str]]], dict[str, tuple[str, ...] | None]]:
    """Each folder name's values with the packs that give them, and the values that are used.

    A pack's values for one folder are kept sorted, so two packs giving one set agree.

    A pack that depends, directly or not, on every other pack giving the folder a value wins. The
    value used is ``None`` when no pack does: two packs, neither depending on the other, conflict.
    """
    reach = {pack.name.pack: reachable(pack, packs) for pack in packs}
    values: dict[str, dict[tuple[str, ...], set[str]]] = {}
    for pack in packs:
        folders = pack.manifest.document.get("folders")
        for name, value in folders.items() if isinstance(folders, dict) else []:
            given = tuple(sorted({value} if isinstance(value, str) else set(value)))
            values.setdefault(name, {}).setdefault(given, set()).add(pack.name.pack)
    settled: dict[str, tuple[str, ...] | None] = {}
    for name, seen in values.items():
        givers = {pack for owners in seen.values() for pack in owners}
        winners = {
            value
            for value, owners in seen.items()
            if any(givers <= reach[owner] for owner in owners)
        }
        settled[name] = winners.pop() if len(winners) == 1 else None
    return values, settled


def _patterns(
    name: str,
    declared: Mapping[str, tuple[str, ...] | None],
    overrides: Mapping[str, str | Sequence[str]],
    stack: tuple[str, ...],
) -> list[str]:
    if name in stack:
        raise FolderUnresolved(
            f"folder {name} refers back to itself", {"folder": name, "chain": " -> ".join(stack)}
        )
    if name in overrides:
        value = overrides[name]
    elif (settled := declared.get(name)) is not None:
        value = settled
    else:
        raise FolderUnresolved(f"folder {name} is not declared", {"folder": name})
    patterns = []
    for item in [value] if isinstance(value, str) else value:
        # Split leaves text at even places and a referenced name at odd ones.
        combined = [""]
        for place, part in enumerate(_REFERENCE.split(item)):
            options = _patterns(part, declared, overrides, (*stack, name)) if place % 2 else [part]
            combined = [done + option for done in combined for option in options]
        patterns.extend(combined)
    return patterns


def _expand(pattern: str, root: Path, selection: Selection | None) -> tuple[str, ...]:
    normal = posixpath.normpath(pattern)
    if normal.startswith("/") or ".." in normal.split("/"):
        raise FolderUnresolved(
            f"folder value {pattern} leaves the project root", {"value": pattern}
        )
    found = [""]
    for segment in normal.split("/"):
        if segment == "**":
            found = [below for base in found for below in _below(root, base, selection)]
        elif segment == "*":
            found = [
                posixpath.join(base, child.name)
                for base in found
                for child in sorted(_listing(root, base) if (root / base).is_dir() else [])
                if child.is_dir()
            ]
        else:
            found = [posixpath.join(base, segment) for base in found]
    return tuple(sorted({path for path in found if (root / path).is_dir()}))


def _below(root: Path, base: str, selection: Selection | None) -> list[str]:
    """The directory and every directory below it, links followed.

    A link whose real folder is the real folder of the directory holding it, or of one of that
    directory's parents up to the filesystem root, is a loop and is not entered. Nor is a folder
    the selection skips. A folder that cannot be listed raises ``SourceUnreadable``.
    """
    found: list[str] = []
    above = {*(root / base).resolve().parents}
    above.update((root / up).resolve() for up in PurePosixPath(base).parents)
    pending: list[tuple[str, frozenset[Path]]] = [(base, frozenset(above))]
    while pending:
        path, parents = pending.pop()
        folder = root / path
        if folder.resolve() in parents or (selection is not None and selection.skips(path)):
            continue
        found.append(path)
        if folder.is_dir():
            inside = parents | {folder.resolve()}
            pending.extend(
                (posixpath.join(path, child.name), inside)
                for child in _listing(root, path)
                if child.is_dir()
            )
    return found


def _listing(root: Path, path: str) -> list[Path]:
    """What the folder holds; a folder that cannot be listed raises ``SourceUnreadable``."""
    try:
        return list((root / path).iterdir())
    except OSError as error:
        message = f"folder {path} cannot be read: {error.strerror or error}"
        raise SourceUnreadable(message, {"folder": path}) from error


@dataclass(frozen=True, slots=True)
class FileType:
    """One file type: its names, the endings and whole file names that claim it, its reader, one of
    ``data``, ``text`` or ``tree``, the pack that declares it, ``""`` for the settings, and whether
    it is declared under ``files.types`` rather than by the short form or the settings, and the
    data format it is read in."""

    names: frozenset[str]
    endings: frozenset[str]
    whole: frozenset[str]
    reader: str
    pack: str
    declared: bool = False
    format: str = SHORT_FORM_FORMAT


@dataclass(frozen=True, slots=True)
class FileTypes:
    """Every file type the loaded packs and the settings declare."""

    types: tuple[FileType, ...]

    @classmethod
    def build(cls, packs: Sequence[LoadedPack], added: Mapping[str, str]) -> FileTypes:
        """The packs' ``files.types``, and the short form ``files.extensions``: one type named by
        each listed ending and claimed by them all, read as a tree when the pack pins a grammar and
        as data otherwise.

        A pack whose ``files.extends`` names a pack adds its ``files.add_extensions`` to each type
        that pack declares. ``added`` is the settings key ``extensions``, ending to type name; the
        ending moves to that type, a type of that name read as data when no pack declares one.
        """
        found: list[tuple[set[str], set[str], set[str], str, str, bool, str]] = []
        for pack in packs:
            document = pack.manifest.document
            files = document.get("files")
            files = files if isinstance(files, Mapping) else {}
            listed = files.get("extensions")
            if isinstance(listed, list) and listed:
                reader = "tree" if isinstance(document.get("grammar"), Mapping) else "data"
                bare = {*map(_bare, listed)}
                found.append(({*listed}, bare, set(), reader, pack.name.pack, False, ""))
            declared = files.get("types")
            for name, spec in declared.items() if isinstance(declared, Mapping) else ():
                endings = {_bare(ending) for ending in spec.get("endings", [])}
                whole = set(spec.get("names", []))
                reader, form = str(spec["reader"]), str(spec.get("format", ""))
                found.append(({name}, endings, whole, reader, pack.name.pack, True, form))
        for pack in packs:
            files = pack.manifest.document.get("files")
            if isinstance(files, Mapping):
                adds = {_bare(ending) for ending in files.get("add_extensions", [])}
                for _, endings, _, _, owner, _, _ in found:
                    if owner in extended(files):
                        endings.update(adds)
        for ending, name in added.items():
            for _, endings, _, _, _, _, _ in found:
                endings.discard(_bare(ending))
            target = [entry for entry in found if name in entry[0]]
            if not target:
                target = [({name}, set(), set(), "data", "", False, "")]
                found.extend(target)
            for _, endings, _, _, _, _, _ in target:
                endings.add(_bare(ending))
        return cls(
            tuple(
                FileType(frozenset(n), frozenset(e), frozenset(w), r, p, d, f or SHORT_FORM_FORMAT)
                for n, e, w, r, p, d, f in found
            )
        )

    def named(self, name: str) -> tuple[FileType, ...]:
        """The types the name names."""
        return tuple(kind for kind in self.types if name in kind.names)

    def names_of(self, file_name: str) -> frozenset[str]:
        """The names of the types that claim a file name; empty when none does."""
        claimed = self.claim(file_name)
        return claimed[0] if claimed is not None else frozenset()

    def claim(self, file_name: str) -> tuple[frozenset[str], str] | None:
        """The names of the types that claim a file name, and its stem; ``None`` when none does.

        A whole file name claims first, and its stem is the whole name. Otherwise the longest
        ending, after a dot and with something before it, claims, and the stem is the name with
        that dot and ending removed.
        """
        whole = [kind.names for kind in self.types if file_name in kind.whole]
        if whole:
            return frozenset().union(*whole), file_name
        best = max(
            (
                ending
                for kind in self.types
                for ending in kind.endings
                if len(file_name) > len(ending) + 1 and file_name.endswith(f".{ending}")
            ),
            key=len,
            default=None,
        )
        if best is None:
            return None
        claimants = [kind.names for kind in self.types if best in kind.endings]
        return frozenset().union(*claimants), file_name[: -len(best) - 1]


def _bare(ending: str) -> str:
    return ending.removeprefix(".")


def extended(files: Mapping[str, object]) -> set[str]:
    """The packs a ``files`` block's ``extends`` names: one string, or a list of them."""
    extends = files.get("extends")
    return (
        {extends}
        if isinstance(extends, str)
        else set(extends)
        if isinstance(extends, list)
        else set()
    )


def _glob(pattern: str) -> re.Pattern[str]:
    """A path pattern as a regular expression: ``*`` stays in one segment, ``**`` crosses them."""
    out: list[str] = []
    rest = pattern.removeprefix("./")
    while rest:
        for token, expression in (
            ("**/", "(?:.*/)?"),
            ("**", ".*"),
            ("*", "[^/]*"),
            ("?", "[^/]"),
        ):
            if rest.startswith(token):
                out.append(expression)
                rest = rest[len(token) :]
                break
        else:
            out.append(re.escape(rest[0]))
            rest = rest[1:]
    return re.compile("".join(out))


@dataclass(frozen=True, slots=True)
class Selection:
    """Which candidate files are read: the settings' patterns and the packs' excludes.

    ``extensions`` is the settings key of that name, a mapping of extension to file type. Every
    other field holds compiled patterns, each matched against a whole path relative to the project
    root.
    """

    extensions: Mapping[str, str]
    include: tuple[re.Pattern[str], ...]
    first_party_exclude: tuple[re.Pattern[str], ...]
    exclude: tuple[re.Pattern[str], ...]
    re_include: tuple[re.Pattern[str], ...]

    @classmethod
    def build(
        cls,
        packs: Sequence[LoadedPack],
        extensions: Mapping[str, str],
        include: Sequence[str],
        first_party_exclude: Sequence[str],
        exclude: Sequence[str],
        re_include: Sequence[str],
    ) -> Selection:
        """The settings' lists plus the packs' ``files.exclude`` and ``files.add_excludes``."""
        excluded = list(exclude)
        for pack in packs:
            files = pack.manifest.document.get("files")
            for key in ("exclude", "add_excludes"):
                listed = files.get(key) if isinstance(files, dict) else None
                excluded.extend(listed if isinstance(listed, list) else [])
        return cls(
            extensions,
            *(
                tuple(_glob(p) for p in patterns)
                for patterns in (include, first_party_exclude, excluded, re_include)
            ),
        )

    def skips(self, folder: str) -> bool:
        """Whether every file below the folder is excluded: no ``re_include`` is set and one
        exclude pattern matches the folder followed by any name, at one level and at two."""
        probes = (f"{folder}/\0", f"{folder}/\0/\0")
        return not self.re_include and any(
            all(pattern.fullmatch(probe) for probe in probes) for pattern in self.exclude
        )

    def reads(self, path: str) -> bool:
        """Whether the file is read."""
        return (
            (not self.include or _any(self.include, path))
            and not _any(self.first_party_exclude, path)
            and (not _any(self.exclude, path) or _any(self.re_include, path))
        )


def _any(patterns: Sequence[re.Pattern[str]], path: str) -> bool:
    return any(pattern.fullmatch(path) for pattern in patterns)


def files_in(
    root: Path, directories: Sequence[str], selection: Selection
) -> tuple[list[str], list[str]]:
    """Every file at any depth below the directories that the selection reads, of any type, sorted,
    and the folders that could not be listed, sorted.

    A folder is listed once; a linked folder, or one whose every file is excluded, is not entered.
    This walk only reports, so a folder it cannot list, or whose children it cannot examine, is
    recorded rather than raised, and none of its children are taken; selection
    for rules lists through ``_listing`` alone and still raises.
    """
    found: set[str] = set()
    unlisted: set[str] = set()
    pending = [directory for directory in directories if (root / directory).is_dir()]
    walked: set[str] = set()
    while pending:
        directory = pending.pop()
        if directory in walked:
            continue
        walked.add(directory)
        try:
            children = [
                (
                    posixpath.join(directory, child.name),
                    child.is_file(),
                    child.is_dir(),
                    child.is_symlink(),
                )
                for child in _listing(root, directory)
            ]
        except (SourceUnreadable, OSError):
            unlisted.add(directory)
            continue
        for path, is_file, is_dir, is_link in children:
            if is_file:
                found.add(path)
            elif is_dir and not is_link and not selection.skips(path):
                pending.append(path)
    return sorted(path for path in found if selection.reads(path)), sorted(unlisted)


def select_files(
    root: Path,
    directories: Sequence[str],
    filetype: str,
    types: FileTypes,
    selection: Selection,
) -> tuple[list[str], list[str]]:
    """The candidates inside the directories, sorted: those read, then those the patterns removed.

    A candidate is a file directly inside a directory that a type of the name ``filetype`` claims.
    """
    candidates: set[str] = set()
    for directory in directories:
        folder = root / directory
        if not folder.is_dir():
            continue
        candidates.update(
            posixpath.join(directory, child.name)
            for child in _listing(root, directory)
            if child.is_file() and filetype in types.names_of(child.name)
        )
    read = sorted(path for path in candidates if selection.reads(path))
    return read, sorted(candidates.difference(read))
