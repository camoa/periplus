"""The ``where`` conditions ``in_table`` and ``not_in_table``: the rule's name, or a named capture
of a name or id pattern in the same ``where``, is a key of a table, or is not, with the rows a
loaded dependent pack adds to that table through ``add_table_rows``."""

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

#: ``known`` and ``fn`` split the functions by their ``where``; ``call`` joins a call to either.
RULES = """\
node_types:
- {{name: own.fn, id_namespace: own.fn}}
- {{name: own.known, id_namespace: own.known}}
- {{name: own.root, id_namespace: own.root}}
edge_kinds:
- {{kind: calls, from: [own.fn, own.known], to: own.fn}}
rules:
- rule: known
  reads: file
  in: [code]
  match: {{declaration: function_definition, name_child: name, filetype: php, where: {known}}}
  id: {{from: declared_name}}
  emits: [{{node: {{type: own.known}}}}]
  confidence: declared
- rule: fn
  reads: file
  in: [code]
  match: {{declaration: function_definition, name_child: name, filetype: php, where: {fn}}}
  id: {{from: declared_name}}
  emits: [{{node: {{type: own.fn}}}}]
  confidence: declared
- rule: call
  reads: file
  in: [code]
  match: {{reference: function_call_expression, name_child: function, filetype: php, where: {call}}}
  emits:
  - edge: {{kind: calls, from: enclosing_declaration, to: {{types: [own.fn], on_miss: unresolved}}}}
  confidence: declared
- rule: root
  reads: map
  match:
    node_type: own.fn
    where: {mapped}
  id: {{template: '{{name}}'}}
  emits: [{{node: {{type: own.root}}}}]
  confidence: inferred
"""

SOURCE = """\
<?php

function alpha()
{
    beta();
    gamma();
}

function gamma()
{
}

function alpha_run()
{
}

function gamma_run()
{
}
"""

#: Adds gamma to own's table builtins.
EXTENDER = """\
pack: ext
version: 0.0.1
depends: [own]
add_table_rows:
  own:
    builtins: {gamma: gamma}
"""

#: The where of a rule a test leaves alone: every tree match passes, and no map node.
ANY = "[{name_matches: '.*'}]"
ANY_ID = "[{id_matches: '^(?<name>x)$'}]"

#: The root of a name: the text before an underscore, or the whole name.
ROOT = "{name_matches: '(?<root>[a-z]+)(?:_[a-z]+)?'}"


