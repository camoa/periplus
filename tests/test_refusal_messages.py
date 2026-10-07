"""The refusals of the three new shapes each name the shape that works: a table step naming an
unknown table names the `tables` key, a grammar block with one constant key names the other, and
an ending no pack claims lists the claimed endings. And of two tables with one name, the nearer
pack's wins whole."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from periplus.map import MapReport, run
from periplus.preflight import check_runtime_dependencies

# A rutter that owns the PHP grammar. {grammar} adds lines to its grammar block, {tables} its
# tables key.
MANIFEST = """\
pack: own
version: 0.0.1
depends: {depends}
grammar:
  provider: tree-sitter
  provider_version: "0.26.0"
  language: php
  grammar_version: "0.24.1"
{grammar}folders:
  code: ./src
files:
  extensions: [php]
identity:
  qualified_name: {{parts: [namespace, declared_name], separator: "\\\\"}}
  namespace: {{declaration: namespace_definition, name_child: name}}
  written_names: [name, qualified_name, namespace_name]
{tables}"""

# Drupal::logger() and Drupal::mail() looked up by their method's name in the table {table}.
RULES = """\
node_types:
- {{name: own.fn, id_namespace: own.fn}}
- {{name: own.svc, id_namespace: own.svc}}
edge_kinds:
- {{kind: uses, from: own.fn, to: own.svc}}
rules:
- rule: fn
  reads: file
  in: [code]
  match: {{declaration: function_definition, name_child: name, filetype: php{ending}}}
  id: {{from: declared_name}}
  emits: [{{node: {{type: own.fn}}}}]
  confidence: declared
- rule: shortcut
  reads: file
  in: [code]
  match: {{reference: scoped_call_expression, name_child: [scope, name], filetype: php}}
  emits:
  - edge:
      kind: uses
      from: enclosing_declaration
      to: {{resolve: [lookup_last_segment_in: {table}], types: [own.svc]}}
  confidence: inferred
"""

SOURCE = """\
<?php
namespace App;

function page()
{
    Drupal::logger('x');
    Drupal::mail();
}
"""

TABLES = "tables:\n  names: {logger: logger.factory}\n"


def _run(
    root: Path,
    *,
    grammar: str = "",
    tables: str = TABLES,
    ending: str = "",
    table: str = "names",
    depends: str = "[]",
    packs: str = "[own@0.0.1]",
) -> MapReport:
    pack = root / ".periplus" / "packs" / "own@0.0.1"
    (pack / "rules").mkdir(parents=True)
    (root / ".periplus" / "settings.yml").write_text(f"periplus_version: 0\npacks: {packs}\n")
    manifest = MANIFEST.format(depends=depends, grammar=grammar, tables=tables)
    (pack / "pack.yaml").write_text(manifest)
    (pack / "rules" / "own.yaml").write_text(RULES.format(ending=ending, table=table))
    (root / "src").mkdir()
    (root / "src" / "a.php").write_text(SOURCE)
    return run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )


def test_a_step_naming_an_unknown_table_names_the_tables_key(tmp_path: Path) -> None:
    """The rule is not run, the map stops with exit 26, and the problem says a table is declared
    under a `tables` key of the pack or a pack it depends on."""
    report = _run(tmp_path, table="missing")
    assert [p.message for p in report.problems] == [
        "own/rules/own.yaml: the rule shortcut cannot be executed: the resolution step"
        " lookup_last_segment_in names missing, which no tables key of the pack or a pack it"
        " depends on declares"
    ], report.problems
    assert report.exit_code == 26, report


@pytest.mark.parametrize(
    ("present", "absent"),
    [("constant_access", "constant_declaration"), ("constant_declaration", "constant_access")],
)
def test_one_constant_key_without_the_other_names_the_missing_one(
    tmp_path: Path, present: str, absent: str
) -> None:
    """Either grammar key alone is refused by the manifest schema, naming the key it needs."""
    block = {
        "constant_access": "  constant_access: {node: class_constant_access_expression,"
        " scope: [name], name: [name]}\n",
        "constant_declaration": "  constant_declaration: {node: const_element, name: [name],"
        " value: [string]}\n",
    }[present]
    report = _run(tmp_path, grammar=block)
    assert [p.message for p in report.problems] == [
        f"own/pack.yaml $.grammar: '{absent}' is a dependency of '{present}'"
    ], report.problems
    assert not (tmp_path / "map.json").exists()


def test_an_ending_no_pack_claims_lists_the_claimed_endings(tmp_path: Path) -> None:
    """match.ending: inc where only php is claimed: the rule is not run, and the problem lists
    php as the ending to write."""
    report = _run(tmp_path, ending=", ending: inc")
    assert [p.message for p in report.problems] == [
        "own/rules/own.yaml: the rule fn cannot be executed: match.ending names inc, which no pack"
        " claims; the claimed endings are php"
    ], report.problems
    assert report.exit_code == 26, report


@pytest.mark.parametrize(("own_table", "to"), [(True, "own.svc::near"), (False, "own.svc::far")])
def test_the_nearer_packs_table_wins_whole(tmp_path: Path, own_table: bool, to: str) -> None:
    """The dependency lib declares names with logger and mail. With its own names, own reads only
    its own table, so mail resolves nowhere; without one, own reads lib's."""
    lib = tmp_path / ".periplus" / "packs" / "lib@0.0.1"
    lib.mkdir(parents=True)
    (lib / "pack.yaml").write_text(
        "pack: lib\nversion: 0.0.1\ndepends: []\ntables:\n  names: {logger: far, mail: mail.far}\n"
    )
    report = _run(
        tmp_path,
        tables="tables:\n  names: {logger: near}\n" if own_table else "",
        depends="[lib]",
        packs="[lib@0.0.1, own@0.0.1]",
    )
    assert report.problems == () and report.not_executed == (), report
    document = json.loads((tmp_path / "map.json").read_text())
    edges = {(e["from"], e["to"]) for e in document["edges"]}
    expected = {("own.fn::page", to)}
    if not own_table:
        expected.add(("own.fn::page", "own.svc::mail.far"))
    assert edges == expected, edges
