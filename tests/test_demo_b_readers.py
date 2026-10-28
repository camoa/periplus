"""Readers and file listing that were once proved by demo scripts: two readers on one ending, the
files no rule read, and a folder nobody can list. Each test plants a small site and maps it
in-process."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from test_demo_b_support import clean_map, fires, line_of, map_site, plant, settings

from periplus.errors import ExitCode
from periplus.map import render_text

# --- two readers on one ending -----------------------------------------------------------------


def _notes_manifest(extra: str = "") -> str:
    return f"""\
pack: notes
version: 0.0.1
depends: []
folders:
  notes: ./**
files:
  types:
    php_notes:
      endings: [php]
      reader: text
      path_values:
        dir:
          pattern: '^(?<d>.+)/[^/]+$'
          template: 'notes:{{d}}'
{extra}"""


NOTES_RULES = r"""node_types:
- name: notes.owner
  id_namespace: notes.owner
rules:
- rule: owner
  reads: file
  in: [notes]
  match: {file: '*', filetype: php_notes, text: '(?m)^[ \t]*// @owner (?<owner>\w+)[ \t]*$'}
  id: {template: '{dir}/{owner}'}
  emits: [{node: {type: notes.owner}}]
  confidence: declared
"""

MODULES_PACK = r"""pack: modules
version: 0.0.1
depends: []
grammar:
  provider: tree-sitter
  provider_version: "0.26.0"
  language: php
  grammar_version: "0.24.1"
folders:
  source: ./**
files:
  types:
    code:
      endings: [php]
      reader: tree
      path_values:
        dir:
          pattern: '^(?<d>.+)/[^/]+$'
          template: '{d}'
      sections:
      - {name: block, open: '/\*', close: '\*/'}
identity:
  qualified_name: {parts: [namespace, declared_name], separator: "\\"}
  namespace: {declaration: namespace_definition, name_child: name}
  written_names: [name]
"""

MODULES_RULES = """\
node_types:
- name: modules.class
  id_namespace: modules.class
rules:
- rule: find_class
  reads: file
  in: [source]
  match: {declaration: class_declaration, name_child: name, filetype: code}
  id: {from: [dir, declared_name], template: '{dir}.{declared_name}'}
  emits: [{node: {type: modules.class}}]
  confidence: declared
"""

OWNER_AS_TEXT = r"""- rule: owner_as_text
  reads: file
  in: [source]
  match: {file: '*', filetype: code, text: '(?m)^[ \t]*// @owner (?<owner>\w+)'}
  id: {template: '{owner}'}
  emits: [{node: {type: modules.class}}]
  confidence: declared
"""

MAIN_PHP = """\
<?php

namespace App;

// @owner ana
class Main
{
    // @owner ben
    public function run()
    {
    }
}
"""

UTIL_PHP = """\
<?php

namespace App\\Lib;

