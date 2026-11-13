"""Boundaries a rule identifies, and unknown boundaries no rule identified.

A general pack marks every call it cannot place as an unknown boundary; a specific pack that
depends on it turns one of those calls into a known boundary into a named API node, on the same
end. Neither pack names a real stack.
"""

from __future__ import annotations

import json
from itertools import permutations
from pathlib import Path
from typing import Any

import pytest
from test_demo_a_support import map_project, nodes, pin, plant, rutter

from periplus.cli import main
from periplus.errors import ExitCode
from periplus.map import render_json, render_text

#: A dependent pack declares no folders or file types: it reads the map the general pack built.
DEPENDENT = "pack: {name}\nversion: 0.0.1\ndepends: [gen]\n"

MANIFEST = """\
pack: gen
version: 0.0.1
depends: []
folders:
  src: ./src
files:
  types:
    code:
      endings: [sx]
      reader: text
"""

GENERAL = """\
node_types:
- {name: gen.function, id_namespace: gen.function}
- {name: gen.callsite, id_namespace: gen.callsite}
edge_kinds:
- {kind: calls, from: gen.function, to: gen.function}
rules:
- rule: function_line
  reads: file
  in: [src]
  match: {file: '*', filetype: code, text: '(?m)^fn (?<name>\\w+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: gen.function}}]
  confidence: declared
- rule: call_site
  reads: file
  in: [src]
  match: {file: '*', filetype: code, text: '(?m)^(?<caller>\\w+) calls (?<callee>\\w+)'}
  id: {template: '{caller}.{callee}'}
  emits: [{node: {type: gen.callsite}}]
  confidence: declared
- rule: runtime_site
  reads: file
  in: [src]
  match: {file: '*', filetype: code, text: '(?m)^(?<caller>\\w+) calls \\$(?<var>\\w+)'}
  id: {template: '{caller}.${var}'}
  emits:
  - node: {type: gen.callsite}
  - attribute: {name: resolution, template: runtime}
  confidence: declared
- rule: call_edge
  reads: map
  match:
    node_type: gen.callsite
    follow:
    - id_matches: '::(?<caller>\\w+)\\.(?<callee>\\w+)$'
    - node: 'gen.function::{caller}'
  emits:
  - edge:
      kind: calls
      from: matched_node
      to: {template: 'gen.function::{callee}', on_miss: unknown_boundary}
  confidence: inferred
"""

SPECIFIC_TYPES = """\
node_types:
- {name: spec.api, id_namespace: spec.api, boundary: true}
edge_kinds:
- {kind: enters, from: gen.function, to: spec.api}
"""

#: A rule of the specific pack that marks the call to config; ``{mark}`` is the end's mark.
MARKING = """\
- rule: {name}
  reads: map
  match:
    node_type: gen.callsite
    follow:
    - id_matches: '::(?<caller>\\w+)\\.config$'
    - node: 'gen.function::{{caller}}'
  emits:
  - edge:
      kind: calls
      from: matched_node
      to: {{template: 'gen.function::config', {mark}}}
  confidence: inferred
"""

MARKS = {
    "boundary": "boundary: {into: {template: config, type: spec.api}, kind: enters}",
    "unresolved": "on_miss: unresolved",
    "unknown_boundary": "on_miss: unknown_boundary",
}

SOURCE = "fn alpha\nalpha calls config\nalpha calls helper\nalpha calls beta\nfn beta\n"
RUNTIME = "alpha calls $name\n"


def _project(
    root: Path,
    files: dict[str, str] | None = None,
    source: str = SOURCE,
    more: dict[str, str] | None = None,
) -> None:
    """The general pack, and with ``files`` the specific pack holding them as its rule files;
    ``more`` adds a third pack, ``more``, that depends on the general pack too."""
    rutter(root, "gen", MANIFEST, {"gen.yaml": GENERAL})
    pins = ["gen@0.0.1"]
    if files is not None:
        rutter(root, "spec", DEPENDENT.format(name="spec"), files)
        pins.append("spec@0.0.1")
    if more is not None:
        rutter(root, "more", DEPENDENT.format(name="more"), more)
        pins.append("more@0.0.1")
    pin(root, *pins)
    plant(root, {"src/one.sx": source})


def _rules(*marks: str) -> str:
    return "rules:\n" + "".join(
        MARKING.format(name=f"mark_{i}", mark=MARKS[m]) for i, m in enumerate(marks)
    )


