"""periplus slice: cut a piece of a planted map into a map file of its own.

The map is planted as a document, so the walk is the only thing under test. Graph, all ``calls``
unless named, files in brackets:

    ext[src/ext] -> a1[src/a/one] -> a2[src/a/two] -> b1[src/b/one] (a2 -> b1 is ``uses``)
    a1 -> b1;  b1 -> b2[src/b/two];  b2 -> c1[src/c/one];  c1 -> far[src/far] (a class)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from periplus.errors import ExitCode

TYPE_HIERARCHY = [
    {"type": "callable", "parent": None},
    {"type": "function", "parent": "callable"},
    {"type": "method", "parent": "function"},
    {"type": "class", "parent": None},
]

# id -> (type, file)
NODES = {
    "py::a1": ("method", "src/a/one.py"),
    "py::a2": ("function", "src/a/two.py"),
    "py::b1": ("function", "src/b/one.py"),
    "py::b2": ("function", "src/b/two.py"),
    "py::c1": ("function", "src/c/one.py"),
    "py::ext": ("function", "src/ext/e.py"),
    "py::far": ("class", "src/far/x.py"),
}

EDGES = [
    ("calls", "py::ext", "py::a1"),
    ("calls", "py::a1", "py::a2"),
    ("calls", "py::a1", "py::b1"),
    ("uses", "py::a2", "py::b1"),
    ("calls", "py::b1", "py::b2"),
    ("calls", "py::b2", "py::c1"),
    ("calls", "py::c1", "py::far"),
]

PROVENANCE = [{"pack": "core", "rule": "r", "confidence": "declared"}]


def _document() -> dict[str, Any]:
    return {
        "periplus_map_version": 3,
        "generated_by": "periplus planted-by-test",
        "packs": [{"pack": "core", "version": "1.2.3"}],
        "settings": "conf/periplus-planted.yml",
        "roots": ["src", "extra"],
        "type_hierarchy": TYPE_HIERARCHY,
        "counts": {},
        "nodes": [
            {
                "id": node_id,
                "type": node_type,
                "state": "mapped",
                "locations": [{"file": file, "line": 1}],
                "provenance": PROVENANCE,
            }
            for node_id, (node_type, file) in sorted(NODES.items())
        ],
        "edges": [
            {
                "kind": kind,
                "from": source,
                "to": target,
                "locations": [{"file": NODES[source][1], "line": 2}],
                "provenance": PROVENANCE,
            }
            for kind, source, target in EDGES
        ],
    }


@pytest.fixture
def planted(tmp_path: Path) -> Path:
    document = _document()
    path = tmp_path / "full-map.json"
    path.write_text(json.dumps(document, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _call(tmp_path: Path, map_path: Path, out: Path, **kw: Any) -> tuple[Any, str]:
    """Run the slice; give back the exit code and the text of what it said."""
    from periplus.navigate import slice as slicing

    args: dict[str, Any] = {
        "ids": (),
        "prefix": None,
        "direction": "both",
        "depth": 1,
        "kinds": (),
        "limit": 500,
    }
    args.update(kw)
    report = slicing.run(tmp_path, {}, out=out, map_path=map_path, **args)
    return report.exit_code, repr(report.problems) + repr(report.warnings)


def _kept(out: Path) -> dict[str, Any]:
    return json.loads(out.read_text(encoding="utf-8"))


def _ids(document: dict[str, Any]) -> set[str]:
    return {node["id"] for node in document["nodes"]}


def _edge_set(document: dict[str, Any]) -> set[tuple[str, str, str]]:
    return {(e["kind"], e["from"], e["to"]) for e in document["edges"]}


def test_slice_from_one_id_at_depth_one_keeps_neighbours_and_their_edges_c1(
    tmp_path: Path, planted: Path
) -> None:
    from periplus import checkmap
    from periplus.navigate import show, walk

    out = tmp_path / "piece.json"
    code, _ = _call(tmp_path, planted, out, ids=("py::a1",), depth=1)

    assert code == 0
    document = _kept(out)
    assert _ids(document) == {"py::a1", "py::a2", "py::b1", "py::ext"}
    assert _edge_set(document) == {
        ("calls", "py::ext", "py::a1"),
        ("calls", "py::a1", "py::a2"),
        ("calls", "py::a1", "py::b1"),
        ("uses", "py::a2", "py::b1"),
    }
    assert checkmap.run(tmp_path, {}, out).exit_code == 0
    assert show.run(tmp_path, {}, "py::a1", 500, out).exit_code == 0
    assert walk.run(tmp_path, {}, "py::a1", "out", 1, (), 500, out).exit_code == 0

    second = tmp_path / "again.json"
    again, _ = _call(tmp_path, planted, second, ids=("py::a1",), depth=1)
    assert again == 0
    assert second.read_bytes() == out.read_bytes()


def test_slice_from_a_path_prefix_at_depth_two_keeps_what_both_ways_reach_c1(
    tmp_path: Path, planted: Path
) -> None:
    out = tmp_path / "piece.json"
    code, _ = _call(tmp_path, planted, out, prefix="src/a/", depth=2)

    assert code == 0
    document = _kept(out)
    assert _ids(document) == {"py::a1", "py::a2", "py::b1", "py::ext", "py::b2"}
    kept = _ids(document)
    for edge in document["edges"]:
        assert edge["from"] in kept and edge["to"] in kept
    assert _edge_set(document) == {
        ("calls", "py::ext", "py::a1"),
        ("calls", "py::a1", "py::a2"),
        ("calls", "py::a1", "py::b1"),
        ("uses", "py::a2", "py::b1"),
        ("calls", "py::b1", "py::b2"),
    }


def test_slice_along_named_edge_kinds_only_follows_those_kinds_c1(
    tmp_path: Path, planted: Path
) -> None:
    out = tmp_path / "piece.json"
    code, _ = _call(
        tmp_path, planted, out, ids=("py::a2",), direction="out", depth=2, kinds=("uses",)
    )

    assert code == 0
    document = _kept(out)
    assert _ids(document) == {"py::a2", "py::b1"}
    assert _edge_set(document) == {("uses", "py::a2", "py::b1")}


def test_slice_file_carries_recomputed_counts_and_copies_the_other_keys_wo1(
    tmp_path: Path, planted: Path
) -> None:
    out = tmp_path / "piece.json"
    code, _ = _call(tmp_path, planted, out, ids=("py::a1",), depth=1)

    assert code == 0
    document = _kept(out)
    full = json.loads(planted.read_text(encoding="utf-8"))
    assert document["counts"] == {
        "nodes": 4,
        "edges": 4,
        "edges_by_kind": {"calls": 3, "uses": 1},
        "nodes_by_state": {"mapped": 4},
        "nodes_by_type": {"function": 3, "method": 1},
    }
    for key in ("periplus_map_version", "generated_by", "packs", "settings", "roots"):
        assert document[key] == full[key]
    assert {row["type"] for row in document["type_hierarchy"]} == {"method", "function", "callable"}
    parents = {row["type"]: row.get("parent") for row in document["type_hierarchy"]}
    assert parents == {"callable": None, "function": "callable", "method": "function"}


def test_slice_over_the_limit_writes_nothing_and_names_count_and_limit_c2(
    tmp_path: Path, planted: Path
) -> None:
    out = tmp_path / "piece.json"
    code, said = _call(tmp_path, planted, out, ids=("py::a1",), depth=9, limit=4)

    assert code == ExitCode.SLICE_TOO_LARGE
    assert not out.exists()
    assert re.search(r"\b7\b", said)
    assert re.search(r"\b4\b", said)


def test_slice_from_an_unknown_id_writes_nothing_and_exits_node_not_found_c2(
    tmp_path: Path, planted: Path
) -> None:
    out = tmp_path / "piece.json"
    code, _ = _call(tmp_path, planted, out, ids=("py::nowhere",))

    assert code == ExitCode.NODE_NOT_FOUND
    assert not out.exists()


def test_slice_from_a_prefix_matching_no_item_exits_node_not_found_naming_it_c2(
    tmp_path: Path, planted: Path
) -> None:
    out = tmp_path / "piece.json"
    code, said = _call(tmp_path, planted, out, prefix="src/missing/")

    assert code == ExitCode.NODE_NOT_FOUND
    assert not out.exists()
    assert "src/missing/" in said


def test_write_document_checks_the_schema_then_writes_the_file_wo1(tmp_path: Path) -> None:
    from periplus import map as mapping

    good = _document()
    target = tmp_path / "written.json"
    assert mapping.write_document(good, target) == ()
    assert json.loads(target.read_text(encoding="utf-8"))["roots"] == good["roots"]

    bad = _document()
    del bad["roots"]
    assert len(mapping.write_document(bad, tmp_path / "bad.json")) >= 1


def test_the_map_file_is_unchanged_by_the_shared_counts_and_write_functions_wo1(
    tmp_path: Path,
) -> None:
    from periplus.map import run
    from periplus.preflight import check_runtime_dependencies

    root = tmp_path
    (root / ".periplus").mkdir(exist_ok=True)
    (root / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks: [php_basic@0.2.0]\n", encoding="utf-8"
    )
    (root / "src").mkdir()
    (root / "src" / "Greeter.php").write_text(
        "<?php\nnamespace App;\nclass Greeter { public function hi(): string { return 'hi'; } }\n",
        encoding="utf-8",
    )

    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )

    assert report.problems == ()
    raw = (root / "map.json").read_bytes()
    document = json.loads(raw)
    assert raw == (json.dumps(document, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode(
        "utf-8"
    )
    assert isinstance(document["generated_by"], str) and document["generated_by"]
    provenance = {"confidence": "declared", "pack": "php_basic"}
    location = [{"file": "src/Greeter.php", "line": 3}]
    assert {k: v for k, v in document.items() if k != "generated_by"} == {
        "periplus_map_version": 0,
        "packs": [{"pack": "php_basic", "version": "0.2.0"}],
        "settings": ".periplus/settings.yml",
        "roots": ["."],
        "type_hierarchy": [
            {"parent": None, "type": "php.callable"},
            {"parent": "php.class_like", "type": "php.class"},
            {"parent": None, "type": "php.class_like"},
            {"parent": "php.callable", "type": "php.method"},
        ],
        "counts": {
            "nodes": 2,
            "edges": 1,
            "edges_by_kind": {"contains": 1},
            "nodes_by_state": {"mapped": 2},
            "nodes_by_type": {"php.class": 1, "php.method": 1},
        },
        "nodes": [
            {
                "id": "php.method::App\\Greeter::hi",
                "locations": location,
                "provenance": [{**provenance, "rule": "find_method", "sets": ["id", "type"]}],
                "state": "mapped",
                "type": "php.method",
            },
            {
                "id": "php.type::App\\Greeter",
                "locations": location,
                "provenance": [{**provenance, "rule": "find_class", "sets": ["id", "type"]}],
                "state": "mapped",
                "type": "php.class",
            },
        ],
        "edges": [
            {
                "from": "php.type::App\\Greeter",
                "kind": "contains",
                "locations": location,
                "occurrences": 1,
                "provenance": [{**provenance, "rule": "contains_method"}],
                "to": "php.method::App\\Greeter::hi",
            }
        ],
    }
