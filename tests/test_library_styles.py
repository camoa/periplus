"""A library links to each local CSS file its definition lists, under any css group."""

from __future__ import annotations

import json
from pathlib import Path

from periplus.map import run
from periplus.preflight import check_runtime_dependencies

MODULE = "web/modules/custom/mymodule"


def test_a_library_links_to_its_local_stylesheets_and_not_to_an_address(tmp_path: Path) -> None:
    module = tmp_path / MODULE
    (module / "css").mkdir(parents=True)
    (tmp_path / ".periplus").mkdir()
    (tmp_path / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks:\n"
        "  - drupal_basic@0.3.0\n  - js_basic@0.0.1\n  - drupal_js_basic@0.0.1\n"
    )
    (module / "mymodule.info.yml").write_text(
        "name: My module\ntype: module\ncore_version_requirement: ^10\n"
    )
    (module / "mymodule.libraries.yml").write_text(
        "form:\n"
        "  css:\n"
        "    component:\n"
        "      css/form.css: {}\n"
        "      https://example.com/remote.css: {type: external}\n"
        "      /core/misc/root.css: {}\n"
        "      css/missing.css: {}\n"
        "    theme:\n"
        "      css/form-theme.css: {}\n"
    )
    (module / "css" / "form.css").write_text(".form { color: red; }\n")
    (module / "css" / "form-theme.css").write_text(".form { margin: 0; }\n")

    report = run(
        start=tmp_path,
        env={},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == (), report.problems
    assert report.map_path is not None
    document = json.loads(Path(report.map_path).read_text())

    missing = f"css.file::{MODULE}/css/missing.css"
    sheets = {f"css.file::{MODULE}/css/form.css", f"css.file::{MODULE}/css/form-theme.css", missing}
    edges = {
        (e["from"], e["to"])
        for e in document["edges"]
        if e["kind"] == "library_includes_stylesheet"
    }
    assert edges == {("drupal.library::mymodule/form", sheet) for sheet in sheets}
    css_nodes = {n["id"]: n["state"] for n in document["nodes"] if n["id"].startswith("css.file::")}
    assert css_nodes == {sheet: "referenced" if sheet == missing else "mapped" for sheet in sheets}
    assert not any("example.com" in n["id"] or "root.css" in n["id"] for n in document["nodes"])
