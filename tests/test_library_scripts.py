"""A library links to the local scripts its definition lists; a script links to its behaviors."""

from __future__ import annotations

import json
from pathlib import Path

from periplus.map import run
from periplus.preflight import check_runtime_dependencies

MODULE = Path("web/modules/custom/mymodule")


def _plant(root: Path) -> None:
    module = root / MODULE
    (module / "js").mkdir(parents=True)
    (root / ".periplus").mkdir()
    (root / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n  - drupal_js_basic@0.0.1\n"
    )
    (module / "mymodule.info.yml").write_text(
        "name: My module\ntype: module\ncore_version_requirement: ^10\n"
    )
    (module / "mymodule.libraries.yml").write_text(
        "form:\n  js:\n    js/form.js: {}\n    js/extra.js: {}\n"
        "  dependencies:\n    - core/drupal\n"
    )
    (module / "js" / "form.js").write_text(
        "Drupal.behaviors.mymoduleForm = {\n  attach() {},\n};\n"
    )
    (module / "js" / "extra.js").write_text(
        "Drupal.behaviors.mymoduleExtra = {\n  attach() {},\n};\n"
    )


def _map(root: Path) -> dict[str, list[dict[str, object]]]:
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == (), report.problems
    assert report.map_path is not None
    return json.loads(Path(report.map_path).read_text())  # type: ignore[no-any-return]


def test_a_library_links_to_its_scripts_and_each_script_to_its_behavior(tmp_path: Path) -> None:
    _plant(tmp_path)
    document = _map(tmp_path)
    nodes = {str(n["id"]): n["state"] for n in document["nodes"]}
    edges = {(str(e["kind"]), str(e["from"]), str(e["to"])) for e in document["edges"]}
    library = "drupal.library::mymodule/form"
    for name, behavior in (("form", "mymoduleForm"), ("extra", "mymoduleExtra")):
        script = f"js.file::{MODULE}/js/{name}.js"
        assert nodes[script] == "mapped"
        assert ("library_includes_script", library, script) in edges
        assert ("script_declares_behavior", script, f"drupal.js_behavior::{behavior}") in edges


def test_the_library_nodes_and_edges_the_map_had_before_are_kept(tmp_path: Path) -> None:
    _plant(tmp_path)
    document = _map(tmp_path)
    nodes = {str(n["id"]): n["state"] for n in document["nodes"]}
    edges = {(str(e["kind"]), str(e["from"]), str(e["to"])) for e in document["edges"]}
    assert nodes["drupal.library::mymodule/form"] == "mapped"
    assert nodes["drupal.library::core/drupal"] == "referenced"
    assert (
        "depends_on_library",
        "drupal.library::mymodule/form",
        "drupal.library::core/drupal",
    ) in edges


def test_a_script_key_read_from_the_drupal_root_gives_no_edge_and_no_node(tmp_path: Path) -> None:
    _plant(tmp_path)
    (tmp_path / MODULE / "mymodule.libraries.yml").write_text(
        "form:\n  js:\n    js/form.js: {}\n    /core/misc/root.js: {}\n"
    )
    document = _map(tmp_path)
    assert not [n["id"] for n in document["nodes"] if "root.js" in str(n["id"])]
    assert not [e for e in document["edges"] if "root.js" in str(e["to"])]
    assert ("library_includes_script", "drupal.library::mymodule/form") in {
        (str(e["kind"]), str(e["from"])) for e in document["edges"]
    }


def test_a_pack_that_declares_the_type_yml_again_in_full_keeps_the_library_edges(
    tmp_path: Path,
) -> None:
    _plant(tmp_path)
    pack = tmp_path / ".periplus" / "packs" / "local@0.0.1"
    pack.mkdir(parents=True)
    (pack / "pack.yaml").write_text(
        "pack: local\nversion: 0.0.1\ndepends: [drupal_basic]\nfiles:\n  types:\n"
        "    yml:\n      endings: [yml]\n      reader: data\n      format: yaml\n"
        "      path_values:\n        stem:\n          pattern: '^(?:.*/)?(?<s>[^/]+)$'\n"
        "          template: '{s}'\n"
    )
    (tmp_path / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n  - drupal_js_basic@0.0.1\n"
        "  - local@0.0.1\n"
    )
    document = _map(tmp_path)
    edges = {(str(e["kind"]), str(e["from"]), str(e["to"])) for e in document["edges"]}
    for name in ("form", "extra"):
        script = f"js.file::{MODULE}/js/{name}.js"
        assert ("library_includes_script", "drupal.library::mymodule/form", script) in edges
