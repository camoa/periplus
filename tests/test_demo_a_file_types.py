"""File types: the ending that wins, a data type's format, and how two rutters claim an ending."""

from __future__ import annotations

from pathlib import Path

import pytest
from ruamel.yaml import YAML
from test_demo_a_support import map_project, mapped, nodes, pin, plant, rutter

from periplus.cli import main
from periplus.errors import ExitCode

KINDS = """\
pack: kinds
version: 0.0.1
depends: []
folders:
  src: ./src
files:
  types:
    page:
      endings: [.html.twig]
      reader: text
    piece:
      endings: [twig]
      reader: text
    build:
      names: [Makefile]
      reader: text
"""

KINDS_RULES = """\
node_types:
- {name: kinds.page, id_namespace: kinds.page}
- {name: kinds.piece, id_namespace: kinds.piece}
- {name: kinds.build, id_namespace: kinds.build}
rules:
- {rule: page_file, reads: file, in: [src], match: {file: '*', filetype: page},
   id: {from: file_stem}, emits: [{node: {type: kinds.page}}], confidence: declared}
- {rule: piece_file, reads: file, in: [src], match: {file: '*', filetype: piece},
   id: {from: file_stem}, emits: [{node: {type: kinds.piece}}], confidence: declared}
- {rule: build_file, reads: file, in: [src], match: {file: '*', filetype: build},
   id: {from: file_stem}, emits: [{node: {type: kinds.build}}], confidence: declared}
"""


def test_the_longest_ending_wins_and_a_type_declared_by_whole_name_selects_that_file(
    tmp_path: Path,
) -> None:
    rutter(tmp_path, "kinds", KINDS, {"kinds.yaml": KINDS_RULES})
    pin(tmp_path, "kinds@0.0.1")
    plant(
        tmp_path,
        {
            "src/a.html.twig": "<p>a</p>\n",
            "src/b.twig": "<p>b</p>\n",
            "src/Makefile": "all:\n\ttrue\n",
            "src/c.txt": "not claimed\n",
        },
    )
    assert {(n["type"], n["id"]) for n in mapped(tmp_path)["nodes"]} == {
        ("kinds.page", "kinds.page::a"),
        ("kinds.piece", "kinds.piece::b"),
        ("kinds.build", "kinds.build::Makefile"),
    }


def test_a_rule_file_whose_applies_to_names_any_tree_node_passes_validate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rutter(
        tmp_path,
        "anynode",
        "pack: anynode\nversion: 0.0.1\ndepends: []\nfolders:\n  src: ./src\n",
        {
            "tagged.yaml": """\
node_types:
- {name: anynode.tagged, id_namespace: anynode.tagged}
rules:
- rule: tagged_item
  reads: file
  in: [src]
  match:
    attribute: Tagged
    filetype: src
    where:
    - applies_to: struct_item
  id:
    from: {attribute_argument: name}
  emits: [{node: {type: anynode.tagged}}]
  confidence: declared
"""
        },
    )
    pin(tmp_path, "anynode@0.0.1")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "_config"))
    assert main(["validate", "anynode"]) == 0


def test_a_short_list_sharing_a_bundled_ending_loads_and_a_text_type_holds_non_yaml(
    tmp_path: Path,
) -> None:
    rutter(
        tmp_path,
        "extra",
        """\
pack: extra
version: 0.0.1
depends: [yaml_basic]
folders:
  data: ./data
files:
  extensions: [yml]
  types:
    piece:
      endings: [twig]
      reader: text
""",
        {
            "extra.yaml": """\
node_types:
- {name: extra.note, id_namespace: extra.note}
- {name: extra.block, id_namespace: extra.block}
rules:
- {rule: note_file, reads: file, in: [data], match: {file: '*', filetype: yml},
   id: {from: file_stem}, emits: [{node: {type: extra.note}}], confidence: declared}
- rule: block
  reads: file
  in: [data]
  match: {file: '*', filetype: piece, text: '\\{% block (?<name>\\w+) %\\}'}
  id: {from: {capture: name}}
  emits: [{node: {type: extra.block}}]
  confidence: declared
"""
        },
    )
    pin(tmp_path, "extra@0.0.1")
    torn = "{% block main %}: [\n"
    plant(tmp_path, {"data/a.yml": "name: a\n", "data/b.twig": torn})
    # The planted file is not YAML, so mapping it proves the text reader read it.
    with pytest.raises(Exception):  # noqa: B017 - any parse error proves the point
        YAML(typ="safe", pure=True).load(torn)
    assert {(n["type"], n["id"]) for n in mapped(tmp_path)["nodes"]} == {
        ("extra.note", "extra.note::a"),
        ("extra.block", "extra.block::main"),
    }


CRATE = """\
pack: crate
version: 0.0.1
depends: []
folders:
  hold: ./hold
files:
{files}
"""

CRATE_RULES = """\
node_types:
- {name: crate.item, id_namespace: crate.item}
rules:
- rule: item
  reads: file
  in: [hold]
  match: {file: '*', filetype: box, each: 'items.*'}
  id: {template: '{key}'}
  emits: [{node: {type: crate.item}}]
  confidence: declared
"""

