"""The refusals of a wrong boundary each name the shape that works: a group type no pack declares,
a names value no pack declares, an ancestry kind no pack declares, and one id two packs list. The
old path-based keys are refused by the manifest schema, naming the key."""

from __future__ import annotations

from pathlib import Path

import pytest

from periplus.map import MapReport, run
from periplus.preflight import check_runtime_dependencies

SHAPE = (
    "boundary: {<group>: {type: <node type>, ancestry: [<edge kind>], "
    "names: {<name>: <node type or ~>}}}"
)

# A rutter that owns the PHP grammar and declares a class type and inherits. {boundary} is its
# boundary block.
MANIFEST = """\
pack: {pack}
version: 0.0.1
depends: {depends}
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
{boundary}"""

RULES = """\
node_types:
- {name: own.cls, id_namespace: own.cls}
edge_kinds:
- {kind: inherits, from: own.cls, to: own.cls}
rules:
- rule: cls
  reads: file
  in: [code]
  match: {declaration: class_declaration, name_child: name, filetype: php}
  id: {from: qualified_name}
  emits: [{node: {type: own.cls}}]
  confidence: declared
"""

SOURCE = "<?php\nnamespace App;\n\nclass Page extends \\Fw\\Base\n{\n}\n"


def _boundary(group_type: str = "own.cls", kind: str = "inherits", value: str = "~") -> str:
    return (
        f"boundary:\n  fw:\n    type: {group_type}\n    ancestry: [{kind}]\n"
        f"    names: {{Fw\\Base: {value}}}\n"
    )


def _run(root: Path, boundary: str, *, second: str | None = None) -> MapReport:
    packs = root / ".periplus" / "packs"
    own = packs / "own@0.0.1"
    (own / "rules").mkdir(parents=True)
    (own / "pack.yaml").write_text(MANIFEST.format(pack="own", depends="[]", boundary=boundary))
    (own / "rules" / "own.yaml").write_text(RULES)
    pinned = "[own@0.0.1]"
    if second is not None:
        other = packs / "other@0.0.1"
        other.mkdir(parents=True)
        (other / "pack.yaml").write_text(f"pack: other\nversion: 0.0.1\ndepends: [own]\n{second}")
        pinned = "[own@0.0.1, other@0.0.1]"
    (root / ".periplus" / "settings.yml").write_text(f"periplus_version: 0\npacks: {pinned}\n")
    (root / "src").mkdir()
    (root / "src" / "a.php").write_text(SOURCE)
    return run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )


@pytest.mark.parametrize(
    ("boundary", "second", "names"),
    [
        (_boundary(group_type="own.missing"), None, "own.missing"),
        (_boundary(value="own.missing"), None, "own.missing"),
        (_boundary(kind="extends_missing"), None, "extends_missing"),
        (_boundary(), _boundary(), "own.cls::Fw\\Base"),
    ],
    ids=["group-type", "names-value", "ancestry-kind", "two-packs-one-id"],
)
def test_a_wrong_boundary_is_refused_naming_the_working_shape(
    tmp_path: Path, boundary: str, second: str | None, names: str
) -> None:
    """The map stops with exit 26 and one problem, which names the wrong word and the shape."""
    report = _run(tmp_path, boundary, second=second)
    assert report.exit_code == 26, report
    assert len(report.problems) == 1, report.problems
    message = report.problems[0].message
    assert names in message and SHAPE in message, message
    assert not (tmp_path / "map.json").exists()


@pytest.mark.parametrize("key", ["applies_to_paths", "emit_boundary_nodes", "type_hierarchy"])
def test_an_old_boundary_key_is_refused_by_the_schema_naming_it(tmp_path: Path, key: str) -> None:
    """The path-based shape before this release: the manifest schema refuses it, exit 16."""
    value = {
        "applies_to_paths": "['vendor/**']",
        "emit_boundary_nodes": "on_reference",
        "type_hierarchy": "[{type: own.cls}]",
    }[key]
    report = _run(tmp_path, f"boundary:\n  {key}: {value}\n")
    assert report.exit_code == 16, report
    assert [p for p in report.problems if f"$.boundary.{key}" in p.message], report.problems
    assert not (tmp_path / "map.json").exists()
