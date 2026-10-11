"""Simple configuration links to the module that provides it; a configuration entity does not."""

from __future__ import annotations

import json
from pathlib import Path

from periplus.map import run
from periplus.preflight import check_runtime_dependencies

MODULE = Path("web/modules/custom/mymodule")


def _plant(root: Path) -> None:
    module = root / MODULE
    (module / "config" / "install").mkdir(parents=True)
    (root / ".periplus").mkdir()
    (root / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n"
    )
    (module / "mymodule.info.yml").write_text(
        "name: My module\ntype: module\ncore_version_requirement: ^10\n"
    )
    install = module / "config" / "install"
    (install / "mymodule.settings.yml").write_text("limit: 5\n")
    (install / "othermodule.settings.yml").write_text("limit: 6\n")
    (install / "mymodule.thing.one.yml").write_text(
        "uuid: 11111111-1111-1111-1111-111111111111\nid: one\n"
    )
    sync = root / "config" / "sync"
    sync.mkdir(parents=True)
    for name in ("mymodule.settings", "othermodule.settings"):
        (sync / f"{name}.yml").write_text("limit: 5\n")
    (sync / "mymodule.thing.one.yml").write_text(
        "uuid: 11111111-1111-1111-1111-111111111111\nid: one\n"
    )
    (sync / "core.extension.yml").write_text("module: {}\n")


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


def test_simple_config_links_to_its_owner_module_and_a_config_entity_does_not(
    tmp_path: Path,
) -> None:
    _plant(tmp_path)
    document = _map(tmp_path)
    nodes = {str(n["id"]): n["state"] for n in document["nodes"]}
    edges = document["edges"]
    owned = {(str(e["from"]), str(e["to"])) for e in edges if e["kind"] == "config_provided_by"}
    assert owned == {
        ("drupal.config::mymodule.settings", "drupal.module::mymodule"),
        ("drupal.config::othermodule.settings", "drupal.module::othermodule"),
    }
    assert nodes["drupal.module::mymodule"] == "mapped"
    assert nodes["drupal.module::othermodule"] == "referenced"
    assert "drupal.module::core" not in nodes


def _local_pack(root: Path, end: str) -> None:
    pack = root / ".periplus" / "packs" / "localcfg@0.0.1"
    (pack / "rules").mkdir(parents=True)
    (pack / "pack.yaml").write_text("pack: localcfg\nversion: 0.0.1\ndepends: [drupal_basic]\n")
    (pack / "rules" / "owner.yaml").write_text(
        "edge_kinds:\n- kind: owned_by\n  from: drupal.config_object\n  to: drupal.module\n"
        "rules:\n- rule: owner\n  reads: file\n  in: [module_config]\n"
        "  match: {file: '*', filetype: yml}\n  id: {from: file_stem}\n  emits:\n"
        f"  - edge: {{kind: owned_by, from: this_node, to: {end}}}\n  confidence: declared\n"
    )
    (root / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n  - localcfg@0.0.1\n"
    )


def test_an_empty_list_end_with_a_template_runs_and_one_without_is_refused(tmp_path: Path) -> None:
    _plant(tmp_path)
    _local_pack(tmp_path, "{from: [], template: '{config_owner}'}")
    owned = [e for e in _map(tmp_path)["edges"] if e["kind"] == "owned_by"]
    assert len(owned) == 3

    other = tmp_path / "other"
    other.mkdir()
    _plant(other)
    _local_pack(other, "{from: []}")
    report = run(
        start=other,
        env={"PERIPLUS_CONFIG_DIR": str(other / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    text = " ".join(str(p) for p in report.problems) + " ".join(
        str(s) for s in getattr(report, "skipped", ())
    )
    assert "from: [] with a template alone" in text, text
