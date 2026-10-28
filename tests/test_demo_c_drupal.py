"""drupal_basic's rules on planted modules: procedural hooks, table steps, constant arguments,
the core-class boundary, typed managers and path strings.

The service and entity calls that name a text literal are in test_demo_c_drupal_calls.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from periplus.cli import main
from periplus.errors import ExitCode
from periplus.map import MapReport, run
from periplus.preflight import check_runtime_dependencies

DRUPAL = "  - drupal_basic@0.3.0\n"
MODULE = Path("web/modules/custom/my_module")


def _plant(root: Path, files: dict[str, str], packs: str = DRUPAL) -> None:
    (root / ".periplus").mkdir(exist_ok=True)
    (root / ".periplus" / "settings.yml").write_text("periplus_version: 0\npacks:\n" + packs)
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def _map(root: Path, name: str = "map.json") -> tuple[dict[str, Any], MapReport]:
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path(name),
    )
    assert report.problems == () and report.not_executed == (), report
    assert report.map_path is not None
    return json.loads(Path(report.map_path).read_text()), report


def _line(source: str, text: str) -> int:
    return next(n for n, found in enumerate(source.splitlines(), 1) if found.strip() == text)


# --- procedural hooks -------------------------------------------------------------------------

THEME = Path("web/themes/custom/my_theme")
HOOK_FILES = {
    str(MODULE / "mymod.module"): """\
<?php

function mymod_cron() {
}

function mymod_form_alter(&$form) {
}

function mymod_settings_submit($form) {
}

function helper_thing() {
}
""",
    str(
        THEME / "my_theme.info.yml"
    ): "name: My theme\ntype: theme\ncore_version_requirement: ^11\n",
    str(THEME / "my_theme.theme"): """\
<?php

function my_theme_preprocess_page(&$variables) {
}
""",
    str(THEME / "includes/content.theme"): """\
<?php

function my_theme_preprocess_node(&$variables) {
}

function other_helper() {
}
""",
    str(THEME / "preprocess/html.preprocess.inc"): """\
<?php

function my_theme_preprocess_html(&$variables) {
}
""",
    str(MODULE / "mymod.post_update.php"): """\
<?php

function mymod_post_update_fix_things(&$sandbox) {
}
""",
    str(MODULE / "mymod.deploy.php"): """\
<?php

function mymod_deploy_seed(&$sandbox) {
}
""",
}


def test_a_procedural_hook_is_mapped_by_its_function_name_and_implements_it(
    tmp_path: Path,
) -> None:
    """The file's name, an underscore, then the hook: cron, form_alter, settings_submit, the theme
    hooks by the theme's own name or folder name, and the post_update and deploy hooks by pattern.
    A function that does not start with the file's name gives no hook and no edge."""
    _plant(tmp_path, HOOK_FILES)
    document, report = _map(tmp_path)
    # The include-hook rules find no theme_name in the theme's own .theme file: one row each.
    own = str(THEME / "my_theme.theme")
    assert sorted((f, r, why) for f, _, r, why in report.skipped) == [
        (own, "hook_from_theme_include", "the id source theme_name is absent"),
        (own, "theme_include_implements_hook", "the id source theme_name is absent"),
    ]
    # hook: (file name, function name)
    wanted = {
        "cron": ("mymod.module", "mymod_cron"),
        "form_alter": ("mymod.module", "mymod_form_alter"),
        "settings_submit": ("mymod.module", "mymod_settings_submit"),
        "preprocess_page": ("my_theme.theme", "my_theme_preprocess_page"),
        "preprocess_node": ("includes/content.theme", "my_theme_preprocess_node"),
        "preprocess_html": ("preprocess/html.preprocess.inc", "my_theme_preprocess_html"),
        "post_update_NAME": ("mymod.post_update.php", "mymod_post_update_fix_things"),
        "deploy_NAME": ("mymod.deploy.php", "mymod_deploy_seed"),
    }
    expected = {}
    for hook, (name, function) in wanted.items():
        path = next(p for p in HOOK_FILES if p.endswith(name))
        source = HOOK_FILES[path]
        line = next(
            n
            for n, text in enumerate(source.splitlines(), 1)
            if text.startswith(f"function {function}(")
        )
        expected[hook] = (path, line, ("inferred",))
    hooks = {
        node["id"].removeprefix("drupal.hook::"): (
            place["file"],
            place["line"],
            tuple(p.get("confidence") for p in node["provenance"]),
        )
        for node in document["nodes"]
        if node["type"] == "drupal.hook"
        for place in node["locations"]
    }
    assert hooks == expected
    edges = sorted(
        (edge["kind"], edge["from"], edge["to"], [p["confidence"] for p in edge["provenance"]])
        for edge in document["edges"]
    )
    assert edges == sorted(
        ("implements_hook", f"php.function::{function}", f"drupal.hook::{hook}", ["inferred"])
        for hook, (_, function) in wanted.items()
    )
    ids = {n["id"] for n in document["nodes"] if n["type"] == "drupal.hook"}
    assert "drupal.hook::" not in ids and not [i for i in ids if "helper" in i], ids


