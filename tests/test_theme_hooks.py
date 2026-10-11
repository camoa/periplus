"""PHP that renders a template links to it: '#theme' values, hook_theme entries and their template
key, and an entity template suggestion to its bundle."""

from __future__ import annotations

import json
from pathlib import Path

from periplus.map import run
from periplus.preflight import check_runtime_dependencies

MODULE = Path("web/modules/custom/mymodule")

CONTROLLER = """\
<?php

namespace Drupal\\mymodule\\Controller;

final class CardController {

  public function page(): array {
    return ['#theme' => 'my_card', '#title' => 'x'];
  }

  public function plain(): array {
    return ['#theme' => 'plain_box'];
  }

}
"""

MODULE_FILE = """\
<?php

/**
 * Implements hook_theme().
 */
function mymodule_theme($existing, $type, $theme, $path): array {
  return [
    'my_card' => [
      'variables' => ['title' => NULL, 'items' => ['a' => [1]]],
      'template' => 'my-card-alt',
    ],
    'plain_box' => [
      'variables' => ['title' => NULL, 'items' => ['a' => [1]]],
    ],
    'func_only' => [
      'variables' => ['x' => NULL],
      'function' => 'theme_func_only',
    ],
  ];
}

function mymodule_other(): array {
  return ['not_a_hook' => ['variables' => ['x' => NULL]]];
}
"""


def _plant(root: Path) -> None:
    module = root / MODULE
    (module / "src" / "Controller").mkdir(parents=True)
    (module / "templates").mkdir()
    (module / "config" / "install").mkdir(parents=True)
    (root / ".periplus").mkdir()
    (root / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n"
    )
    (module / "mymodule.info.yml").write_text(
        "name: My module\ntype: module\ncore_version_requirement: ^10\n"
    )
    (module / "mymodule.module").write_text(MODULE_FILE)
    (module / "src" / "Controller" / "CardController.php").write_text(CONTROLLER)
    templates = module / "templates"
    for name in (
        "my-card-alt",
        "plain-box",
        "node--article--teaser",
        "node--full",
        "node--12",
        "node--12--teaser",
        "field--node--title--article",
    ):
        (templates / f"{name}.html.twig").write_text("{# A comment first. #}\n<p></p>\n")
    (module / "config" / "install" / "node.type.article.yml").write_text(
        "langcode: en\nstatus: true\ndependencies: {}\ntype: article\nname: Article\n"
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


def _edges(document: dict[str, list[dict[str, object]]], kind: str) -> set[tuple[str, str, str]]:
    return {
        (str(e["from"]), str(e["to"]), str(e["provenance"][0]["confidence"]))
        for e in document["edges"]
        if e["kind"] == kind
    }


def test_a_class_links_to_the_theme_hook_its_render_array_names(tmp_path: Path) -> None:
    _plant(tmp_path)
    document = _map(tmp_path)
    nodes = {str(n["id"]): n["state"] for n in document["nodes"]}
    assert _edges(document, "renders_theme_hook") == {
        (
            "php.type::Drupal\\mymodule\\Controller\\CardController",
            "drupal.theme_hook::my_card",
            "declared",
        ),
        (
            "php.type::Drupal\\mymodule\\Controller\\CardController",
            "drupal.theme_hook::plain_box",
            "declared",
        ),
    }
    assert nodes["drupal.theme_hook::my_card"] == "mapped"
    assert nodes["drupal.theme_hook::plain_box"] == "mapped"
    assert nodes["drupal.theme_hook::func_only"] == "mapped"
    assert "drupal.theme_hook::not_a_hook" not in nodes
    assert "drupal.theme_hook::variables" not in nodes


def test_a_theme_hook_links_to_its_template_key_or_to_its_default_name(tmp_path: Path) -> None:
    _plant(tmp_path)
    document = _map(tmp_path)
    assert _edges(document, "theme_hook_template") == {
        ("drupal.theme_hook::my_card", "drupal.template::my-card-alt", "declared"),
        ("drupal.theme_hook::plain_box", "drupal.template::plain-box", "inferred"),
    }


def test_an_entity_template_suggestion_links_to_its_bundle_and_a_view_mode_or_id_does_not(
    tmp_path: Path,
) -> None:
    _plant(tmp_path)
    document = _map(tmp_path)
    assert _edges(document, "suggests_bundle") == {
        ("drupal.template::node--article--teaser", "drupal.bundle::node.article", "inferred"),
    }
    nodes = {str(n["id"]): n["state"] for n in document["nodes"]}
    assert nodes["drupal.bundle::node.article"] == "mapped"


TRAIT = """\
<?php

namespace Drupal\\mymodule;

trait CardTrait {

  public function card(): array {
    return ['#theme' => 'my_card'];
  }

}
"""


def test_a_trait_links_to_the_theme_hook_its_render_array_names(tmp_path: Path) -> None:
    _plant(tmp_path)
    (tmp_path / MODULE / "src" / "CardTrait.php").write_text(TRAIT)
    document = _map(tmp_path)
    assert (
        "php.type::Drupal\\mymodule\\CardTrait",
        "drupal.theme_hook::my_card",
        "declared",
    ) in _edges(document, "renders_theme_hook")


EXTRA_THEME = """\
<?php

function mymodule_extra_theme(): array {
  return [
    'with_file' => [
      'file' => 'mymodule.pages.inc',
      'variables' => ['link' => ['path' => NULL]],
    ],
  ];
}
"""

EXTRA_CONTROLLER = """\
<?php

namespace Drupal\\mymodule\\Controller;

final class OtherController {

  public function page(): array {
    return ['#theme' => 'undeclared_box'];
  }

}
"""


def _plant_extra(root: Path) -> dict[str, list[dict[str, object]]]:
    _plant(root)
    (root / MODULE / "mymodule.extra.inc").write_text(EXTRA_THEME)
    (root / MODULE / "src" / "Controller" / "OtherController.php").write_text(EXTRA_CONTROLLER)
    return _map(root)


def test_a_name_no_hook_declares_and_a_template_no_file_holds_end_referenced(
    tmp_path: Path,
) -> None:
    document = _plant_extra(tmp_path)
    nodes = {str(n["id"]): n["state"] for n in document["nodes"]}
    assert nodes["drupal.theme_hook::undeclared_box"] == "referenced"
    assert (
        "drupal.theme_hook::with_file",
        "drupal.template::with-file",
        "inferred",
    ) in _edges(document, "theme_hook_template")
    assert nodes["drupal.template::with-file"] == "referenced"


def test_an_entry_opening_with_file_maps_and_a_variable_default_named_path_does_not(
    tmp_path: Path,
) -> None:
    document = _plant_extra(tmp_path)
    nodes = {str(n["id"]): n["state"] for n in document["nodes"]}
    assert nodes["drupal.theme_hook::with_file"] == "mapped"
    assert "drupal.theme_hook::link" not in nodes
