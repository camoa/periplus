"""Drupal calls that name a service or an entity type by a text literal, on one planted module.

A controller calls the service my_module.helper and the content entity type thing in many written
forms. The module is mapped once and each test reads one part of the result.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from periplus.map import MapReport, run
from periplus.preflight import check_runtime_dependencies

MODULE = Path("web/modules/custom/my_module")

HELPER = r"""<?php

namespace Drupal\my_module;

class Helper {

  public function run() {
  }

}
"""
HELPER_CONTROLLER = r"""<?php

namespace Drupal\my_module\Controller;

class HelperController {

  protected $helper;

  public function __construct() {
    $this->helper = \Drupal::service("my_module.helper");
  }

  public function go() {
    $this->helper->run();
  }

}
"""
SERVICES = """\
services:
  my_module.helper:
    class: Drupal\\my_module\\Helper
"""
THING = r"""<?php

namespace Drupal\my_module\Entity;

use Drupal\Core\Entity\Attribute\ContentEntityType;
use Drupal\Core\Entity\ContentEntityBase;

#[ContentEntityType(id: 'thing', label: 'Thing')]
class Thing extends ContentEntityBase {
}
"""
CONTROLLER = r"""<?php

namespace Drupal\my_module\Controller;

class ThingController {

  public function services($name) {
    $helper = \Drupal::service('my_module.helper');
    $path = \Drupal::service('path.current');
    $dq = \Drupal::service("dq.service");
    $other = \Drupal::service($name);
    $not = Other::service('my_module.other');
  }

  public function entities($type) {
    $query = \Drupal::entityQuery('thing');
    $dq_query = \Drupal::entityQuery("dq_query");
    $mine = $this->entityTypeManager->getStorage('thing');
    $dq_mine = $this->entityTypeManager->getStorage("dq_storage");
    $nodes = \Drupal::entityTypeManager()->getStorage('node');
    $safe = $this->entityTypeManager?->getStorage('safe_thing');
    $bar = $this->other->getStorage('bar');
    $any = $this->entityTypeManager->getStorage($type);
  }

}
"""
FORM = r"""<?php

namespace Drupal\my_module\Form;

use Symfony\Component\DependencyInjection\ContainerInterface;

class ThingForm {

  public static function create(ContainerInterface $container) {
    $helper = $container->get('my_module.helper');
    $manager = $container->get('entity_type.manager');
    $any = $container->get($name);
    $dq = $container->get("dq.get");
    $dq_any = $container->get("$name");
  }

  public function setUp() {
    $path = $this->container->get('path.current');
    $global = \Drupal::getContainer()->get('my_module.helper');
  }

  public function reads() {
    $a = $this->getContainer()->get('a');
    $b = static::getContainer()->get('b');
    $c = self::getContainer()->get('c');
    $d = $container?->get('d');
    $e = \Drupal::getContainer()
      ->get('e');
  }

  public function negatives($request, $form_state, $other) {
    $a = $this->config->get('my_module.settings');
    $b = $request->get('page');
    $c = $form_state->get('step');
    $d = $other->get('my_module.helper');
    $e = Drush::getContainer()->get('drush.helper');
    $e2 = $containerBuilder->get('my_module.helper');
  }

}
"""
PROCEDURAL = r"""<?php

