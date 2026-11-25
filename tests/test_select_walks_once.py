"""File selection lists each folder of the project once per run, whatever the number of rules and
folder patterns, and selects exactly the files it selected when it listed a folder once per use."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_demo_a_support import plant

import periplus.engine.select as select_module
from periplus.map import run
from periplus.preflight import check_runtime_dependencies

MANIFEST = """\
pack: sel
version: 0.0.1
depends: []
folders:
  everything: ./**
  here: .
  deep: a/**
  one: '*'
  kids: a/*
  joined: ['{here}/d', '{deep}']
files:
  types:
    t:
      endings: [t]
      reader: text
"""

#: A second rutter whose folder is the project root alone, beside the first one's ``./**``.
DOT = """\
pack: dot
version: 0.0.1
depends: [sel]
folders:
  top: .
"""

DOT_RULES = r"""node_types:
- {name: dot.file, id_namespace: dot.file}
rules:
- rule: top
  reads: file
  in: [top]
  match: {file: '*', filetype: t, text: '(?m)^(?<name>\w+)$'}
  id: {from: {capture: name}}
  emits: [{node: {type: dot.file}}]
  confidence: declared
"""

FOLDERS = ("everything", "here", "deep", "one", "kids", "joined")
GLOBS = ("*", "?", "a*", "*z*", "*e*")

TREE = {
    "top.t": "top\n",
    "a/x.t": "ax\n",
    "a/b/y.t": "aby\n",
    "a/b/c/z.t": "abcz\n",
    "a/skip/s.t": "askips\n",
    "a/skip/keep.t": "askipkeep\n",
    "a/skip/deeper/w.t": "askipdeeperw\n",
    "d/e.t": "de\n",
    "d/f/g.t": "dfg\n",
    "d/notes.txt": "plain\n",
}

SETTINGS = {
    "plain": "",
    "excluded": "exclude: ['**/skip/**']\n",
    "reincluded": "exclude: ['**/skip/**']\nre_include: ['**/keep.t']\n",
}


def _rules(count: int) -> str:
    """``count`` rules, each a node type of its own, cycling through the folders and the globs."""
    types = "".join(f"- {{name: sel.r{n}, id_namespace: sel.r{n}}}\n" for n in range(count))
    rules = "".join(
        f"- rule: r{n}\n"
        "  reads: file\n"
        f"  in: [{FOLDERS[n % len(FOLDERS)]}]\n"
        f"  match: {{file: '{GLOBS[n // len(FOLDERS) % len(GLOBS)]}', filetype: t,"
        " text: '(?m)^(?<name>\\w+)$'}\n"
        "  id: {from: {capture: name}}\n"
        f"  emits: [{{node: {{type: sel.r{n}}}}}]\n"
        "  confidence: declared\n"
        for n in range(count)
    )
    return f"node_types:\n{types}rules:\n{rules}"


def _project(root: Path, rules: int, settings: str) -> None:
    plant(
        root,
        {
            **TREE,
            ".periplus/packs/sel@0.0.1/pack.yaml": MANIFEST,
            ".periplus/packs/sel@0.0.1/rules/sel.yaml": _rules(rules),
            ".periplus/packs/dot@0.0.1/pack.yaml": DOT,
            ".periplus/packs/dot@0.0.1/rules/dot.yaml": DOT_RULES,
            ".periplus/settings.yml": (
                f"periplus_version: 0\npacks: [sel@0.0.1, dot@0.0.1]\n{settings}"
            ),
        },
    )
    (root / "link").symlink_to("a/b")
    (root / "d" / "ln.t").symlink_to("../a/x.t")
    (root / "d" / "gone.t").symlink_to("nowhere.t")
    (root / "a" / "b" / "c" / "loop").symlink_to("../..")


def _map(root: Path) -> tuple[object, ...]:
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config-dir")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == (), report.problems
    document = json.loads((root / "map.json").read_text())
    picked: dict[str, list[str]] = {}
    for node in document["nodes"]:
        picked.setdefault(node["type"], []).extend(at["file"] for at in node["locations"])
    per_rule = {kind: tuple(sorted(files)) for kind, files in sorted(picked.items())}
    return per_rule, report.opened, report.selected, report.excluded, report.unread, report.unlisted


