"""Spans and the enclosing value, the line capture, a path value relative to a folder, and the
skipped rows of a fire that emits nothing and of an edge whose end is not made."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from test_demo_a_support import edges, pin, plant, rutter

from periplus.cli import main
from periplus.engine.packload import _balance
from periplus.engine.pattern import compile_pattern
from periplus.engine.rules import _sections, _spans
from periplus.errors import ExitCode
from periplus.map import MapReport, run
from periplus.preflight import check_runtime_dependencies

MANIFEST = """\
pack: blocks
version: 0.0.1
depends: []
folders:
  src: ./src/**
  base: {base}
files:
  types:
    blk:
      endings: [blk]
      reader: text
      path_values:
        rel: {{pattern: '^(?<p>.+)\\.blk$', template: '{{p}}', relative_to: base}}
      sections:
      - {{name: quote, open: '"', close: '"'}}
      spans:
      - {{name: group, open: 'group(?: (?<prefix>\\w+))?(?=\\s*\\{{)', balance: ['{{', '}}']}}
"""

RULES = """\
node_types:
- {name: blocks.item, id_namespace: blocks.item}
- {name: blocks.file, id_namespace: blocks.file}
edge_kinds:
- {kind: first, from: blocks.item, to: blocks.item}
- {kind: second, from: blocks.item, to: blocks.item}
rules:
- rule: item
  reads: file
  in: [src]
  match: {file: '*', filetype: blk, text: 'item\\s+(?<name>\\w+)'}
  values:
    path: {from: {enclosing: group, capture: prefix}, join: '/'}
  id: {from: {capture: name}}
  line: {capture: name}
  emits: [{node: {type: blocks.item}}, {attribute: {name: path, from: {value: path}}}]
  confidence: declared
- rule: opener
  reads: file
  in: [src]
  match: {file: '*', filetype: blk, text: 'group (?<name>\\w+)'}
  values:
    path: {from: {enclosing: group, capture: prefix, excluding_own: true}, join: '/'}
  id: {template: 'g-{name}'}
  line: {capture: name}
  emits: [{node: {type: blocks.item}}, {attribute: {name: path, from: {value: path}}}]
  confidence: declared
- rule: whole
  reads: file
  in: [src]
  match: {file: '*', filetype: blk, text: '\\A'}
  id: {template: '{rel}'}
  emits: [{node: {type: blocks.file}}]
  confidence: declared
- rule: link
  reads: file
  in: [src]
  match: {file: '*', filetype: blk, text: 'link (?<a>\\w+) (?<b>\\w*);'}
  id: {from: {capture: a}}
  emits:
  - edge: {kind: first, from: this_node, to: {from: {capture: a}}}
  - edge: {kind: second, from: this_node, to: {from: {capture: b}}}
  confidence: declared
- rule: empty
  reads: file
  in: [src]
  match: {file: '*', filetype: blk, text: 'none (?<a>\\w+) (?<b>\\w*);'}
  id: {from: {capture: a}}
  emits:
  - edge: {kind: second, from: this_node, to: {from: {capture: b}}}
  confidence: declared
"""

TEXT = """\
group a {
  item one
  "}" item two
  group b {
    item three
  }
  group {
    item four
  }
}
item
  five
link x y;
link x ;
none z ;
"""


def _map(root: Path) -> tuple[MapReport, dict[str, Any]]:
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    document = json.loads((root / "map.json").read_text()) if report.map_path else {}
    return report, document


def _site(root: Path, base: str = "./src/base", rules: str = RULES) -> Path:
    pack = root / ".periplus" / "packs" / "blocks@0.0.1"
    (pack / "rules").mkdir(parents=True)
    (root / ".periplus" / "settings.yml").write_text("periplus_version: 0\npacks: [blocks@0.0.1]\n")
    (pack / "pack.yaml").write_text(MANIFEST.format(base=base))
    (pack / "rules" / "blocks.yaml").write_text(rules)
    (root / "src" / "base" / "deep").mkdir(parents=True)
    (root / "src" / "one.blk").write_text(TEXT)
    (root / "src" / "base" / "deep" / "two.blk").write_text("")
    return root


def test_an_enclosing_value_joins_each_holding_span_outermost_first(tmp_path: Path) -> None:
    """The quoted brace is skipped, a nested span adds its capture after its holder's, a span with
    no capture adds nothing, and a match no span holds gives the empty value."""
    report, document = _map(_site(tmp_path))
    assert report.problems == () and report.not_executed == (), report
    items = {
        n["id"]: (n["attributes"]["path"], n["locations"][0]["line"])
        for n in document["nodes"]
        if n["type"] == "blocks.item" and "path" in n.get("attributes", {})
    }
    assert items == {
        "blocks.item::one": ("a", 2),
        "blocks.item::two": ("a", 3),
        "blocks.item::three": ("a/b", 5),
        "blocks.item::four": ("a", 8),
        "blocks.item::five": ("", 12),
        "blocks.item::g-a": ("", 1),
        "blocks.item::g-b": ("a", 4),
    }, items


def test_a_match_at_a_spans_own_opening_is_held_by_the_spans_around_it_only(tmp_path: Path) -> None:
    """The rule that matches the opening of a group starts where the span starts; with
    excluding_own that span is left out: `group a` has no prefix and `group b` has `a`."""
    _, document = _map(_site(tmp_path))
    openers = {
        n["id"]: n["attributes"]["path"]
        for n in document["nodes"]
        if n["id"].startswith("blocks.item::g-")
    }
    assert openers == {"blocks.item::g-a": "", "blocks.item::g-b": "a"}, openers


def test_a_relative_path_value_strips_the_folder_and_is_absent_outside_it(tmp_path: Path) -> None:
    _, document = _map(_site(tmp_path))
    files = sorted(n["id"] for n in document["nodes"] if n["type"] == "blocks.file")
    assert files == ["blocks.file::deep/two"], files


def test_a_relative_to_folder_holding_a_double_star_is_refused(tmp_path: Path) -> None:
    report, _ = _map(_site(tmp_path, base="'./src/**'"))
    assert report.map_path is None
    assert [p.code for p in report.problems] == [ExitCode.PACK_RULES_UNREADABLE], report
    message = report.problems[0].message
    assert "path_values.rel.relative_to" in message and "folder base" in message, message


def test_a_text_edge_with_an_empty_end_leaves_a_row_and_the_other_edge_emits(
    tmp_path: Path,
) -> None:
    report, document = _map(_site(tmp_path))
    rows = {(line, rule, reason) for _, line, rule, reason in report.skipped}
    assert rows == {
        (14, "link", "edge second: no value for capture b"),
        (15, "empty", "edge second: no value for capture b"),
    }, rows
    edges = {(e["kind"], e["from"], e["to"]) for e in document["edges"]}
    assert ("first", "blocks.item::x", "blocks.item::x") in edges, edges
    assert ("second", "blocks.item::x", "blocks.item::y") in edges, edges


PHP_RULES = """\
node_types:
- {name: probe.fn, id_namespace: probe.fn}
- {name: probe.cls, id_namespace: probe.cls}
edge_kinds:
- {kind: inside, from: probe.fn, to: probe.cls}
- {kind: self, from: probe.fn, to: probe.fn}
- {kind: calls_any, from: probe.fn, to: probe.fn}
- {kind: calls_bound, from: probe.fn, to: probe.fn}
rules:
- rule: cls
  reads: file
  in: [code]
  match: {declaration: class_declaration, name_child: name, body_child: body, filetype: php}
  id: {from: qualified_name}
  emits: [{node: {type: probe.cls}}]
  confidence: declared
- rule: fn
  reads: file
  in: [code]
  match: {declaration: function_definition, name_child: name, filetype: php}
  id: {from: qualified_name}
  emits: [{node: {type: probe.fn}}]
  confidence: declared
- rule: fn_edges
  reads: file
  in: [code]
  match: {declaration: function_definition, name_child: name, filetype: php}
  id: {from: qualified_name}
  emits:
  - edge: {kind: inside, from: this_node, to: enclosing_class}
  - edge: {kind: self, from: this_node, to: this_node}
  confidence: declared
- rule: fn_inside
  reads: file
  in: [code]
  match: {declaration: function_definition, name_child: name, filetype: php}
  id: {from: [namespace, declared_name], template: '{namespace}\\{declared_name}'}
  emits:
  - edge: {kind: inside, from: this_node, to: enclosing_class}
  confidence: declared
- rule: call
  reads: file
  in: [code]
  match: {reference: function_call_expression, name_child: function, filetype: php}
  emits:
  - edge:
      kind: calls_any
      from: enclosing_declaration
      to: {types: [probe.fn], on_miss: unresolved}
  - edge:
      kind: calls_bound
      from: enclosing_declaration
      to: {types: [probe.fn], resolve: [bound_first_segment], on_miss: unresolved}
  confidence: declared
"""


def test_a_declaration_and_a_reference_rule_list_the_end_they_cannot_make(tmp_path: Path) -> None:
    """A top-level function has no enclosing class: the edge to it leaves a row and the edge to the
    function itself emits; with that edge alone the fire emits nothing. A call no import binds
    leaves a row for the edge that needs a binding, and the other edge emits."""
    pack = tmp_path / ".periplus" / "packs" / "probe@0.0.1"
    (pack / "rules").mkdir(parents=True)
    (tmp_path / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks: [php_basic@0.2.0, probe@0.0.1]\n"
    )
    (pack / "pack.yaml").write_text(
        "pack: probe\nversion: 0.0.1\ndepends: [php_basic]\nfolders:\n  code: ./src\n"
    )
    (pack / "rules" / "probe.yaml").write_text(PHP_RULES)
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.php").write_text(
        "<?php\nnamespace App;\n\nfunction run()\n{\n    helper();\n}\n\nfunction helper()\n{\n}\n"
    )
    report, document = _map(tmp_path)
    assert report.problems == (), report
    rows = {(line, rule, reason) for _, line, rule, reason in report.skipped if rule != "fn"}
    assert rows == {
        (4, "fn_edges", "edge inside: no value for enclosing_class"),
        (9, "fn_edges", "edge inside: no value for enclosing_class"),
        (4, "fn_inside", "edge inside: no value for enclosing_class"),
        (9, "fn_inside", "edge inside: no value for enclosing_class"),
        (6, "call", "edge calls_bound: no resolution step holds for function"),
    }, rows
    edges = {(e["kind"], e["from"], e["to"]) for e in document["edges"]}
    assert ("self", "probe.fn::App\\run", "probe.fn::App\\run") in edges, edges
    assert ("calls_any", "probe.fn::App\\run", "probe.fn::App\\helper") in edges, edges
    assert not [e for e in edges if e[0] in ("inside", "calls_bound")], edges


def test_a_data_rule_is_silent_on_an_absent_key_and_lists_a_fire_that_made_nothing(
    tmp_path: Path,
) -> None:
    """An entry without the optional keys states no edge and leaves no row; an entry whose key
    holds a value that the edge's where filters out made nothing, and leaves one row."""
    pack = tmp_path / ".periplus" / "packs" / "cfgs@0.0.1"
    (pack / "rules").mkdir(parents=True)
    (tmp_path / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks: [cfgs@0.0.1]\n"
    )
    (pack / "pack.yaml").write_text(
        "pack: cfgs\nversion: 0.0.1\ndepends: []\nfolders:\n  src: ./src\nfiles:\n  types:\n"
        "    cfg: {endings: [cfg], reader: data, format: yaml}\n"
    )
    (pack / "rules" / "cfgs.yaml").write_text(
        """\
node_types:
- {name: cfgs.entry, id_namespace: cfgs.entry}
edge_kinds:
- {kind: needs, from: cfgs.entry, to: cfgs.entry}
- {kind: wants, from: cfgs.entry, to: cfgs.entry}
rules:
- rule: deps
  reads: file
  in: [src]
  match: {file: '*', filetype: cfg, each: '*'}
  id: {from: key}
  emits:
  - edge: {kind: needs, from: this_node, to: {from: {key: needs}}}
  - edge: {kind: wants, from: this_node, to: {from: {key: wants}, where: [{matches: 'x*'}]}}
  confidence: declared
"""
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.cfg").write_text("a:\n  needs: b\nb: {}\nc:\n  wants: y\n")
    report, document = _map(tmp_path)
    assert report.problems == () and report.not_executed == (), report
    assert report.skipped == (("src/a.cfg", 4, "deps", "fired and emitted nothing"),), report
    edges = {(e["kind"], e["from"], e["to"]) for e in document["edges"]}
    assert edges == {("needs", "cfgs.entry::a", "cfgs.entry::b")}, edges


def test_a_data_edge_with_no_where_lists_a_value_that_is_not_text(tmp_path: Path) -> None:
    """An entry whose needs holds a mapping gives no needs edge and one row for it; its wants edge
    still emits."""
    pack = tmp_path / ".periplus" / "packs" / "cfgs@0.0.1"
    (pack / "rules").mkdir(parents=True)
    (tmp_path / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks: [cfgs@0.0.1]\n"
    )
    (pack / "pack.yaml").write_text(
        "pack: cfgs\nversion: 0.0.1\ndepends: []\nfolders:\n  src: ./src\nfiles:\n  types:\n"
        "    cfg: {endings: [cfg], reader: data, format: yaml}\n"
    )
    (pack / "rules" / "cfgs.yaml").write_text(
        """\
node_types:
- {name: cfgs.entry, id_namespace: cfgs.entry}
edge_kinds:
- {kind: needs, from: cfgs.entry, to: cfgs.entry}
- {kind: wants, from: cfgs.entry, to: cfgs.entry}
rules:
- rule: deps
  reads: file
  in: [src]
  match: {file: '*', filetype: cfg, each: '*'}
  id: {from: key}
  emits:
  - edge: {kind: needs, from: this_node, to: {from: {key: needs}}}
  - edge: {kind: wants, from: this_node, to: {from: {key: wants}}}
  confidence: declared
"""
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.cfg").write_text("a: {needs: {x: 1}, wants: b}\nb: {}\n")
    report, document = _map(tmp_path)
    assert report.problems == () and report.not_executed == (), report
    row = ("src/a.cfg", 1, "deps", "edge needs: no value for key needs")
    assert report.skipped == (row,), report
    edges = {(e["kind"], e["from"], e["to"]) for e in document["edges"]}
    assert edges == {("wants", "cfgs.entry::a", "cfgs.entry::b")}, edges


def test_a_declaration_with_no_written_name_then_an_absent_id_source_still_maps(
    tmp_path: Path,
) -> None:
    """A closure has no written-name child, so its edge to a written name is silent; the next
    closure lacks the return type its id names, and leaves that row."""
    pack = tmp_path / ".periplus" / "packs" / "probe@0.0.1"
    (pack / "rules").mkdir(parents=True)
    (tmp_path / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks: [php_basic@0.2.0, probe@0.0.1]\n"
    )
    (pack / "pack.yaml").write_text(
        "pack: probe\nversion: 0.0.1\ndepends: [php_basic]\nfolders:\n  code: ./src\n"
    )
    (pack / "rules" / "probe.yaml").write_text(
        """\
node_types:
- {name: probe.fn, id_namespace: probe.fn}
edge_kinds:
- {kind: names, from: probe.fn, to: probe.fn}
rules:
- rule: closure
  reads: file
  in: [code]
  match: {declaration: anonymous_function, filetype: php}
  id: {from: return_type}
  emits:
  - edge: {kind: names, from: this_node, to: {from: qualified_name}}
  confidence: declared
"""
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.php").write_text(
        "<?php\n$a = function (): int { return 1; };\n$b = function () { return 2; };\n"
    )
    report, _ = _map(tmp_path)
    assert report.problems == () and report.map_path is not None, report
    rows = {(line, rule, reason) for _, line, rule, reason in report.skipped}
    assert rows == {(3, "closure", "the id source return_type is absent")}, rows


TAGS_MANIFEST = """\
pack: tags
version: 0.0.1
depends: []
folders:
  src: ./src
files:
  types:
    tpl:
      endings: [tpl]
      reader: text
      sections:
      - {name: comment, open: '<!--', close: '-->'}
      spans:
      - {name: fn, open: '(?=<fn\\s+name="(?<name>\\w+)")', balance: ['<fn\\b', '</fn>']}
"""

TAGS_RULES = """\
node_types:
- {name: tags.fn, id_namespace: tags.fn}
- {name: tags.query, id_namespace: tags.query}
edge_kinds:
- {kind: runs, from: tags.fn, to: tags.query}
rules:
- rule: query
  reads: file
  in: [src]
  match: {file: '*', filetype: tpl, text: '<query\\s+name="(?<query>\\w+)"'}
  values:
    owner:
      from: {enclosing: fn, capture: name}
      join: '|'
      normalize: [{replace: '^.*\\|', with: ''}]
  id: {template: '{owner}'}
  emits: [{edge: {kind: runs, from: this_node, to: {from: {capture: query}}}}]
  confidence: declared
"""

TAGS_TEXT = """\
<fn name="outer" access="public">
  <query name="first">
  <!-- </fn> <query name="hidden"> -->
  <fn name="inner">
    <query name="second">
  </fn>
  <query name="third">
</fn>
<query name="outside">
"""


def _tags_map(
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    manifest: str = TAGS_MANIFEST,
    text: str = TAGS_TEXT,
    rules: str = TAGS_RULES,
) -> tuple[int, dict[str, Any]]:
    """Plant the tag pack and its file, run ``periplus map`` once, and give the exit code and
    the written map ({} when none)."""
    monkeypatch.chdir(root)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(root / "_config"))
    rutter(root, "tags", manifest, {"tags.yaml": rules})
    pin(root, "tags@0.0.1")
    plant(root, {"src/page.tpl": text})
    code = main(["map", "--output", str(root / "out.json")])
    out = root / "out.json"
    return code, json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}


def test_a_span_balancing_tag_patterns_holds_a_match_inside_a_nested_tag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A query takes the name of the innermost fn tag around it: an fn inside an fn opens one
    more and its own close ends it, so the outer fn's close ends the outer span."""
    code, document = _tags_map(tmp_path, monkeypatch)
    assert code == 0, code
    assert edges(document, "runs") == {
        ("runs", "tags.fn::outer", "tags.query::first"),
        ("runs", "tags.fn::inner", "tags.query::second"),
        ("runs", "tags.fn::outer", "tags.query::third"),
    }, edges(document)


def test_a_comment_inside_a_tag_balanced_span_stays_a_section(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The body of an fn is no section, so the comment section holds inside it: the commented
    query makes no edge and the commented close tag does not end the span."""
    code, document = _tags_map(tmp_path, monkeypatch)
    assert code == 0, code
    runs = edges(document, "runs")
    assert ("runs", "tags.fn::outer", "tags.query::first") in runs, runs
    assert ("runs", "tags.fn::outer", "tags.query::third") in runs, runs
    assert not [e for e in runs if e[2] == "tags.query::hidden"], runs


def test_a_balance_entry_of_one_character_matches_that_character(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A one-character entry is the character itself, never a pattern: ``(`` and ``)`` balance
    parentheses, and a parenthesis inside the comment section does not count."""
    manifest = TAGS_MANIFEST.replace(
        """open: '(?=<fn\\s+name="(?<name>\\w+)")', balance: ['<fn\\b', '</fn>']""",
        """open: 'fn (?<name>\\w+)(?=\\()', balance: ['(', ')']""",
    )
    text = 'fn outer(<query name="first"> <!-- ) --> (fn inner(<query name="second">))\n'
    text += '<query name="third">) <query name="outside">\n'
    code, document = _tags_map(tmp_path, monkeypatch, manifest, text)
    assert code == 0, code
    assert edges(document, "runs") == {
        ("runs", "tags.fn::outer", "tags.query::first"),
        ("runs", "tags.fn::inner", "tags.query::second"),
        ("runs", "tags.fn::outer", "tags.query::third"),
    }, edges(document)


def _spans_of(
    text: str, opening: str, balance: list[str], comment: bool = False
) -> list[tuple[int, int]]:
    """The start and end of each span of the text, the balance read as a manifest reads it, with
    a ``<!--``/``-->`` comment section when ``comment`` is set."""
    declared = [("comment", compile_pattern("<!--"), "-->")] if comment else []
    up, down = _balance(balance)
    sections = _sections(text, declared)
    spans = _spans(text, [("x", compile_pattern(opening), up, down)], sections)
    return [(begin, end) for _, begin, end, _ in spans]


def test_a_balance_entry_whose_pattern_matches_the_empty_text_is_refused_by_validate_and_map(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """``/*`` is the pattern "zero or more slashes", not a comment opening: it matches nothing at
    every offset, so validate and map both refuse the pack and name the entry."""
    manifest = TAGS_MANIFEST.replace("['<fn\\b', '</fn>']", "['/*', '\\*/']")
    code, document = _tags_map(tmp_path, monkeypatch, manifest)
    assert code == ExitCode.PACK_RULES_UNREADABLE and document == {}, code
    mapped = capsys.readouterr()
    assert main(["validate", "tags"]) == ExitCode.PACK_RULES_UNREADABLE
    validated = capsys.readouterr()
    for out in (mapped, validated):
        assert "the balance entry /* matches the empty text" in out.out + out.err, out


