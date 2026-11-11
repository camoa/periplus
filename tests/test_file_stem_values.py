"""A text rule names ``{file_stem}`` as other file rules do, and a whole-file rule takes values."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_demo_a_support import plant, rutter

from periplus.cli import main

MANIFEST = """\
pack: stem
version: 0.0.1
depends: []
values:
  app: The application's prefix.
folders:
  src: ./src/**
files:
  types:
    code:
      endings: [sx]
      reader: text
      path_values:
        area: {pattern: '^src/(?<area>\\w+)/', template: '{area}'}
"""

TYPES = """\
node_types:
- {name: stem.item, id_namespace: stem.item}
- {name: stem.file, id_namespace: stem.file}
rules:
"""

TEXT_RULE = """\
- rule: item
  reads: file
  in: [src]
  match: {file: '*', filetype: code, text: '(?m)^item (?<name>\\w+)$'}
  values:
    owner: {template: '{file_stem}', case: upper}
  id: {template: '{file_stem}.{name}'}
  emits:
  - node: {type: stem.item}
  - attribute: {name: owner, from: {value: owner}}
  confidence: declared
"""

WHOLE_FILE_RULE = """\
- rule: whole
  reads: file
  in: [src]
  match: {file: '*', filetype: code}
  values:
    module:
      template: '{app}/{area}/{file_stem}'
      normalize: [{replace: '/', with: '.'}]
      case: upper
  id: {template: '{module}'}
  emits: [{node: {type: stem.file}}]
  confidence: declared
"""


@pytest.fixture(autouse=True)
def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "_config"))


def _map(root: Path, capsys: pytest.CaptureFixture[str], rule: str) -> dict[str, dict]:
    rutter(root, "stem", MANIFEST, {"stem.yaml": TYPES + rule})
    plant(
        root,
        {
            ".periplus/settings.yml": (
                "periplus_version: 0\npacks:\n  - stem@0.0.1\nvalues:\n  app: shop\n"
            ),
            "src/lib/one.sx": "item alpha\n",
        },
    )
    capsys.readouterr()
    status = main(["map", "--format", "json", "--output", str(root / "out.json")])
    report = json.loads(capsys.readouterr().out)
    problems = report["problems"]
    assert (status, problems, report["not_executed"]) == (0, [], []), (problems, report)
    document = json.loads((root / "out.json").read_text(encoding="utf-8"))
    return {node["id"]: node for node in document["nodes"]}


def test_a_text_rule_names_file_stem_in_its_id_and_its_values(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    nodes = _map(tmp_path, capsys, TEXT_RULE)

    assert nodes["stem.item::one.alpha"]["attributes"] == {"owner": "ONE"}


def test_a_whole_file_rule_fills_its_values_from_path_settings_and_file_stem(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    nodes = _map(tmp_path, capsys, WHOLE_FILE_RULE)

    assert [n for n in nodes if n.startswith("stem.file::")] == ["stem.file::SHOP.LIB.ONE"]


@pytest.mark.parametrize("name", ["file_stem", "key"])
def test_a_whole_file_rule_value_named_as_an_engine_given_name_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str
) -> None:
    rule = WHOLE_FILE_RULE.replace("module:", f"{name}:").replace("'{module}'", f"'{{{name}}}'")
    rutter(tmp_path, "stem", MANIFEST, {"stem.yaml": TYPES + rule})
    plant(
        tmp_path,
        {
            ".periplus/settings.yml": (
                "periplus_version: 0\npacks:\n  - stem@0.0.1\nvalues:\n  app: shop\n"
            ),
            "src/lib/one.sx": "item alpha\n",
        },
    )
    capsys.readouterr()
    status = main(["map", "--format", "json", "--output", str(tmp_path / "out.json")])
    problems = json.loads(capsys.readouterr().out)["problems"]

    assert status == 26
    assert [p["message"] for p in problems] == [
        f"stem/rules/stem.yaml: the rule whole cannot be executed: the value {name} of a file rule "
        "has a name the engine gives"
    ]
