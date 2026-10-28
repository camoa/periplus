"""Library attachments and drupalSettings keys written in a .module file or in a class."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from periplus.map import run
from periplus.preflight import check_runtime_dependencies

MODULE = Path("web/modules/custom/mymodule")

MODULE_FILE = """\
<?php

function mymodule_preprocess_page(array &$variables) {
  $variables['#attached']['library'][] = 'mymodule/one';
  $variables['#attached']['drupalSettings']['bracketKey'] = 1;
  $lib = 'mymodule/' . 'hidden';
  $variables['#attached']['library'][] = $lib;
}

function mymodule_build_thing() {
  $key = 'varKey';
  return [
    '#attached' => [
      'library' => ['mymodule/two'],
      'drupalSettings' => [
        'arrayKey' => ['nestedKey' => 1],
        $key => 2,
        $other => ['belowVar' => 1],
        'deepKey' => ['a' => ['b' => ['c' => ['d' => 1]]]],
        'ternKey' => $flag ? ['ternInner' => 1] : [],
        'callKey' => foo(['callInner' => 1]),
        'oldKey' => array('oldInnerA' => 1, 'oldInnerB' => 2),
        'castKey' => (array) ['castInner' => 1],
        'listKey' => ['x', ['listInner' => 1]],
        $var['subKey'] => ['subInner' => 1],
        'nextKey' =>
          ['nextInner' => 1],
      ],
    ],
  ];
}

function mymodule_two_lists() {
  return ['one' => ['#attached' => ['drupalSettings' => ['k1' => ['n' => 1]]]], 'two' => ['#attached' => ['drupalSettings' => ['k2' => 1]]]];
}
"""  # noqa: E501

CLASS_FILE = """\
<?php

namespace Drupal\\mymodule\\Controller;

class Page {
  public function view() {
    return ['#attached' => ['drupalSettings' => ['classKey' => ['w' => ['x' => ['y' => ['z' => 1]]]]]]];
  }
}
"""  # noqa: E501

SCRIPT = """\
Drupal.behaviors.mymoduleOne = {
  attach(context) {
    const value = drupalSettings.arrayKey;
  },
};
"""

PREPROCESS = "php.function::mymodule_preprocess_page"
BUILD = "php.function::mymodule_build_thing"
TWO = "php.function::mymodule_two_lists"
PAGE = "php.type::Drupal\\mymodule\\Controller\\Page"


@pytest.fixture
def document(tmp_path: Path) -> dict[str, list[dict[str, object]]]:
    module = tmp_path / MODULE
    (module / "js").mkdir(parents=True)
    (module / "src" / "Controller").mkdir(parents=True)
    (tmp_path / ".periplus").mkdir()
    (tmp_path / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n  - js_basic@0.0.1\n"
        "  - drupal_js_basic@0.0.1\n"
    )
    (module / "mymodule.info.yml").write_text(
        "name: My module\ntype: module\ncore_version_requirement: ^10\n"
    )
    (module / "mymodule.libraries.yml").write_text("one:\n  js:\n    js/one.js: {}\ntwo: {}\n")
    (module / "mymodule.module").write_text(MODULE_FILE)
    (module / "src" / "Controller" / "Page.php").write_text(CLASS_FILE)
    (module / "js" / "one.js").write_text(SCRIPT)
    report = run(
        start=tmp_path,
        env={"PERIPLUS_CONFIG_DIR": str(tmp_path / "cfg")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == (), report.problems
    assert report.not_executed == (), report.not_executed
    assert report.map_path is not None
    return json.loads(Path(report.map_path).read_text())  # type: ignore[no-any-return]


def _ends(document: dict[str, list[dict[str, object]]], kind: str) -> list[tuple[str, str]]:
    return sorted((str(e["from"]), str(e["to"])) for e in document["edges"] if e["kind"] == kind)


def test_a_library_attachment_starts_at_the_function_around_it_and_a_named_by_variable_gives_none(
    document: dict[str, list[dict[str, object]]],
) -> None:
    assert _ends(document, "attaches_library") == [
        (BUILD, "drupal.library::mymodule/two"),
        (PREPROCESS, "drupal.library::mymodule/one"),
    ]
    assert not any("hidden" in str(n["id"]) for n in document["nodes"])


def test_a_settings_key_is_first_level_only_in_every_array_shape_and_starts_at_its_function(
    document: dict[str, list[dict[str, object]]],
) -> None:
    keys = sorted(
        str(n["id"]) for n in document["nodes"] if str(n["id"]).startswith("drupal.js_setting::")
    )
    assert keys == [
        "drupal.js_setting::" + name
        for name in (
            "arrayKey", "bracketKey", "callKey", "castKey", "classKey", "deepKey", "k1", "k2",
            "listKey", "nextKey", "oldKey", "ternKey",
        )
    ]
    assert not any("Inner" in str(n["id"]) or "subKey" in str(n["id"]) for n in document["nodes"])
    assert _ends(document, "provides_setting") == [
        (BUILD, "drupal.js_setting::arrayKey"),
        (BUILD, "drupal.js_setting::callKey"),
        (BUILD, "drupal.js_setting::castKey"),
        (BUILD, "drupal.js_setting::deepKey"),
        (BUILD, "drupal.js_setting::listKey"),
        (BUILD, "drupal.js_setting::nextKey"),
        (BUILD, "drupal.js_setting::oldKey"),
        (BUILD, "drupal.js_setting::ternKey"),
        (PREPROCESS, "drupal.js_setting::bracketKey"),
        (TWO, "drupal.js_setting::k1"),
        (TWO, "drupal.js_setting::k2"),
        (PAGE, "drupal.js_setting::classKey"),
    ]


def test_a_behavior_that_reads_a_key_meets_the_node_the_php_side_made(
    document: dict[str, list[dict[str, object]]],
) -> None:
    assert _ends(document, "reads_setting") == [
        ("drupal.js_behavior::mymoduleOne", "drupal.js_setting::arrayKey")
    ]