def _project(root: Path, extender: str | None = None, **where: str) -> None:
    packs = ".periplus/packs"
    rules = RULES.format(
        known=where.get("known", ANY),
        fn=where.get("fn", ANY),
        call=where.get("call", ANY),
        mapped=where.get("mapped", ANY_ID),
    )
    files = {
        f"{packs}/own@0.0.1/pack.yaml": OWNER,
        f"{packs}/own@0.0.1/rules/own.yaml": rules,
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


def _map(root: Path) -> dict[str, set[str]]:
    """The ids of each node type a rule mapped, and under ``calls`` the ids the calls edges
    reach."""
    report = _run(root)
    assert report.problems == () and report.not_executed == (), report
    document = json.loads((root / "map.json").read_text())
    found: dict[str, set[str]] = {}
    for node in document["nodes"]:
        if node.get("state") == "unresolved":
            continue
        found.setdefault(node["type"], set()).add(node["id"].split("::", 1)[1])
    for edge in document["edges"]:
        if edge["kind"] == "calls":
            found.setdefault("calls", set()).add(edge["to"].split("::", 1)[1])
    return found


def test_the_two_conditions_split_declarations_by_their_name(tmp_path: Path) -> None:
    _project(tmp_path, known="[{in_table: builtins}]", fn="[{not_in_table: builtins}]")
    found = _map(tmp_path)
    assert found["own.known"] == {"alpha"}
    assert found["own.fn"] == {"gamma", "alpha_run", "gamma_run"}


def test_a_capture_of_a_name_pattern_is_tested_in_place_of_the_name(tmp_path: Path) -> None:
    _project(
        tmp_path,
        known=f"[{ROOT}, {{in_table: {{table: builtins, capture: root}}}}]",
        fn=f"[{ROOT}, {{not_in_table: {{table: builtins, capture: root}}}}]",
    )
    found = _map(tmp_path)
    assert found["own.known"] == {"alpha", "alpha_run"}
    assert found["own.fn"] == {"gamma", "gamma_run"}


def test_a_reference_rule_passes_a_call_the_condition_fails_with_no_row(tmp_path: Path) -> None:
    for name, where, called in (
        ("in", "[{in_table: builtins}]", {"beta"}),
        ("out", "[{not_in_table: builtins}]", {"gamma"}),
    ):
        root = tmp_path / name
        _project(root, call=where)
        assert _map(root)["calls"] == called
        assert _run(root).skipped == ()


def test_a_map_rule_tests_a_capture_of_its_id_pattern(tmp_path: Path) -> None:
    pattern = "{id_matches: '^own\\.fn::(?<name>[a-z]+)_run$'}"
    for name, condition, made in (
        ("in", "in_table", {"alpha"}),
        ("out", "not_in_table", {"gamma"}),
    ):
        root = tmp_path / name
        _project(root, mapped=f"[{pattern}, {{{condition}: {{table: builtins, capture: name}}}}]")
        assert _map(root)["own.root"] == made


def test_a_row_a_dependent_adds_counts_only_when_that_pack_is_loaded(tmp_path: Path) -> None:
    loaded, alone = tmp_path / "loaded", tmp_path / "alone"
    _project(loaded, EXTENDER, known="[{in_table: builtins}]")
    _project(alone, known="[{in_table: builtins}]")
    assert _map(loaded)["own.known"] == {"alpha", "gamma"}
    assert _map(alone)["own.known"] == {"alpha"}


DATA = """\
pack: own
version: 0.0.1
depends: []
folders:
  config: ./config
files:
  types:
    yml:
      endings: [yml]
      reader: data
      format: yaml
tables:
  builtins: {alpha: alpha}
"""

DATA_RULES = """\
node_types:
- {{name: own.config, id_namespace: own.config}}
rules:
- rule: config
  reads: file
  in: [config]
  match: {{file: '*', filetype: yml, where: [{condition}]}}
  id: {{template: '{{file_stem}}'}}
  emits: [{{node: {{type: own.config}}}}]
  confidence: declared
"""


def test_a_file_rule_tests_the_file_stem(tmp_path: Path) -> None:
    for condition, made in (("in_table", {"alpha"}), ("not_in_table", {"gamma"})):
        root = tmp_path / condition
        plant(
            root,
            {
                ".periplus/packs/own@0.0.1/pack.yaml": DATA,
                ".periplus/packs/own@0.0.1/rules/own.yaml": DATA_RULES.format(
                    condition=f"{{{condition}: builtins}}"
                ),
                ".periplus/settings.yml": "periplus_version: 0\npacks: [own@0.0.1]\n",
                "config/alpha.yml": "a: 1\n",
                "config/gamma.yml": "a: 1\n",
            },
        )
        assert _map(root)["own.config"] == made


def _refused(root: Path, rule: str) -> list[str]:
    prefix = f"own/rules/own.yaml: the rule {rule} "
    return [p.message.removeprefix(prefix) for p in _run(root).problems]


def test_a_table_no_visible_pack_declares_is_refused(tmp_path: Path) -> None:
    """missing is declared nowhere; extras only by ext, which depends on own, so own's rule does
    not see it."""
    extender = "pack: ext\nversion: 0.0.1\ndepends: [own]\ntables:\n  extras: {gamma: gamma}\n"
    for table in ("missing", "extras"):
        root = tmp_path / table
        _project(root, extender, known=f"[{{not_in_table: {table}}}]")
        assert _refused(root, "known") == [
            f"cannot be executed: not_in_table names the table {table}, which no tables key of "
            "the pack or a pack it depends on declares"
        ]


def test_a_capture_no_pattern_of_the_where_defines_is_refused(tmp_path: Path) -> None:
    tree, mapped = tmp_path / "tree", tmp_path / "map"
    _project(tree, fn=f"[{ROOT}, {{in_table: {{table: builtins, capture: rest}}}}]")
    _project(mapped, mapped="[{id_matches: '^own'}, {in_table: {table: builtins, capture: name}}]")
    assert _refused(tree, "fn") == [
        "cannot be executed: in_table names the capture rest, which no name_matches pattern of "
        "the rule's where defines"
    ]
    assert _refused(mapped, "root") == [
        "cannot be executed: in_table names the capture name, which no id_matches pattern of "
        "the rule's where defines"
    ]
