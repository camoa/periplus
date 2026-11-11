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


ENTITY_CLASSES = {
    "Gadget": (
        "use Drupal\\Core\\Entity\\Attribute\\ContentEntityType;\n",
        "#[ContentEntityType(id: 'gadget')]\n",
    ),
    "Widget": ("", '/**\n * @ContentEntityType(\n *   id = "widget",\n * )\n */\n'),
    "Preset": (
        "use Drupal\\Core\\Entity\\Attribute\\ConfigEntityType;\n",
        "#[ConfigEntityType(id: 'preset')]\n",
    ),
    "Recipe": ("", '/**\n * @ConfigEntityType(\n *   id = "recipe",\n * )\n */\n'),
}
OWN_CALLER = r"""<?php

namespace Drupal\my_module\Controller;

use Drupal\my_module\Entity\Gadget;
use Drupal\my_module\Entity\Widget;
use Drupal\my_module\Entity\Preset;
use Drupal\my_module\Entity\Recipe;

class OwnController {

  public function run() {
    $a = Gadget::load(1);
    $b = Widget::loadMultiple();
    $c = Preset::create([]);
    $d = Recipe::load('x');
    $e = Gadget::save();
  }

}
"""


def test_a_static_call_on_a_mapped_entity_class_ends_at_its_entity_type(tmp_path: Path) -> None:
    """load, loadMultiple and create on a module's own entity class, declared by attribute or
    annotation, content or config, end at that entity type, inferred, at the method's line;
    another method makes nothing."""
    files = {
        str(MODULE / f"src/Entity/{name}.php"): "<?php\n\nnamespace Drupal\\my_module\\Entity;\n\n"
        + use
        + "\n"
        + head
        + f"class {name} {{\n}}\n"
        for name, (use, head) in ENTITY_CLASSES.items()
    }
    files[str(MODULE / "src/Controller/OwnController.php")] = OWN_CALLER
    _plant(tmp_path, files)
    document, _ = _map(tmp_path)
    run_method = "php.method::Drupal\\my_module\\Controller\\OwnController::run"
    found = {
        (e["to"], place["line"], p["rule"], p["confidence"])
        for e in document["edges"]
        if e["kind"] == "uses_entity_type" and e["from"] == run_method
        for place in e["locations"]
        for p in e["provenance"]
    }
    rule = "entity_class_static_call_mapped"
    line = _line(OWN_CALLER, "public function run() {")
    assert found == {
        (f"drupal.entity_type::{name}", line, rule, "inferred")
        for name in ("gadget", "widget", "preset", "recipe")
    }
    of_class = {
        (e["from"], e["to"]) for e in document["edges"] if e["kind"] == "entity_type_of_class"
    }
    assert of_class == {
        (f"php.type::Drupal\\my_module\\Entity\\{name}", f"drupal.entity_type::{name.lower()}")
        for name in ENTITY_CLASSES
    }


VIEWS_FIELD = r"""<?php

namespace Drupal\my_module\Plugin\views\field;

use Drupal\views\Attribute\ViewsField;

#[ViewsField('my_field')]
class MyField {
}
"""
VIEW = """\
id: things
display:
  default:
    display_options:
      fields:
        title:
          plugin_id: field
        mine:
          plugin_id: my_field
      filters:
        status:
          plugin_id: boolean
      style:
        type: table
  page_1:
    display_options:
      path: things
"""