def _listed(root: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    real = select_module._listing
    calls: list[str] = []

    def spy(at: Path, path: str) -> list[Path]:
        calls.append(path)
        return real(at, path)

    monkeypatch.setattr(select_module, "_listing", spy)
    _map(root)
    monkeypatch.setattr(select_module, "_listing", real)
    return calls


#: Recorded from the code that listed a folder once per use, before the walk was shared.
EXPECTED = {
    "plain": (
        {
            "dot.file": ("top.t",),
            "sel.r0": (
                "a/b/c/z.t",
                "a/b/y.t",
                "a/skip/deeper/w.t",
                "a/skip/keep.t",
                "a/skip/s.t",
                "a/x.t",
                "d/e.t",
                "d/f/g.t",
                "d/ln.t",
                "link/c/loop/skip/deeper/w.t",
                "link/c/loop/skip/keep.t",
                "link/c/loop/skip/s.t",
                "link/c/loop/x.t",
                "link/c/z.t",
                "link/y.t",
                "top.t",
            ),
            "sel.r1": ("top.t",),
            "sel.r2": (
                "a/b/c/z.t",
                "a/b/y.t",
                "a/skip/deeper/w.t",
                "a/skip/keep.t",
                "a/skip/s.t",
                "a/x.t",
            ),
            "sel.r3": ("a/x.t", "d/e.t", "d/ln.t", "link/y.t"),
            "sel.r4": ("a/b/y.t", "a/skip/keep.t", "a/skip/s.t"),
            "sel.r5": (
                "a/b/c/z.t",
                "a/b/y.t",
                "a/skip/deeper/w.t",
                "a/skip/keep.t",
                "a/skip/s.t",
                "a/x.t",
                "d/e.t",
                "d/ln.t",
            ),
        },
        (
            "a/b/c/z.t",
            "a/b/y.t",
            "a/skip/deeper/w.t",
            "a/skip/keep.t",
            "a/skip/s.t",
            "a/x.t",
            "d/e.t",
            "d/f/g.t",
            "d/ln.t",
            "link/c/loop/skip/deeper/w.t",
            "link/c/loop/skip/keep.t",
            "link/c/loop/skip/s.t",
            "link/c/loop/x.t",
            "link/c/z.t",
            "link/y.t",
            "top.t",
        ),
        16,
        0,
        ("d/notes.txt", "link/c/loop/b/c/z.t", "link/c/loop/b/y.t"),
        (),
    ),
    "excluded": (
        {
            "dot.file": ("top.t",),
            "sel.r0": (
                "a/b/c/z.t",
                "a/b/y.t",
                "a/x.t",
                "d/e.t",
                "d/f/g.t",
                "d/ln.t",
                "link/c/loop/x.t",
                "link/c/z.t",
                "link/y.t",
                "top.t",
            ),
            "sel.r1": ("top.t",),
            "sel.r2": ("a/b/c/z.t", "a/b/y.t", "a/x.t"),
            "sel.r3": ("a/x.t", "d/e.t", "d/ln.t", "link/y.t"),
            "sel.r4": ("a/b/y.t",),
            "sel.r5": ("a/b/c/z.t", "a/b/y.t", "a/x.t", "d/e.t", "d/ln.t"),
        },
        (
            "a/b/c/z.t",
            "a/b/y.t",
            "a/x.t",
            "d/e.t",
            "d/f/g.t",
            "d/ln.t",
            "link/c/loop/x.t",
            "link/c/z.t",
            "link/y.t",
            "top.t",
        ),
        10,
        2,
        ("d/notes.txt", "link/c/loop/b/c/z.t", "link/c/loop/b/y.t"),
        (),
    ),
    "reincluded": (
        {
            "dot.file": ("top.t",),
            "sel.r0": (
                "a/b/c/z.t",
                "a/b/y.t",
                "a/skip/keep.t",
                "a/x.t",
                "d/e.t",
                "d/f/g.t",
                "d/ln.t",
                "link/c/loop/skip/keep.t",
                "link/c/loop/x.t",
                "link/c/z.t",
                "link/y.t",
                "top.t",
            ),
            "sel.r1": ("top.t",),
            "sel.r2": ("a/b/c/z.t", "a/b/y.t", "a/skip/keep.t", "a/x.t"),
            "sel.r3": ("a/x.t", "d/e.t", "d/ln.t", "link/y.t"),
            "sel.r4": ("a/b/y.t", "a/skip/keep.t"),
            "sel.r5": ("a/b/c/z.t", "a/b/y.t", "a/skip/keep.t", "a/x.t", "d/e.t", "d/ln.t"),
        },
        (
            "a/b/c/z.t",
            "a/b/y.t",
            "a/skip/keep.t",
            "a/x.t",
            "d/e.t",
            "d/f/g.t",
            "d/ln.t",
            "link/c/loop/skip/keep.t",
            "link/c/loop/x.t",
            "link/c/z.t",
            "link/y.t",
            "top.t",
        ),
        12,
        4,
        ("d/notes.txt", "link/c/loop/b/c/z.t", "link/c/loop/b/y.t"),
        (),
    ),
}


@pytest.mark.parametrize("settings", sorted(SETTINGS))
def test_each_rule_selects_the_files_it_selected_before(tmp_path: Path, settings: str) -> None:
    _project(tmp_path, 6, SETTINGS[settings])
    assert _map(tmp_path) == EXPECTED[settings]


def test_each_folder_is_listed_once_whatever_the_number_of_rules_and_patterns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _project(tmp_path / "one", 1, "")
    _project(tmp_path / "fifty", 50, "")
    one = _listed(tmp_path / "one", monkeypatch)
    fifty = _listed(tmp_path / "fifty", monkeypatch)
    assert sorted(one) == sorted(set(one)), sorted(one)
    assert sorted(fifty) == sorted(one)