def _mapped(root: Path) -> dict[str, Any]:
    report, document = map_project(root)
    assert report.problems == () and report.not_executed == (), report
    return document


def _edges(document: dict[str, Any]) -> dict[tuple[str, str, str], dict[str, Any]]:
    return {(e["kind"], e["from"], e["to"]): e for e in document["edges"]}


def _rules_of(entry: dict[str, Any]) -> list[tuple[str, str]]:
    return [(p["pack"], p["rule"]) for p in entry["provenance"]]


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "_config"))


def test_the_general_rule_alone_marks_an_outside_end_an_unknown_boundary(tmp_path: Path) -> None:
    _project(tmp_path)
    found = nodes(_mapped(tmp_path))
    for name in ("config", "helper"):
        node = found[f"gen.function::{name}"]
        assert node["state"] == "unknown_boundary", node
        assert node["unresolved_detail"]["rule"] == "gen/call_edge", node
        assert node["unresolved_detail"]["searched_for"] == name, node
    assert found["gen.function::beta"]["state"] == "mapped"


def test_the_specific_rule_makes_the_same_end_a_boundary_into_the_api_node(tmp_path: Path) -> None:
    _project(tmp_path, {"spec.yaml": SPECIFIC_TYPES + _rules("boundary")})
    document = _mapped(tmp_path)
    found, edges = nodes(document), _edges(document)
    end = found["gen.function::config"]
    assert end["state"] == "boundary", end
    assert "unresolved_detail" not in end, end
    assert _rules_of(end) == [("gen", "call_edge"), ("spec", "mark_0")], end
    # One node for the end, one call edge carrying both rules.
    assert [n for n in found if n.endswith("::config")] == [
        "gen.function::config",
        "spec.api::config",
    ]
    calls = [k for k in edges if k[0] == "calls" and k[2] == "gen.function::config"]
    assert calls == [("calls", "gen.function::alpha", "gen.function::config")], calls
    assert _rules_of(edges[calls[0]]) == [("gen", "call_edge"), ("spec", "mark_0")]
    into = edges[("enters", "gen.function::config", "spec.api::config")]
    assert _rules_of(into) == [("spec", "mark_0")], into
    assert into["locations"] == edges[calls[0]]["locations"], into
    api = found["spec.api::config"]
    assert (api["type"], api["state"], api["locations"]) == ("spec.api", "boundary", []), api
    assert _rules_of(api) == [("spec", "mark_0")], api
    # The call the specific pack does not identify stays an unknown boundary.
    assert found["gen.function::helper"]["state"] == "unknown_boundary"


def test_a_node_of_a_boundary_type_an_edge_reaches_reads_boundary(tmp_path: Path) -> None:
    """An edge straight to the API node, with no end mark, gives a boundary node too."""
    rule = (
        MARKING.format(name="uses", mark="type: spec.api")
        .replace("'gen.function::config'", "config")
        .replace("kind: calls", "kind: enters")
    )
    _project(tmp_path, {"spec.yaml": SPECIFIC_TYPES + "rules:\n" + rule})
    found = nodes(_mapped(tmp_path))
    assert found["spec.api::config"]["state"] == "boundary", found["spec.api::config"]


_PAIRS = [
    (a, b)
    for a, b in permutations(("mapped", "boundary", "unresolved", "unknown_boundary"), 2)
    if b != "mapped"
]
_RANK = ("mapped", "boundary", "unresolved", "unknown_boundary")