/*
// @owner carl
*/
class Util extends \\App\\Main
{
}
"""


def _notes_site(root: Path, *pins: str, extra: str = "", modules_rules: str = "") -> None:
    plant(
        root,
        {
            **settings(*pins),
            ".periplus/packs/notes@0.0.1/pack.yaml": _notes_manifest(extra),
            ".periplus/packs/notes@0.0.1/rules/notes.yaml": NOTES_RULES,
            ".periplus/packs/modules@0.0.1/pack.yaml": MODULES_PACK,
            ".periplus/packs/modules@0.0.1/rules/modules.yaml": MODULES_RULES + modules_rules,
            "src/App/Main.php": MAIN_PHP,
            "src/Lib/Util.php": UTIL_PHP,
        },
    )


def _notes(document: Any) -> dict[str, list[tuple[str, int]]]:
    """Each notes node and the file and line it sits at."""
    found = {n["id"]: n for n in document["nodes"] if n["type"] == "notes.owner"}
    return {i: [(loc["file"], loc["line"]) for loc in n["locations"]] for i, n in found.items()}


def _expected_notes(root: Path) -> dict[str, list[tuple[str, int]]]:
    where = {
        "ana": ("src/App/Main.php", "// @owner ana"),
        "ben": ("src/App/Main.php", "// @owner ben"),
        "carl": ("src/Lib/Util.php", "// @owner carl"),
    }
    return {
        f"notes.owner::notes:{Path(file).parent}/{owner}": [(file, line_of(root / file, text))]
        for owner, (file, text) in where.items()
    }


def test_a_text_reader_beside_php_basic_adds_its_nodes_and_changes_nothing_else(
    tmp_path: Path,
) -> None:
    """php_basic reads php as a tree and notes reads it as text. The joint map holds php_basic's
    map alone, node for node and edge for edge, plus one notes node per owner line, at that line;
    both packs' rules run."""
    alone_root, joint_root = tmp_path / "alone", tmp_path / "joint"
    _notes_site(alone_root, "php_basic@0.2.0")
    _notes_site(joint_root, "php_basic@0.2.0", "notes@0.0.1")
    alone_report, alone = clean_map(alone_root)
    joint_report, joint = clean_map(joint_root)

    assert alone["nodes"] and alone["edges"]
    assert [n for n in joint["nodes"] if n["type"] != "notes.owner"] == alone["nodes"]
    assert joint["edges"] == alone["edges"]
    assert _notes(joint) == _expected_notes(joint_root)
    joint_fires = fires(joint_report)
    assert joint_fires[("notes", "owner")] == 3 and joint_fires[("php_basic", "find_class")] == 2
    assert {k: v for k, v in joint_fires.items() if k[0] == "php_basic"} == fires(alone_report)


def test_each_reader_uses_the_path_values_and_sections_of_its_own_file_type(
    tmp_path: Path,
) -> None:
    """Beside a tree rutter whose type code declares its own path value dir and a section over
    block comments, the class ids take code's dir and the notes ids take php_notes' dir, and an
    owner line inside a block comment is still a note."""
    _notes_site(tmp_path, "modules@0.0.1", "notes@0.0.1")
    _, document = clean_map(tmp_path)
    classes = sorted(n["id"] for n in document["nodes"] if n["type"] == "modules.class")
    assert classes == ["modules.class::src/App.Main", "modules.class::src/Lib.Util"]
    assert _notes(document) == _expected_notes(tmp_path)


def test_a_data_rule_and_a_text_rule_both_fire_on_one_ending(tmp_path: Path) -> None:
    """ledger reads yml as data (through yaml_basic) and as text; a rule on each fires."""
    plant(
        tmp_path,
        {
            **settings("yaml_basic@0.1.0", "ledger@0.0.1"),
            ".periplus/packs/ledger@0.0.1/pack.yaml": """\
pack: ledger
version: 0.0.1
depends: [yaml_basic]
folders:
  stock: ./stock
files:
  types:
    yml_notes:
      endings: [yml]
      reader: text
""",
            ".periplus/packs/ledger@0.0.1/rules/ledger.yaml": r"""node_types:
- name: ledger.item
  id_namespace: ledger.item
- name: ledger.owner
  id_namespace: ledger.owner
rules:
- rule: item
  reads: file
  in: [stock]
  match: {file: '*', filetype: yaml, each: '*'}
  id: {from: key}
  emits: [{node: {type: ledger.item}}]
  confidence: declared
- rule: owner
  reads: file
  in: [stock]
  match: {file: '*', filetype: yml_notes, text: '(?m)^# @owner (?<owner>\w+)$'}
  id: {template: '{owner}'}
  emits: [{node: {type: ledger.owner}}]
  confidence: declared
""",
            "stock/shelf.yml": "# @owner dora\nnails: 3\nscrews: 5\n",
        },
    )
    report, document = clean_map(tmp_path)
    assert fires(report) == {("ledger", "item"): 2, ("ledger", "owner"): 1}
    assert sorted(n["id"] for n in document["nodes"] if n["type"].startswith("ledger.")) == [
        "ledger.item::nails",
        "ledger.item::screws",
        "ledger.owner::dora",
    ]


def test_a_text_rule_on_a_type_read_only_as_a_tree_is_refused(tmp_path: Path) -> None:
    _notes_site(tmp_path, "modules@0.0.1", "notes@0.0.1", modules_rules=OWNER_AS_TEXT)
    report, document = map_site(tmp_path)
    assert document is None
    assert report.exit_code == ExitCode.RULE_NOT_EXECUTABLE
    [problem] = report.problems
    assert "owner_as_text" in problem.message and "text" in problem.message
    assert "code" in problem.message and "tree" in problem.message, problem.message


