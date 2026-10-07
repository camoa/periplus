"""Step one and a half: refuse what the loaded packs say about themselves and cannot honour.

The checks read the packs' own documents, not only the rules the engine supports, so a rule of a
shape the engine does not execute is still checked for what it declares. Nothing here opens a
source file.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from periplus.engine.emit import type_chain
from periplus.engine.packload import (
    _BOUNDARY_SHAPE,
    RuleSet,
    load_rules,
    node_types,
    twin_type,
    unexecuted,
)
from periplus.engine.select import FileTypes, extended, folder_values, reachable
from periplus.engine.source import DATA_READERS
from periplus.engine.tree import grammar_problems
from periplus.errors import ExitCode, HarnessError, Problem
from periplus.manifest import MANIFEST_FILENAME, LoadedPack
from periplus.validate import _check_directory, _load, _yaml_files

__all__ = ["check_packs", "checked", "reachable"]


def checked(
    packs: Sequence[LoadedPack],
    values: Mapping[str, str] | None = None,
    origins: Mapping[str, str] | None = None,
) -> tuple[RuleSet | None, list[Problem]]:
    """The packs' rules and every problem ``periplus map`` refuses them for before it reads a
    source file; ``None`` in place of the rules when a rule file cannot be read. ``values`` are the
    project's settings values, and ``origins`` the settings file of each.

    A pack that fails its schema does not hide the problems of the packs that do not depend on it.
    """
    schema, failed = _schema_problems(packs)
    sound = [pack for pack in packs if not reachable(pack, packs) & failed]
    try:
        rule_set = load_rules(sound, values, origins)
    except HarnessError as error:
        return None, [*schema, error.problem()]
    return rule_set, [*schema, *rule_set.conflicts, *check_packs(sound, rule_set)]


def _schema_problems(packs: Sequence[LoadedPack]) -> tuple[list[Problem], set[str]]:
    """Each loaded pack checked as ``periplus validate`` checks it, one problem per error.

    The second value names the packs that failed.
    """
    problems: list[Problem] = []
    failed: set[str] = set()
    for pack in packs:
        found: list[Problem] = []
        _, errors = _check_directory(pack.directory, found)
        problems.extend(found)
        problems.extend(
            Problem(
                ExitCode.SCHEMA_INVALID,
                f"{pack.name.pack}/{error.file} {error.pointer}: {error.message}"
                + (f"; write {_BOUNDARY_SHAPE}" if error.pointer.startswith("$.boundary") else ""),
                {"pack": pack.name.pack, "file": error.file, "pointer": error.pointer},
            )
            for error in errors
        )
        if found or errors:
            failed.add(pack.name.pack)
    return problems, failed


def check_packs(packs: Sequence[LoadedPack], rule_set: RuleSet) -> list[Problem]:
    """Every problem the loaded packs have, sorted by code and message; empty when none.

    A type or an edge kind must be declared by the pack that names it or by a pack it depends on,
    directly or not. An edge rule whose ``this_node`` end has a twin node rule must give that end a
    type its kind allows. Rule names are unique within a pack, every rule is one the engine can
    execute, no folder name has two values across the packs that neither pack's dependency settles,
    a ``files.extends`` beside ``add_extensions`` names one pack, no ending or whole file name is
    claimed for two file types read the same way, a type read as a tree belongs to a pack that
    pins a grammar, and every grammar pin is met.
    """
    documents = {pack.name.pack: _documents(pack) for pack in packs}
    reach = {pack.name.pack: reachable(pack, packs) for pack in packs}
    declared_types = {
        name: {t for _, document in documents[name] for t in _declared(document, "node_types")}
        | {t for _, document in documents[name] for t in _declared(document, "roles")}
        for name in documents
    }
    kinds = {
        name: {
            k for _, document in documents[name] for k in _declared(document, "edge_kinds", "kind")
        }
        for name in documents
    }
    rule_files = {
        (owner, str(rule.get("rule"))): file
        for owner, found in documents.items()
        for file, document in found
        for rule in _rules(document)
    }
    problems: list[Problem] = []
    for pack in packs:
        name = pack.name.pack
        visible = reach[name]
        types = set().union(*(declared_types[p] for p in visible))
        known_kinds = set().union(*(kinds[p] for p in visible))
        files_of: dict[str, list[str]] = {}
        for file, document in documents[name]:
            for rule in _rules(document):
                files_of.setdefault(str(rule.get("rule")), []).append(file)
            problems.extend(_undeclared(name, file, document, types, known_kinds))
            problems.extend(_unexecuted_keys(name, file, document, "file."))
            problems.extend(_illegal_ends(name, file, document, documents[name], rule_set))
        problems.extend(
            _unexecuted_keys(name, MANIFEST_FILENAME, pack.manifest.document, "manifest.")
        )
        abstract = {
            str(entry.get("name"))
            for _, document in documents[name]
            for entry in _entries(document, "node_types")
            if entry.get("abstract") is True
        }
        # Only a node is refused: an edge end may be typed by an abstract type, which any of its
        # descendants then meets.
        problems.extend(
            Problem(
                ExitCode.PACK_RULES_UNREADABLE,
                f"{rule.pack}/{rule_files.get((rule.pack, rule.name), rule.name)}: the rule "
                f"{rule.name} emits the abstract type {rule.node_type}, which {name} declares "
                "abstract",
                {"pack": rule.pack, "rule": rule.name, "type": rule.node_type, "declared_by": name},
            )
            for rule in rule_set.rules
            if rule.supported and rule.node_type in abstract
        )
        problems.extend(
            Problem(
                ExitCode.RULE_DUPLICATED,
                f"{name}: the rule {rule} is written {len(files)} times, in {', '.join(files)}",
                {"pack": name, "rule": rule},
            )
            for rule, files in files_of.items()
            if len(files) > 1
        )
        problems.extend(
            Problem(
                ExitCode.RULE_NOT_EXECUTABLE,
                f"{name}/{', '.join(files_of.get(rule.name, [rule.name]))}: the rule {rule.name} "
                f"cannot be executed: {rule.reason}",
                {"pack": name, "rule": rule.name},
            )
            for rule in rule_set.rules
            if rule.pack == name and not rule.supported
        )
    problems.extend(_folder_conflicts(packs))
    problems.extend(_extends_ambiguous(packs))
    problems.extend(_type_conflicts(packs))
    problems.extend(grammar_problems(packs))
    return sorted(problems, key=lambda problem: (int(problem.code), problem.message))


def _documents(pack: LoadedPack) -> list[tuple[str, Mapping[str, Any]]]:
    """Each rule file of the pack, as its relative path and its parsed mapping."""
    found: list[tuple[str, Mapping[str, Any]]] = []
    for relative, node in _yaml_files(pack.directory):
        document, _ = _load(node, [])
        if relative != MANIFEST_FILENAME and isinstance(document, Mapping):
            found.append((relative, document))
    return found


def _unexecuted_keys(
    pack: str, file: str, document: Mapping[str, Any], prefix: str
) -> list[Problem]:
    """Each key the document holds that the schemas accept and nothing executes."""
    return [
        Problem(
            ExitCode.RULE_NOT_EXECUTABLE,
            f"{pack}/{file}: the key {key} is accepted and not executed",
            {"pack": pack, "file": file, "key": key},
        )
        for key in unexecuted(document, prefix)
    ]


def _entries(document: Mapping[str, Any], section: str) -> list[Mapping[str, Any]]:
    entries = document.get(section)
    return [e for e in (entries if isinstance(entries, list) else []) if isinstance(e, Mapping)]


def _declared(document: Mapping[str, Any], section: str, key: str = "name") -> list[str]:
    entries = document.get(section)
    return [
        entry[key]
        for entry in (entries if isinstance(entries, list) else [])
        if isinstance(entry, Mapping) and isinstance(entry.get(key), str)
    ]


def _rules(document: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rules = document.get("rules")
    return [r for r in (rules if isinstance(rules, list) else []) if isinstance(r, Mapping)]


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    return [item for item in (value if isinstance(value, list) else []) if isinstance(item, str)]


def _emits(rule: Mapping[str, Any], key: str) -> list[Any]:
    emits = rule.get("emits")
    return [e[key] for e in (emits if isinstance(emits, list) else []) if _has(e, key)]


def _has(emit: object, key: str) -> bool:
    return isinstance(emit, Mapping) and key in emit


def _undeclared(
    pack: str,
    file: str,
    document: Mapping[str, Any],
    types: set[str],
    kinds: set[str],
) -> list[Problem]:
    """The types and edge kinds this file names that no reachable pack declares."""
    named: list[tuple[str, str]] = []
    needs = document.get("needs")
    for section in ("types", "roles"):
        listed = needs.get(section) if isinstance(needs, Mapping) else None
        named.extend((f"needs.{section}", t) for t in _strings(listed))
    for section in ("node_types", "edge_kinds"):
        entries = document.get(section)
        for entry in entries if isinstance(entries, list) else []:
            if isinstance(entry, Mapping):
                label = f"{section[:-1]} {entry.get('name', entry.get('kind'))}"
                ends = (
                    (entry.get("parent"),)
                    if section == "node_types"
                    else (
                        entry.get("from"),
                        entry.get("to"),
                    )
                )
                named.extend((label, t) for end in ends for t in _strings(end))
    problems = [
        Problem(
            ExitCode.UNDECLARED_TYPE,
            f"{pack}/{file}: {where} names the type {name}, which neither {pack} nor a pack it "
            "depends on declares",
            {"pack": pack, "file": file, "type": name},
        )
        for where, name in named
        if name not in types
    ]
    for rule in _rules(document):
        rule_name = rule.get("rule")
        used = node_types(rule)
        used += [t for key in ("type", "role") for t in _strings(_emits(rule, key))]
        used += [
            edge[side]["declared"]
            for edge in _emits(rule, "edge")
            for side in ("from", "to")
            if isinstance(edge, Mapping) and _has(edge.get(side), "declared")
        ]
        problems.extend(
            Problem(
                ExitCode.UNDECLARED_TYPE,
                f"{pack}/{file}: the rule {rule_name} emits the type {name}, which neither "
                f"{pack} nor a pack it depends on declares",
                {"pack": pack, "file": file, "rule": str(rule_name), "type": name},
            )
            for name in used
            if isinstance(name, str) and name not in types
        )
        problems.extend(
            Problem(
                ExitCode.UNDECLARED_EDGE_KIND,
                f"{pack}/{file}: the rule {rule_name} emits the edge kind {edge['kind']}, which "
                f"neither {pack} nor a pack it depends on declares",
                {"pack": pack, "file": file, "rule": str(rule_name), "kind": str(edge["kind"])},
            )
            for edge in _emits(rule, "edge")
            if isinstance(edge, Mapping) and edge.get("kind") not in kinds
        )
    return problems


def _illegal_ends(
    pack: str,
    file: str,
    document: Mapping[str, Any],
    siblings: Sequence[tuple[str, Mapping[str, Any]]],
    rule_set: RuleSet,
) -> list[Problem]:
    """The edge rules whose ``this_node`` end has a twin of a type the kind does not allow there,
    or whose to end, or ``declared`` end at either side, names a type the kind does not allow
    there."""
    problems: list[Problem] = []
    for rule in _rules(document):
        for edge in _emits(rule, "edge"):
            kind = rule_set.edge_kinds.get(str(edge.get("kind"))) if _has(edge, "kind") else None
            end = edge["to"] if isinstance(edge.get("to"), Mapping) else {}
            for named in [end["type"]] if end.get("type") else _strings(end.get("types")):
                if not kind or set(kind.to_types) & set(type_chain(rule_set.types, named)):
                    continue
                problems.append(
                    Problem(
                        ExitCode.EDGE_ILLEGAL,
                        f"{pack}/{file}: the rule {rule.get('rule')} names its to end a {named}, "
                        f"and the edge {kind.name} allows {', '.join(kind.to_types)} there",
                        {"pack": pack, "file": file, "rule": str(rule.get("rule"))},
                    )
                )
            for side, allowed in (("from", kind.from_types), ("to", kind.to_types)) if kind else ():
                end = edge[side] if isinstance(edge.get(side), Mapping) else {}
                named = end.get("declared")
                # A type no pack declares is refused as undeclared instead.
                if (
                    not isinstance(named, str)
                    or named not in rule_set.types
                    or set(allowed) & set(type_chain(rule_set.types, named))
                ):
                    continue
                problems.append(
                    Problem(
                        ExitCode.EDGE_ILLEGAL,
                        f"{pack}/{file}: the rule {rule.get('rule')} names its {side} end "
                        f"{{declared: {named}}}, and the edge {edge['kind']} allows "
                        f"{', '.join(allowed)} there",
                        {"pack": pack, "file": file, "rule": str(rule.get("rule"))},
                    )
                )
            twin = twin_type(rule, [other for _, d in siblings for other in _rules(d)])
            if kind is None or twin is None:
                continue
            allowed_by_end = (("from", kind.from_types), ("to", kind.to_types))
            for end, allowed in allowed_by_end:
                chain = set(type_chain(rule_set.types, twin))
                if edge.get(end) == "this_node" and not set(allowed) & chain:
                    problems.append(
                        Problem(
                            ExitCode.EDGE_ILLEGAL,
                            f"{pack}/{file}: the rule {rule.get('rule')} has an illegal end: "
                            f"the edge {kind.name} runs {end} this_node, a {twin}, and the kind "
                            f"allows {', '.join(allowed)} there",
                            {"pack": pack, "file": file, "rule": str(rule.get("rule"))},
                        )
                    )
    return problems


def _folder_conflicts(packs: Sequence[LoadedPack]) -> list[Problem]:
    """Each folder name two loaded packs give different values, settings or no settings, where
    neither pack depends on the other."""
    values, settled = folder_values(packs)
    return [
        Problem(
            ExitCode.FOLDER_UNRESOLVED,
            f"folder {name} has different values in the loaded packs: "
            + "; ".join(
                f"{', '.join(value)} in "
                + ", ".join(f"{p}/{MANIFEST_FILENAME}" for p in sorted(owners))
                for value, owners in sorted(seen.items())
            ),
            {"folder": name},
        )
        for name, seen in values.items()
        if settled[name] is None
    ]


def _extends_ambiguous(packs: Sequence[LoadedPack]) -> list[Problem]:
    """Each pack whose ``files.extends`` names several packs beside ``add_extensions``."""
    problems = []
    for pack in packs:
        files = pack.manifest.document.get("files")
        if isinstance(files, Mapping) and "add_extensions" in files and len(extended(files)) > 1:
            problems.append(
                Problem(
                    ExitCode.PACK_RULES_UNREADABLE,
                    f"{pack.name.pack}/{MANIFEST_FILENAME}: files.extends names "
                    f"{', '.join(sorted(extended(files)))} beside add_extensions, which does not "
                    "say which pack's extension list grows",
                    {"pack": pack.name.pack},
                )
            )
    return problems


def _type_conflicts(packs: Sequence[LoadedPack]) -> list[Problem]:
    """Each ending or whole file name claimed for file types of different names read the same way,
    whichever form each pack writes, each data type whose format no reader reads, and each type
    read as a tree whose pack pins no grammar. Two types of different readers may share an ending,
    as a tree type and a text type do. A short-form ``files.extensions`` list claims each of its
    endings for the type named by that ending, so two short lists sharing an ending agree."""
    pinned = {p.name.pack for p in packs if isinstance(p.manifest.document.get("grammar"), Mapping)}
    claims: dict[tuple[str, str], dict[frozenset[str], set[str]]] = {}
    problems = []
    for kind in FileTypes.build(packs, {}).types:
        for ending in kind.endings:
            # An ending another pack's add_extensions gave a short-form type keeps its names.
            named = {n for n in kind.names if n.removeprefix(".") == ending}
            names = kind.names if kind.declared or not named else frozenset({ending})
            claim = (f"ending {ending}", kind.reader)
            claims.setdefault(claim, {}).setdefault(names, set()).add(kind.pack)
        for whole in kind.whole:
            claim = (f"name {whole}", kind.reader)
            claims.setdefault(claim, {}).setdefault(kind.names, set()).add(kind.pack)
        if kind.reader == "data" and kind.format not in DATA_READERS:
            problems.append(
                Problem(
                    ExitCode.PACK_RULES_UNREADABLE,
                    f"{kind.pack}/{MANIFEST_FILENAME}: the file type "
                    f"{', '.join(sorted(kind.names))} is read as data in the format "
                    f"{kind.format}, which no reader of the engine reads",
                    {
                        "pack": kind.pack,
                        "type": ", ".join(sorted(kind.names)),
                        "format": kind.format,
                    },
                )
            )
        if kind.reader == "tree" and kind.pack not in pinned:
            problems.append(
                Problem(
                    ExitCode.PACK_RULES_UNREADABLE,
                    f"{kind.pack}/{MANIFEST_FILENAME}: the file type "
                    f"{', '.join(sorted(kind.names))} is read as a tree, and the pack pins no "
                    "grammar",
                    {"pack": kind.pack},
                )
            )
    problems.extend(
        Problem(
            ExitCode.PACK_RULES_UNREADABLE,
            f"the file {claim} is claimed for different file types read as {reader}: "
            + "; ".join(
                f"{', '.join(sorted(names))} in "
                + ", ".join(f"{p}/{MANIFEST_FILENAME}" for p in sorted(owners))
                for names, owners in sorted(seen.items(), key=lambda item: sorted(item[0]))
            ),
            {"claim": claim, "reader": reader},
        )
        for (claim, reader), seen in sorted(claims.items())
        if len(seen) > 1
    )
    return problems
