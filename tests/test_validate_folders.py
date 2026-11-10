"""validate gives the folder problems map gives, with the same message and exit code."""

import json
from pathlib import Path

import pytest

from periplus.cli import main

FOLDER_EXIT = 18

RULES = """\
node_types:
- name: t.thing
  id_namespace: t.thing
rules:
- rule: thing
  reads: file
  in: [{in_folder}]
  match: {{file: '**', filetype: txt, text: '(?m)^(?<name>\\w+)'}}
  id: {{template: '{{name}}'}}
  emits: [{{node: {{type: t.thing}}}}]
  confidence: declared
"""

PACK = """\
pack: t
version: 0.1.0
depends: []
folders:
  src: {src}
files:
  types:
    txt:
      endings: [txt]
      reader: text
{path_values}"""

RELATIVE_TO = """\
      path_values:
        base: {relative_to: src, pattern: '^(?<b>.+)\\.txt$', template: '{b}'}
"""


def plant(
    root: Path, *, src: str, in_folder: str, path_values: str = "", settings_src: str | None = None
) -> None:
    pack = root / ".periplus" / "packs" / "t@0.1.0"
    (pack / "rules").mkdir(parents=True)
    (pack / "pack.yaml").write_text(PACK.format(src=src, path_values=path_values))
    (pack / "rules" / "r.yaml").write_text(RULES.format(in_folder=in_folder))
    settings = "periplus_version: 0\npacks:\n  - t@0.1.0\n"
    if settings_src is not None:
        settings += f"folders:\n  src: '{settings_src}'\n"
    (root / ".periplus" / "settings.yml").write_text(settings)
    (root / "src").mkdir()
    (root / "src" / "a.txt").write_text("alpha\n")


def run(root: Path, capsys, monkeypatch, *args: str) -> tuple[int, list[tuple[int, str]]]:
    """Call the entry function in the project and return the exit code and its problems."""
    monkeypatch.chdir(root)
    monkeypatch.setenv("HOME", str(root / "home"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(root / "home"))
    capsys.readouterr()
    code = main([*args, "--format", "json"])
    report = json.loads(capsys.readouterr().out)
    return code, [(p["code"], p["message"]) for p in report["problems"]]


def folder_problems(problems: list[tuple[int, str]]) -> list[tuple[int, str]]:
    return [p for p in problems if p[0] == FOLDER_EXIT]


CASES = {
    "self": dict(src="'{src}/x'", in_folder="src", message="folder src refers back to itself"),
    "leaves": dict(
        src="../out", in_folder="src", message="folder value ../out leaves the project root"
    ),
    "relative": dict(
        src="./src",
        in_folder="src",
        path_values=RELATIVE_TO,
        settings_src="./**",
        message="the folder src, which a path value is relative_to, holds ** in its value",
    ),
}
UNDECLARED = dict(src="./src", in_folder="nope", message="folder nope is not declared")


def both(
    tmp_path: Path, capsys, monkeypatch, case: dict
) -> tuple[tuple[int, list], tuple[int, list]]:
    spec = {k: v for k, v in case.items() if k != "message"}
    plant(tmp_path, **spec)
    return (
        run(tmp_path, capsys, monkeypatch, "validate", "t"),
        run(tmp_path, capsys, monkeypatch, "map"),
    )


def test_validate_gives_map_problem_for_undeclared_folder_wo7(tmp_path, capsys, monkeypatch):
    (v_code, v_problems), (m_code, m_problems) = both(tmp_path, capsys, monkeypatch, UNDECLARED)
    assert m_code == FOLDER_EXIT
    assert folder_problems(m_problems) == [(FOLDER_EXIT, UNDECLARED["message"])]
    assert v_code == m_code
    assert folder_problems(v_problems) == folder_problems(m_problems)


@pytest.mark.parametrize("name", sorted(CASES))
def test_validate_gives_map_problem_for_each_other_folder_fault_wo7(
    tmp_path, capsys, monkeypatch, name
):
    case = CASES[name]
    (v_code, v_problems), (m_code, m_problems) = both(tmp_path, capsys, monkeypatch, case)
    assert folder_problems(m_problems) == [(FOLDER_EXIT, case["message"])]
    assert v_code == m_code == FOLDER_EXIT
    assert folder_problems(v_problems) == folder_problems(m_problems)


@pytest.mark.parametrize("name", ["undeclared", *sorted(CASES)])
def test_map_still_refuses_each_folder_fault_with_its_message_wo7(
    tmp_path, capsys, monkeypatch, name
):
    case = UNDECLARED if name == "undeclared" else CASES[name]
    _, (m_code, m_problems) = both(tmp_path, capsys, monkeypatch, case)
    assert m_code == FOLDER_EXIT
    assert folder_problems(m_problems) == [(FOLDER_EXIT, case["message"])]
