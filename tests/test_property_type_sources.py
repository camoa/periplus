"""Tests for two abilities of a tree declaration rule: a ``name_child`` that is a path walked from
the matched node, and an id source ``{docblock: <pattern>}`` read in the comment that is the
matched node's previous sibling, alone or wrapped in ``qualified``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
  comment: comment
  resolve:
  - full_if_prefixed: "\\\\"
  - bound_first_segment
  - prefix_with: namespace
"""

VAR = "'@var\\s+(?<type>[\\w\\\\]+)'"

RULES = f"""\
imports:
- ast: namespace_use_declaration
  group_ast: namespace_use_group
  clause: namespace_use_clause
  facts: {{alias: alias, use_kind: type}}
  bind:
    name: [alias, last_segment]
    prefix_from_group: true
    strip_prefix: "\\\\"
    skip_when_field_set: use_kind
node_types:
- {{name: probe.named, id_namespace: probe.named}}
- {{name: probe.written, id_namespace: probe.written}}
- {{name: probe.resolved, id_namespace: probe.resolved}}
- {{name: probe.gated, id_namespace: probe.gated}}
rules:
- rule: named
  reads: file
  in: [source]
  match: {{declaration: property_declaration, name_child: [property_element, name], filetype: php}}
  id: {{from: declared_name}}
  emits: [{{node: {{type: probe.named}}}}]
  confidence: declared
- rule: written
  reads: file
  in: [source]
  match: {{declaration: property_declaration, name_child: [property_element, name], filetype: php}}
  id:
    from: [declared_name, {{docblock: {VAR}}}]
    template: '{{declared_name}}:{{type}}'
  emits: [{{node: {{type: probe.written}}}}]
  confidence: declared
- rule: resolved
  reads: file
  in: [source]
  match: {{declaration: property_declaration, name_child: [property_element, name], filetype: php}}
  id:
    from: [declared_name, {{qualified: {{docblock: {VAR}}}}}]
    template: '{{declared_name}}:{{type}}'
  emits: [{{node: {{type: probe.resolved}}}}]
  confidence: declared
- rule: gated
  reads: file
  in: [source]
  match: {{declaration: property_declaration, name_child: [property_element, name], filetype: php}}
  id:
    from: [declared_name, {{docblock: {VAR}}}]
    template: '{{declared_name}}'
  emits: [{{node: {{type: probe.gated}}}}]
  confidence: declared
"""

SOURCE = """\
<?php

namespace App\\Ctl;

use App\\Service\\Registration;

class Thing
{
    /** @var Registration */
    protected $reg;

    /** @var \\Other\\Helper */
    protected $help;

    /** A note and no type. */
    protected $noted;

    protected $bare;
}
"""


def _map(root: Path) -> tuple[MapReport, Any]:
    pack = root / ".periplus" / "packs" / "probe@0.0.1"
    (pack / "rules").mkdir(parents=True)
    (root / ".periplus" / "settings.yml").write_text("periplus_version: 0\npacks: [probe@0.0.1]\n")
    (pack / "pack.yaml").write_text(PACK)
    (pack / "rules" / "probe.yaml").write_text(RULES)
    (root / "Thing.php").write_text(SOURCE)
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == () and report.not_executed == (), report
    return report, json.loads((root / "map.json").read_text())


def _nodes(document: Any, kind: str) -> list[tuple[str, int]]:
    return sorted(
        (n["id"], n["locations"][0]["line"]) for n in document["nodes"] if n["type"] == kind
    )


def test_a_name_child_path_names_the_leafs_text_at_its_line(tmp_path: Path) -> None:
    """[property_element, name] walks from the property_declaration to the variable_name below it,
    a child by node type and then by field."""
    _, document = _map(tmp_path)
    assert _nodes(document, "probe.named") == [
        ("probe.named::$bare", 18),
        ("probe.named::$help", 13),
        ("probe.named::$noted", 16),
        ("probe.named::$reg", 10),
    ], _nodes(document, "probe.named")


def test_a_docblock_source_takes_its_group_as_written(tmp_path: Path) -> None:
    _, document = _map(tmp_path)
    assert _nodes(document, "probe.written") == [
        ("probe.written::$help:\\Other\\Helper", 13),
        ("probe.written::$reg:Registration", 10),
    ], _nodes(document, "probe.written")


def test_a_qualified_docblock_source_resolves_through_the_imports(tmp_path: Path) -> None:
    """Registration is imported, so its full name is the use line's; \\Other\\Helper is fully
    qualified, so its leading separator goes."""
    _, document = _map(tmp_path)
    assert _nodes(document, "probe.resolved") == [
        ("probe.resolved::$help:Other\\Helper", 13),
        ("probe.resolved::$reg:App\\Service\\Registration", 10),
    ], _nodes(document, "probe.resolved")


def test_no_docblock_or_no_match_makes_nothing_and_no_skipped_row(tmp_path: Path) -> None:
    """$noted's comment holds no @var and $bare has no comment: neither makes a node of a docblock
    rule, and no rule lists a skipped row. A template that leaves the value out still needs it."""
    report, document = _map(tmp_path)
    assert report.skipped == (), report.skipped
    assert _nodes(document, "probe.gated") == [
        ("probe.gated::$help", 13),
        ("probe.gated::$reg", 10),
    ], _nodes(document, "probe.gated")


NULLABLE = """\
<?php
namespace App\\Web;

use App\\Service\\Mailer;

class Page
{
  protected ?Mailer $mailer;

  protected ?int $count;

  public function __construct(
    private ?\\App\\Service\\Clock $clock = NULL,
    private ?string $s = null,
  ) {}

  public function run(): void
  {
    $this->mailer->send();
    $this->clock->now();
    $this->count->go();
    $this->s->go();
  }
}
"""


def test_a_nullable_typed_or_promoted_property_gives_a_call_and_a_nullable_scalar_nothing(
    tmp_path: Path,
) -> None:
    """php_basic: ?Mailer resolves through the use line and ?\\App\\Service\\Clock as written, each
    giving calls_through_typed_property's edge; ?int and ?string give no edge and no skipped row."""
    (tmp_path / ".periplus").mkdir()
    (tmp_path / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks: [php_basic@0.2.0]\n"
    )
    (tmp_path / "Page.php").write_text(NULLABLE)
    report = run(
        start=tmp_path,
        env={"PERIPLUS_CONFIG_DIR": str(tmp_path / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == () and report.skipped == (), report
    document = json.loads((tmp_path / "map.json").read_text())
    calls = sorted(
        (e["to"], e["locations"][0]["line"])
        for e in document["edges"]
        if e["kind"] == "calls"
        and any(p["rule"] == "calls_through_typed_property" for p in e["provenance"])
    )
    assert calls == [
        ("php.method::App\\Service\\Clock::now", 20),
        ("php.method::App\\Service\\Mailer::send", 19),
    ], calls