def test_a_view_config_file_names_the_views_plugins_its_displays_use(tmp_path: Path) -> None:
    """A field's and a filter's plugin_id and the style's type, declared; the module's own field
    plugin is mapped, the core ones referenced."""
    _plant(
        tmp_path,
        {
            str(MODULE / "src/Plugin/views/field/MyField.php"): VIEWS_FIELD,
            "config/sync/views.view.things.yml": VIEW,
        },
    )
    document, _ = _map(tmp_path)
    view = "drupal.config::views.view.things"
    found = {
        (e["kind"], e["to"], p["confidence"])
        for e in document["edges"]
        if e["from"] == view and e["kind"].startswith("view_uses_")
        for p in e["provenance"]
    }
    assert found == {
        ("view_uses_field_plugin", "drupal.plugin.views_field::field", "declared"),
        ("view_uses_field_plugin", "drupal.plugin.views_field::my_field", "declared"),
        ("view_uses_filter_plugin", "drupal.plugin.views_filter::boolean", "declared"),
        ("view_uses_style_plugin", "drupal.plugin.views_style::table", "declared"),
    }
    states = {n["id"]: n["state"] for n in document["nodes"]}
    assert states["drupal.plugin.views_field::my_field"] == "mapped"
    assert states["drupal.plugin.views_field::field"] == "referenced"
    assert states["drupal.plugin.views_style::table"] == "referenced"


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


# --- cache shortcut, access check binding, nested arguments, route subscribers ----------------

CACHE_CONTROLLER = r"""<?php

namespace Drupal\my_module\Controller;

class CacheController {

  public function run($bin) {
    $a = \Drupal::cache();
    $b = \Drupal::cache('render');
    $c = \Drupal::cache("data");
    $d = \Drupal::cache($bin);
    \Drupal::setContainer($container);
    \Drupal::unsetContainer();
  }

}
"""


def test_drupal_cache_ends_at_its_bin_service_and_set_container_leaves_no_row(
    tmp_path: Path,
) -> None:
    """cache() gives cache.default and a quoted bin cache.<bin>, inferred, at each call's line; a
    variable bin is a call site marked runtime; setContainer and unsetContainer give nothing."""
    path = str(MODULE / "src/Controller/CacheController.php")
    _plant(tmp_path, {path: CACHE_CONTROLLER})
    document, report = _map(tmp_path)
    assert report.skipped == (), report.skipped
    run_method = "php.method::Drupal\\my_module\\Controller\\CacheController::run"
    found = {
        (e["from"], e["to"], place["line"], p["rule"], p["confidence"])
        for e in document["edges"]
        if e["kind"] == "uses_service"
        for place in e["locations"]
        for p in e["provenance"]
    }
    assert found == {
        (run_method, "drupal.service::cache.default", 8, "drupal_cache_call", "inferred"),
        (run_method, "drupal.service::cache.render", 9, "drupal_cache_bin_call", "inferred"),
        (run_method, "drupal.service::cache.data", 10, "drupal_cache_bin_call", "inferred"),
    }
    runtime = [
        (n["id"], n["locations"][0]["line"])
        for n in document["nodes"]
        if n.get("attributes", {}).get("resolution") == "runtime"
    ]
    assert runtime == [
        ("php.call_site::Drupal\\my_module\\Controller\\CacheController::run::\\Drupal::cache", 11)
    ]


ACCESS_ROUTING = """\
my_module.page:
  path: '/my/page'
  requirements:
    _my_module_access: 'TRUE'
my_module.open:
  path: '/my/open'
  requirements:
    _permission: 'access content'
"""
ACCESS_SERVICES = """\
services:
  my_module.access_check:
    class: Drupal\\my_module\\Access\\MyAccessCheck
    tags:
      - { name: access_check, applies_to: _my_module_access }
  my_module.chain:
    class: Drupal\\my_module\\Chain
    arguments:
      - ['@my_module.first', '@?my_module.second']
      - '@my_module.third'
"""


def test_a_route_requirement_joins_the_service_whose_tag_applies_to_it(tmp_path: Path) -> None:
    """The route holding the key gets one declared edge to the service; the other route none, and
    the internal requirement nodes stay out of the written map."""
    _plant(
        tmp_path,
        {
            str(MODULE / "my_module.routing.yml"): ACCESS_ROUTING,
            str(MODULE / "my_module.services.yml"): ACCESS_SERVICES,
        },
    )
    document, report = _map(tmp_path)
    checked = {
        (e["from"], e["to"], p["rule"], p["confidence"])
        for e in document["edges"]
        if e["kind"] == "access_checked_by_service"
        for p in e["provenance"]
    }
    assert checked == {
        (
            "drupal.route::my_module.page",
            "drupal.service::my_module.access_check",
            "route_access_checked_by_applies_to",
            "declared",
        )
    }
    assert not [n for n in document["nodes"] if n["type"] == "drupal.route_requirement"]
    assert (report.internal.nodes, report.internal.edges) == (2, 3), report.internal