@pytest.mark.parametrize(("first", "second"), _PAIRS, ids=[f"{a}-{b}" for a, b in _PAIRS])
def test_the_strongest_mark_wins_in_either_file_order(
    tmp_path: Path, first: str, second: str
) -> None:
    """mapped beats boundary, boundary beats unresolved, unresolved beats unknown boundary,
    whichever rule file loads first; every rule stays in the end's provenance."""
    winner = min(first, second, key=_RANK.index)
    marks = [m for m in (first, second) if m != "mapped"]
    source = SOURCE + ("fn config\n" if "mapped" in (first, second) else "")
    maps = []
    for order, root in ((0, tmp_path / "ab"), (1, tmp_path / "ba")):
        rules = [_rules(m).replace("mark_0", f"mark_{m}") for m in marks]
        files = {
            f"{'ab'[i]}.yaml": body for i, body in enumerate(rules if order == 0 else rules[::-1])
        }
        files["types.yaml"] = SPECIFIC_TYPES
        _project(root, files, source)
        document = _mapped(root)
        end = nodes(document)["gen.function::config"]
        assert end["state"] == winner, (order, end)
        call = _edges(document)[("calls", "gen.function::alpha", "gen.function::config")]
        for mark in marks:
            assert ("spec", f"mark_{mark}") in _rules_of(call), call
            # A node a rule found keeps the rules that found it; an end keeps every marking rule.
            assert winner == "mapped" or ("spec", f"mark_{mark}") in _rules_of(end), end
        if winner in ("unresolved", "unknown_boundary"):
            # The detail names a rule of the winning mark, chosen by name, not by load order.
            rule = "spec/mark_unresolved" if winner == "unresolved" else "gen/call_edge"
            assert end["unresolved_detail"]["rule"] == rule, end
        else:
            assert "unresolved_detail" not in end, end
        # Only an end that reads boundary enters the API node.
        into = ("enters", "gen.function::config", "spec.api::config")
        assert (into in _edges(document)) == (winner == "boundary"), _edges(document)
        maps.append((root / "map.json").read_bytes())
    assert maps[0] == maps[1]


@pytest.mark.parametrize("mark", ["unresolved", "unknown_boundary"])
def test_the_detail_names_the_first_rule_of_the_mark_by_name_in_either_file_order(
    tmp_path: Path, mark: str
) -> None:
    for order, root in ((0, tmp_path / "ab"), (1, tmp_path / "ba")):
        rules = [_rules(mark).replace("mark_0", name) for name in ("mark_a", "mark_b")]
        files = {f"{'ab'[i]}.yaml": body for i, body in enumerate(rules[:: 1 - 2 * order])}
        files["types.yaml"] = SPECIFIC_TYPES
        _project(root, files)
        end = nodes(_mapped(root))["gen.function::config"]
        assert end["state"] == mark, end
        expected = "spec/mark_a" if mark == "unresolved" else "gen/call_edge"
        assert end["unresolved_detail"]["rule"] == expected, (order, end)


