"""A pack's ``add_table_rows``: rows a pack adds to a table a pack it depends on declares, which
the owner's own rules then look names up in."""

from __future__ import annotations

import json
from pathlib import Path

from test_demo_a_support import plant

from periplus.engine.packload import load_rules
from periplus.manifest import resolve_pack_order
from periplus.map import MapReport, run
from periplus.preflight import check_runtime_dependencies
from periplus.resolution import resolve

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
  kinds: {Store: store_kind}
"""

RULES = """\
node_types:
- {name: own.fn, id_namespace: own.fn}
- {name: own.kind, id_namespace: own.kind}
edge_kinds:
- {kind: loads, from: own.fn, to: own.kind}
rules:
- rule: fn
  reads: file
  in: [code]
  match: {declaration: function_definition, name_child: name, filetype: php}
  id: {from: declared_name}
  emits: [{node: {type: own.fn}}]
  confidence: declared
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
    Store::load(1);
    Crate::load(2);
    Box::load(3);
    Other::load(4);
}
"""


def _extender(name: str, depends: str, rows: str) -> str:
    return f"pack: {name}\nversion: 0.0.1\ndepends: [{depends}]\n{rows}"


def _crate(owner: str = "own", table: str = "kinds", value: str = "crate_kind") -> str:
    return f"add_table_rows:\n  {owner}:\n    {table}: {{Crate: {value}}}\n"


def _project(root: Path, extenders: dict[str, str], pins: list[str] | None = None) -> None:
    packs = ".periplus/packs"
    order = pins if pins is not None else ["own", *extenders]
    plant(
        root,
        {
            f"{packs}/own@0.0.1/pack.yaml": OWNER,
            f"{packs}/own@0.0.1/rules/own.yaml": RULES,
            **{f"{packs}/{name}@0.0.1/pack.yaml": text for name, text in extenders.items()},
            ".periplus/settings.yml": "periplus_version: 0\npacks: ["
            + ", ".join(f"{name}@0.0.1" for name in order)
            + "]\n",
            "src/a.php": SOURCE,
        },
    )


def _run(root: Path) -> MapReport:
    return run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )


def _loaded(root: Path) -> tuple[set[str], set[int]]:
    """The ends of the loads edges, and the lines of the skipped rows."""
    report = _run(root)
    assert report.problems == () and report.not_executed == (), report
    document = json.loads((root / "map.json").read_text())
    loads = {e["to"] for e in document["edges"] if e["kind"] == "loads"}
    return loads, {line for _, line, _, _ in report.skipped}


def _messages(root: Path) -> list[str]:
    return [problem.message for problem in _run(root).problems]


def test_the_owner_s_rule_finds_the_rows_a_dependent_adds(tmp_path: Path) -> None:
    """ext_a adds Crate directly; ext_b, which depends on own only through ext_a, adds Box. The
    owner's rule load finds both, and neither call leaves a skipped row."""
    box = "add_table_rows:\n  own:\n    kinds: {Box: box_kind}\n"
    _project(tmp_path, {"ext_a": _extender("ext_a", "own", _crate()), "ext_b": _extender(
        "ext_b", "ext_a", box
    )})
    assert _loaded(tmp_path) == (
        {"own.kind::store_kind", "own.kind::crate_kind", "own.kind::box_kind"},
        {8},
    )


def test_no_extender_leaves_the_owner_s_table_as_it_declares_it(tmp_path: Path) -> None:
    _project(tmp_path, {})
    assert _loaded(tmp_path) == ({"own.kind::store_kind"}, {6, 7, 8})


def test_a_same_name_table_of_a_dependent_still_adds_nothing_to_the_owner_s_rule(
    tmp_path: Path,
) -> None:
    rows = "tables:\n  kinds: {Crate: crate_kind}\n"
    _project(tmp_path, {"ext_a": _extender("ext_a", "own", rows)})
    assert _loaded(tmp_path) == ({"own.kind::store_kind"}, {6, 7, 8})


def test_rows_for_a_pack_that_is_not_a_dependency_are_refused(tmp_path: Path) -> None:
    _project(tmp_path, {"ext_a": _extender("ext_a", "", _crate())})
    assert _messages(tmp_path) == [
        "ext_a/pack.yaml: add_table_rows names own, which ext_a does not depend on"
    ]


def test_rows_for_a_table_the_owner_does_not_declare_are_refused(tmp_path: Path) -> None:
    _project(tmp_path, {"ext_a": _extender("ext_a", "own", _crate(table="sorts"))})
    assert _messages(tmp_path) == [
        "ext_a/pack.yaml: add_table_rows names the table sorts of own, which own does not "
        "declare under tables"
    ]


