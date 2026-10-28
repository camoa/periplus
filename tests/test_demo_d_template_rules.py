"""An end from the file's path alone, and a component template that attaches a library."""

from __future__ import annotations

import json
from pathlib import Path

from periplus.map import run
from periplus.preflight import check_runtime_dependencies

MODULE = Path("web/modules/custom/mymodule")

PACK = """\
pack: owner
version: 0.0.1
depends: []
folders:
  config: ./config
files:
  types:
    yml:
      endings: [yml]
      reader: data
      format: yaml
      path_values:
        owner:
          pattern: '^(?:.*/)?(?<owner>[^/.]+)\\.[^/]+\\.yml$'
          template: '{owner}'
"""

RULES = """\
node_types:
- name: app.config
  id_namespace: app.config
- name: app.module
  id_namespace: app.module
edge_kinds:
- kind: provided_by
  from: app.config
  to: app.module
rules:
- rule: config_file
  reads: file
  in: [config]
  match: {file: '*', filetype: yml}
  id: {template: '{file_stem}'}
  emits: [{node: {type: app.config}}]
  confidence: declared
- rule: config_provider
  reads: file
  in: [config]
  match: {file: '*', filetype: yml}
  id: {template: '{file_stem}'}
  emits:
  - edge:
      kind: provided_by
      from: this_node
      to: {from: [], template: '{owner}'}
  confidence: inferred
"""


def _map(root: Path) -> dict[str, list[dict[str, object]]]:
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "cfg")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == (), report.problems
    assert report.not_executed == (), report.not_executed
    assert report.map_path is not None
    return json.loads(Path(report.map_path).read_text())  # type: ignore[no-any-return]


def test_a_path_only_end_links_a_named_file_to_its_owner_and_a_plain_file_to_none(
    tmp_path: Path,
) -> None:
    pack = tmp_path / ".periplus" / "packs" / "owner@0.0.1"
    (pack / "rules").mkdir(parents=True)
    (pack / "pack.yaml").write_text(PACK)
    (pack / "rules" / "config.yaml").write_text(RULES)
    (tmp_path / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks: [owner@0.0.1]\n"
    )
    config = tmp_path / "config"
    config.mkdir()
    (config / "mymod.settings.yml").write_text("name: x\n")
    (config / "othermod.mail.yml").write_text("id: a\n")
    (config / "plain.yml").write_text("id: b\n")

    document = _map(tmp_path)

    edges = sorted((e["from"], e["kind"], e["to"]) for e in document["edges"])
    assert edges == [
        ("app.config::mymod.settings", "provided_by", "app.module::mymod"),
        ("app.config::othermod.mail", "provided_by", "app.module::othermod"),
    ]
    states = {n["id"]: n["state"] for n in document["nodes"]}
    assert states["app.config::plain"] == "mapped"
    assert states["app.module::mymod"] == "referenced"


def test_a_component_template_that_attaches_a_library_gives_a_component_edge_and_no_template_node(
    tmp_path: Path,
) -> None:
    module = tmp_path / MODULE
    (module / "components" / "card").mkdir(parents=True)
    (module / "templates").mkdir()
    (tmp_path / ".periplus").mkdir()
    (tmp_path / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n  - drupal_js_basic@0.0.1\n"
    )
    (module / "mymodule.info.yml").write_text(
        "name: My module\ntype: module\ncore_version_requirement: ^10\n"
    )
    (module / "mymodule.libraries.yml").write_text("card:\n  js:\n    js/card.js: {}\n")
    (module / "components" / "card" / "card.component.yml").write_text("name: Card\n")
    attach = "<div>{{ attach_library('mymodule/card') }}</div>\n"
    (module / "components" / "card" / "card.twig").write_text(attach)
    (module / "templates" / "mymodule-page.html.twig").write_text(attach)

    document = _map(tmp_path)

    library = "drupal.library::mymodule/card"
    nodes = {str(n["id"]): n["state"] for n in document["nodes"]}
    assert nodes["drupal.component::card"] == "mapped"
    assert "drupal.template::card" not in nodes
    attaches = [e for e in document["edges"] if e["to"] == library and "attaches" in str(e["kind"])]
    assert sorted((str(e["kind"]), str(e["from"])) for e in attaches) == [
        ("component_attaches_library", "drupal.component::card"),
        ("template_attaches_library", "drupal.template::mymodule-page"),
    ]
    template = next(e for e in attaches if e["kind"] == "template_attaches_library")
    assert [row["rule"] for row in template["provenance"]] == [  # type: ignore[attr-defined]
        "library_attached_in_template"
    ]
