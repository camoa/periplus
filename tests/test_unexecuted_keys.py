"""Every key path the two pack schemas accept is executed, or is reported when a pack writes it."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from periplus.engine.packload import EXECUTED_KEYS, UNEXECUTED_KEYS, unexecuted

SCHEMAS = Path(__file__).resolve().parent.parent / "src" / "periplus" / "contract" / "schema"

RULE = "file.rules.*."


def _paths(schema: dict[str, Any], node: object, path: str) -> set[str]:
    """Every key path under a ``properties`` keyword below ``path``; ``*`` is one key or item."""
    if isinstance(node, list):
        return set().union(*(_paths(schema, item, path) for item in node))
    if not isinstance(node, dict):
        return set()
    if "$ref" in node:
        return _paths(schema, schema["$defs"][node["$ref"].split("/")[-1]], path)
    found = set()
    for name, child in node.get("properties", {}).items():
        found |= {f"{path}.{name}"} | _paths(schema, child, f"{path}.{name}")
    found |= _paths(schema, node.get("oneOf", []) + node.get("anyOf", []), path)
    found |= _paths(schema, [node.get("items"), node.get("additionalProperties")], f"{path}.*")
    return found


def _schema_paths() -> set[str]:
    found: set[str] = set()
    for prefix, name in (("manifest", "pack-manifest"), ("file", "pack-file")):
        schema = json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))
        found |= _paths(schema, schema, prefix)
    return found


def _holding(segments: list[str]) -> object:
    """The smallest document that holds the key path: a list for each ``*``."""
    if not segments:
        return "x"
    inner = _holding(segments[1:])
    return [inner] if segments[0] == "*" else {segments[0]: inner}


def test_every_schema_path_is_executed_or_reported() -> None:
    """A path neither executed nor reported fails, and so does an executed path the schemas do not
    hold. ``$schema`` names the contract a file is written against and carries no data, so exactly
    that property is left out."""
    paths = _schema_paths()
    exempt = {path for path in paths if path.rsplit(".", 1)[-1] == "$schema"}
    assert exempt == {"manifest.$schema", "file.$schema"}
    assert not EXECUTED_KEYS & set(UNEXECUTED_KEYS)
    assert EXECUTED_KEYS | set(UNEXECUTED_KEYS) == paths - exempt


def test_each_reported_path_is_found_in_a_document_holding_it() -> None:
    """A document holding only the path reports it, or the reported path above it, by name; a
    rule's path under the rule prefix, any other under its document's, and never both."""
    for path in UNEXECUTED_KEYS:
        named = min((q for q in UNEXECUTED_KEYS if path == q or path.startswith(f"{q}.")), key=len)
        prefix = RULE if path.startswith(RULE) else f"{path.split('.')[0]}."
        document = _holding(path.removeprefix(prefix).split("."))
        assert unexecuted(document, prefix) == [named.removeprefix(prefix)], path
        if prefix == RULE:
            assert unexecuted({"rules": [document]}, "file.") == [], path


def test_the_span_relative_to_and_line_keys_are_executed() -> None:
    """Spans, the enclosing value and its join, a text rule's line and a path value's
    relative_to."""
    spans = {f"manifest.files.types.*.spans{k}" for k in ("", ".*.name", ".*.open", ".*.balance")}
    keys = spans | {
        "manifest.files.types.*.path_values.*.relative_to",
        "file.rules.*.values.*.from.enclosing",
        "file.rules.*.values.*.join",
        "file.rules.*.line",
        "file.rules.*.line.capture",
    }
    assert keys <= EXECUTED_KEYS & _schema_paths()


def test_the_call_argument_and_name_matches_keys_are_executed() -> None:
    """A reference end and a declaration id from a call's argument, the grammar's call field, and
    name_matches on a rule's match."""
    keys = {
        "manifest.identity.call_arguments",
        "file.rules.*.id.from.argument",
        "file.rules.*.emits.*.edge.to.from.argument",
        "file.rules.*.match.where.*.name_matches",
    }
    assert keys <= EXECUTED_KEYS & _schema_paths()