def test_a_key_the_owner_gives_another_value_is_refused(tmp_path: Path) -> None:
    rows = "add_table_rows:\n  own:\n    kinds: {Store: shop_kind}\n"
    _project(tmp_path, {"ext_a": _extender("ext_a", "own", rows)})
    assert _messages(tmp_path) == [
        "ext_a/pack.yaml: add_table_rows gives Store in the table kinds of own the value "
        "shop_kind, where own gives store_kind"
    ]


def test_a_key_another_extender_gives_another_value_is_refused(tmp_path: Path) -> None:
    _project(
        tmp_path,
        {
            "ext_b": _extender("ext_b", "own", _crate(value="crate_box")),
            "ext_a": _extender("ext_a", "own", _crate()),
        },
    )
    assert _messages(tmp_path) == [
        "ext_b/pack.yaml: add_table_rows gives Crate in the table kinds of own the value "
        "crate_box, where ext_a gives crate_kind"
    ]


def test_a_key_given_the_same_value_twice_is_no_problem(tmp_path: Path) -> None:
    same = "add_table_rows:\n  own:\n    kinds: {Store: store_kind, Crate: crate_kind}\n"
    _project(
        tmp_path,
        {"ext_a": _extender("ext_a", "own", same), "ext_b": _extender("ext_b", "own", _crate())},
    )
    assert _loaded(tmp_path) == ({"own.kind::store_kind", "own.kind::crate_kind"}, {7, 8})


def test_the_table_and_the_map_do_not_depend_on_the_order_packs_load_in(tmp_path: Path) -> None:
    """Two projects pin the same packs in opposite orders and write their rows in opposite orders;
    the maps are the same bytes, and the owner's table, read in either load order, lists its own
    rows and then the added keys sorted."""
    box = "add_table_rows:\n  own:\n    kinds: {Box: box_kind, Bin: bin_kind}\n"
    xob = "add_table_rows:\n  own:\n    kinds: {Bin: bin_kind, Box: box_kind}\n"
    first, second = tmp_path / "first", tmp_path / "second"
    _project(first, {"ext_a": _extender("ext_a", "own", _crate()), "ext_b": _extender(
        "ext_b", "own", box
    )})
    _project(
        second,
        {"ext_b": _extender("ext_b", "own", xob), "ext_a": _extender("ext_a", "own", _crate())},
        pins=["ext_b", "ext_a", "own"],
    )
    assert _run(first).problems == () and _run(second).problems == ()
    assert (first / "map.json").read_bytes() == (second / "map.json").read_bytes()
    resolution = resolve(
        start=first, env={"PERIPLUS_CONFIG_DIR": str(first / "config")}, dependencies=()
    )
    packs, problems = resolve_pack_order(resolution.packs, resolution.candidates)
    assert not problems
    rows = ["Store", "Bin", "Box", "Crate"]
    assert list(load_rules(packs).tables["own"]["kinds"]) == rows
    assert list(load_rules(list(reversed(packs))).tables["own"]["kinds"]) == rows


MODULE = "web/modules/custom/mymodule"
CONTROLLER = r"""<?php

namespace Drupal\mymodule\Controller;

class ThingController {

  public function run() {
    \Drupal::thing();
  }

}
"""


def test_a_project_pack_adds_rows_to_a_bundled_pack_s_table(tmp_path: Path) -> None:
    """A rutter in the project's packs folder adds a row to drupal_basic's shortcut_services, and
    drupal_basic's own rule drupal_shortcut_call finds it."""
    rows = "add_table_rows:\n  drupal_basic:\n    shortcut_services: {thing: mymodule.thing}\n"
    plant(
        tmp_path,
        {
            ".periplus/packs/mine@0.0.1/pack.yaml": _extender("mine", "drupal_basic", rows),
            ".periplus/settings.yml": "periplus_version: 0\n"
            "packs: [drupal_basic@0.3.0, mine@0.0.1]\n",
            f"{MODULE}/mymodule.info.yml": (
                "name: My module\ntype: module\ncore_version_requirement: ^10\n"
            ),
            f"{MODULE}/src/Controller/ThingController.php": CONTROLLER,
        },
    )
    report = _run(tmp_path)
    assert report.problems == () and report.not_executed == (), report
    assert report.skipped == (), report.skipped
    document = json.loads((tmp_path / "map.json").read_text())
    assert {
        (e["to"], p["rule"]) for e in document["edges"] if e["kind"] == "uses_service"
        for p in e["provenance"]
    } == {("drupal.service::mymodule.thing", "drupal_shortcut_call")}