# --- table steps ------------------------------------------------------------------------------

TABLE_CONTROLLER = r"""<?php

namespace Drupal\my_module\Controller;

use Drupal\user\Entity\User;

class ThingController {

  public function run() {
    \Drupal::logger('x')->notice('y');
    $account = User::load(1);
  }

}
"""
TABLE_PATH = str(MODULE / "src/Controller/ThingController.php")


def test_a_shortcut_and_an_entity_class_end_at_the_names_the_tables_give(tmp_path: Path) -> None:
    """Drupal::logger gives logger.factory and User::load gives user, both inferred and both
    ends referenced."""
    _plant(tmp_path, {TABLE_PATH: TABLE_CONTROLLER})
    document, _ = _map(tmp_path)
    run_method = "php.method::Drupal\\my_module\\Controller\\ThingController::run"
    found = {
        (e["kind"], e["from"], e["to"], place["line"], p["rule"], p["confidence"])
        for e in document["edges"]
        if e["kind"] in ("uses_service", "uses_entity_type")
        for place in e["locations"]
        for p in e["provenance"]
    }
    assert found == {
        (
            "uses_service",
            run_method,
            "drupal.service::logger.factory",
            _line(TABLE_CONTROLLER, "\\Drupal::logger('x')->notice('y');"),
            "drupal_shortcut_call",
            "inferred",
        ),
        (
            "uses_entity_type",
            run_method,
            "drupal.entity_type::user",
            _line(TABLE_CONTROLLER, "$account = User::load(1);"),
            "entity_class_static_call",
            "inferred",
        ),
    }
    nodes = {n["id"]: n["state"] for n in document["nodes"]}
    assert nodes["drupal.service::logger.factory"] == "referenced"
    assert nodes["drupal.entity_type::user"] == "referenced"


def test_a_rutter_whose_step_names_a_table_no_pack_declares_is_refused_with_exit_26(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    pack = ".periplus/packs/own@0.0.1"
    _plant(
        tmp_path,
        {
            f"{pack}/pack.yaml": "pack: own\nversion: 0.0.1\ndepends: [drupal_basic]\n",
            f"{pack}/rules/own.yaml": """\
rules:
- rule: unknown_table
  reads: file
  in: [source]
  match:
    reference: scoped_call_expression
    name_child: [scope, name]
    filetype: php
  emits:
  - edge:
      kind: uses_service
      from: enclosing_declaration
      to: {resolve: [lookup_last_segment_in: no_such_table], types: [drupal.service]}
  confidence: inferred
""",
            "src/.keep": "",
        },
        packs="  - own@0.0.1\n",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "config"))
    assert main(["map", "--output", "bad.json"]) == int(ExitCode.RULE_NOT_EXECUTABLE) == 26
    assert "no_such_table" in capsys.readouterr().out


# --- a class constant as a call argument ------------------------------------------------------

CONSTANT_USE = r"""<?php

namespace Drupal\my_module\Controller;

use Drupal\my_module\Entity\MyType;

class ThingController {

  public function run() {
    $this->entityTypeManager->getStorage(MyType::ENTITY_TYPE);
  }

}
"""
CONSTANT_DECLARATION = r"""<?php

namespace Drupal\my_module\Entity;

class MyType {

  const ENTITY_TYPE = 'my_type';

}
"""


def test_a_class_constant_argument_resolves_to_the_text_a_later_file_declares(
    tmp_path: Path,
) -> None:
    """The declaring file sorts after the controller, so the value is read from a file the run
    reached later; the storage call still gives an inferred edge and no skipped row."""
    use = str(MODULE / "src/Controller/ThingController.php")
    declared = str(MODULE / "src/Entity/MyType.php")
    assert use < declared
    _plant(tmp_path, {use: CONSTANT_USE, declared: CONSTANT_DECLARATION})
    document, report = _map(tmp_path)
    found = {
        (e["from"], e["to"], place["line"], p["rule"], p["confidence"])
        for e in document["edges"]
        if e["kind"] == "uses_entity_type"
        for place in e["locations"]
        for p in e["provenance"]
    }
    assert found == {
        (
            "php.method::Drupal\\my_module\\Controller\\ThingController::run",
            "drupal.entity_type::my_type",
            _line(CONSTANT_USE, "$this->entityTypeManager->getStorage(MyType::ENTITY_TYPE);"),
            "storage_call",
            "inferred",
        )
    }
    assert [row for row in report.skipped if row[2] == "storage_call"] == []