SHORT_BOX = "  extensions: [box]"
YAML_BOX = "  types:\n    box:\n      endings: [box]\n      reader: data\n      format: yaml"


def _crate(root: Path, files: str) -> None:
    rutter(root, "crate", CRATE.format(files=files), {"crate.yaml": CRATE_RULES})
    pin(root, "crate@0.0.1")
    plant(
        root,
        {
            "hold/tools.box": "items:\n  hammer: 1\n  saw: 2\n",
            "hold/ties.box": "items:\n  rope: 3\n",
        },
    )


def test_a_box_type_declared_with_format_yaml_gives_the_map_the_short_form_gives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _crate(tmp_path, SHORT_BOX)
    short = mapped(tmp_path)
    _crate(tmp_path, YAML_BOX)
    declared = mapped(tmp_path)
    assert declared == short
    assert sorted(nodes(declared)) == ["crate.item::hammer", "crate.item::rope", "crate.item::saw"]
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "_config"))
    assert main(["validate", "crate"]) == 0


def test_a_format_the_engine_has_no_reader_for_is_a_pack_problem_before_any_file_is_read(
    tmp_path: Path,
) -> None:
    _crate(tmp_path, YAML_BOX.replace("yaml", "inkblot"))
    # Not YAML: reading it would end the run with another code.
    plant(tmp_path, {"hold/torn.box": "items: [unclosed\n"})
    report, _ = map_project(tmp_path)
    assert report.map_path is None and not (tmp_path / "map.json").exists()
    assert report.problems and {p.code for p in report.problems} == {ExitCode.PACK_RULES_UNREADABLE}
    named = [m for m in (p.message for p in report.problems) if "inkblot" in m]
    assert named and "crate/" in named[0] and "box" in named[0], report.problems


@pytest.mark.parametrize(
    "box",
    [
        "    box:\n      endings: [box]\n      reader: data",
        "    box:\n      endings: [box]\n      reader: text\n      format: yaml",
    ],
    ids=["data type with no format", "text type with a format"],
)
def test_a_data_type_with_no_format_and_a_text_type_with_one_fail_the_manifest_schema(
    tmp_path: Path, box: str
) -> None:
    _crate(tmp_path, "  types:\n" + box)
    report, _ = map_project(tmp_path)
    assert report.map_path is None and not (tmp_path / "map.json").exists()
    assert report.exit_code == ExitCode.SCHEMA_INVALID
    assert any("format" in p.message for p in report.problems), report.problems


def test_validate_refuses_a_data_type_with_no_format_by_the_manifest_schema(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _crate(tmp_path, "  types:\n    box:\n      endings: [box]\n      reader: data")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "_config"))
    assert main(["validate", "crate"]) == ExitCode.SCHEMA_INVALID
    assert "format" in capsys.readouterr().out


TANNERY = "pack: tannery\nversion: 0.0.1\ndepends: []\nfiles:\n  extensions: [{ends}]\n"
FURRIER = "pack: furrier\nversion: 0.0.1\ndepends: []\nfiles:\n{files}\n"
HIDE_TYPE = "  types:\n    {name}:\n      endings: [hide]\n      reader: data\n      format: yaml"


def _tannery_and_furrier(root: Path, files: str, ends: str = "hide, fur") -> None:
    rutter(root, "tannery", TANNERY.format(ends=ends))
    rutter(root, "furrier", FURRIER.format(files=files))
    pin(root, "tannery@0.0.1", "furrier@0.0.1")
    plant(root, {"hides/one.hide": "x\n"})


def test_a_declared_type_of_another_name_claiming_a_listed_ending_is_a_conflict_naming_both(
    tmp_path: Path,
) -> None:
    _tannery_and_furrier(tmp_path, HIDE_TYPE.format(name="pelt"))
    report, _ = map_project(tmp_path)
    assert report.map_path is None and not (tmp_path / "map.json").exists()
    conflicts = [
        p.message
        for p in report.problems
        if p.code == ExitCode.PACK_RULES_UNREADABLE and "ending hide" in p.message
    ]
    assert len(conflicts) == 1, report.problems
    assert all(name in conflicts[0] for name in ("tannery/", "furrier/", "pelt")), conflicts


@pytest.mark.parametrize(
    ("furrier", "tannery_ends"),
    [
        (HIDE_TYPE.format(name="hide"), "hide, fur"),
        ("  extensions: [hide]", "hide, fur"),
        ("  extensions: [.hide]", "hide, fur"),
        (HIDE_TYPE.format(name="hide"), ".hide, fur"),
    ],
    ids=[
        "a declared type named by the ending",
        "two short lists sharing the ending",
        "a short list with a leading dot beside one without",
        "a short list with a leading dot beside a declared type named by the ending",
    ],
)
def test_claims_that_name_one_type_for_an_ending_load(
    tmp_path: Path, furrier: str, tannery_ends: str
) -> None:
    _tannery_and_furrier(tmp_path, furrier, tannery_ends)
    report, _ = map_project(tmp_path)
    assert report.problems == (), report.problems