def test_two_types_of_one_ending_read_the_same_way_are_refused(tmp_path: Path) -> None:
    extra = "    php_more:\n      endings: [php]\n      reader: text\n"
    _notes_site(tmp_path, "php_basic@0.2.0", "notes@0.0.1", extra=extra)
    report, document = map_site(tmp_path)
    assert document is None
    assert report.exit_code == ExitCode.PACK_RULES_UNREADABLE
    [problem] = report.problems
    for name in ("php", "text", "php_more", "php_notes"):
        assert name in problem.message, problem.message


# --- files no rule read ------------------------------------------------------------------------

DRAWER_PACK = """\
pack: drawer
version: 0.0.1
depends: []
folders:
  drawer: ./drawer/**
{shelf}files:
  exclude: ['**/*.skip']
  types:
    sock:
      endings: [sock]
      reader: text
"""

DRAWER_RULES = r"""node_types:
- name: drawer.sock
  id_namespace: drawer.sock
rules:
- rule: sock
  reads: file
  in: [IN]
  match: {file: '*', filetype: sock, text: '(?m)^(?<colour>\w+)$'}
  id: {from: {capture: colour}}
  emits: [{node: {type: drawer.sock}}]
  confidence: declared
"""


def _drawer(root: Path, files: dict[str, str], *, shelf: bool = True) -> None:
    folders = "  shelf: ./shelf/*\n" if shelf else ""
    plant(
        root,
        {
            **settings("drawer@0.0.1"),
            ".periplus/packs/drawer@0.0.1/pack.yaml": DRAWER_PACK.format(shelf=folders),
            ".periplus/packs/drawer@0.0.1/rules/drawer.yaml": DRAWER_RULES.replace(
                "IN", "drawer, shelf" if shelf else "drawer"
            ),
            **files,
        },
    )


def _section(text: str, heading: str) -> list[str]:
    """The stripped rows under ``heading:`` in the text report, up to the blank line."""
    lines = text.split("\n")
    start = lines.index(f"{heading}:")
    rows = []
    for line in lines[start + 1 :]:
        if not line:
            break
        rows.append(line.strip())
    return rows


def test_a_file_below_the_rules_folders_that_no_rule_read_is_listed_as_unread(
    tmp_path: Path,
) -> None:
    """Every file below the rules' folders, at any depth, after excludes, that no executed rule
    selected. An excluded file, a file a rule read and a file outside the folders are not listed;
    a folder ending in one star selects its direct children only, so a file two levels down is
    unread. The text report gives the count, the count per ending most first, and the paths."""
    files = {
        "drawer/left.sock": "red\n",
        "drawer/inner/right.sock": "blue\n",
        "drawer/coin.button": "x\n",
        "drawer/lint.button": "x\n",
        "drawer/key.ring": "x\n",
        "drawer/note": "x\n",
        "drawer/inner/old.button": "x\n",
        "drawer/hole.skip": "x\n",
        "outside.button": "x\n",
        "shelf/alpha/top.sock": "green\n",
        "shelf/alpha/sub/deep.button": "x\n",
        "shelf/alpha/sub/low.sock": "grey\n",
    }
    _drawer(tmp_path, files)
    report, _ = clean_map(tmp_path)
    expected = [
        "drawer/coin.button",
        "drawer/inner/old.button",
        "drawer/key.ring",
        "drawer/lint.button",
        "drawer/note",
        "shelf/alpha/sub/deep.button",
        "shelf/alpha/sub/low.sock",
    ]
    assert list(report.unread) == expected

    text = render_text(report)
    assert ["unread", str(len(expected))] in [row.split() for row in _section(text, "Files")]
    assert _section(text, "Files no rule read, by ending") == [
        "button 4",
        "none 1",
        "ring 1",
        "sock 1",
    ]
    assert _section(text, "Files no rule read") == expected