function helper_lookup() {
  $s = \Drupal::getContainer()->get('my_module.helper');
}
"""

FILES = {
    "src/Helper.php": HELPER,
    "src/Controller/HelperController.php": HELPER_CONTROLLER,
    "my_module.services.yml": SERVICES,
    "src/Entity/Thing.php": THING,
    "src/Controller/ThingController.php": CONTROLLER,
    "src/Form/ThingForm.php": FORM,
    "my_module.module": PROCEDURAL,
}

NS = "Drupal\\my_module\\"
SERVICES_M = f"php.method::{NS}Controller\\ThingController::services"
ENTITIES = f"php.method::{NS}Controller\\ThingController::entities"
CREATE = f"php.method::{NS}Form\\ThingForm::create"
SET_UP = f"php.method::{NS}Form\\ThingForm::setUp"
READS = f"php.method::{NS}Form\\ThingForm::reads"
HELPER_LOOKUP = "php.function::helper_lookup"
CONSTRUCT = f"php.method::{NS}Controller\\HelperController::__construct"


def _line(source: str, text: str) -> int:
    return next(n for n, found in enumerate(source.splitlines(), 1) if found.strip() == text)


@pytest.fixture(scope="module")
def mapped(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict[str, Any], MapReport]:
    root = tmp_path_factory.mktemp("drupal_calls")
    (root / ".periplus").mkdir()
    (root / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n"
    )
    for name, text in FILES.items():
        path = root / MODULE / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == () and report.not_executed == (), report
    assert report.map_path is not None
    return json.loads(Path(report.map_path).read_text()), report


def _uses(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [e for e in document["edges"] if e["kind"] in ("uses_service", "uses_entity_type")]


def test_each_written_form_of_a_lookup_gives_one_edge_at_its_line(
    mapped: tuple[dict[str, Any], MapReport],
) -> None:
    """Single and double quotes, through ->, ?->, a container written four ways and a call split
    over two lines; other receivers, a variable argument and Other::service give nothing."""
    document, _ = mapped

    def ctl(text: str) -> int:
        return _line(CONTROLLER, text)

    def form(text: str) -> int:
        return _line(FORM, text)

    found = {
        (e["kind"], e["from"], e["to"], place["line"])
        for e in _uses(document)
        for place in e["locations"]
    }
    assert found == {
        (
            "uses_service",
            SERVICES_M,
            "drupal.service::my_module.helper",
            ctl("$helper = \\Drupal::service('my_module.helper');"),
        ),
        (
            "uses_service",
            SERVICES_M,
            "drupal.service::path.current",
            ctl("$path = \\Drupal::service('path.current');"),
        ),
        (
            "uses_service",
            SERVICES_M,
            "drupal.service::dq.service",
            ctl('$dq = \\Drupal::service("dq.service");'),
        ),
        (
            "uses_entity_type",
            ENTITIES,
            "drupal.entity_type::dq_query",
            ctl('$dq_query = \\Drupal::entityQuery("dq_query");'),
        ),
        (
            "uses_entity_type",
            ENTITIES,
            "drupal.entity_type::dq_storage",
            ctl('$dq_mine = $this->entityTypeManager->getStorage("dq_storage");'),
        ),
        (
            "uses_service",
            CREATE,
            "drupal.service::dq.get",
            form('$dq = $container->get("dq.get");'),
        ),
        (
            "uses_entity_type",
            ENTITIES,
            "drupal.entity_type::thing",
            ctl("$query = \\Drupal::entityQuery('thing');"),
        ),
        (
            "uses_entity_type",
            ENTITIES,
            "drupal.entity_type::thing",
            ctl("$mine = $this->entityTypeManager->getStorage('thing');"),
        ),
        (
            "uses_entity_type",
            ENTITIES,
            "drupal.entity_type::node",
            ctl("$nodes = \\Drupal::entityTypeManager()->getStorage('node');"),
        ),
        (
            "uses_service",
            ENTITIES,
            "drupal.service::entity_type.manager",
            ctl("$nodes = \\Drupal::entityTypeManager()->getStorage('node');"),
        ),
        (
            "uses_entity_type",
            ENTITIES,
            "drupal.entity_type::safe_thing",
            ctl("$safe = $this->entityTypeManager?->getStorage('safe_thing');"),
        ),
        (
            "uses_service",
            CREATE,
            "drupal.service::my_module.helper",
            form("$helper = $container->get('my_module.helper');"),
        ),
        (
            "uses_service",
            CREATE,
            "drupal.service::entity_type.manager",
            form("$manager = $container->get('entity_type.manager');"),
        ),
        (
            "uses_service",
            SET_UP,
            "drupal.service::path.current",
            form("$path = $this->container->get('path.current');"),
        ),
        (
            "uses_service",
            SET_UP,
            "drupal.service::my_module.helper",
            form("$global = \\Drupal::getContainer()->get('my_module.helper');"),
        ),
        ("uses_service", READS, "drupal.service::a", form("$a = $this->getContainer()->get('a');")),
        (
            "uses_service",
            READS,
            "drupal.service::b",
            form("$b = static::getContainer()->get('b');"),
        ),
        ("uses_service", READS, "drupal.service::c", form("$c = self::getContainer()->get('c');")),
        ("uses_service", READS, "drupal.service::d", form("$d = $container?->get('d');")),
        ("uses_service", READS, "drupal.service::e", form("$e = \\Drupal::getContainer()")),
        (
            "uses_service",
            HELPER_LOOKUP,
            "drupal.service::my_module.helper",
            _line(PROCEDURAL, "$s = \\Drupal::getContainer()->get('my_module.helper');"),
        ),
        (
            "uses_service",
            CONSTRUCT,
            "drupal.service::my_module.helper",
            _line(HELPER_CONTROLLER, '$this->helper = \\Drupal::service("my_module.helper");'),
        ),
    }


def test_an_explicit_name_gives_declared_and_a_name_read_from_the_receiver_gives_inferred(
    mapped: tuple[dict[str, Any], MapReport],
) -> None:
    document, _ = mapped
    confidence = {
        (e["to"], p["rule"], p["confidence"]) for e in _uses(document) for p in e["provenance"]
    }
    assert confidence == {
        ("drupal.service::my_module.helper", "service_call", "declared"),
        ("drupal.service::path.current", "service_call", "declared"),
        ("drupal.service::dq.service", "service_call", "declared"),
        ("drupal.entity_type::dq_query", "entity_query_call", "declared"),
        ("drupal.entity_type::dq_storage", "storage_call", "inferred"),
        ("drupal.service::dq.get", "container_get_call", "inferred"),
        ("drupal.entity_type::thing", "entity_query_call", "declared"),
        ("drupal.entity_type::thing", "storage_call", "inferred"),
        ("drupal.entity_type::node", "storage_call", "inferred"),
        ("drupal.entity_type::safe_thing", "storage_nullsafe_call", "inferred"),
        ("drupal.service::my_module.helper", "container_get_call", "inferred"),
        ("drupal.service::entity_type.manager", "container_get_call", "inferred"),
        ("drupal.service::path.current", "container_get_call", "inferred"),
        ("drupal.service::entity_type.manager", "drupal_shortcut_call", "inferred"),
        ("drupal.service::a", "container_get_call", "inferred"),
        ("drupal.service::b", "container_get_call", "inferred"),
        ("drupal.service::c", "container_get_call", "inferred"),
        ("drupal.service::d", "container_nullsafe_get_call", "inferred"),
        ("drupal.service::e", "container_get_call", "inferred"),
    }


def test_a_declared_name_ends_at_a_mapped_node_and_an_undeclared_one_at_a_referenced_node(
    mapped: tuple[dict[str, Any], MapReport],
) -> None:
    document, _ = mapped
    nodes = {n["id"]: n for n in document["nodes"]}
    assert nodes["drupal.service::my_module.helper"]["state"] == "mapped"
    for referenced in (
        "drupal.service::path.current",
        "drupal.service::entity_type.manager",
        "drupal.service::dq.service",
        "drupal.entity_type::node",
        "drupal.entity_type::dq_query",
        "drupal.entity_type::dq_storage",
    ):
        assert nodes[referenced]["state"] == "referenced", nodes[referenced]
    assert nodes["drupal.entity_type::thing"]["type"] == "drupal.content_entity_type"
    assert nodes[HELPER_LOOKUP]["type"] == "php.function"


def test_a_variable_argument_gives_a_skipped_row_and_no_edge(
    mapped: tuple[dict[str, Any], MapReport],
) -> None:
    _, report = mapped
    rules = ("service_call", "entity_query_call", "storage_call", "container_get_call")
    skipped = sorted((rule, line) for _, line, rule, _ in report.skipped if rule in rules)
    assert skipped == sorted(
        [
            ("service_call", _line(CONTROLLER, "$other = \\Drupal::service($name);")),
            (
                "storage_call",
                _line(CONTROLLER, "$any = $this->entityTypeManager->getStorage($type);"),
            ),
            ("container_get_call", _line(FORM, "$any = $container->get($name);")),
            ("container_get_call", _line(FORM, '$dq_any = $container->get("$name");')),
        ]
    )


def test_a_class_whose_property_holds_a_service_calls_the_services_method_through_it(
    mapped: tuple[dict[str, Any], MapReport],
) -> None:
    document, _ = mapped
    calls = sorted(
        (e["to"], [place["line"] for place in e["locations"]], [p["rule"] for p in e["provenance"]])
        for e in document["edges"]
        if e["kind"] == "calls" and e["from"] == f"php.method::{NS}Controller\\HelperController::go"
    )
    assert calls == [
        (
            f"php.method::{NS}Helper::run",
            [_line(HELPER_CONTROLLER, "$this->helper->run();")],
            ["calls_through_service_property"],
        )
    ]
