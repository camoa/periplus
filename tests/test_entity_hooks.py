"""A hook named <type>_<operation>, such as node_presave, links to the entity type it acts on."""

from __future__ import annotations

import json
from pathlib import Path

from periplus.map import run
from periplus.preflight import check_runtime_dependencies

MODULE = Path("web/modules/custom/mymodule")

MODULE_FILE = """\
<?php

function mymodule_node_presave($node): void {}

function mymodule_my_entity_insert($entity): void {}

function mymodule_node_create_access($account, $context, $bundle): void {}

function mymodule_entity_view(array &$build, $entity, $display, $view_mode): void {}

function mymodule_block_view($delta): array {
  return [];
}

function mymodule_views_pre_view($view, $display_id, array &$args): void {}

function mymodule_form_alter(&$form, $form_state, $form_id): void {}

function mymodule_preprocess_views_view(&$variables): void {}

function mymodule_theme_suggestions_views_view_alter(array &$suggestions, array $variables): void {}
"""

HOOK_CLASS = """\
<?php

namespace Drupal\\mymodule\\Hook;

use Drupal\\Core\\Hook\\Attribute\\Hook;

class MyHooks {

  #[Hook('node_update')]
  public function nodeUpdate($node): void {}

  #[Hook(hook: 'my_entity_delete')]
  public function myEntityDelete($entity): void {}

  #[Hook('preprocess_views_view')]
  public function preprocessViewsView(array &$variables): void {}

  #[Hook('jsonapi_node_filter_access')]
  public function jsonapiNodeFilterAccess($entity_type, $account): array {}

}
"""

ENTITY_CLASS = """\
<?php

namespace Drupal\\mymodule\\Entity;

use Drupal\\Core\\Entity\\Attribute\\ContentEntityType;
use Drupal\\Core\\Entity\\ContentEntityBase;

#[ContentEntityType(id: 'my_entity', label: 'My entity')]
class MyEntity extends ContentEntityBase {}
"""


def _plant(root: Path) -> None:
    module = root / MODULE
    module.mkdir(parents=True)
    (root / ".periplus").mkdir()
    (root / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n"
    )
    (module / "mymodule.info.yml").write_text(
        "name: My module\ntype: module\ncore_version_requirement: ^10\n"
    )
    (module / "mymodule.module").write_text(MODULE_FILE)
    (module / "src" / "Hook").mkdir(parents=True)
    (module / "src" / "Hook" / "MyHooks.php").write_text(HOOK_CLASS)
    (module / "src" / "Entity").mkdir()
    (module / "src" / "Entity" / "MyEntity.php").write_text(ENTITY_CLASS)


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


def test_an_entity_hook_links_to_the_entity_type_it_names(tmp_path: Path) -> None:
    _plant(tmp_path)
    document = _map(tmp_path)
    edges = {
        (str(e["from"]), str(e["to"]), str(e["provenance"][0]["confidence"]))
        for e in document["edges"]
        if e["kind"] == "hook_acts_on_entity_type"
    }
    assert edges == {
        ("drupal.hook::node_presave", "drupal.entity_type::node", "inferred"),
        ("drupal.hook::my_entity_insert", "drupal.entity_type::my_entity", "inferred"),
        ("drupal.hook::node_create_access", "drupal.entity_type::node", "inferred"),
        ("drupal.hook::node_update", "drupal.entity_type::node", "inferred"),
        ("drupal.hook::my_entity_delete", "drupal.entity_type::my_entity", "inferred"),
    }
    # The edge lands on the entity type the module declares, not on a second node of that id.
    my_entity = [n for n in document["nodes"] if n["id"] == "drupal.entity_type::my_entity"]
    assert len(my_entity) == 1, my_entity
    assert my_entity[0]["type"] == "drupal.content_entity_type"
    hooks = {str(n["id"]) for n in document["nodes"] if n["type"] == "drupal.hook"}
    # The hooks left without an edge are still mapped as hooks.
    assert {
        "drupal.hook::entity_view",
        "drupal.hook::block_view",
        "drupal.hook::views_pre_view",
        "drupal.hook::form_alter",
        "drupal.hook::preprocess_views_view",
        "drupal.hook::theme_suggestions_views_view_alter",
        "drupal.hook::jsonapi_node_filter_access",
    } <= hooks
