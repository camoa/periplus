"""Tests for ``enclosing_method`` on a tree declaration rule: as an id source, the declared name of
the method around the match, and as an edge end, that method's node id."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from periplus.map import MapReport, run
from periplus.preflight import check_runtime_dependencies

PACK = """\
pack: probe
version: 0.0.1
depends: []
grammar:
  provider: tree-sitter
  provider_version: "0.26.0"
  language: php
  grammar_version: "0.24.1"
folders:
  source: ./**
files:
  extensions: [php]
identity:
  qualified_name: {parts: [namespace, declared_name], separator: "\\\\"}
  namespace: {declaration: namespace_definition, name_child: name}
  written_names: [name, qualified_name, namespace_name]
"""

RULES = """\
node_types:
- {name: probe.class, id_namespace: probe.class}
- {name: probe.method, id_namespace: probe.method}
- {name: probe.variable, id_namespace: probe.variable}
edge_kinds:
- {kind: probe_holds, from: probe.method, to: probe.variable}
- {kind: probe_held_by, from: probe.variable, to: probe.method}
rules:
- rule: find_class
  reads: file
  in: [source]
  match: {declaration: class_declaration, name_child: name, body_child: declaration_list,
    filetype: php}
  id: {from: qualified_name}
  emits: [{node: {type: probe.class}}]
  confidence: declared
- rule: find_method
  reads: file
  in: [source]
  match: {declaration: method_declaration, name_child: name, filetype: php}
  id: {from: [enclosing_type, declared_name], template: '{enclosing_type}::{declared_name}'}
  emits: [{node: {type: probe.method}}]
  confidence: declared
- rule: variable
  reads: file
  in: [source]
  match: {declaration: simple_parameter, name_child: name, filetype: php}
  id: {from: declared_name}
  emits: [{node: {type: probe.variable}}]
  confidence: declared
- rule: tie
  reads: file
  in: [source]
  match: {declaration: simple_parameter, name_child: name, filetype: php}
  id: {from: declared_name}
  emits: [{edge: {kind: KIND, from: FROM, to: TO}}]
  confidence: declared
"""

SOURCE = """\
<?php

namespace App;

class Thing
{
    public function run($box)
    {
    }
}

function loose($free)
{
}
"""


def _map(root: Path, rules: str) -> tuple[MapReport, Any]:
    pack = root / ".periplus" / "packs" / "probe@0.0.1"
    (pack / "rules").mkdir(parents=True)
    (root / ".periplus" / "settings.yml").write_text("periplus_version: 0\npacks: [probe@0.0.1]\n")
    (pack / "pack.yaml").write_text(PACK)
    (pack / "rules" / "probe.yaml").write_text(rules)
    (root / "Thing.php").write_text(SOURCE)
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    written = root / "map.json"
    return report, json.loads(written.read_text()) if written.exists() else None


@pytest.mark.parametrize(
    ("kind", "start", "finish", "edge"),
    [
        (
            "probe_holds",
            "enclosing_method",
            "this_node",
            ("probe.method::App\\Thing::run", "probe.variable::$box"),
        ),
        (
            "probe_held_by",
            "this_node",
            "enclosing_method",
            ("probe.variable::$box", "probe.method::App\\Thing::run"),
        ),
    ],
)
def test_an_edge_runs_to_or_from_the_enclosing_method(
    tmp_path: Path, kind: str, start: str, finish: str, edge: tuple[str, str]
) -> None:
    """$box sits in run, so the edge joins the two; $free sits in a function outside any class,
    so it has no enclosing method and makes no edge, with no row."""
    rules = RULES.replace("KIND", kind).replace("FROM", start).replace("TO", finish)
    report, document = _map(tmp_path, rules)
    assert report.problems == (), report
    assert report.not_executed == ()
    edges = [(e["from"], e["to"]) for e in document["edges"] if e["kind"] == kind]
    assert edges == [edge]
    rows = [(line, rule, reason) for _, line, rule, reason in report.skipped if rule == "tie"]
    assert rows == []


def test_an_id_names_the_enclosing_method(tmp_path: Path) -> None:
    """The variable's id is composed from the method's declared name; at file level the source is
    absent, so the match makes nothing, with no row."""
    rules = RULES.replace(
        "id: {from: declared_name}\n  emits: [{node: {type: probe.variable}}]",
        "id:\n    from: [enclosing_type, enclosing_method, declared_name]\n"
        "    template: '{enclosing_type}::{enclosing_method}::{declared_name}'\n"
        "  emits: [{node: {type: probe.variable}}]",
    )
    rules = rules[: rules.index("- rule: tie")]
    report, document = _map(tmp_path, rules)
    assert report.problems == (), report
    assert report.not_executed == ()
    ids = [n["id"] for n in document["nodes"] if n["type"] == "probe.variable"]
    assert ids == ["probe.variable::App\\Thing::run::$box"]
    rows = [(line, rule, reason) for _, line, rule, reason in report.skipped]
    assert rows == []