def test_affected_reads_what_touches_the_api_node(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _project(tmp_path, {"spec.yaml": SPECIFIC_TYPES + _rules("boundary")})
    _mapped(tmp_path)
    capsys.readouterr()
    command = ["affected", "spec.api::config", "--depth", "2", "--map", "map.json"]
    assert main([*command, "--format", "json"]) == 0
    rows = json.loads(capsys.readouterr().out)["rows"]["items"]
    assert [(r["id"], r["state"], r["depth"]) for r in rows] == [
        ("gen.function::config", "boundary", 1),
        ("gen.function::alpha", "mapped", 2),
    ], rows


def test_two_packs_marking_one_end_keep_one_node_and_both_rules(tmp_path: Path) -> None:
    more_types = SPECIFIC_TYPES.replace("spec.api", "more.api").replace("enters", "reaches")
    more = _rules("boundary").replace("mark_0", "more_mark")
    more = more.replace("spec.api", "more.api").replace("kind: enters", "kind: reaches")
    _project(
        tmp_path,
        {"spec.yaml": SPECIFIC_TYPES + _rules("boundary")},
        more={"more.yaml": more_types + more},
    )
    document = _mapped(tmp_path)
    end = nodes(document)["gen.function::config"]
    assert end["state"] == "boundary", end
    assert _rules_of(end) == [("gen", "call_edge"), ("more", "more_mark"), ("spec", "mark_0")]
    edges = _edges(document)
    assert ("enters", "gen.function::config", "spec.api::config") in edges
    assert ("reaches", "gen.function::config", "more.api::config") in edges


def test_the_runtime_mark_is_an_unknown_boundary_with_its_reason(tmp_path: Path) -> None:
    _project(tmp_path, source=SOURCE + RUNTIME)
    site = nodes(_mapped(tmp_path))["gen.callsite::alpha.$name"]
    assert site["state"] == "unknown_boundary", site
    assert site["attributes"] == {"resolution": "runtime"}, site
    assert site["locations"] == [{"file": "src/one.sx", "line": 6}], site


def test_the_report_counts_boundaries_and_unknown_boundaries(tmp_path: Path) -> None:
    _project(tmp_path, {"spec.yaml": SPECIFIC_TYPES + _rules("boundary")}, SOURCE + RUNTIME)
    report, _ = map_project(tmp_path)
    assert report.problems == (), report
    text = render_text(report)
    assert "\nBoundaries:\n  total 2\n  gen.function::config 1\n  spec.api::config 1\n" in text
    assert (
        "\nUnknown boundaries:\n  total 2\n  by pack: gen 2\n  by reason: no rule 1, run-time 1\n"
    ) in text, text
    payload = json.loads(render_json(report))
    assert payload["boundaries"] == {
        "total": 2,
        "by_node": [
            {"node": "gen.function::config", "edges": 1},
            {"node": "spec.api::config", "edges": 1},
        ],
    }
    assert payload["unknown_boundaries"] == {
        "total": 2,
        "by_pack": {"gen": 2},
        "by_reason": {"no rule": 1, "run-time": 1},
    }


def test_the_map_is_byte_identical_on_two_runs(tmp_path: Path) -> None:
    _project(tmp_path, {"spec.yaml": SPECIFIC_TYPES + _rules("boundary")}, SOURCE + RUNTIME)
    _mapped(tmp_path)
    first = (tmp_path / "map.json").read_bytes()
    _mapped(tmp_path)
    assert (tmp_path / "map.json").read_bytes() == first


def _refused(root: Path) -> list[tuple[ExitCode, str]]:
    report, _ = map_project(root)
    assert report.map_path is None
    return [(p.code, p.message) for p in report.problems]


def test_an_unknown_on_miss_value_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _project(tmp_path, {"spec.yaml": SPECIFIC_TYPES + _rules("unresolved")})
    rules = tmp_path / ".periplus/packs/spec@0.0.1/rules/spec.yaml"
    rules.write_text(rules.read_text().replace("on_miss: unresolved", "on_miss: outside"))
    problems = _refused(tmp_path)
    assert [code for code, _ in problems] == [ExitCode.SCHEMA_INVALID], problems
    assert problems[0][1].endswith(
        "; $.rules[0].emits[0].edge.to.on_miss: 'outside' is not one of "
        "['unresolved', 'unknown_boundary']"
    ), problems
    capsys.readouterr()
    assert main(["validate", "spec@0.0.1"]) == ExitCode.SCHEMA_INVALID
    printed = capsys.readouterr().out
    assert "'outside' is not one of ['unresolved', 'unknown_boundary']" in printed, printed


def test_a_boundary_type_a_rule_emits_as_a_node_is_refused(tmp_path: Path) -> None:
    node_rule = (
        "- rule: api_line\n  reads: file\n  in: [src]\n"
        "  match: {file: '*', filetype: code, text: '(?m)^api (?<name>\\w+)'}\n"
        "  id: {from: {capture: name}}\n  emits: [{node: {type: spec.api}}]\n"
        "  confidence: declared\n"
    )
    _project(tmp_path, {"spec.yaml": SPECIFIC_TYPES + _rules("boundary") + node_rule})
    problems = _refused(tmp_path)
    assert problems == [
        (
            ExitCode.PACK_RULES_UNREADABLE,
            "spec/rules/spec.yaml: the rule api_line emits the boundary type spec.api, which spec "
            "declares boundary: true; a node of a boundary type is one no rule finds",
        )
    ], problems


@pytest.mark.parametrize(
    ("change", "words"),
    [
        (
            ("to: spec.api}", "to: gen.function}"),
            "the rule mark_0 marks its to end a boundary into spec.api, and the edge enters "
            "allows gen.function there",
        ),
        (
            ("from: gen.function, to: spec.api}", "from: gen.callsite, to: spec.api}"),
            "the rule mark_0 marks its to end a boundary into spec.api by the edge enters, "
            "which allows gen.callsite at its from end, and the end is a gen.function",
        ),
        (
            ("boundary: true", "boundary: false"),
            "the rule mark_0 marks its to end a boundary into spec.api, which no pack declares "
            "boundary: true",
        ),
    ],
    ids=["into-type", "end-type", "not-a-boundary-type"],
)
def test_an_into_edge_its_kind_or_type_cannot_carry_is_refused(
    tmp_path: Path, change: tuple[str, str], words: str
) -> None:
    _project(tmp_path, {"spec.yaml": SPECIFIC_TYPES.replace(*change) + _rules("boundary")})
    problems = _refused(tmp_path)
    assert problems == [(ExitCode.EDGE_ILLEGAL, f"spec/rules/spec.yaml: {words}")], problems


def test_two_rules_entering_one_api_node_as_different_types_are_refused(tmp_path: Path) -> None:
    """Which into type the node took would depend on which rule file loaded first."""
    types = (
        "node_types:\n"
        "- {name: spec.api, id_namespace: spec.api, boundary: true}\n"
        "- {name: spec.api3, id_namespace: spec.api, boundary: true}\n"
        "edge_kinds:\n"
        "- {kind: enters, from: gen.function, to: [spec.api, spec.api3]}\n"
    )
    other = _rules("boundary").replace("mark_0", "mark_y").replace("spec.api}", "spec.api3}")
    _project(tmp_path, {"types.yaml": types, "a.yaml": _rules("boundary"), "b.yaml": other})
    assert _refused(tmp_path) == [
        (
            ExitCode.TYPE_COLLISION,
            "spec/rules/a.yaml: the rule mark_0 enters spec.api::config as a spec.api, and the "
            "rule spec/mark_y in spec/rules/b.yaml enters it as a spec.api3; one into node takes "
            "one type",
        )
    ]


#: One pack that reads a tree, a text and a data file, for an end marked by each kind of file rule.
KINDS_MANIFEST = """\
pack: own
version: 0.0.1
depends: []
folders:
  source: ./src
grammar:
  provider: tree-sitter
  provider_version: 0.26.0
  language: php
  grammar_version: 0.24.1
files:
  types:
    php:
      endings: [php]
      reader: tree
    note:
      endings: [txt]
      reader: text
    conf:
      endings: [yml]
      reader: data
      format: yaml
identity:
  qualified_name: {parts: [namespace, declared_name], separator: "\\\\"}
  namespace: {declaration: namespace_definition, name_child: name}
  written_names: [name, qualified_name]
"""

KINDS_RULES = """\
node_types:
- {name: own.fn, id_namespace: own.fn}
- {name: own.api, id_namespace: own.api, boundary: true}
edge_kinds:
- {kind: calls, from: own.fn, to: own.fn}
- {kind: enters, from: own.fn, to: own.api}
rules:
- rule: fn
  reads: file
  in: [source]
  match: {declaration: function_definition, name_child: name, filetype: php}
  id: {from: declared_name}
  emits: [{node: {type: own.fn}}]
  confidence: declared
"""

INTO = "boundary: {into: {template: settings, type: own.api}, kind: enters}"

KIND_RULES = {
    "reference": f"""\
- rule: marks
  reads: file
  in: [source]
  match: {{reference: function_call_expression, name_child: function, filetype: php}}
  emits: [{{edge: {{kind: calls, from: enclosing_declaration, to: {{types: [own.fn], {INTO}}}}}}}]
  confidence: declared
""",
    "text": f"""\
- rule: marks
  reads: file
  in: [source]
  match: {{file: '*', filetype: note, text: '(?m)^(?<caller>\\w+) calls config$'}}
  id: {{from: {{capture: caller}}}}
  emits: [{{edge: {{kind: calls, from: this_node, to: {{template: config, {INTO}}}}}}}]
  confidence: declared
""",
    "data": f"""\
- rule: marks
  reads: file
  in: [source]
  match: {{file: '*', filetype: conf}}
  id: {{from: file_stem}}
  emits: [{{edge: {{kind: calls, from: this_node, to: {{from: {{key: uses}}, {INTO}}}}}}}]
  confidence: declared
""",
}


@pytest.mark.parametrize("kind", sorted(KIND_RULES))
def test_a_reference_text_or_data_rule_marks_its_end_a_boundary(tmp_path: Path, kind: str) -> None:
    rutter(tmp_path, "own", KINDS_MANIFEST, {"own.yaml": KINDS_RULES + KIND_RULES[kind]})
    pin(tmp_path, "own@0.0.1")
    plant(
        tmp_path,
        {
            "src/alpha.php": "<?php\nfunction alpha() {\n  config();\n}\n",
            "src/alpha.txt": "alpha calls config\n",
            "src/alpha.yml": "uses: config\n",
        },
    )
    document = _mapped(tmp_path)
    found, edges = nodes(document), _edges(document)
    assert ("calls", "own.fn::alpha", "own.fn::config") in edges, edges
    end = found["own.fn::config"]
    assert (end["state"], end["locations"]) == ("boundary", []), end
    into = edges[("enters", "own.fn::config", "own.api::settings")]
    assert _rules_of(into) == [("own", "marks")], into
    api = found["own.api::settings"]
    assert (api["type"], api["state"]) == ("own.api", "boundary"), api
