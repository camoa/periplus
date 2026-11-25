"""``periplus fresh`` says stale exactly when a rebuild writes a different map or opens another set
of files: the record holds the files some rule matches, and the bytes of each one a rule reads."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest
from test_demo_a_support import plant

from periplus.fresh import run as fresh
from periplus.map import run
from periplus.preflight import check_runtime_dependencies

#: A text rule that reads files whose names start with ``a``, and a rule that makes a node of each
#: ``n*`` file from its name alone and never reads it.
TEXT = {
    ".periplus/packs/own@0.0.1/pack.yaml": """\
pack: own
version: 0.0.1
depends: []
folders:
  src: ./src
files:
  types:
    t:
      endings: [t]
      reader: text
""",
    ".periplus/packs/own@0.0.1/rules/own.yaml": r"""node_types:
- {name: own.word, id_namespace: own.word}
- {name: own.name, id_namespace: own.name}
rules:
- rule: word
  reads: file
  in: [src]
  match: {file: 'a*', filetype: t, text: '(?m)^(?<name>\w+)$'}
  id: {from: {capture: name}}
  emits: [{node: {type: own.word}}]
  confidence: declared
- {rule: name, reads: file, in: [src], match: {file: 'n*', filetype: t},
   id: {from: file_stem}, emits: [{node: {type: own.name}}], confidence: declared}
""",
    ".periplus/settings.yml": "periplus_version: 0\npacks: [own@0.0.1]\n",
    "src/a1.t": "alpha\n",
    "src/b1.t": "beta\n",
    "src/n1.t": "never read\n",
}

#: A tree rule that reads each PHP file in its folder, beside a file of another ending.
TREE = {
    ".periplus/packs/probe@0.0.1/pack.yaml": """\
pack: probe
version: 0.0.1
depends: []
grammar:
  provider: tree-sitter
  provider_version: "0.26.0"
  language: php
  grammar_version: "0.24.1"
folders:
  source: ./src
files:
  extensions: [php]
identity:
  qualified_name: {parts: [namespace, declared_name], separator: "\\\\"}
  namespace: {declaration: namespace_definition, name_child: name}
  written_names: [name, qualified_name, namespace_name]
""",
    ".periplus/packs/probe@0.0.1/rules/probe.yaml": """\
node_types:
- {name: probe.class, id_namespace: probe.class}
rules:
- rule: find_class
  reads: file
  in: [source]
  match: {declaration: class_declaration, name_child: name,
    body_child: declaration_list, filetype: php}
  id: {from: qualified_name}
  emits: [{node: {type: probe.class}}]
  confidence: declared
""",
    ".periplus/settings.yml": "periplus_version: 0\npacks: [probe@0.0.1]\n",
    "src/Alpha.php": "<?php\n\nnamespace App;\n\nclass Alpha\n{\n}\n",
    "src/notes.txt": "about Alpha\n",
}


def _env(root: Path) -> dict[str, str]:
    return {"PERIPLUS_CONFIG_DIR": str(root / "config-dir")}


def _build(root: Path, output: str) -> tuple[bytes, tuple[str, ...]]:
    report = run(
        start=root,
        env=_env(root),
        dependencies=check_runtime_dependencies(),
        output=Path(output),
    )
    assert report.problems == (), report.problems
    return (root / output).read_bytes(), report.opened


def _write(path: str, text: str) -> Callable[[Path], None]:
    return lambda root: plant(root, {path: text})


EDITS = {
    "a matched and read file edited": (TEXT, _write("src/a1.t", "alpha\nomega\n"), True),
    "a file in the folder no rule's pattern matches edited": (
        TEXT,
        _write("src/b1.t", "changed\n"),
        False,
    ),
    "a file matched by name and never read edited": (TEXT, _write("src/n1.t", "x\n"), False),
    "a file a rule would match added": (TEXT, _write("src/a2.t", "gamma\n"), True),
    "a file a rule would match by name added": (TEXT, _write("src/n2.t", "x\n"), True),
    "a file no rule's pattern matches added": (TEXT, _write("src/b2.t", "delta\n"), False),
    "a matched file deleted": (TEXT, lambda root: (root / "src/a1.t").unlink(), True),
    "an unmatched file deleted": (TEXT, lambda root: (root / "src/b1.t").unlink(), False),
    "a tree rule's file edited": (
        TREE,
        _write("src/Alpha.php", "<?php\n\nnamespace App;\n\nclass Alphabet\n{\n}\n"),
        True,
    ),
    "a file of another ending in a tree rule's folder edited": (
        TREE,
        _write("src/notes.txt", "about Gamma\n"),
        False,
    ),
}


@pytest.mark.parametrize("edit", sorted(EDITS))
def test_fresh_is_stale_exactly_when_a_rebuild_differs(tmp_path: Path, edit: str) -> None:
    project, change, differs = EDITS[edit]
    plant(tmp_path, project)
    before = _build(tmp_path, ".periplus/map.json")
    change(tmp_path)
    report = fresh(
        start=tmp_path,
        env=_env(tmp_path),
        dependencies=check_runtime_dependencies(),
        map_path=None,
    )
    after = _build(tmp_path, "rebuilt.json")
    assert (after != before) is differs
    assert report.state == ("stale" if differs else "fresh"), report


@pytest.mark.parametrize(
    ("project", "matched", "opened"),
    [
        (TEXT, ["src/a1.t", "src/n1.t"], ("src/a1.t",)),
        (TREE, ["src/Alpha.php"], ("src/Alpha.php",)),
    ],
)
def test_the_record_holds_the_files_rules_match_and_the_bytes_of_those_they_read(
    tmp_path: Path, project: dict[str, str], matched: list[str], opened: tuple[str, ...]
) -> None:
    """Its files are those some rule matches; those with bytes are exactly those the run opened."""
    plant(tmp_path, project)
    _, run_opened = _build(tmp_path, ".periplus/map.json")
    record = json.loads((tmp_path / ".periplus/map.inputs.json").read_text())
    assert run_opened == opened
    assert sorted(record["files"]) == matched
    assert tuple(sorted(f for f, v in record["files"].items() if v != "not read")) == opened
