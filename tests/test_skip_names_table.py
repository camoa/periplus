"""A reference rule's ``skip_names`` may name a table, whose keys it skips beside the names it
lists, with the rows a loaded dependent pack adds to that table through ``add_table_rows``."""

from __future__ import annotations

import json
from pathlib import Path

from test_demo_a_support import plant

from periplus.map import MapReport, run
from periplus.preflight import check_runtime_dependencies

OWNER = """\
pack: own
version: 0.0.1
depends: []
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
  qualified_name: {parts: [namespace, declared_name], separator: "\\\\"}
  namespace: {declaration: namespace_definition, name_child: name}
  written_names: [name, qualified_name, namespace_name]
tables:
  builtins: {alpha: alpha, beta: beta}
"""

RULES = """\
node_types:
- {{name: own.fn, id_namespace: own.fn}}
edge_kinds:
- {{kind: calls, from: own.fn, to: own.fn}}
rules:
- rule: fn
  reads: file
  in: [code]
  match: {{declaration: function_definition, name_child: name, filetype: php}}
  id: {{from: declared_name}}
  emits: [{{node: {{type: own.fn}}}}]
  confidence: declared
- rule: call
  reads: file
  in: [code]
  match:
    reference: function_call_expression
    name_child: function
    filetype: php
    skip_names: {skip}
  emits:
  - edge: {{kind: calls, from: enclosing_declaration, to: {{types: [own.fn], on_miss: unresolved}}}}
  confidence: declared
"""

SOURCE = """\
<?php

function page()
{
    alpha();
    beta();
    gamma();
    delta();
}
"""

#: Adds delta to own's table builtins.
EXTENDER = """\
pack: ext
version: 0.0.1
depends: [own]
add_table_rows:
  own:
    builtins: {delta: delta}
"""


def _project(root: Path, skip: str, extender: str | None = None) -> None:
    packs = ".periplus/packs"
    files = {
        f"{packs}/own@0.0.1/pack.yaml": OWNER,
        f"{packs}/own@0.0.1/rules/own.yaml": RULES.format(skip=skip),
        "src/a.php": SOURCE,
    }
    pins = ["own@0.0.1"]
    if extender is not None:
        files[f"{packs}/ext@0.0.1/pack.yaml"] = extender
        pins.append("ext@0.0.1")
    files[".periplus/settings.yml"] = f"periplus_version: 0\npacks: [{', '.join(pins)}]\n"
    plant(root, files)


def _run(root: Path) -> MapReport:
    return run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )


def _called(root: Path) -> set[str]:
    """The names the calls edges reach; a skipped name makes no edge and no row."""
    report = _run(root)
    assert report.problems == () and report.not_executed == (), report
    assert report.skipped == (), report.skipped
    document = json.loads((root / "map.json").read_text())
    return {e["to"].removeprefix("own.fn::") for e in document["edges"] if e["kind"] == "calls"}


def test_a_list_of_names_still_skips_those_names(tmp_path: Path) -> None:
    _project(tmp_path, "[alpha]")
    assert _called(tmp_path) == {"beta", "gamma", "delta"}


def test_the_keys_of_a_named_table_are_skipped(tmp_path: Path) -> None:
    _project(tmp_path, "[{table: builtins}]")
    assert _called(tmp_path) == {"gamma", "delta"}


def test_names_and_a_table_skip_together(tmp_path: Path) -> None:
    _project(tmp_path, "[gamma, {table: builtins}]")
    assert _called(tmp_path) == {"delta"}


def test_a_row_a_dependent_adds_is_skipped_only_when_that_pack_is_loaded(tmp_path: Path) -> None:
    loaded, alone = tmp_path / "loaded", tmp_path / "alone"
    _project(loaded, "[{table: builtins}]", EXTENDER)
    _project(alone, "[{table: builtins}]")
    assert _called(loaded) == {"gamma"}
    assert _called(alone) == {"gamma", "delta"}


def test_a_table_no_visible_pack_declares_is_refused(tmp_path: Path) -> None:
    """missing is declared nowhere; extras only by ext, which depends on own, so own's rule does
    not see it."""
    extender = "pack: ext\nversion: 0.0.1\ndepends: [own]\ntables:\n  extras: {gamma: gamma}\n"
    for table in ("missing", "extras"):
        root = tmp_path / table
        _project(root, f"[alpha, {{table: {table}}}]", extender)
        assert [p.message for p in _run(root).problems] == [
            f"own/rules/own.yaml: the rule call cannot be executed: skip_names names the table "
            f"{table}, which no tables key of the pack or a pack it depends on declares"
        ]
