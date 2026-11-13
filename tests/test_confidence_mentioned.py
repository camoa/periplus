"""The confidence ``mentioned``: a rule may declare it, the map keeps it beside a stronger value
on one edge in any rule order, and ``show`` prints it."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from periplus.cli import main
from periplus.errors import ExitCode
from periplus.map import MapReport, run
from periplus.navigate import show
from periplus.preflight import check_runtime_dependencies

PACK = """\
pack: tagger
version: 0.0.1
depends: [php_basic]
folders:
  code: ./**
files:
  extends: php_basic
  add_extensions: [module]
"""

TYPES = """\
node_types:
- {name: tag.task, id_namespace: tag.task}
edge_kinds:
- {kind: runs_task, from: php.function, to: tag.task}
rules:
- rule: task
  reads: file
  in: [code]
  match: {declaration: function_definition, name_child: name, filetype: php}
  id: {from: declared_name, pattern: '^mymod_(?<task>.+)$', template: '{task}'}
  emits: [{node: {type: tag.task}}]
  confidence: declared
"""

EDGE = """\
rules:
- rule: NAME
  reads: file
  in: [code]
  match: {declaration: function_definition, name_child: name, filetype: php}
  emits: [{edge: {kind: runs_task, from: {declared: php.function}, to: {declared: tag.task}}}]
  confidence: CONFIDENCE
"""

SOURCE = "<?php\n\nfunction mymod_cron()\n{\n}\n"


def _map(root: Path, files: dict[str, str]) -> tuple[MapReport, Any]:
    pack = root / ".periplus" / "packs" / "tagger@0.0.1"
    (pack / "rules").mkdir(parents=True)
    (root / ".periplus" / "settings.yml").write_text("periplus_version: 0\npacks: [tagger@0.0.1]\n")
    (pack / "pack.yaml").write_text(PACK)
    (pack / "rules" / "types.yaml").write_text(TYPES)
    for name, text in files.items():
        (pack / "rules" / name).write_text(text)
    (root / "mymod.module").write_text(SOURCE)
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    written = root / "map.json"
    return report, json.loads(written.read_text()) if written.exists() else None


def _rule(name: str, confidence: str) -> str:
    return EDGE.replace("NAME", name).replace("CONFIDENCE", confidence)


def test_a_rule_that_declares_mentioned_writes_it_on_its_edge(tmp_path: Path) -> None:
    report, document = _map(tmp_path, {"edge.yaml": _rule("named", "mentioned")})
    assert report.problems == (), report
    assert [e["provenance"] for e in document["edges"]] == [
        [{"pack": "tagger", "rule": "named", "confidence": "mentioned"}]
    ]


@pytest.mark.parametrize("first", ["declared", "mentioned"])
def test_two_rules_on_one_edge_keep_both_values_whatever_the_file_order(
    tmp_path: Path, first: str
) -> None:
    """The rule in a.yaml reads first; swapping which value it holds leaves the map's bytes
    unchanged, and the declared row is never dropped for the mentioned one."""
    second = "mentioned" if first == "declared" else "declared"
    names = {"declared": "runs", "mentioned": "named"}
    _map(tmp_path / "a", {"a.yaml": _rule(names[first], first), "b.yaml": _rule(names[second], second)})
    _map(tmp_path / "b", {"b.yaml": _rule(names[first], first), "a.yaml": _rule(names[second], second)})
    one = (tmp_path / "a" / "map.json").read_bytes()
    assert one == (tmp_path / "b" / "map.json").read_bytes()
    assert [e["provenance"] for e in json.loads(one)["edges"]] == [
        [
            {"pack": "tagger", "rule": "named", "confidence": "mentioned"},
            {"pack": "tagger", "rule": "runs", "confidence": "declared"},
        ]
    ]


def test_show_lists_both_values_in_text_and_json(tmp_path: Path) -> None:
    _map(tmp_path, {"a.yaml": _rule("named", "mentioned"), "b.yaml": _rule("runs", "declared")})
    report = show.run(tmp_path, {}, "php.function::mymod_cron", 50, tmp_path / "map.json")
    assert report.outgoing.items[0].confidences == ("declared", "mentioned")
    assert "  declared,mentioned" in show.render_text(report)
    schema_path = Path(__file__).parents[1] / "src/periplus/contract/schema/navigation.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator({**schema, "anyOf": [{"$ref": "#/$defs/show"}]})
    printed = json.loads(show.render_json(report))
    assert list(validator.iter_errors(printed)) == [], printed


def test_an_unknown_value_is_refused_naming_the_three_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    report, _ = _map(tmp_path, {"edge.yaml": _rule("named", "compared")})
    assert [p.code for p in report.problems] == [ExitCode.SCHEMA_INVALID], report
    assert report.problems[0].message.endswith(
        "'compared' is not one of ['declared', 'inferred', 'mentioned']"
    ), report.problems
    monkeypatch.chdir(tmp_path)
    capsys.readouterr()
    assert main(["validate", "tagger@0.0.1"]) == ExitCode.SCHEMA_INVALID
    assert "'compared' is not one of ['declared', 'inferred', 'mentioned']" in capsys.readouterr().out
