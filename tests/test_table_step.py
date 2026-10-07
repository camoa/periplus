"""The table step of an edge end: a written name's last segment looked up in a table the pack,
or a pack it depends on, carries."""

from __future__ import annotations

import json
from pathlib import Path

from periplus.map import MapReport, run
from periplus.preflight import check_runtime_dependencies

MANIFEST = """\
pack: own
version: 0.0.1
depends: [{depends}]
grammar:
  provider: tree-sitter
  provider_version: "0.26.0"
  language: php
  grammar_version: "0.24.1"
folders:
  code: ./src
files:
  extensions: [php]
identity:
  qualified_name: {{parts: [namespace, declared_name], separator: "\\\\"}}
  namespace: {{declaration: namespace_definition, name_child: name}}
  written_names: [name, qualified_name, namespace_name]
{tables}"""

TABLES = """\
tables:
  services: {logger: logger.factory, state: state}
  kinds: {Store: store_kind}
"""

RULES = """\
node_types:
- {name: own.fn, id_namespace: own.fn}
- {name: own.svc, id_namespace: own.svc}
- {name: own.kind, id_namespace: own.kind}
edge_kinds:
- {kind: uses, from: own.fn, to: own.svc}
- {kind: loads, from: own.fn, to: own.kind}
rules:
- rule: fn
  reads: file
  in: [code]
  match: {declaration: function_definition, name_child: name, filetype: php}
  id: {from: declared_name}
  emits: [{node: {type: own.fn}}]
  confidence: declared
- rule: shortcut
  reads: file
  in: [code]
  match:
    reference: scoped_call_expression
    name_child: [scope, name]
    filetype: php
    where: [{name_matches: {child: scope, pattern: Svc}}]
  emits:
  - edge:
      kind: uses
      from: enclosing_declaration
      to: {resolve: [lookup_last_segment_in: services], types: [own.svc]}
  confidence: inferred
- rule: load
  reads: file
  in: [code]
  match:
    reference: scoped_call_expression
    name_child: scope
    filetype: php
    where: [{name_matches: {child: name, pattern: load}}]
  emits:
  - edge:
      kind: loads
      from: enclosing_declaration
      to: {resolve: [lookup_last_segment_in: kinds], types: [own.kind]}
  confidence: inferred
"""

SOURCE = """\
<?php

function page()
{
    Svc::logger('x');
    Svc::nope();
    Store::load(1);
    Other::load(2);
}
"""


def _run(root: Path, manifest: str, rules: str = RULES, base: str | None = None) -> MapReport:
    packs = root / ".periplus" / "packs"
    pins = ["own@0.0.1"]
    if base is not None:
        (packs / "base@0.0.1").mkdir(parents=True)
        (packs / "base@0.0.1" / "pack.yaml").write_text(base)
        pins.append("base@0.0.1")
    (packs / "own@0.0.1" / "rules").mkdir(parents=True)
    (packs / "own@0.0.1" / "pack.yaml").write_text(manifest)
    (packs / "own@0.0.1" / "rules" / "own.yaml").write_text(rules)
    (root / ".periplus" / "settings.yml").write_text(
        f"periplus_version: 0\npacks: [{', '.join(pins)}]\n"
    )
    (root / "src").mkdir()
    (root / "src" / "a.php").write_text(SOURCE)
    return run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )


def _edges(root: Path) -> set[tuple[str, str, str, str]]:
    document = json.loads((root / "map.json").read_text())
    return {
        (e["kind"], e["from"], e["to"], p["confidence"])
        for e in document["edges"]
        for p in e["provenance"]
    }


def test_the_lookup_step_holds_on_a_key_and_gives_its_value(tmp_path: Path) -> None:
    """Svc::logger gives logger, its last segment, and the scope Store gives Store; each table's
    value alone is the end."""
    report = _run(tmp_path, MANIFEST.format(depends="", tables=TABLES))
    assert report.problems == () and report.not_executed == (), report
    assert _edges(tmp_path) == {
        ("uses", "own.fn::page", "own.svc::logger.factory", "inferred"),
        ("loads", "own.fn::page", "own.kind::store_kind", "inferred"),
    }, _edges(tmp_path)


def test_a_name_not_in_the_table_makes_no_edge_and_a_skipped_row(tmp_path: Path) -> None:
    """Svc::nope's last segment and Other::load's scope are in no table."""
    report = _run(tmp_path, MANIFEST.format(depends="", tables=TABLES))
    rows = {(line, rule, reason) for _, line, rule, reason in report.skipped}
    assert rows == {
        (6, "shortcut", "no resolution step holds for scope"),
        (8, "load", "no resolution step holds for scope"),
    }, rows


def test_a_table_a_dependency_declares_is_looked_up(tmp_path: Path) -> None:
    base = "pack: base\nversion: 0.0.1\ndepends: []\n" + TABLES
    report = _run(tmp_path, MANIFEST.format(depends="base", tables=""), base=base)
    assert report.problems == () and report.not_executed == (), report
    assert ("uses", "own.fn::page", "own.svc::logger.factory", "inferred") in _edges(tmp_path)


def test_a_step_naming_a_table_no_pack_declares_is_refused(tmp_path: Path) -> None:
    rules = RULES.replace("lookup_last_segment_in: kinds", "lookup_last_segment_in: missing")
    report = _run(tmp_path, MANIFEST.format(depends="", tables=TABLES), rules=rules)
    assert [p.message for p in report.problems] == [
        "own/rules/own.yaml: the rule load cannot be executed: the resolution step "
        "lookup_last_segment_in names missing, which no tables key of the pack or a pack it "
        "depends on declares"
    ], report.problems