def test_a_list_argument_of_a_service_injects_each_service_it_names(tmp_path: Path) -> None:
    """A nested list of @names gives one injects_service edge each, beside the plain argument."""
    _plant(tmp_path, {str(MODULE / "my_module.services.yml"): ACCESS_SERVICES})
    document, _ = _map(tmp_path)
    injected = sorted(
        (e["to"], e["locations"][0]["line"])
        for e in document["edges"]
        if e["kind"] == "injects_service" and e["from"] == "drupal.service::my_module.chain"
    )
    assert injected == [
        ("drupal.service::my_module.first", 9),
        ("drupal.service::my_module.second", 9),
        ("drupal.service::my_module.third", 10),
    ]


SUBSCRIBERS = {
    str(MODULE / "src/Routing/RouteSubscriber.php"): r"""<?php

namespace Drupal\my_module\Routing;

use Drupal\Core\Routing\RouteSubscriberBase;
use Symfony\Component\Routing\RouteCollection;

class RouteSubscriber extends RouteSubscriberBase {

  protected function alterRoutes(RouteCollection $collection) {
  }

}
""",
    str(MODULE / "src/EventSubscriber/DeniedSubscriber.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\Core\EventSubscriber\HttpExceptionSubscriberBase;

class DeniedSubscriber extends HttpExceptionSubscriberBase {
}
""",
}


def test_route_and_exception_subscribers_are_event_subscribers_and_a_route_one_alters_routes(
    tmp_path: Path,
) -> None:
    """Both classes take the event subscriber type; only the route subscriber has an inferred
    alters_routes edge, to a node marked resolution runtime at the class's line."""
    _plant(tmp_path, SUBSCRIBERS)
    document, _ = _map(tmp_path)
    nodes = {n["id"]: n for n in document["nodes"]}
    route = "php.type::Drupal\\my_module\\Routing\\RouteSubscriber"
    denied = "php.type::Drupal\\my_module\\EventSubscriber\\DeniedSubscriber"
    assert nodes[route]["type"] == nodes[denied]["type"] == "drupal.event_subscriber_class"
    alters = [
        (e["from"], e["to"], e["provenance"][0]["confidence"])
        for e in document["edges"]
        if e["kind"] == "alters_routes"
    ]
    mark = "drupal.route_alter::Drupal\\my_module\\Routing\\RouteSubscriber"
    assert alters == [(route, mark, "inferred")]
    assert nodes[mark]["attributes"] == {"resolution": "runtime"}
    assert nodes[mark]["locations"][0]["line"] == 8


# --- constraint validators, entity handlers, plugin types --------------------------------------

CONSTRAINT = MODULE / "src/Plugin/Validation/Constraint"
CONSTRAINTS = {
    str(CONSTRAINT / "SkuConstraint.php"): r"""<?php

namespace Drupal\my_module\Plugin\Validation\Constraint;

use Drupal\Core\Validation\Attribute\Constraint;
use Symfony\Component\Validator\Constraint as SymfonyConstraint;

#[Constraint(id: 'MySku', label: 'Sku')]
class SkuConstraint extends SymfonyConstraint {
}
""",
    str(CONSTRAINT / "SkuConstraintValidator.php"): r"""<?php

namespace Drupal\my_module\Plugin\Validation\Constraint;

class SkuConstraintValidator {
}
""",
    str(CONSTRAINT / "PriceConstraint.php"): r"""<?php

namespace Drupal\my_module\Plugin\Validation\Constraint;

/**
 * @Constraint(
 *   id = "MyPrice",
 *   label = @Translation("Price")
 * )
 */
class PriceConstraint {

  public function validatedBy() {
    return PriceChecker::class;
  }

}
""",
    str(CONSTRAINT / "PriceChecker.php"): r"""<?php

namespace Drupal\my_module\Plugin\Validation\Constraint;

class PriceChecker {
}
""",
    str(CONSTRAINT / "LoneConstraint.php"): r"""<?php

namespace Drupal\my_module\Plugin\Validation\Constraint;

use Drupal\Core\Validation\Attribute\Constraint;

#[Constraint(id: 'MyLone', label: 'Lone')]
class LoneConstraint {
}
""",
}


def test_a_constraint_links_to_the_class_validated_by_returns_else_to_its_named_validator(
    tmp_path: Path,
) -> None:
    """validatedBy() returning Name::class gives a declared edge; the name <class>Validator an
    inferred one; a constraint with neither gives none."""
    _plant(tmp_path, CONSTRAINTS)
    document, _ = _map(tmp_path)
    own = "php.type::Drupal\\my_module\\Plugin\\Validation\\Constraint\\"
    found = {
        (e["from"], e["to"], p["rule"], p["confidence"])
        for e in document["edges"]
        if e["kind"] == "validated_by"
        for p in e["provenance"]
    }
    assert found == {
        (
            "drupal.plugin.constraint::MyPrice",
            own + "PriceChecker",
            "constraint_validated_by_method",
            "declared",
        ),
        (
            "drupal.plugin.constraint::MySku",
            own + "SkuConstraintValidator",
            "constraint_validated_by_name",
            "inferred",
        ),
    }


ENTITY = MODULE / "src/Entity"
HANDLED = {
    str(ENTITY / "Order.php"): r"""<?php

namespace Drupal\my_module\Entity;

use Drupal\Core\Entity\Attribute\ContentEntityType;
use Drupal\my_module\OrderAccess;

#[ContentEntityType(
  id: 'my_order',
  handlers: [
    'access' => OrderAccess::class,
    'list_builder' => \Drupal\my_module\OrderListBuilder::class,
    'storage' => 'Drupal\my_module\OrderStorage',
    'form' => [
      'default' => Form\OrderForm::class,
    ],
  ],
)]
class Order {

  public function helper() {
    return ['access' => OrderAccess::class];
  }

}
""",
    str(ENTITY / "Coupon.php"): r"""<?php

namespace Drupal\my_module\Entity;

/**
 * @ConfigEntityType(
 *   id = "my_coupon",
 *   handlers = {
 *     "view_builder" = "\Drupal\my_module\CouponViewBuilder",
 *     "form" = {
 *       "add" = "Drupal\my_module\CouponForm",
 *       "delete" = "Drupal\my_module\CouponDeleteForm",
 *     },
 *     "route_provider" = {
 *       "html" = "Drupal\Core\Entity\Routing\AdminHtmlRouteProvider",
 *     },
 *   },
 * )
 */
class Coupon {
}
""",
}


def test_an_entity_type_links_to_each_handler_class_its_attribute_or_annotation_names(
    tmp_path: Path,
) -> None:
    """One declared edge per handler, of the kind its key names, at the class's line; a handler
    written as text in the attribute and an array in a method give none."""
    _plant(tmp_path, HANDLED)
    document, _ = _map(tmp_path)
    own = "php.type::Drupal\\my_module\\"
    found = {
        (e["kind"], e["from"], e["to"], e["provenance"][0]["confidence"])
        for e in document["edges"]
        if e["kind"].startswith("has_") and e["from"].startswith("drupal.entity_type::")
    }
    order, coupon = "drupal.entity_type::my_order", "drupal.entity_type::my_coupon"
    assert found == {
        ("has_access_handler", order, own + "OrderAccess", "declared"),
        ("has_list_builder", order, own + "OrderListBuilder", "declared"),
        ("has_form_handler", order, own + "Entity\\Form\\OrderForm", "declared"),
        ("has_view_builder", coupon, own + "CouponViewBuilder", "declared"),
        ("has_form_handler", coupon, own + "CouponForm", "declared"),
        ("has_form_handler", coupon, own + "CouponDeleteForm", "declared"),
        (
            "has_route_provider",
            coupon,
            "php.type::Drupal\\Core\\Entity\\Routing\\AdminHtmlRouteProvider",
            "declared",
        ),
    }


PLUGIN_TYPES = {
    str(MODULE / "src/Attribute/Gizmo.php"): r"""<?php

namespace Drupal\my_module\Attribute;

use Drupal\Component\Plugin\Attribute\Plugin;

#[\Attribute(\Attribute::TARGET_CLASS)]
class Gizmo extends Plugin {
}
""",
    str(MODULE / "src/Annotation/Gadget.php"): r"""<?php

namespace Drupal\my_module\Annotation;

use Drupal\Component\Annotation\Plugin;

/**
 * @Annotation
 */
class Gadget extends Plugin {
}
""",
    str(MODULE / "src/Plugin/Gizmo/Spinner.php"): r"""<?php

namespace Drupal\my_module\Plugin\Gizmo;

use Drupal\my_module\Attribute\Gizmo;

#[Gizmo(id: 'spinner')]
class Spinner {
}
""",
    str(MODULE / "src/Plugin/Gizmo/Wobbler.php"): r"""<?php

namespace Drupal\my_module\Plugin\Gizmo;

#[\Drupal\my_module\Attribute\Gizmo(id: 'wobbler')]
class Wobbler {
}
""",
    str(MODULE / "src/Plugin/Gadget/Lever.php"): r"""<?php

namespace Drupal\my_module\Plugin\Gadget;

use Drupal\my_module\Annotation\Gadget;

/**
 * @Gadget(
 *   id = "lever"
 * )
 */
class Lever {
}
""",
    str(MODULE / "src/GizmoManager.php"): r"""<?php

namespace Drupal\my_module;

use Drupal\Core\Plugin\DefaultPluginManager;
use Drupal\my_module\Attribute\Gizmo;

class GizmoManager extends DefaultPluginManager {

  public function __construct(\Traversable $namespaces, $handler) {
    parent::__construct('Plugin/Gizmo', $namespaces, $handler, NULL, Gizmo::class);
  }

}
""",
}


def test_a_plugin_type_comes_from_its_attribute_or_annotation_class_and_joins_plugins_and_manager(
    tmp_path: Path,
) -> None:
    """Each class extending a core Plugin base is a plugin type; plugins by short, qualified and
    annotation names join it, and the manager's constructor names it, inferred."""
    _plant(tmp_path, PLUGIN_TYPES)
    document, report = _map(tmp_path)
    assert report.skipped == (), report.skipped
    own = "Drupal\\my_module\\"
    gizmo = f"drupal.plugin_type::{own}Attribute\\Gizmo"
    gadget = f"drupal.plugin_type::{own}Annotation\\Gadget"
    types = sorted(n["id"] for n in document["nodes"] if n["type"] == "drupal.plugin_type")
    assert types == sorted([gizmo, gadget])
    plugins = {(e["from"], e["to"]) for e in document["edges"] if e["kind"] == "plugin_of_type"}
    assert plugins == {
        (f"php.type::{own}Plugin\\Gizmo\\Spinner", gizmo),
        (f"php.type::{own}Plugin\\Gizmo\\Wobbler", gizmo),
        (f"php.type::{own}Plugin\\Gadget\\Lever", gadget),
    }
    managed = [
        (e["from"], e["to"], e["provenance"][0]["confidence"])
        for e in document["edges"]
        if e["kind"] == "manages_plugin_type"
    ]
    assert managed == [(f"php.method::{own}GizmoManager::__construct", gizmo, "inferred")]
    attributes = {(e["from"], e["to"]) for e in document["edges"] if e["kind"] == "has_attribute"}
    assert (f"php.type::{own}Attribute\\Gizmo", "php.type::Attribute") in attributes