def test_the_text_report_shows_twenty_unread_paths_and_counts_the_rest(tmp_path: Path) -> None:
    files = {f"drawer/coin{n:02d}.button": "x\n" for n in range(1, 24)}
    _drawer(tmp_path, files, shelf=False)
    report, _ = clean_map(tmp_path)
    planted = sorted(files)
    assert list(report.unread) == planted
    rows = _section(render_text(report), "Files no rule read")
    assert rows[:20] == planted[:20]
    assert len(rows) == 21 and rows[20].startswith("and 3 more"), rows


# --- a folder nobody can list ------------------------------------------------------------------

not_for_root = pytest.mark.skipif(
    os.geteuid() == 0, reason="folder permissions do not bind for root"
)


@pytest.fixture
def shut() -> Iterator[list[Path]]:
    """Folders a test closes; they open again so the temporary folder can be removed."""
    closed: list[Path] = []
    yield closed
    for folder in closed:
        folder.chmod(0o755)


def _socks(root: Path, folder: str, files: dict[str, str]) -> None:
    plant(
        root,
        {
            **settings("drawer@0.0.1"),
            ".periplus/packs/drawer@0.0.1/pack.yaml": f"""\
pack: drawer
version: 0.0.1
depends: []
folders:
  drawer: {folder}
files:
  types:
    sock:
      endings: [sock]
      reader: text
""",
            ".periplus/packs/drawer@0.0.1/rules/drawer.yaml": DRAWER_RULES.replace("IN", "drawer"),
            **files,
        },
    )


@not_for_root
@pytest.mark.parametrize("mode", [0o444, 0o000], ids=["mode_444", "mode_000"])
def test_a_closed_folder_below_a_direct_children_rule_leaves_the_map_as_open_and_is_unlisted(
    tmp_path: Path, shut: list[Path], mode: int
) -> None:
    """Mode 444 lists the folder but cannot examine its children; mode 000 cannot list it. The
    rule reads drawer's direct children only, so the map is the one the open folder gives, and the
    path stands under unlisted in the JSON report and in the text report."""
    _socks(
        tmp_path,
        "./drawer",
        {
            "drawer/left.sock": "red\n",
            "drawer/closed/hidden.sock": "blue\n",
            "drawer/closed/inner/note": "x\n",
        },
    )
    opened, open_document = clean_map(tmp_path)
    assert opened.unlisted == ()

    closed = tmp_path / "drawer" / "closed"
    shut.append(closed)
    closed.chmod(mode)
    report, document = clean_map(tmp_path)
    assert document == open_document
    assert report.unlisted == ("drawer/closed",)
    text = render_text(report)
    assert ["unlisted", "1"] in [row.split() for row in _section(text, "Files")]
    assert _section(text, "Folders that could not be listed") == ["drawer/closed"]


@not_for_root
def test_a_closed_folder_two_levels_below_a_one_star_rule_is_unlisted(
    tmp_path: Path, shut: list[Path]
) -> None:
    _socks(
        tmp_path,
        "./chest/*",
        {"chest/top/one.sock": "green\n", "chest/top/lining/closed/two.sock": "grey\n"},
    )
    _, open_document = clean_map(tmp_path)

    closed = tmp_path / "chest" / "top" / "lining" / "closed"
    shut.append(closed)
    closed.chmod(0o000)
    report, document = clean_map(tmp_path)
    assert document == open_document
    assert report.unlisted == ("chest/top/lining/closed",)
    assert _section(render_text(report), "Folders that could not be listed") == [
        "chest/top/lining/closed"
    ]


@not_for_root
def test_a_closed_folder_a_two_star_rule_must_list_ends_the_run_unreadable(
    tmp_path: Path, shut: list[Path]
) -> None:
    _socks(
        tmp_path,
        "./drawer/**",
        {"drawer/left.sock": "red\n", "drawer/closed/hidden.sock": "blue\n"},
    )
    closed = tmp_path / "drawer" / "closed"
    shut.append(closed)
    closed.chmod(0o000)
    report, document = map_site(tmp_path)
    assert document is None
    assert report.exit_code == ExitCode.SOURCE_UNREADABLE
    assert any("drawer/closed" in p.message for p in report.problems), report.problems
