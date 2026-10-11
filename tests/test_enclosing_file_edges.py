"""A declaration rule's edge end ``enclosing_file`` is the node the file's own rule made."""

from __future__ import annotations

from pathlib import Path

import pytest
from test_library_scripts import MODULE, _map, _plant
from test_spans import _map as _spans_map

from periplus.engine.packload import _read_tree_edge, _Unsupported

SCRIPT = (
    "function declared() {}\n"
    "const arrow = () => {};\n"
    "const expression = function () {};\n"
    "Drupal.behaviors.mymoduleAll = {\n  attach() {},\n};\n"
)


def test_a_script_links_to_every_function_and_behavior_it_declares(tmp_path: Path) -> None:
    _plant(tmp_path)
    (tmp_path / MODULE / "js" / "all.js").write_text(SCRIPT)
    script = f"js.file::{MODULE}/js/all.js"
    edges = [e for e in _map(tmp_path)["edges"] if e["from"] == script]
    found = sorted(
        (
            str(e["kind"]),
            str(e["to"]),
            "declared" if all(c["confidence"] == "declared" for c in e["provenance"]) else "other",
        )
        for e in edges
    )
    functions = [
        f"js.function::{MODULE}/js/all.js:{n}" for n in ("arrow", "declared", "expression")
    ]
    assert found == sorted(
        [("script_declares_function", f, "declared") for f in functions]
        + [("script_declares_behavior", "drupal.js_behavior::mymoduleAll", "declared")]
    )


def test_a_declaration_edge_may_start_at_the_enclosing_file() -> None:
    spec = _read_tree_edge({"kind": "k", "from": "enclosing_file", "to": "this_node"})
    assert spec.start == "enclosing_file"


def test_a_declaration_edge_from_another_end_is_still_refused() -> None:
    with pytest.raises(_Unsupported, match="enclosing_file"):
        _read_tree_edge({"kind": "k", "from": "matched_node", "to": "this_node"})


def test_a_declaration_edge_to_a_file_no_rule_mints_is_skipped_and_listed(tmp_path: Path) -> None:
    pack = tmp_path / ".periplus" / "packs" / "probe@0.0.1"
    (pack / "rules").mkdir(parents=True)
    (tmp_path / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks: [php_basic@0.2.0, probe@0.0.1]\n"
    )
    (pack / "pack.yaml").write_text(
        "pack: probe\nversion: 0.0.1\ndepends: [php_basic]\nfolders:\n  code: ./src\n"
    )
    (pack / "rules" / "probe.yaml").write_text(
        "node_types:\n- {name: probe.fn, id_namespace: probe.fn}\n"
        "- {name: probe.file, id_namespace: probe.file}\n"
        "edge_kinds:\n- {kind: in_file, from: probe.file, to: probe.fn}\n"
        "rules:\n- rule: fn\n  reads: file\n  in: [code]\n"
        "  match: {declaration: function_definition, name_child: name, filetype: php}\n"
        "  id: {from: qualified_name}\n"
        "  emits: [{node: {type: probe.fn}}]\n"
        "  confidence: declared\n"
        "- rule: fn_edge\n  reads: file\n  in: [code]\n"
        "  match: {declaration: function_definition, name_child: name, filetype: php}\n"
        "  id: {from: qualified_name}\n"
        "  emits: [{edge: {kind: in_file, from: enclosing_file, to: this_node}}]\n"
        "  confidence: declared\n"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.php").write_text("<?php\nnamespace App;\n\nfunction run()\n{\n}\n")
    report, document = _spans_map(tmp_path)
    assert report.problems == (), report
    assert [r[2:] for r in report.skipped] == [
        ("fn_edge", "edge in_file: no value for enclosing_file")
    ]
    assert not [e for e in document["edges"] if e["kind"] == "in_file"]
