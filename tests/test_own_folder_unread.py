"""No rule reads a file under the project's own ``.periplus`` folder, whatever the folders, the
settings or ``re_include`` say, so a map never depends on the map before it. The project's own
rutters there are read as rutters, by the pack loader."""

from __future__ import annotations

import json
from pathlib import Path

from test_demo_a_support import plant

from periplus.fresh import run as fresh
from periplus.map import MapReport, run
from periplus.preflight import check_runtime_dependencies

RUTTER = ".periplus/packs/own@0.0.1"

#: A whole-project folder, and one that names the project's own folder outright.
MANIFEST = """\
pack: own
version: 0.0.1
depends: []
folders:
  everything: ./**
  inside: .periplus/**
files:
  types:
    data:
      endings: [json]
      reader: text
    page:
      endings: [md]
      reader: text
    code:
      endings: [php]
      reader: text
"""

#: Each JSON key, each Markdown heading and each PHP class is a node.
RULES = r"""node_types:
- {name: own.key, id_namespace: own.key}
- {name: own.page, id_namespace: own.page}
- {name: own.code, id_namespace: own.code}
rules:
- rule: key
  reads: file
  in: [everything, inside]
  match: {file: '*', filetype: data, text: '"(?<name>[a-z]\w*)":'}
  id: {from: {capture: name}}
  emits: [{node: {type: own.key}}]
  confidence: declared
- rule: page
  reads: file
  in: [everything, inside]
  match: {file: '*', filetype: page, text: '(?m)^# (?<name>\w+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: own.page}}]
  confidence: declared
- rule: code
  reads: file
  in: [everything, inside]
  match: {file: '*', filetype: code, text: 'class (?<name>\w+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: own.code}}]
  confidence: declared
"""


def _project(root: Path) -> Path:
    plant(
        root,
        {
            f"{RUTTER}/pack.yaml": MANIFEST,
            f"{RUTTER}/rules/own.yaml": RULES,
            ".periplus/settings.yml": (
                "periplus_version: 0\npacks: [own@0.0.1]\nre_include: ['.periplus/**']\n"
            ),
            ".periplus/extra.json": '{"hidden": 1}\n',
            ".periplus/notes.md": "# Conventions\n",
            ".periplus/tool.php": "<?php class Hidden {}\n",
            "src/a.json": '{"alpha": 1}\n',
            "src/b.php": "<?php class Beta {}\n",
            "README.md": "# Readme\n",
        },
    )
    return root


def _map(root: Path) -> MapReport:
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config-dir")},
        dependencies=check_runtime_dependencies(),
    )
    assert report.problems == (), report.problems
    return report


def test_a_rule_whose_folders_cover_the_project_folder_selects_no_file_in_it(
    tmp_path: Path,
) -> None:
    report = _map(_project(tmp_path))
    document = json.loads((tmp_path / ".periplus/map.json").read_text())
    files = sorted({at["file"] for node in document["nodes"] for at in node["locations"]})
    assert files == ["README.md", "src/a.json", "src/b.php"]
    assert report.opened == ("README.md", "src/a.json", "src/b.php")
    assert (report.selected, report.excluded) == (3, 0)
    assert not [path for path in report.unread if path.startswith(".periplus/")]


def test_two_map_runs_in_a_row_write_the_same_bytes(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _map(root)
    first = (root / ".periplus/map.json").read_bytes()
    _map(root)
    assert (root / ".periplus/map.json").read_bytes() == first


def test_the_map_is_fresh_right_after_it_is_built_and_its_rutter_is_recorded(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path)
    _map(root)
    record = json.loads((root / ".periplus/map.inputs.json").read_text())
    assert sorted(record["files"]) == ["README.md", "src/a.json", "src/b.php"]
    assert list(record["packs"]) == ["own@0.0.1"]
    report = fresh(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config-dir")},
        dependencies=check_runtime_dependencies(),
        map_path=None,
    )
    assert (report.state, report.files) == ("fresh", ((), (), ()))
