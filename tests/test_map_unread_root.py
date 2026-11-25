"""The files no rule read, when one pack's folder is `.` and another's is `./**`.

The fault: the two values named the project root in two spellings, `.` and the empty path, so
the list named each file twice, `./x` and `x`, and named files a rule did read in the other
spelling. Two neutral packs stand in for any stack.
"""

from __future__ import annotations

from pathlib import Path

from test_demo_a_support import map_project, pin, plant, rutter


def _pack(root: Path, name: str, folder: str, ending: str) -> None:
    manifest = (
        f"pack: {name}\nversion: 0.0.1\ndepends: []\nfolders:\n  {name}_here: '{folder}'\n"
        f"files:\n  types:\n    {ending}:\n      endings: [{ending}]\n      reader: data\n"
        "      format: yaml\n"
    )
    rules = (
        f"node_types:\n- {{name: {name}.item, id_namespace: {name}.item}}\nrules:\n"
        f"- rule: item\n  reads: file\n  in: [{name}_here]\n"
        f"  match: {{file: '*', filetype: {ending}}}\n  id: {{template: '{{file_stem}}'}}\n"
        f"  emits: [{{node: {{type: {name}.item}}}}]\n  confidence: declared\n"
    )
    rutter(root, name, manifest, {f"{name}.yaml": rules})


def _root_and_deep(root: Path) -> tuple[str, ...]:
    """`flat` reads `.note` files in `.`, `deep` reads `.memo` files in `./**`."""
    _pack(root, "flat", ".", "note")
    _pack(root, "deep", "./**", "memo")
    pin(root, "flat@0.0.1", "deep@0.0.1")
    plant(
        root,
        {
            "one.note": "a: 1\n",
            "two.memo": "b: 2\n",
            "sub/three.memo": "c: 3\n",
            "README.md": "x\n",
        },
    )
    report, _ = map_project(root)
    assert report.nodes == 3, report
    return report.unread


def test_a_file_a_rule_read_is_not_unread_in_any_spelling(tmp_path: Path) -> None:
    unread = {path.removeprefix("./") for path in _root_and_deep(tmp_path)}

    assert not unread & {"one.note", "two.memo", "sub/three.memo"}, unread


def test_each_unread_file_is_listed_once_in_one_spelling(tmp_path: Path) -> None:
    unread = _root_and_deep(tmp_path)

    assert [path for path in unread if path.startswith("./")] == [], unread
    assert unread.count("README.md") == 1, unread


def test_no_file_under_the_project_marker_is_unread(tmp_path: Path) -> None:
    unread = _root_and_deep(tmp_path)

    assert [path for path in unread if path.removeprefix("./").startswith(".periplus/")] == []
    assert "README.md" in unread
