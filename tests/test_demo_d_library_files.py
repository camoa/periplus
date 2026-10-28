"""A library's script and stylesheet lists, and a third party writing the same file links."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from periplus.map import MapReport, run
from periplus.preflight import check_runtime_dependencies

FOLDER = "web/modules/custom/mymodule"
JS_PACKS = "  - drupal_basic@0.3.0\n  - js_basic@0.0.1\n  - drupal_js_basic@0.0.1\n"

LOCAL_PACK = """\
pack: localjs
version: 0.0.1
depends: [js_basic, drupal_basic]
files:
  types:
    yml:
      endings: [yml]
      reader: data
      format: yaml
      path_values:
        libraries_dir:
          pattern: '^(?<dir>.+)/[^/]+$'
          template: '{dir}'
"""

LOCAL_RULES = """\
node_types:
- name: drupal.js_behavior
  id_namespace: drupal.js_behavior
edge_kinds:
- kind: library_includes_script
  from: drupal.library
  to: js.file
- kind: script_declares_behavior
  from: js.file
  to: drupal.js_behavior
rules:
- rule: local_behavior
  reads: file
  in: [js_source]
  match: {declaration: assignment_expression, name_child: left, body_child: object, filetype: javascript, where: [{has_child: object}]}
  id: {from: declared_name, pattern: '^Drupal\\.behaviors\\.(?<behavior>[A-Za-z_$][\\w$]*)$', template: '{behavior}'}
  emits: [{node: {type: drupal.js_behavior}}]
  confidence: declared
- rule: local_behavior_in_file
  reads: file
  in: [js_source]
  match: {declaration: assignment_expression, name_child: left, body_child: object, filetype: javascript, where: [{has_child: object}]}
  id: {from: declared_name, pattern: '^Drupal\\.behaviors\\.(?<behavior>[A-Za-z_$][\\w$]*)$', template: '{behavior}'}
  emits: [{edge: {kind: script_declares_behavior, from: enclosing_file, to: this_node}}]
  confidence: declared
- rule: local_library_script
  reads: file
  in: [module_root, theme_root]
  match: {file: '*.libraries', filetype: yml, each: '*'}
  id:
    from: [file_stem, key]
    template: '{file_stem}/{key}'
    normalize: [{replace: '\\.libraries/', with: /}]
  emits:
  - edge:
      kind: library_includes_script
      from: this_node
      to:
        from: [{each: js.*}]
        template: '{libraries_dir}/{key}'
        where: [{not_matches: '//*'}, {not_matches: 'http:*'}, {not_matches: 'https:*'}]
  confidence: declared
