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
    ends referenced, each at its call's line."""
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


# --- events, Twig extensions, field access, theme suggestions ---------------------------------

EVENTS = {
    str(MODULE / "src/Event/OrderEvent.php"): r"""<?php

namespace Drupal\my_module\Event;

use Symfony\Contracts\EventDispatcher\Event;

class OrderEvent extends Event {

  const PLACED = 'my_module.placed', CANCELLED = 'my_module.cancelled';

}
""",
    str(MODULE / "src/Event/OrderEvents.php"): r"""<?php

namespace Drupal\my_module\Event;

final class OrderEvents {

  const PAID = 'my_module.paid';

}
""",
    str(MODULE / "src/EventSubscriber/LocalEvents.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

final class LocalEvents {

  const LOCAL = 'my_module.local';

}
""",
    str(MODULE / "src/EventSubscriber/OrderSubscriber.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\my_module\Event\OrderEvent;
use Drupal\my_module\Event\OrderEvents;
use Symfony\Component\EventDispatcher\EventSubscriberInterface;
use Symfony\Component\HttpKernel\KernelEvents;

class OrderSubscriber implements EventSubscriberInterface {

  const MINE = 'my_module.mine';

  public static function getSubscribedEvents() {
    $events[OrderEvent::CANCELLED][] = ['onCancelled', 5];
    $events[self::MINE][] = ['onMine'];
    return $events + [
      OrderEvent::PLACED => 'onPlaced',
      KernelEvents::REQUEST => ['onRequest', 100],
      OrderEvents::PAID => 'onPaid',
      LocalEvents::LOCAL => 'onLocal',
    ];
  }

  public function helper() {
    return [OrderEvent::PLACED => 'notAListener'];
  }

  public function onPlaced($event) {
  }

  public function onCancelled($event) {
  }

  public function onMine($event) {
  }

  public function onRequest($event) {
  }

  public function onPaid($event) {
  }

  public function onLocal($event) {
  }

}
""",
    str(MODULE / "src/Service/Notifier.php"): r"""<?php

namespace Drupal\my_module\Service;

use Drupal\my_module\Event\OrderEvent;
use Drupal\my_module\Event\OrderEvents;

class Notifier {

  const SENT = 'my_module.sent';

  public function notify($order) {
    $event = new OrderEvent();
    $this->dispatcher->dispatch($event, OrderEvent::PLACED);
    $this->dispatcher->dispatch(new OrderEvent(f(g($order))), OrderEvents::PAID);
    $this->dispatcher->dispatch($event, self::SENT);
    $later = function () use ($event) {
      $this->dispatcher->dispatch($event, OrderEvent::CANCELLED);
    };
  }

}
""",
    str(MODULE / "my_module.module"): r"""<?php

use Drupal\my_module\Event\OrderEvent;

function my_module_user_login($account) {
  \Drupal::service('event_dispatcher')->dispatch(new OrderEvent(), OrderEvent::PLACED);
}
""",
}


def test_an_event_is_subscribed_by_the_methods_its_keys_name_and_dispatched_by_the_methods_around(
    tmp_path: Path,
) -> None:
    """A constant of an Event class or an *Events class is an event; each key of
    getSubscribedEvents, in either form, joins its listener, and each dispatch its method, all
    inferred. A second constant of one statement is an event too. An outside event and an
    own-class constant end at referenced events; an array outside getSubscribedEvents gives
    nothing; a class in the file's namespace joins in the map and keeps its skipped row."""
    _plant(tmp_path, EVENTS)
    document, report = _map(tmp_path)
    own = "Drupal\\my_module\\"
    event = "drupal.event::" + own
    sub = f"php.method::{own}EventSubscriber\\OrderSubscriber::"
    notify = f"php.method::{own}Service\\Notifier::notify"
    states = {n["id"]: n["state"] for n in document["nodes"] if n["type"] == "drupal.event"}
    assert states == {
        event + "Event\\OrderEvent::PLACED": "mapped",
        event + "Event\\OrderEvent::CANCELLED": "mapped",
        event + "Event\\OrderEvents::PAID": "mapped",
        event + "EventSubscriber\\LocalEvents::LOCAL": "mapped",
        event + "EventSubscriber\\OrderSubscriber::MINE": "referenced",
        event + "Service\\Notifier::SENT": "referenced",
        "drupal.event::Symfony\\Component\\HttpKernel\\KernelEvents::REQUEST": "referenced",
    }
    found = {
        (e["kind"], e["from"], e["to"], e["locations"][0]["line"], p["rule"], p["confidence"])
        for e in document["edges"]
        if e["kind"] in ("subscribed_by", "dispatched_by", "dispatched_by_function")
        for p in e["provenance"]
    }
    request = "drupal.event::Symfony\\Component\\HttpKernel\\KernelEvents::REQUEST"
    assert found == {
        (
            "subscribed_by",
            event + "Event\\OrderEvent::CANCELLED",
            sub + "onCancelled",
            15,
            "event_subscribed_by",
            "inferred",
        ),
        (
            "subscribed_by",
            event + "EventSubscriber\\OrderSubscriber::MINE",
            sub + "onMine",
            16,
            "event_subscribed_by_own_class",
            "inferred",
        ),
        (
            "subscribed_by",
            event + "Event\\OrderEvent::PLACED",
            sub + "onPlaced",
            18,
            "event_subscribed_by",
            "inferred",
        ),
        ("subscribed_by", request, sub + "onRequest", 19, "event_subscribed_by", "inferred"),
        (
            "subscribed_by",
            event + "Event\\OrderEvents::PAID",
            sub + "onPaid",
            20,
            "event_subscribed_by",
            "inferred",
        ),
        (
            "subscribed_by",
            event + "EventSubscriber\\LocalEvents::LOCAL",
            sub + "onLocal",
            21,
            "event_subscribed_in_namespace",
            "inferred",
        ),
        (
            "dispatched_by",
            event + "Event\\OrderEvent::PLACED",
            notify,
            14,
            "event_dispatched_by",
            "inferred",
        ),
        (
            "dispatched_by",
            event + "Event\\OrderEvents::PAID",
            notify,
            15,
            "event_dispatched_by",
            "inferred",
        ),
        (
            "dispatched_by",
            event + "Service\\Notifier::SENT",
            notify,
            16,
            "event_dispatched_by_own_class",
            "inferred",
        ),
        (
            "dispatched_by",
            event + "Event\\OrderEvent::CANCELLED",
            notify,
            18,
            "event_dispatched_by",
            "inferred",
        ),
        (
            "dispatched_by_function",
            event + "Event\\OrderEvent::PLACED",
            "php.function::my_module_user_login",
            6,
            "event_dispatched_by_function",
            "inferred",
        ),
    }
    rows = [(file.rsplit("/", 1)[-1], line, rule, why) for file, line, rule, why in report.skipped]
    assert rows == [
        (
            "OrderSubscriber.php",
            21,
            "event_subscribed_by",
            "edge subscribed_by: no resolution step holds for capture key",
        )
    ]


TWIG_EXTENSIONS = {
    str(MODULE / "src/Twig/ShopExtension.php"): r"""<?php

namespace Drupal\my_module\Twig;

use Twig\Extension\AbstractExtension;
use Twig\TwigFilter;
use Twig\TwigFunction;

class ShopExtension extends AbstractExtension {

  public function getFilters() {
    return [new TwigFilter('money', [$this, 'money'])];
  }

  public function getFunctions() {
    return [new TwigFunction('cart_total', [$this, 'total'])];
  }

}
""",
    str(MODULE / "src/Twig/MoreExtension.php"): r"""<?php

namespace Drupal\my_module\Twig;

use Twig\TwigFilter;

class MoreExtension extends ShopExtension {

  public function getFilters() {
    return [new TwigFilter('short', [$this, 'short'])];
  }

}
""",
    str(MODULE / "src/Helper.php"): r"""<?php

namespace Drupal\my_module;

use Twig\TwigFilter;

class Helper {

  public function make() {
    return new TwigFilter('loose', 'strtoupper');
  }

}
""",
    str(MODULE / "src/Twig/WrittenExtension.php"): r"""<?php

namespace Drupal\my_module\Twig;

class WrittenExtension extends ShopExtension {

  public function getFilters() {
    return [new \Twig\TwigFilter('long', [$this, 'long'])];
  }

  public function getFunctions() {
    return [new \Twig\TwigFunction('cart_count', [$this, 'count'])];
  }

}
""",
    str(MODULE / "templates/my-cart.html.twig"): """\
<div>{{ price|money }} {{ cart_total() }}</div>
{% if cart_total() %}{{ 'Cart'|t }}{% endif %}
<p>Plain text | short and a note.</p>
{{ {a: 1}|merge({b: 2})|short }}
{{ title|loose }}
{# {{ title|short }} #}
{{ price|long }} {{ cart_count() }}
""",
}


def test_a_twig_extension_provides_its_filters_and_functions_and_templates_use_them(
    tmp_path: Path,
) -> None:
    """A filter or function created in a class that descends from AbstractExtension, by the short
    class name or as \\Twig\\TwigFilter, is a node provided by that class, declared; a template
    that calls it uses it, inferred. A filter made in any other class, a core filter, text outside
    Twig, a filter after a hash and a comment give nothing."""
    _plant(tmp_path, TWIG_EXTENSIONS)
    document, report = _map(tmp_path)
    assert report.skipped == (), report.skipped
    twig = "php.type::Drupal\\my_module\\Twig\\"
    names = sorted(
        (n["id"], n["locations"][0]["line"])
        for n in document["nodes"]
        if n["type"] in ("twig.filter", "twig.function")
    )
    assert names == [
        ("twig.filter::long", 8),
        ("twig.filter::money", 12),
        ("twig.filter::short", 10),
        ("twig.function::cart_count", 12),
        ("twig.function::cart_total", 16),
    ]
    found = {
        (e["kind"], e["from"], e["to"], p["confidence"])
        for e in document["edges"]
        if "twig" in e["kind"]
        for p in e["provenance"]
    }
    template = "drupal.template::my-cart"
    assert found == {
        ("twig_filter_provided_by", "twig.filter::money", twig + "ShopExtension", "declared"),
        ("twig_filter_provided_by", "twig.filter::short", twig + "MoreExtension", "declared"),
        (
            "twig_function_provided_by",
            "twig.function::cart_total",
            twig + "ShopExtension",
            "declared",
        ),
        ("template_uses_twig_filter", template, "twig.filter::money", "inferred"),
        ("template_uses_twig_function", template, "twig.function::cart_total", "inferred"),
        ("twig_filter_provided_by", "twig.filter::long", twig + "WrittenExtension", "declared"),
        (
            "twig_function_provided_by",
            "twig.function::cart_count",
            twig + "WrittenExtension",
            "declared",
        ),
        ("template_uses_twig_filter", template, "twig.filter::long", "inferred"),
        ("template_uses_twig_function", template, "twig.function::cart_count", "inferred"),
    }


FIELD_STORAGE = """\
langcode: en
status: true
id: {entity}.{field}
field_name: {field}
entity_type: {entity}
type: string
"""
FIELD_FILES = {
    "config/sync/field.storage.node.field_color.yml": FIELD_STORAGE.format(
        entity="node", field="field_color"
    ),
    "config/sync/field.storage.user.field_color.yml": FIELD_STORAGE.format(
        entity="user", field="field_color"
    ),
    "config/sync/field.storage.node.body.yml": FIELD_STORAGE.format(entity="node", field="body"),
    str(MODULE / "src/Painter.php"): r"""<?php

namespace Drupal\my_module;

class Painter {

  const GONE = 'field_gone';

  public function paint($entity, $config, $name) {
    if ($entity->hasField('field_color')) {
      $entity->set('field_size', 3);
      $entity->get('body');
      $entity->get(self::GONE);
      $entity->get($name);
      $config->get('my_module.setting');
    }
  }

}
""",
    str(MODULE / "my_module.module"): """\
<?php

function my_module_node_presave($node) {
  $node->get('field_color');
}
""",
    str(THEME / "templates/node--article--full.html.twig"): """\
<article>{{ node.field_color.value }} {{ content.field_width }}</article>
<p>node.field_plain in text</p>
""",
}


def test_code_and_templates_that_name_a_field_access_each_storage_of_that_name_or_leave_a_mark(
    tmp_path: Path,
) -> None:
    """get, set and hasField in a method or a function, and x.field_y in Twig, give accesses_field
    to every storage of that name, inferred, at the method's or the template's line. A field_ name
    with no storage ends at an unresolved field.storage.<name>; any other unmapped name, a
    variable and a name in plain text give nothing."""
    _plant(tmp_path, FIELD_FILES)
    document, report = _map(tmp_path)
    assert report.skipped == (), report.skipped
    paint = "php.method::Drupal\\my_module\\Painter::paint"
    presave = "php.function::my_module_node_presave"
    template = "drupal.template::node--article--full"
    storage = "drupal.config::field.storage."
    found = {
        (e["from"], e["to"], e["locations"][0]["line"], p["rule"])
        for e in document["edges"]
        if e["kind"] == "accesses_field"
        for p in e["provenance"]
    }
    assert found == {
        (paint, storage + "node.field_color", 9, "code_accesses_field_or_mark"),
        (paint, storage + "user.field_color", 9, "code_accesses_field_or_mark"),
        (paint, storage + "field_size", 9, "code_accesses_field_or_mark"),
        (paint, storage + "field_gone", 9, "code_accesses_field_or_mark"),
        (paint, storage + "field_gone", 9, "code_accesses_field_by_class_constant"),
        (paint, storage + "node.body", 9, "code_accesses_field"),
        (presave, storage + "node.field_color", 3, "code_accesses_field_or_mark"),
        (presave, storage + "user.field_color", 3, "code_accesses_field_or_mark"),
        (template, storage + "node.field_color", 1, "template_accesses_field_or_mark"),
        (template, storage + "user.field_color", 1, "template_accesses_field_or_mark"),
        (template, storage + "field_width", 1, "template_accesses_field_or_mark"),
    }
    marks = sorted((n["id"], n["type"]) for n in document["nodes"] if n["state"] == "unresolved")
    assert marks == [
        (storage + "field_gone", "drupal.field_storage"),
        (storage + "field_size", "drupal.field_storage"),
        (storage + "field_width", "drupal.field_storage"),
    ]


SUGGESTIONS = {
    str(MODULE / "src/Plugin/Block/CartBlock.php"): r"""<?php

namespace Drupal\my_module\Plugin\Block;

use Drupal\Core\Block\Attribute\Block;
use Drupal\Core\Block\BlockBase;

#[Block(id: 'my_cart_block', admin_label: 'Cart')]
class CartBlock extends BlockBase {
}
""",
    str(MODULE / "my_module.module"): """\
<?php

function my_module_theme($existing, $type, $theme, $path) {
  return [
    'my_card' => [
      'variables' => ['title' => NULL],
    ],
  ];
}
""",
    "config/sync/block.block.my_theme_branding.yml": (
        "id: my_theme_branding\ntheme: my_theme\nregion: header\nplugin: system_branding_block\n"
    ),
    "config/sync/block.block.views_block__recent_list.yml": (
        "id: views_block__recent_list\ntheme: my_theme\nregion: content\n"
        "plugin: 'views_block:recent-list'\n"
    ),
    "config/sync/block.block.my_theme_main_menu.yml": (
        "id: my_theme_main_menu\ntheme: my_theme\nregion: header\n"
        "plugin: 'system_menu_block:main'\n"
    ),
    "config/sync/field.storage.node.field_color.yml": FIELD_STORAGE.format(
        entity="node", field="field_color"
    ),
    "config/sync/field.storage.user.field_color.yml": FIELD_STORAGE.format(
        entity="user", field="field_color"
    ),
    "config/sync/field.storage.taxonomy_term.field_tags.yml": FIELD_STORAGE.format(
        entity="taxonomy_term", field="field_tags"
    ),
    **{
        str(THEME / f"templates/{name}.html.twig"): "<div>{{ content }}</div>\n"
        for name in (
            "block--my-cart-block",
            "block--my-theme-branding",
            "block--system-menu-block--main",
            "block--views-block--recent-list",
            "block--system",
            "my-card--wide",
            "field--field-color",
            "field--node--field-color--article",
            "field--taxonomy-term--field-tags",
            "field--entity-reference",
            "field--node--article",
        )
    },
}


def test_a_suggestion_template_links_to_the_block_hook_or_field_its_name_suggests_when_mapped(
    tmp_path: Path,
) -> None:
    """Each edge is inferred and ends only on a node the map holds: a block plugin, a derivative
    plugin a placement names, a placement, a theme hook, every storage of a field name, or the one
    storage an entity type names. A module, a field type and a bundle name link nowhere."""
    _plant(tmp_path, SUGGESTIONS)
    document, report = _map(tmp_path)
    assert report.skipped == (), report.skipped
    storage = "drupal.config::field.storage."
    found = {
        (e["kind"], e["from"].split("::", 1)[1], e["to"], p["confidence"])
        for e in document["edges"]
        if e["kind"].startswith("suggests_") and e["kind"] != "suggests_bundle"
        for p in e["provenance"]
    }
    assert found == {
        (
            "suggests_block_plugin",
            "block--my-cart-block",
            "drupal.plugin.block::my_cart_block",
            "inferred",
        ),
        (
            "suggests_block_plugin",
            "block--system-menu-block--main",
            "drupal.plugin.block::system_menu_block:main",
            "inferred",
        ),
        (
            "suggests_block_placement",
            "block--my-theme-branding",
            "drupal.config::block.block.my_theme_branding",
            "inferred",
        ),
        (
            "suggests_block_placement",
            "block--views-block--recent-list",
            "drupal.config::block.block.views_block__recent_list",
            "inferred",
        ),
        ("suggests_theme_hook", "my-card--wide", "drupal.theme_hook::my_card", "inferred"),
        ("suggests_field", "field--field-color", storage + "node.field_color", "inferred"),
        ("suggests_field", "field--field-color", storage + "user.field_color", "inferred"),
        (
            "suggests_field",
            "field--node--field-color--article",
            storage + "node.field_color",
            "inferred",
        ),
        (
            "suggests_field",
            "field--taxonomy-term--field-tags",
            storage + "taxonomy_term.field_tags",
            "inferred",
        ),
    }


# --- roles, configuration, queues and form alters named in code -------------------------------

ROLE_FILES = {
    "config/sync/user.role.editor.yml": (
        "uuid: 1\nid: editor\nlabel: Editor\nis_admin: false\npermissions: []\n"
    ),
    str(MODULE / "src/Access/Gate.php"): r"""<?php

namespace Drupal\my_module\Access;

use Drupal\user\RoleInterface;

class Gate {

  const ROLE = 'editor';

  public function check($account, $role) {
    if ($account->hasRole('editor')) {
      $account->addRole('ghost');
      $account->removeRole(self::ROLE);
    }
    $account->hasRole($role);
    $account->hasRole(RoleInterface::AUTHENTICATED_ID);
  }

}
""",
    str(MODULE / "my_module.module"): """\
<?php

function my_module_user_presave($account) {
  $account->addRole('editor');
  $account->removeRole($account->name . '_x');
}
""",
}


def test_a_role_named_in_code_is_checked_or_changed_and_a_variable_role_is_a_runtime_mark(
    tmp_path: Path,
) -> None:
    """hasRole gives checks_role, addRole and removeRole give changes_role, to user.role.<name> at
    the method's or function's line; a role no file declares is unresolved. A variable argument
    keeps the call as a runtime call site and a core constant leaves a skipped row."""
    _plant(tmp_path, ROLE_FILES)
    document, report = _map(tmp_path)
    gate = str(MODULE / "src/Access/Gate.php")
    module = str(MODULE / "my_module.module")
    assert sorted((f, line, r, why) for f, line, r, why in report.skipped) == [
        (
            "config/sync/user.role.editor.yml",
            1,
            "role_from_config_edges",
            "edge grants_permission: no value for key permissions",
        ),
        (module, 5, "role_changed_in_call", "argument 0 is not a text literal"),
        (gate, 16, "role_checked_in_call", "argument 0 is not a text literal"),
        (gate, 17, "role_checked_in_call", "argument 0 is a class constant with no declared text"),
    ]
    check = "php.method::Drupal\\my_module\\Access\\Gate::check"
    presave = "php.function::my_module_user_presave"
    role = "drupal.config::user.role."
    found = {
        (e["kind"], e["from"], e["to"], e["locations"][0]["line"], p["confidence"])
        for e in document["edges"]
        if e["kind"] in ("checks_role", "changes_role")
        for p in e["provenance"]
    }
    assert found == {
        ("checks_role", check, role + "editor", 11, "declared"),
        ("changes_role", check, role + "ghost", 11, "declared"),
        ("changes_role", check, role + "editor", 11, "declared"),
        ("changes_role", check, role + "editor", 11, "inferred"),
        ("changes_role", presave, role + "editor", 3, "declared"),
    }
    marks = sorted((n["id"], n["type"]) for n in document["nodes"] if n["state"] == "unresolved")
    assert marks == [(role + "ghost", "drupal.role")]
    runtime = {
        (e["from"], e["to"], e["locations"][0]["line"])
        for e in document["edges"]
        if e["kind"] == "has_call_site"
    }
    assert runtime == {
        (
            check,
            "php.call_site::Drupal\\my_module\\Access\\Gate::check::$account->hasRole(runtime)",
            16,
        ),
        (presave, "php.call_site::my_module_user_presave::$account->removeRole(runtime)", 5),
    }


CONFIG_FORM = r"""<?php

namespace Drupal\my_module\Form;

use Drupal\Core\Form\ConfigFormBase;

class SettingsForm extends ConfigFormBase {

  const SETTINGS = 'my_module.settings';

  public function buildForm(array $form, $form_state) {
    $this->config(self::SETTINGS)->get('mode');
    \Drupal::config('system.site')->get('name');
    $this->configFactory->get('my_module.settings');
    \Drupal::configFactory()->getEditable('my_module.settings')->save();
    $this->container->get('config.factory')->getEditable('my_module.other');
    $this->configFactoryOverride->get('my_module.none');
    $config = \Drupal::config('my_module.settings');
    $config->get('my_module.none');
    return $form;
  }

}
"""


def test_a_config_name_read_or_edited_through_a_config_factory_links_to_its_config_object(
    tmp_path: Path,
) -> None:
    """\\Drupal::config is declared; $this->config and get or getEditable on an object named as a
    config factory are inferred. A name no file declares is an unresolved config object; get on
    any other object gives nothing."""
    _plant(
        tmp_path,
        {
            "config/sync/my_module.settings.yml": "mode: soft\n",
            str(MODULE / "src/Form/SettingsForm.php"): CONFIG_FORM,
        },
    )
    document, report = _map(tmp_path)
    assert report.skipped == (), report.skipped
    build = "php.method::Drupal\\my_module\\Form\\SettingsForm::buildForm"
    found = {
        (
            e["kind"],
            e["to"],
            tuple(location["line"] for location in e["locations"]),
            tuple((p["rule"], p["confidence"]) for p in e["provenance"]),
        )
        for e in document["edges"]
        if e["kind"] in ("reads_config_object", "edits_config_object") and e["from"] == build
    }
    config = "drupal.config::"
    own = ("config_read_by_own_method", "inferred")
    by_drupal = ("config_read_by_drupal", "declared")
    from_factory = ("config_read_from_factory", "inferred")
    edited = ("config_edited_from_factory", "inferred")
    by_constant = ("config_read_by_class_constant", "inferred")
    assert found == {
        (
            "reads_config_object",
            config + "my_module.settings",
            (11, 12, 14, 18),
            (by_constant, by_drupal, own, from_factory),
        ),
        ("reads_config_object", config + "system.site", (13,), (by_drupal,)),
        ("edits_config_object", config + "my_module.settings", (15,), (edited,)),
        ("edits_config_object", config + "my_module.other", (16,), (edited,)),
    }
    marks = sorted(
        (n["id"], n["type"])
        for n in document["nodes"]
        if n["state"] == "unresolved" and n["id"].startswith(config)
    )
    assert marks == [
        (config + "my_module.other", "drupal.config_object"),
        (config + "system.site", "drupal.config_object"),
    ]


QUEUE_FILES = {
    str(MODULE / "src/Plugin/QueueWorker/SendWorker.php"): r"""<?php

namespace Drupal\my_module\Plugin\QueueWorker;

use Drupal\Core\Queue\QueueWorkerBase;

/**
 * @QueueWorker(
 *   id = "my_module_send",
 *   title = @Translation("Send"),
 * )
 */
class SendWorker extends QueueWorkerBase {

  public function processItem($data) {
  }

}
""",
    str(MODULE / "src/Service/Sender.php"): r"""<?php

namespace Drupal\my_module\Service;

class Sender {

  const QUEUE = 'my_module_send';

  public function send($name) {
    $this->queueFactory->get(self::QUEUE)->createItem([]);
    \Drupal::queue('contrib_pull')->createItem([]);
    $this->queueFactory->get($name);
    $this->cache->get('my_module_send');
  }

}
""",
    str(MODULE / "my_module.module"): """\
<?php

function my_module_cron() {
  \\Drupal::service('queue')->get('my_module_send')->claimItem();
}
""",
}


def test_a_queue_got_by_name_links_to_the_worker_of_that_queue(tmp_path: Path) -> None:
    """\\Drupal::queue('x') and get('x') on a queue factory give uses_queue to the worker plugin
    x; a worker no file declares is referenced, and a variable queue leaves a skipped row."""
    _plant(tmp_path, QUEUE_FILES)
    document, report = _map(tmp_path)
    sender = str(MODULE / "src/Service/Sender.php")
    assert [(f, line, r, why) for f, line, r, why in report.skipped] == [
        (sender, 12, "queue_from_factory", "argument 0 is not a text literal"),
    ]
    worker = "drupal.plugin.queue_worker::"
    send = "php.method::Drupal\\my_module\\Service\\Sender::send"
    found = {
        (e["from"], e["to"], e["locations"][0]["line"], p["confidence"])
        for e in document["edges"]
        if e["kind"] == "uses_queue"
        for p in e["provenance"]
    }
    assert found == {
        (send, worker + "my_module_send", 9, "inferred"),
        (send, worker + "contrib_pull", 11, "declared"),
        ("php.function::my_module_cron", worker + "my_module_send", 4, "inferred"),
    }
    states = {n["id"]: n["state"] for n in document["nodes"] if n["id"].startswith(worker)}
    assert states == {worker + "my_module_send": "mapped", worker + "contrib_pull": "referenced"}


FORM_ALTER_FILES = {
    str(MODULE / "src/Form/SettingsForm.php"): r"""<?php

namespace Drupal\my_module\Form;

use Drupal\Core\Form\FormBase;

class SettingsForm extends FormBase {

  public function getFormId() {
    return 'my_module_settings';
  }

}
""",
    str(MODULE / "my_module.module"): """\
<?php

function my_module_form_my_module_settings_alter(&$form, $form_state) {
}

function my_module_form_node_form_alter(&$form, $form_state) {
}

function my_module_form_alter(&$form, $form_state, $form_id) {
}
""",
    str(MODULE / "src/Hook/FormHooks.php"): r"""<?php

namespace Drupal\my_module\Hook;

use Drupal\Core\Hook\Attribute\Hook;

class FormHooks {

  #[Hook('form_user_login_form_alter')]
  public function loginAlter(&$form) {
  }

}
""",
}


def test_a_form_id_alter_hook_alters_the_form_its_name_gives(tmp_path: Path) -> None:
    """A function or method implementing form_<id>_alter gives alters_form to the form id <id>,
    inferred; a form id no class returns, a core or base form id, is referenced. form_alter itself
    gives none."""
    _plant(tmp_path, FORM_ALTER_FILES)
    document, _ = _map(tmp_path)
    form = "drupal.form_id::"
    found = {
        (e["from"], e["to"], e["locations"][0]["line"], p["confidence"])
        for e in document["edges"]
        if e["kind"] == "alters_form"
        for p in e["provenance"]
    }
    assert found == {
        (
            "php.function::my_module_form_my_module_settings_alter",
            form + "my_module_settings",
            3,
            "inferred",
        ),
        ("php.function::my_module_form_node_form_alter", form + "node_form", 6, "inferred"),
        (
            "php.method::Drupal\\my_module\\Hook\\FormHooks::loginAlter",
            form + "user_login_form",
            10,
            "inferred",
        ),
    }
    states = {n["id"]: n["state"] for n in document["nodes"] if n["id"].startswith(form)}
    assert states == {
        form + "my_module_settings": "mapped",
        form + "node_form": "referenced",
        form + "user_login_form": "referenced",
    }


# --- service factories, links files, form bases and macro imports ----------------------------

FACTORY_SERVICES = r"""services:
  my_module.client_factory:
    class: Drupal\my_module\ClientFactory
  my_module.client:
    class: Drupal\my_module\Client
    factory: ['@my_module.client_factory', 'create']
  my_module.export:
    class: Drupal\my_module\Client
    factory: ['Drupal\my_module\ClientFactory', 'export']
  my_module.static_export:
    class: Drupal\my_module\Client
    factory: 'Drupal\my_module\ClientFactory::export'
  my_module.outside:
    class: Drupal\my_module\Client
    factory: ['@other.factory', 'build']
  my_module.missing:
    factory: ['@my_module.client_factory', 'absent']
"""
FACTORY_CLASS = r"""<?php

namespace Drupal\my_module;

class ClientFactory {

  public function create() {
  }

  public static function export() {
  }

}
"""


def test_a_service_built_by_a_factory_links_to_the_factory_and_its_method(tmp_path: Path) -> None:
    """factory: ['@s', 'm'] gives built_by_service, factory: ['Class', 'm'] and 'Class::m' give
    built_by_class, and each gives built_by_method to <class>::m, all declared; a method the class
    lacks is unresolved, and an unmapped factory service names no method."""
    _plant(
        tmp_path,
        {
            str(MODULE / "my_module.services.yml"): FACTORY_SERVICES,
            str(MODULE / "src/ClientFactory.php"): FACTORY_CLASS,
            str(MODULE / "src/Client.php"): (
                "<?php\n\nnamespace Drupal\\my_module;\n\nclass Client {\n}\n"
            ),
        },
    )
    document, report = _map(tmp_path)
    assert [r for _, _, r, _ in report.skipped if r.startswith("service_factory")] == []
    service = "drupal.service::my_module."
    factory = "php.type::Drupal\\my_module\\ClientFactory"
    method = "php.method::Drupal\\my_module\\ClientFactory::"
    found = {
        (e["kind"], e["from"], e["to"], p["confidence"])
        for e in document["edges"]
        if e["kind"].startswith("built_by")
        for p in e["provenance"]
    }
    assert found == {
        ("built_by_service", service + "client", service + "client_factory", "declared"),
        ("built_by_service", service + "outside", "drupal.service::other.factory", "declared"),
        ("built_by_service", service + "missing", service + "client_factory", "declared"),
        ("built_by_class", service + "export", factory, "declared"),
        ("built_by_class", service + "static_export", factory, "declared"),
        ("built_by_method", service + "client", method + "create", "declared"),
        ("built_by_method", service + "export", method + "export", "declared"),
        ("built_by_method", service + "static_export", method + "export", "declared"),
        ("built_by_method", service + "missing", method + "absent", "declared"),
    }
    states = {n["id"]: n["state"] for n in document["nodes"]}
    assert states[method + "absent"] == "unresolved"
    assert states["drupal.service::other.factory"] == "referenced"


LINKS_FILES = {
    str(MODULE / "my_module.links.task.yml"): """\
my_module.list:
  title: 'List'
  route_name: my_module.list
  base_route: my_module.list
my_module.settings_tab:
  title: 'Settings'
  route_name: my_module.settings
  base_route: my_module.list
my_module.sub_tab:
  title: 'Sub'
  route_name: my_module.settings
  parent_id: my_module.settings_tab
my_module.dynamic:
  class: \\Drupal\\Core\\Menu\\LocalTaskDefault
  deriver: \\Drupal\\my_module\\Plugin\\Derivative\\DynamicTasks
""",
    str(MODULE / "my_module.links.action.yml"): """\
my_module.derived_add:
  route_name: my_module.list
  deriver: \\Drupal\\my_module\\Plugin\\Derivative\\DynamicTasks
""",
    str(MODULE / "my_module.links.contextual.yml"): """\
my_module.edit:
  title: 'Edit'
  route_name: my_module.settings
  group: my_module
  class: \\Drupal\\my_module\\Plugin\\Derivative\\DynamicTasks
""",
    str(MODULE / "src/Plugin/Derivative/DynamicTasks.php"): r"""<?php

namespace Drupal\my_module\Plugin\Derivative;

class DynamicTasks {
}
""",
}


def test_local_tasks_actions_and_contextual_links_link_to_routes_and_classes(
    tmp_path: Path,
) -> None:
    """Each entry of a links.task or links.contextual file is a node; route_name, base_route,
    parent_id, class and deriver give an edge each, declared, and a local action's class and
    deriver do too. A route or class no file declares is referenced."""
    _plant(tmp_path, LINKS_FILES)
    document, _ = _map(tmp_path)
    task = "drupal.local_task::my_module."
    route = "drupal.route::my_module."
    deriver = "php.type::Drupal\\my_module\\Plugin\\Derivative\\DynamicTasks"
    default = "php.type::Drupal\\Core\\Menu\\LocalTaskDefault"
    action = "drupal.local_action::my_module.derived_add"
    link = "drupal.contextual_link::my_module.edit"
    kinds = {"links_to_route", "task_base_route", "child_of_task", "link_class", "link_deriver"}
    found = {
        (e["kind"], e["from"], e["to"], p["confidence"])
        for e in document["edges"]
        if e["kind"] in kinds
        for p in e["provenance"]
    }
    assert found == {
        ("links_to_route", task + "list", route + "list", "declared"),
        ("links_to_route", task + "settings_tab", route + "settings", "declared"),
        ("links_to_route", task + "sub_tab", route + "settings", "declared"),
        ("task_base_route", task + "list", route + "list", "declared"),
        ("task_base_route", task + "settings_tab", route + "list", "declared"),
        ("child_of_task", task + "sub_tab", task + "settings_tab", "declared"),
        ("link_class", task + "dynamic", default, "declared"),
        ("link_deriver", task + "dynamic", deriver, "declared"),
        ("links_to_route", action, route + "list", "declared"),
        ("link_deriver", action, deriver, "declared"),
        ("links_to_route", link, route + "settings", "declared"),
        ("link_class", link, deriver, "declared"),
    }
    attributes = {
        n["id"]: n.get("attributes")
        for n in document["nodes"]
        if n["type"] in ("drupal.local_task", "drupal.contextual_link")
    }
    assert attributes == {
        task + "list": {"title": "List"},
        task + "settings_tab": {"title": "Settings"},
        task + "sub_tab": {"title": "Sub"},
        task + "dynamic": None,
        link: {"group": "my_module", "title": "Edit"},
    }


FORM_BASES = {
    "ThingForm": "Drupal\\Core\\Entity\\EntityForm",
    "ThingContentForm": "Drupal\\Core\\Entity\\ContentEntityForm",
    "ThingBundleForm": "Drupal\\Core\\Entity\\BundleEntityFormBase",
    "ThingDeleteForm": "Drupal\\Core\\Entity\\EntityDeleteForm",
    "ThingContentDeleteForm": "Drupal\\Core\\Entity\\ContentEntityDeleteForm",
    "ThingConfirmForm": "Drupal\\Core\\Form\\ConfirmFormBase",
    "ThingEntityConfirmForm": "Drupal\\Core\\Entity\\EntityConfirmFormBase",
    "ThingContentConfirmForm": "Drupal\\Core\\Entity\\ContentEntityConfirmFormBase",
}


def test_a_class_on_a_core_entity_or_confirm_form_base_is_a_form_class(tmp_path: Path) -> None:
    """A class that extends a core entity form, delete form or confirm form base, or extends such
    a class of the module, is typed drupal.form_class."""
    files = {
        str(MODULE / f"src/Form/{name}.php"): (
            f"<?php\n\nnamespace Drupal\\my_module\\Form;\n\nuse {base};\n\n"
            f"class {name} extends {base.rsplit(chr(92), 1)[-1]} {{\n}}\n"
        )
        for name, base in FORM_BASES.items()
    }
    files[str(MODULE / "src/Form/SubForm.php")] = (
        "<?php\n\nnamespace Drupal\\my_module\\Form;\n\nclass SubForm extends ThingForm {\n}\n"
    )
    _plant(tmp_path, files)
    document, _ = _map(tmp_path)
    types = {
        n["id"]: n["type"]
        for n in document["nodes"]
        if n["id"].startswith("php.type::Drupal\\my_module\\Form\\")
    }
    assert types == {
        f"php.type::Drupal\\my_module\\Form\\{name}": "drupal.form_class"
        for name in [*FORM_BASES, "SubForm"]
    }


MACRO_THEME = Path("web/themes/custom/my_theme")
MACRO_FILES = {
    str(MACRO_THEME / "my_theme.info.yml"): "name: My theme\ntype: theme\n",
    str(MACRO_THEME / "templates/misc/macros.twig"): (
        "{# Icons. #}\n{% macro icon(name) %}<i>{{ name }}</i>{% endmacro %}\n"
        "{%- macro badge(x) -%}<b>{{ x }}</b>{%- endmacro -%}\n"
    ),
    str(MACRO_THEME / "templates/misc/forms.html.twig"): (
        "{% macro row(x) %}{{ x }}{% endmacro %}\n"
    ),
    str(MACRO_THEME / "templates/misc/plain.twig"): "<p></p>\n",
    str(MACRO_THEME / "templates/page.html.twig"): (
        '{% import "@my_theme/misc/macros.twig" as macros %}\n'
        "{% from 'macros.twig' import icon, badge as b %}\n"
        '{% import "@my_theme/misc/forms.html.twig" as forms %}\n'
        "{% import _self as own %}\n"
    ),
    str(MACRO_THEME / "components/button/button.component.yml"): "name: Button\n",
    str(MACRO_THEME / "components/button/button.twig"): (
        "{% import '@my_theme/misc/macros.twig' as m %}\n<button></button>\n"
    ),
}


def test_a_macro_file_is_a_template_that_its_importers_link_to(tmp_path: Path) -> None:
    """A Twig file not named .html.twig that defines a macro is a template, at each macro's line;
    import and from of it give template_includes from a template and
    component_includes_template from a component. A Twig file with no macro is no template, and
    _self links nothing."""
    _plant(tmp_path, MACRO_FILES)
    document, report = _map(tmp_path)
    assert [r for _, _, r, _ in report.skipped if r.startswith("macro_file")] == []
    templates = {
        n["id"]: sorted(place["line"] for place in n["locations"])
        for n in document["nodes"]
        if n["type"] == "drupal.template"
    }
    assert templates == {
        "drupal.template::macros": [2, 3],
        "drupal.template::forms": [1],
        "drupal.template::page": [1],
    }
    found = {
        (e["kind"], e["from"], e["to"], tuple(sorted(p["line"] for p in e["locations"])))
        for e in document["edges"]
        if e["kind"] in ("template_includes", "component_includes_template")
    }
    assert found == {
        ("template_includes", "drupal.template::page", "drupal.template::macros", (1, 2)),
        ("template_includes", "drupal.template::page", "drupal.template::forms", (3,)),
        (
            "component_includes_template",
            "drupal.component::button",
            "drupal.template::macros",
            (1,),
        ),
    }


# --- own entity classes, validators, config objects and inherited constants ------------------

SHORT_NAME_LIST = r"""<?php

namespace Drupal\my_module\Controller;

use Drupal\my_module\Entity\User;
use Drupal\node\Entity\Node;

class ListController {

  public function run() {
    $own = User::load(1);
    $node = Node::load(2);
    $term = \Drupal\taxonomy\Entity\Term::load(3);
    $other = Unlisted::load(4);
  }

}
"""
SHORT_NAME_FILES = {
    str(MODULE / "src/Entity/User.php"): r"""<?php

namespace Drupal\my_module\Entity;

use Drupal\Core\Entity\Attribute\ContentEntityType;

#[ContentEntityType(id: 'my_user')]
class User {
}
""",
    str(MODULE / "src/Controller/ListController.php"): SHORT_NAME_LIST,
    str(MODULE / "src/Controller/CoreController.php"): r"""<?php

namespace Drupal\my_module\Controller;

use Drupal\user\Entity\User;

class CoreController {

  public function run() {
    $account = User::load(1);
  }

}
""",
}


def test_a_module_class_named_as_a_core_entity_class_ends_only_at_its_own_entity_type(
    tmp_path: Path,
) -> None:
    """User::load on a module's own User class ends at its own entity type only, and keeps the
    skipped row of a class the table does not list, as Unlisted does; User, Node and Term of core
    end at core's entity types, through the use statements or written whole."""
    _plant(tmp_path, SHORT_NAME_FILES)
    document, report = _map(tmp_path)
    listing = str(MODULE / "src/Controller/ListController.php")
    assert [(f, line, r, why) for f, line, r, why in report.skipped] == [
        (
            listing,
            _line(SHORT_NAME_LIST, written),
            "entity_class_static_call",
            "no resolution step holds for scope",
        )
        for written in ("$own = User::load(1);", "$other = Unlisted::load(4);")
    ]
    listed = "php.method::Drupal\\my_module\\Controller\\ListController::run"
    core = "php.method::Drupal\\my_module\\Controller\\CoreController::run"
    entity = "drupal.entity_type::"
    found = {
        (e["from"], e["to"], p["rule"])
        for e in document["edges"]
        if e["kind"] == "uses_entity_type"
        for p in e["provenance"]
    }
    assert found == {
        (listed, entity + "my_user", "entity_class_static_call_mapped"),
        (listed, entity + "node", "entity_class_static_call"),
        (listed, entity + "taxonomy_term", "entity_class_static_call"),
        (core, entity + "user", "entity_class_static_call"),
    }


VALIDATOR_FILES = {
    **{
        str(CONSTRAINT / f"{name}ConstraintValidator.php"): (
            "<?php\n\nnamespace Drupal\\my_module\\Plugin\\Validation\\Constraint;\n\n"
            f"class {name}ConstraintValidator {{\n}}\n"
        )
        for name in ("Other", "Text", "Built")
    },
    str(CONSTRAINT / "SharedValidator.php"): (
        "<?php\n\nnamespace Drupal\\my_module\\Plugin\\Validation\\Constraint;\n\n"
        "class SharedValidator {\n}\n"
    ),
    **{
        str(CONSTRAINT / f"{name}Constraint.php"): (
            "<?php\n\nnamespace Drupal\\my_module\\Plugin\\Validation\\Constraint;\n\n"
            "use Drupal\\Core\\Validation\\Attribute\\Constraint;\n\n"
            f"#[Constraint(id: 'My{name}', label: '{name}')]\n"
            f"class {name}Constraint {{\n\n"
            f"  public function validatedBy() {{\n    return {returned};\n  }}\n\n}}\n"
        )
        for name, returned in (
            ("Other", "SharedValidator::class"),
            ("Text", "'\\Drupal\\my_module\\Plugin\\Validation\\Constraint\\SharedValidator'"),
            ("Built", "static::class . 'Validator'"),
        )
    },
}


def test_a_written_validated_by_stops_the_validator_named_by_convention(tmp_path: Path) -> None:
    """validatedBy() returning Name::class or the class's full name as text gives a declared edge
    to that class and no inferred edge to <class>Validator, though that class is mapped; one that
    returns anything else gives neither."""
    _plant(tmp_path, VALIDATOR_FILES)
    document, _ = _map(tmp_path)
    shared = "php.type::Drupal\\my_module\\Plugin\\Validation\\Constraint\\SharedValidator"
    found = {
        (e["from"], e["to"], p["rule"], p["confidence"])
        for e in document["edges"]
        if e["kind"] == "validated_by"
        for p in e["provenance"]
    }
    assert found == {
        ("drupal.plugin.constraint::MyOther", shared, "constraint_validated_by_method", "declared"),
        ("drupal.plugin.constraint::MyText", shared, "constraint_validated_by_method", "declared"),
    }


CONFIG_OBJECT_FIELDS = r"""<?php

namespace Drupal\my_module;

class Reader {

  public function read($entity, $config, $form_state, $site_config) {
    $entity->get('field_color');
    $this->entity->get('field_color');
    $entity->get('field_ref')->entity->get('field_color');
    $this->getEntity()->get('field_color');
    $form_state->get('field_state');
    $config->get('field_conf_var');
    $site_config->get('field_conf_suffix');
    $this->config->get('field_conf_property');
    \Drupal::config('my_module.settings')->get('field_conf_drupal');
    $this->config('my_module.settings')->get('field_conf_own');
    $this->configFactory->get('my_module.settings')->get('field_conf_factory');
    $this->configFactory->getEditable('my_module.settings')->set('field_conf_editable', 1);
  }

}
"""


def test_a_field_name_read_on_a_config_object_links_to_no_field(tmp_path: Path) -> None:
    """get, set and hasField on a config factory or a config object, a variable or property
    ending in config, give no accesses_field edge and no mark; on any other object they do."""
    _plant(
        tmp_path,
        {
            "config/sync/field.storage.node.field_color.yml": FIELD_STORAGE.format(
                entity="node", field="field_color"
            ),
            str(MODULE / "src/Reader.php"): CONFIG_OBJECT_FIELDS,
        },
    )
    document, _ = _map(tmp_path)
    storage = "drupal.config::field.storage."
    found = {
        (e["from"], e["to"])
        for e in document["edges"]
        if e["kind"] == "accesses_field"
    }
    read = "php.method::Drupal\\my_module\\Reader::read"
    assert found == {
        (read, storage + "node.field_color"),
        (read, storage + "field_ref"),
        (read, storage + "field_state"),
    }


CONSTANT_FILES = {
    "config/sync/user.role.my_editor.yml": "id: my_editor\nlabel: Editor\npermissions: []\n",
    "config/sync/my_module.settings.yml": "mode: soft\n",
    "config/sync/field.storage.node.field_size.yml": FIELD_STORAGE.format(
        entity="node", field="field_size"
    ),
    **{
        str(MODULE / f"src/Plugin/QueueWorker/{name}Worker.php"): (
            "<?php\n\nnamespace Drupal\\my_module\\Plugin\\QueueWorker;\n\n"
            "use Drupal\\Core\\Queue\\Attribute\\QueueWorker;\n\n"
            f"#[QueueWorker(id: '{queue}')]\nclass {name}Worker {{\n}}\n"
        )
        for name, queue in (("Notify", "my_notify"), ("Sweep", "my_sweep"))
    },
    str(MODULE / "src/Service/NotifierInterface.php"): r"""<?php

namespace Drupal\my_module\Service;

interface NotifierInterface {

  public const QUEUE_NAME = 'my_notify';
  const EDITOR_ROLE = "my_editor";
  const SETTINGS = 'my_module.settings';
  const SIZE_FIELD = 'field_size';
  const GONE_FIELD = 'field_gone';

}
""",
    str(MODULE / "src/Service/Notifier.php"): r"""<?php

namespace Drupal\my_module\Service;

class Notifier implements NotifierInterface {

  public function run($account, $entity) {
    $this->queueFactory->get(self::QUEUE_NAME);
    $account->hasRole(self::EDITOR_ROLE);
    $account->addRole(static::EDITOR_ROLE);
    \Drupal::config(self::SETTINGS);
    $this->configFactory->getEditable(self::SETTINGS);
    $entity->get(self::SIZE_FIELD);
    $entity->get(self::GONE_FIELD);
  }

}
""",
    str(MODULE / "src/Service/SweeperInterface.php"): r"""<?php

namespace Drupal\my_module\Service;

interface SweeperInterface {

  const QUEUE_NAME = 'my_sweep';

}
""",
    str(MODULE / "src/Service/BaseSweeper.php"): r"""<?php

namespace Drupal\my_module\Service;

abstract class BaseSweeper implements SweeperInterface {
}
""",
    str(MODULE / "src/Service/Sweeper.php"): r"""<?php

namespace Drupal\my_module\Service;

class Sweeper extends BaseSweeper {

  public function sweep() {
    \Drupal::queue(static::QUEUE_NAME);
  }

}
""",
}


def test_a_name_given_as_a_constant_of_an_interface_or_a_parent_links_to_its_target(
    tmp_path: Path,
) -> None:
    """A queue, role, configuration or field name given as self::X or static::X, where X is
    declared as text on an interface the class implements or on a parent's interface, gives the
    edge the text would, inferred, at the method's line; a field_ name with no storage ends at an
    unresolved storage. The file rules keep their skipped rows."""
    _plant(tmp_path, CONSTANT_FILES)
    document, report = _map(tmp_path)
    notifier = str(MODULE / "src/Service/Notifier.php")
    sweeper = str(MODULE / "src/Service/Sweeper.php")
    no_text = "argument 0 is a class constant with no declared text"
    assert sorted((f, line, r, why) for f, line, r, why in report.skipped) == sorted(
        [
            (
                "config/sync/user.role.my_editor.yml",
                1,
                "role_from_config_edges",
                "edge grants_permission: no value for key permissions",
            ),
            (notifier, 8, "queue_from_factory", no_text),
            (notifier, 8, "field_named_by_constant_in_call", no_text),
            (notifier, 9, "role_checked_in_call", no_text),
            (notifier, 10, "role_changed_in_call", no_text),
            (notifier, 11, "config_read_by_drupal", no_text),
            (notifier, 12, "config_edited_from_factory", no_text),
            (notifier, 13, "field_named_by_constant_in_call", no_text),
            (notifier, 14, "field_named_by_constant_in_call", no_text),
            (sweeper, 8, "queue_by_drupal", no_text),
        ]
    )
    run = "php.method::Drupal\\my_module\\Service\\Notifier::run"
    sweep = "php.method::Drupal\\my_module\\Service\\Sweeper::sweep"
    found = {
        (e["kind"], e["from"], e["to"], e["locations"][0]["line"], p["rule"], p["confidence"])
        for e in document["edges"]
        if e["kind"]
        in (
            "uses_queue",
            "checks_role",
            "changes_role",
            "reads_config_object",
            "edits_config_object",
            "accesses_field",
        )
        for p in e["provenance"]
    }
    worker = "drupal.plugin.queue_worker::"
    role = "drupal.config::user.role.my_editor"
    settings = "drupal.config::my_module.settings"
    storage = "drupal.config::field.storage."
    assert found == {
        ("uses_queue", run, worker + "my_notify", 7, "queue_by_class_constant", "inferred"),
        ("uses_queue", sweep, worker + "my_sweep", 7, "queue_by_class_constant", "inferred"),
        ("checks_role", run, role, 7, "code_checks_role_by_constant", "inferred"),
        ("changes_role", run, role, 7, "code_changes_role_by_constant", "inferred"),
        ("reads_config_object", run, settings, 7, "config_read_by_class_constant", "inferred"),
        ("edits_config_object", run, settings, 7, "config_edited_by_class_constant", "inferred"),
        (
            "accesses_field",
            run,
            storage + "node.field_size",
            7,
            "code_accesses_field_by_class_constant",
            "inferred",
        ),
        (
            "accesses_field",
            run,
            storage + "field_gone",
            7,
            "code_accesses_field_by_class_constant",
            "inferred",
        ),
    }