def test_a_zero_width_token_at_the_end_of_the_text_ends_the_count(tmp_path: Path) -> None:
    r"""``\b`` matches no empty text, so it loads, but it matches at the end of ``f a``. The count
    stops there and the map finishes; before, the search found that match again forever."""
    root = tmp_path.resolve()
    manifest = TAGS_MANIFEST.replace("['<fn\\b', '</fn>']", "['\\b', '\\)']").replace(
        """'(?=<fn\\s+name="(?<name>\\w+)")'""", "'(?<name>f)'"
    )
    rutter(root, "tags", manifest, {"tags.yaml": TAGS_RULES})
    pin(root, "tags@0.0.1")
    plant(root, {"src/page.tpl": "f a"})
    child = "import sys; from periplus.cli import main; sys.exit(main(['map']))"
    result = subprocess.run(  # noqa: S603 - list argv, shell unset, nothing interpolated
        [sys.executable, "-c", child],
        cwd=root,
        env={**os.environ, "PERIPLUS_CONFIG_DIR": str(root / "_config")},
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_a_token_skipped_inside_a_section_does_not_swallow_a_token_after_the_section() -> None:
    """The ``<fn`` inside the comment runs past ``-->`` up to ``/``; the search resumes at the
    end of the comment, so the first ``</fn>`` after it closes the span."""
    text = "S <!-- <fn --> </fn> </fn>"
    assert _spans_of(text, "S", ["<fn\\b[^/]*/?", "</fn>"], comment=True) == [(0, 20)]


def test_a_token_that_starts_outside_a_section_counts_though_it_runs_into_one() -> None:
    """The closing ``</fn`` starts before the comment, so it counts, and its match runs on into
    the comment up to the last ``>``."""
    text = "<fn a> </fn<!-- x -->"
    assert _spans_of(text, "(?=<fn)", ["<fn\\b", "</fn[^>]*"], comment=True) == [(0, 20)]


def test_an_opening_and_a_closing_token_that_start_together_count_as_the_opening() -> None:
    """``<`` and ``</`` both start at each ``</x>``; the opening counts there, so this pair never
    closes and the span runs to the end of the text."""
    text = "f <x> </x> </x>"
    assert _spans_of(text, "f", ["<", "</"]) == [(0, len(text))]


def test_a_zero_width_token_counts_once_and_the_search_moves_past_it() -> None:
    """A lookahead opening matches before each ``<fn`` without taking it: each tag counts once."""
    text = "<fn a><fn b></fn></fn> tail"
    assert _spans_of(text, "(?=<fn a)", ["(?=<fn)", "</fn>"]) == [(0, 22)]


def test_tokens_do_not_overlap() -> None:
    """``<fn>`` is one opening ``<f``; the closing ``fn>`` inside it does not count, since the
    search resumes after the opening. The span ends at the closing ``fn>`` that stands alone."""
    text = "S <fn> fn> tail"
    assert _spans_of(text, "S", ["<f", "f\\w*>"]) == [(0, 10)]


def test_an_unclosed_tag_span_ends_at_the_end_of_the_text() -> None:
    text = "<fn a> body"
    assert _spans_of(text, "(?=<fn)", ["<fn\\b", "</fn>"]) == [(0, len(text))]


def test_an_open_that_takes_its_own_opening_token_ends_at_the_first_inner_close() -> None:
    """The open takes ``<fn a``, so the count starts one short: the inner ``</fn>`` ends it."""
    text = "<fn a><fn b></fn>X</fn>"
    assert _spans_of(text, "<fn\\s+a", ["<fn\\b", "</fn>"]) == [(0, 17)]


def test_the_guides_tag_example_balances_nested_tags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The guide's tag example, read from the page, maps the nested fn tags as the guide says."""
    guide = (Path(__file__).parents[1] / "docs" / "rutter-author-guide-text.md").read_text()
    found = re.search(r"tag language balances its tags:\n\n```yaml\n(.*?)```", guide, re.S)
    assert found is not None
    head, _, _ = TAGS_MANIFEST.partition("      sections:\n")
    manifest = head + "".join(f"      {line}\n" for line in found[1].splitlines())
    rules = TAGS_RULES.replace("enclosing: fn,", "enclosing: function,")
    code, document = _tags_map(tmp_path, monkeypatch, manifest, rules=rules)
    assert code == 0, code
    assert edges(document, "runs") == {
        ("runs", "tags.fn::outer", "tags.query::first"),
        ("runs", "tags.fn::inner", "tags.query::second"),
        ("runs", "tags.fn::outer", "tags.query::third"),
    }, edges(document)