"""  # noqa: E501


def _plant(root: Path, packs: str, libraries: str) -> Path:
    module = root / FOLDER
    module.mkdir(parents=True)
    (root / ".periplus").mkdir()
    (root / ".periplus" / "settings.yml").write_text(f"periplus_version: 0\npacks:\n{packs}")
    (module / "mymodule.info.yml").write_text(
        "name: My module\ntype: module\ncore_version_requirement: ^10\n"
    )
    (module / "mymodule.libraries.yml").write_text(libraries)
    return module


def _map(root: Path, name: str = "map.json") -> tuple[MapReport, dict[str, list[dict[str, str]]]]:
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path(name),
    )
    assert report.problems == (), report.problems
    assert report.not_executed == (), report.not_executed
    assert report.map_path is not None
    return report, json.loads(Path(report.map_path).read_text())  # type: ignore[no-any-return]


def _states(document: dict[str, list[dict[str, str]]]) -> dict[str, str]:
    return {n["id"]: n["state"] for n in document["nodes"]}


def _edge_set(document: dict[str, list[dict[str, str]]], kind: str) -> set[tuple[str, str]]:
    return {(e["from"], e["to"]) for e in document["edges"] if e["kind"] == kind}


def test_a_script_key_from_the_drupal_root_ends_at_the_modules_own_script_when_mapped(
    tmp_path: Path,
) -> None:
    module = _plant(
        tmp_path,
        JS_PACKS,
        "form:\n  js:\n    /modules/custom/mymodule/js/root.js: {}\n    /core/misc/drupal.js: {}\n",
    )
    (module / "js").mkdir()
    (module / "js" / "root.js").write_text("const mymoduleRoot = 1;\n")
    _, document = _map(tmp_path)
    states = _states(document)
    assert states[f"js.file::{FOLDER}/js/root.js"] == "mapped"
    assert states["js.file::web/core/misc/drupal.js"] == "referenced"
    assert _edge_set(document, "library_includes_script") == {
        ("drupal.library::mymodule/form", f"js.file::{FOLDER}/js/root.js"),
        ("drupal.library::mymodule/form", "js.file::web/core/misc/drupal.js"),
    }


def test_a_remote_script_makes_no_node_and_a_library_listing_only_urls_gives_one_skipped_row(
    tmp_path: Path,
) -> None:
    module = _plant(
        tmp_path,
        JS_PACKS,
        "form:\n  js:\n    js/form.js: {}\n    https://example.com/remote.js: {type: external}\n"
        "remote:\n  js:\n    //cdn.example.com/remote.js: {type: external}\n",
    )
    (module / "js").mkdir()
    (module / "js" / "form.js").write_text(
        "Drupal.behaviors.mymoduleForm = {\n  attach() {},\n};\n"
    )
    report, document = _map(tmp_path)
    states = _states(document)
    assert states["drupal.library::mymodule/remote"] == "mapped"
    assert not any("example.com" in node for node in states), states
    assert {to for _, to in _edge_set(document, "library_includes_script")} == {
        f"js.file::{FOLDER}/js/form.js"
    }
    assert [(rule, file) for file, _, rule, _ in report.skipped] == [
        ("library_script", f"{FOLDER}/mymodule.libraries.yml")
    ]


def test_a_library_attached_from_php_is_mapped_and_links_to_the_class_that_attaches_it(
    tmp_path: Path,
) -> None:
    module = _plant(tmp_path, JS_PACKS, "form:\n  js:\n    js/form.js: {}\n")
    (module / "js").mkdir()
    (module / "js" / "form.js").write_text("const x = 1;\n")
    (module / "src" / "Controller").mkdir(parents=True)
    (module / "src" / "Controller" / "FormController.php").write_text(
        "<?php\n\nnamespace Drupal\\mymodule\\Controller;\n\nfinal class FormController {\n\n"
        "  public function page(): array {\n"
        "    $build['#attached']['library'][] = 'mymodule/form';\n"
        "    return $build;\n  }\n\n}\n"
    )
    _, document = _map(tmp_path)
    assert _states(document)["drupal.library::mymodule/form"] == "mapped"
    assert _edge_set(document, "attaches_library") == {
        ("php.type::Drupal\\mymodule\\Controller\\FormController", "drupal.library::mymodule/form")
    }


def test_a_protocol_relative_address_makes_no_stylesheet_node_and_a_root_key_ends_at_the_own_file(
    tmp_path: Path,
) -> None:
    module = _plant(
        tmp_path,
        JS_PACKS,
        "form:\n  css:\n    theme:\n      //cdn.example.com/other.css: {}\n"
        "      /modules/custom/mymodule/css/root.css: {}\n",
    )
    (module / "css").mkdir()
    (module / "css" / "root.css").write_text(".root { color: blue; }\n")
    _, document = _map(tmp_path)
    sheets = {n["id"]: n["state"] for n in document["nodes"] if n["type"] == "css.file"}
    assert sheets == {f"css.file::{FOLDER}/css/root.css": "mapped"}
    assert not any("example.com" in n["id"] for n in document["nodes"])


def test_a_library_listing_only_a_stylesheet_url_gives_one_skipped_row(tmp_path: Path) -> None:
    _plant(
        tmp_path,
        JS_PACKS,
        "remote:\n  css:\n    theme:\n      https://example.com/cdn.css: {type: external}\n",
    )
    report, document = _map(tmp_path)
    assert [(rule, file) for file, _, rule, _ in report.skipped] == [
        ("library_stylesheet", f"{FOLDER}/mymodule.libraries.yml")
    ]
    assert _edge_set(document, "library_includes_stylesheet") == set()


def test_a_project_local_pack_writes_the_same_file_links_as_the_bundled_rutters(
    tmp_path: Path,
) -> None:
    libraries = (
        "form:\n  js:\n    js/form.js: {}\n    https://example.com/remote.js: {type: external}\n"
        "    //cdn.example.com/other.js: {}\n"
    )
    module = _plant(tmp_path, JS_PACKS, libraries)
    (module / "js").mkdir()
    (module / "js" / "form.js").write_text(
        "function helper() {}\nconst arrow = () => {};\n"
        "Drupal.behaviors.mymoduleForm = {\n  attach() {},\n};\n"
    )
    pack = tmp_path / ".periplus" / "packs" / "localjs@0.0.1"
    (pack / "rules").mkdir(parents=True)
    (pack / "pack.yaml").write_text(LOCAL_PACK)
    (pack / "rules" / "links.yaml").write_text(LOCAL_RULES)

    _, bundled = _map(tmp_path, "bundled.json")
    (tmp_path / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n  - js_basic@0.0.1\n"
        "  - localjs@0.0.1\n"
    )
    _, local = _map(tmp_path, "local.json")

    def shape(document: dict[str, list[dict[str, str]]]) -> tuple[list[Any], list[Any]]:
        nodes = sorted((n["id"], n["state"]) for n in document["nodes"])
        edges = sorted((e["kind"], e["from"], e["to"]) for e in document["edges"])
        return nodes, edges

    assert shape(local) == shape(bundled)
    script = f"js.file::{FOLDER}/js/form.js"
    edges = shape(bundled)[1]
    assert ("library_includes_script", "drupal.library::mymodule/form", script) in edges
    assert ("script_declares_behavior", script, "drupal.js_behavior::mymoduleForm") in edges
    assert ("script_declares_function", script, f"js.function::{FOLDER}/js/form.js:helper") in edges
    assert not any("example.com" in e[2] for e in edges), edges
