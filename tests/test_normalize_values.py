"""A ``{name}`` in a normalize step's ``replace`` pattern is a path or settings value, filled as
literal text; one naming no such value is refused when the pack loads; a quantifier stays one."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_demo_a_support import plant, rutter

from periplus.cli import main

RULE_NOT_EXECUTABLE = 26

MANIFEST = """\
pack: site
version: 0.0.1
depends: []
values:
  app_prefix: The prefix of the application's own names.
folders:
  src: ./src
files:
  types:
    code:
      endings: [sx]
      reader: text
"""

RULES = """\
node_types:
- {name: site.thing, id_namespace: site.thing}
rules:
- rule: thing_line
  reads: file
  in: [src]
  match: {file: '*', filetype: code, text: '(?m)^use (?<name>[\\w.]+)$'}
  id: {from: {capture: name}, normalize: [{replace: 'REPLACE', with: ''}]}
  emits: [{node: {type: site.thing}}]
  confidence: declared
"""


def _plant(root: Path, replace: str, prefix: str, used: str) -> None:
    rutter(root, "site", MANIFEST, {"site.yaml": RULES.replace("REPLACE", replace)})
    plant(
        root,
        {
            ".periplus/settings.yml": (
                f"periplus_version: 0\npacks:\n  - site@0.0.1\nvalues:\n  app_prefix: '{prefix}'\n"
            ),
            "src/one.sx": f"use {used}\n",
        },
    )


def _call(args: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, dict]:
    capsys.readouterr()
    status = main([*args, "--format", "json"])
    return status, json.loads(capsys.readouterr().out)


def _ids(root: Path, capsys: pytest.CaptureFixture[str]) -> list[str]:
    status, report = _call(["map", "--output", str(root / "out.json")], capsys)
    assert (status, report["problems"]) == (0, [])
    document = json.loads((root / "out.json").read_text(encoding="utf-8"))
    return [node["id"] for node in document["nodes"]]


@pytest.fixture(autouse=True)
def _project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "_config"))


@pytest.mark.parametrize(
    ("prefix", "used", "expected"),
    [
        ("shop", "shop.cart.Basket", "site.thing::cart.Basket"),
        # Unescaped, the dot of s.op would let sxop fit.
        ("s.op", "sxop.cart.Basket", "site.thing::sxop.cart.Basket"),
    ],
)
def test_a_settings_value_in_a_replace_pattern_is_filled_as_literal_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], prefix: str, used: str, expected: str
) -> None:
    _plant(tmp_path, "^{app_prefix}\\.", prefix, used)

    assert _ids(tmp_path, capsys) == [expected]


def test_a_replace_pattern_naming_no_value_is_refused_by_validate_and_map(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _plant(tmp_path, "^{nowhere}\\.", "shop", "shop.cart.Basket")

    map_status, mapped = _call(["map", "--output", str(tmp_path / "out.json")], capsys)
    status, validated = _call(["validate", "site"], capsys)

    problems = [(p["code"], p["message"]) for p in mapped["problems"]]
    assert map_status == RULE_NOT_EXECUTABLE
    assert [code for code, _ in problems] == [RULE_NOT_EXECUTABLE]
    assert "nowhere" in problems[0][1]
    assert (status, [(p["code"], p["message"]) for p in validated["problems"]]) == (
        map_status,
        problems,
    )


def test_a_quantifier_in_a_replace_pattern_stays_a_quantifier(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _plant(tmp_path, "^\\w{2}\\.", "shop", "ab.cart.Basket")

    assert _ids(tmp_path, capsys) == ["site.thing::cart.Basket"]