# --- the core-class boundary ------------------------------------------------------------------

BOUNDARY_FILES = {
    str(MODULE / "src/Controller/ModuleControllerBase.php"): r"""<?php

namespace Drupal\my_module\Controller;

use Drupal\Core\Controller\ControllerBase;

abstract class ModuleControllerBase extends ControllerBase {}
""",
    str(MODULE / "src/Controller/ThingController.php"): r"""<?php

namespace Drupal\my_module\Controller;

class ThingController extends ModuleControllerBase {}
""",
    str(MODULE / "src/Form/SettingsForm.php"): r"""<?php

namespace Drupal\my_module\Form;

use Drupal\Core\Form\ConfigFormBase;

class SettingsForm extends ConfigFormBase {}
""",
    str(MODULE / "src/EventSubscriber/ThingSubscriber.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Symfony\Component\EventDispatcher\EventSubscriberInterface;

class ThingSubscriber implements EventSubscriberInterface {}
""",
    str(MODULE / "src/Helper.php"): r"""<?php

namespace Drupal\my_module;

use Vendor\Library\UnlistedBase;

class Helper extends UnlistedBase {}
""",
}


def test_core_bases_the_code_reaches_become_declared_nodes_and_type_their_subclasses(
    tmp_path: Path,
) -> None:
    """No core file is planted. Each listed base is a declared node with no location; the
    classes that extend or implement one take its type at inferred; an unlisted base stays
    referenced and keeps php_basic's provenance."""
    _plant(tmp_path, BOUNDARY_FILES)
    document, report = _map(tmp_path)
    assert report.skipped == ()
    listed = report.unread + report.unlisted
    nodes = {n["id"]: n for n in document["nodes"]}
    own = "php.type::Drupal\\my_module\\"
    bases = {
        "php.type::Drupal\\Core\\Controller\\ControllerBase": ("php.class_like", "core_classes"),
        "php.type::Drupal\\Core\\Form\\ConfigFormBase": ("php.class_like", "core_classes"),
        "php.type::Symfony\\Component\\EventDispatcher\\EventSubscriberInterface": (
            "php.interface",
            "core_interfaces",
        ),
    }
    for base, (kind, group) in bases.items():
        node = nodes[base]
        assert (node["type"], node["state"], node["locations"]) == (kind, "declared", [])
        assert "unresolved_detail" not in node, node
        assert node["provenance"] == [
            {
                "pack": "drupal_basic",
                "rule": f"boundary.{group}",
                "confidence": "declared",
                "sets": ["id", "type"],
            }
        ]
        assert not any(base.rsplit("\\", 1)[1] in row for row in listed), listed
    classified = {
        own + "Controller\\ModuleControllerBase": ("drupal.controller_class", "core_classes"),
        own + "Controller\\ThingController": ("drupal.controller_class", "core_classes"),
        own + "Form\\SettingsForm": ("drupal.config_form_class", "core_classes"),
        own + "EventSubscriber\\ThingSubscriber": (
            "drupal.event_subscriber_class",
            "core_interfaces",
        ),
    }
    for cls, (kind, group) in classified.items():
        node = nodes[cls]
        assert (node["type"], node["state"]) == (kind, "mapped"), node
        rows = [p for p in node["provenance"] if p["rule"].startswith("boundary.")]
        assert rows == [
            {
                "pack": "drupal_basic",
                "rule": f"boundary.{group}",
                "confidence": "inferred",
                "sets": ["type"],
            }
        ]
    assert nodes[own + "Helper"]["type"] == "php.class"
    unlisted = nodes["php.type::Vendor\\Library\\UnlistedBase"]
    assert (unlisted["state"], unlisted["locations"]) == ("referenced", [])
    assert all(p["pack"] == "php_basic" for p in unlisted["provenance"]), unlisted


# --- calls through a typed entity type manager ------------------------------------------------

TYPED = r"""<?php

namespace Drupal\my_module;

use Drupal\Core\Entity\EntityTypeManager;
use Drupal\Core\Entity\EntityTypeManagerInterface;

class Typed {

  protected EntityTypeManagerInterface $etm;

  protected $mgr;

  protected EntityTypeManagerInterface $entityTypeManager;

  public function __construct(protected EntityTypeManager $em) {
  }

  public function run() {
    $a = $this->etm->getStorage('a');
    $b = $this->em->getViewBuilder('b');
    $c = $this->etm?->getListBuilder('c');
    $d = $this->mgr->getStorage('d');
    $e = $this->entityTypeManager->getStorage('e');
  }

}
"""


def test_entity_calls_join_by_the_receivers_declared_type_and_an_untyped_receiver_gives_none(
    tmp_path: Path,
) -> None:
    _plant(tmp_path, {str(MODULE / "src/Typed.php"): TYPED})
    document, report = _map(tmp_path)
    run_method = "php.method::Drupal\\my_module\\Typed::run"
    edges = [e for e in document["edges"] if e["kind"] == "uses_entity_type"]
    found = {(e["from"], e["to"], place["line"]) for e in edges for place in e["locations"]}
    assert found == {
        (run_method, "drupal.entity_type::a", _line(TYPED, "$a = $this->etm->getStorage('a');")),
        (run_method, "drupal.entity_type::b", _line(TYPED, "$b = $this->em->getViewBuilder('b');")),
        (
            run_method,
            "drupal.entity_type::c",
            _line(TYPED, "$c = $this->etm?->getListBuilder('c');"),
        ),
        (
            run_method,
            "drupal.entity_type::e",
            _line(TYPED, "$e = $this->entityTypeManager->getStorage('e');"),
        ),
    }
    typed = ("entity_call_through_typed_manager", "inferred")
    provenance = {
        e["to"]: sorted((p["rule"], p["confidence"]) for p in e["provenance"]) for e in edges
    }
    assert provenance == {
        "drupal.entity_type::a": [typed],
        "drupal.entity_type::b": [typed],
        "drupal.entity_type::c": [typed],
        # $this->entityTypeManager is also the name storage_call reads: one edge, two rows.
        "drupal.entity_type::e": sorted([typed, ("storage_call", "inferred")]),
    }
    states = {n["id"]: n["state"] for n in document["nodes"] if n["id"] in provenance}
    assert states == {entity: "referenced" for entity in provenance}
    fires = [
        fired
        for _, rows in report.map_passes
        for _, rule, fired in rows
        if rule == "entity_call_through_typed_manager"
    ]
    assert sum(fires) == 4, report.map_passes


# --- path strings in a Twig attribute and a script --------------------------------------------

ROUTING = r"""mymod.xy:
  path: '/x/y'
  defaults:
    _controller: '\Drupal\mymod\Controller\XyController::page'
"""
BUTTON = """\
<button data-endpoint="/x/y" data-relative="x/y" title="/x y">Go</button>
{# <a href="/x/commented">no</a> #}
{% set url = '/x/set' %}
"""
SCRIPT = """\
(function () {
  let endpoint = "/x/y";
  let relative = 'x/y';
  let label = '/x y';
  let joined = fetch('/x/joined/' + endpoint);
  let after = base + '/api/x';
  let before = '/api/y/' + id;
  let across = base +
    '/api/n';
  let spaced = base +   '/api/s';
  let tight = base+'/api/t';
  let paren = base + ('/api/p');
  x = '/x/y';
  let list = ['/x/y'];
  let pick = flag ? '/x/y' : other;
  fetch(
    '/x/y'
  );
  // fetch('/x/commented');
  fetch(endpoint);
})();
"""


def test_a_path_written_whole_links_to_the_node_its_route_serves_and_a_joined_one_does_not(
    tmp_path: Path,
) -> None:
    """The template's attribute and the script's assignment, list, ternary branch and argument
    link; a relative value, one with a space, a joined one, a comment and a set statement do not."""
    module = MODULE.parent / "mymod"
    _plant(
        tmp_path,
        {
            str(module / "mymod.info.yml"): "name: My module\ntype: module\n"
            "core_version_requirement: ^10\n",
            str(module / "mymod.routing.yml"): ROUTING,
            str(module / "templates/xy-button.html.twig"): BUTTON,
            str(module / "js/xy.js"): SCRIPT,
        },
        packs=DRUPAL + "  - drupal_js_basic@0.0.1\n",
    )
    document, _ = _map(tmp_path)
    path = "drupal.url_path::/x/y"
    links = sorted(
        (e["kind"], e["from"], e["to"])
        for e in document["edges"]
        if e["kind"] in ("links_to_path", "script_links_to_path")
    )
    assert links == [
        ("links_to_path", "drupal.template::xy-button", path),
        ("script_links_to_path", f"js.file::{module}/js/xy.js", path),
    ]
    script_lines = sorted(
        location["line"]
        for e in document["edges"]
        if e["kind"] == "script_links_to_path"
        for location in e["locations"]
    )
    assert script_lines == [2, 13, 14, 15, 17]
    serves = [(e["from"], e["to"]) for e in document["edges"] if e["kind"] == "route_serves_path"]
    assert serves == [("drupal.route::mymod.xy", path)]
    assert [n["id"] for n in document["nodes"] if n["type"] == "drupal.url_path"] == [path]
