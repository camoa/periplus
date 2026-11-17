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
    # No core table, api file or invocation names these two, so hook_by_name_only marks each.
    for hook in ("settings_submit", "deploy_NAME"):
        expected[hook] = (*expected[hook][:2], ("inferred", "inferred"))
    marked = sorted(
        node["id"] for node in document["nodes"] if node.get("attributes", {}).get("hook_known")
    )
    assert marked == [
        "drupal.hook::deploy_NAME",
        "drupal.hook::settings_submit",
        "php.function::mymod_deploy_seed",
        "php.function::mymod_settings_submit",
    ]
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
    # The theme has an info file, so each function in its folder belongs to it; the module has none.
    members = [
        ("function_in_theme", f"php.function::{function}", "drupal.theme::my_theme", ["declared"])
        for function in (
            "my_theme_preprocess_html",
            "my_theme_preprocess_node",
            "my_theme_preprocess_page",
            "other_helper",
        )
    ]
    # Each function with a parameter holds it.
    parameters = [
        ("has_parameter", f"php.function::{fn}", f"php.parameter::{fn}::{name}", ["declared"])
        for fn, name in (
            ("mymod_form_alter", "$form"),
            ("mymod_settings_submit", "$form"),
            ("my_theme_preprocess_page", "$variables"),
            ("my_theme_preprocess_node", "$variables"),
            ("my_theme_preprocess_html", "$variables"),
            ("mymod_post_update_fix_things", "$sandbox"),
            ("mymod_deploy_seed", "$sandbox"),
        )
    ]
    assert edges == sorted(
        [
            ("implements_hook", f"php.function::{function}", f"drupal.hook::{hook}", ["inferred"])
            for hook, (_, function) in wanted.items()
        ]
        + members
        + parameters
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
    """No core file is planted. Each listed base is a boundary node with no location; the
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
        assert (node["type"], node["state"], node["locations"]) == (kind, "boundary", [])
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
    assert (report.internal.nodes, report.internal.edges) == (4, 5), report.internal


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
    """A constant of an Event class or an *Events class is an event, named by the text it holds,
    with a drupal.event_constant that names it; each key of getSubscribedEvents, in either form,
    joins its listener, and each dispatch its method, all inferred, at the key's line. A second
    constant of one statement is an event named by its text too. An outside event keeps its
    constant's name; an own-class constant ends at a referenced event of its text; an array
    outside getSubscribedEvents gives nothing; a class in the file's namespace joins in the map."""
    _plant(tmp_path, EVENTS)
    document, report = _map(tmp_path)
    own = "Drupal\\my_module\\"
    sub = f"php.method::{own}EventSubscriber\\OrderSubscriber::"
    notify = f"php.method::{own}Service\\Notifier::notify"
    cancelled = "drupal.event::my_module.cancelled"
    constant = f"drupal.event_constant::{own}"
    states = {
        n["id"]: n["state"]
        for n in document["nodes"]
        if n["type"] in ("drupal.event", "drupal.event_constant")
    }
    assert states == {
        "drupal.event::my_module.placed": "mapped",
        cancelled: "mapped",
        "drupal.event::my_module.paid": "mapped",
        "drupal.event::my_module.local": "mapped",
        "drupal.event::my_module.mine": "referenced",
        "drupal.event::my_module.sent": "referenced",
        "drupal.event::Symfony\\Component\\HttpKernel\\KernelEvents::REQUEST": "referenced",
        constant + "Event\\OrderEvent::PLACED": "mapped",
        constant + "Event\\OrderEvent::CANCELLED": "mapped",
        constant + "Event\\OrderEvents::PAID": "mapped",
        constant + "EventSubscriber\\LocalEvents::LOCAL": "mapped",
    }
    names = {(e["from"], e["to"]) for e in document["edges"] if e["kind"] == "names_event"}
    assert names == {
        (constant + "Event\\OrderEvent::PLACED", "drupal.event::my_module.placed"),
        (constant + "Event\\OrderEvent::CANCELLED", cancelled),
        (constant + "Event\\OrderEvents::PAID", "drupal.event::my_module.paid"),
        (constant + "EventSubscriber\\LocalEvents::LOCAL", "drupal.event::my_module.local"),
    }
    found = {
        (e["kind"], e["from"], e["to"], e["locations"][0]["line"], p["rule"], p["confidence"])
        for e in document["edges"]
        if e["kind"] in ("subscribed_by", "dispatched_by", "dispatched_by_function")
        for p in e["provenance"]
    }
    request = "drupal.event::Symfony\\Component\\HttpKernel\\KernelEvents::REQUEST"
    text = "event_subscribed_by_text"
    sent = "event_dispatched_by_text"
    by_constant = "event_subscribed_by_constant"
    assert found == {
        ("subscribed_by", cancelled, sub + "onCancelled", 15, text, "inferred"),
        ("subscribed_by", "drupal.event::my_module.mine", sub + "onMine", 16, text, "inferred"),
        ("subscribed_by", "drupal.event::my_module.placed", sub + "onPlaced", 18, text, "inferred"),
        ("subscribed_by", request, sub + "onRequest", 19, by_constant, "inferred"),
        ("subscribed_by", "drupal.event::my_module.paid", sub + "onPaid", 20, text, "inferred"),
        ("subscribed_by", "drupal.event::my_module.local", sub + "onLocal", 21, text, "inferred"),
        ("dispatched_by", "drupal.event::my_module.placed", notify, 14, sent, "inferred"),
        ("dispatched_by", "drupal.event::my_module.paid", notify, 15, sent, "inferred"),
        ("dispatched_by", "drupal.event::my_module.sent", notify, 16, sent, "inferred"),
        ("dispatched_by", cancelled, notify, 18, sent, "inferred"),
        (
            "dispatched_by_function",
            "drupal.event::my_module.placed",
            "php.function::my_module_user_login",
            6,
            "event_dispatched_by_function_text",
            "inferred",
        ),
    }
    assert report.skipped == ()


PRIORITIES = {
    **EVENTS,
    str(MODULE / "src/EventSubscriber/PrioritySubscriber.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\my_module\Event\OrderEvent;
use Drupal\my_module\Event\OrderEvents;
use Symfony\Component\EventDispatcher\EventSubscriberInterface;
use Symfony\Component\HttpKernel\KernelEvents;

class PrioritySubscriber implements EventSubscriberInterface {

  const LATE = -100;

  public static function getSubscribedEvents() {
    return [
      OrderEvents::PAID => [['onPaidFirst', -10], ['onPaidSecond', 20]],
      OrderEvent::PLACED => ['onPlacedLate', self::LATE],
      LocalEvents::LOCAL => [
        'onLocalHigh',
        50,
      ],
      KernelEvents::REQUEST => ['onRequestMax', PHP_INT_MAX],
      OrderEvent::CANCELLED => ['onCancelledPlain'],
    ];
  }

  public function helper() {
    return [OrderEvent::PLACED => ['notAListener', 9]];
  }

  public function onPaidFirst($event) {
  }

  public function onPaidSecond($event) {
  }

  public function onPlacedLate($event) {
  }

  public function onLocalHigh($event) {
  }

  public function onRequestMax($event) {
  }

  public function onCancelledPlain($event) {
  }

}
""",
}


def test_a_subscribed_by_edge_holds_the_priority_as_written_and_0_when_none_is(
    tmp_path: Path,
) -> None:
    """Each form of getSubscribedEvents gives its listener's priority: a number, a negative one, a
    constant, a value on its own line, and 0 when none is written, as Symfony runs it; each
    listener of a list of lists holds its own. A key outside getSubscribedEvents gives nothing."""
    _plant(tmp_path, PRIORITIES)
    document, _ = _map(tmp_path)
    own = "Drupal\\my_module\\EventSubscriber\\"
    found = {
        e["to"].removeprefix(f"php.method::{own}"): e.get("attributes")
        for e in document["edges"]
        if e["kind"] == "subscribed_by"
    }
    assert found == {
        "OrderSubscriber::onCancelled": {"priority": "5"},
        "OrderSubscriber::onMine": {"priority": "0"},
        "OrderSubscriber::onPlaced": {"priority": "0"},
        "OrderSubscriber::onRequest": {"priority": "100"},
        "OrderSubscriber::onPaid": {"priority": "0"},
        "OrderSubscriber::onLocal": {"priority": "0"},
        "PrioritySubscriber::onPaidFirst": {"priority": "-10"},
        "PrioritySubscriber::onPaidSecond": {"priority": "20"},
        "PrioritySubscriber::onPlacedLate": {"priority": "self::LATE"},
        "PrioritySubscriber::onLocalHigh": {"priority": "50"},
        "PrioritySubscriber::onRequestMax": {"priority": "PHP_INT_MAX"},
        "PrioritySubscriber::onCancelledPlain": {"priority": "0"},
    }


LIST_LISTENERS = {
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
    str(MODULE / "src/EventSubscriber/ListSubscriber.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\my_module\Event\OrderEvents;
use Symfony\Component\EventDispatcher\EventSubscriberInterface;
use Symfony\Component\HttpKernel\KernelEvents;

class ListSubscriber implements EventSubscriberInterface {

  const MINE = 'my_module.mine';

  public static function getSubscribedEvents() {
    $events[KernelEvents::RESPONSE] = [['onResponseA', 3], ['onResponseB']];
    return $events + [
      OrderEvents::PAID => [['first', 10], ['second'], ['third', -5]],
      self::MINE => [
        ['mineFirst'],
        ['mineSecond', self::LATE],
      ],
      LocalEvents::LOCAL => [['localFirst', 1], ['localSecond', 2]],
      KernelEvents::REQUEST => ['onRequestSingle', 7],
    ];
  }

  public function helper() {
    return [OrderEvents::PAID => [['notA', 1], ['notB', 2]]];
  }

  public function first() {}
  public function second() {}
  public function third() {}
  public function mineFirst() {}
  public function mineSecond() {}
  public function localFirst() {}
  public function localSecond() {}
  public function onResponseA() {}
  public function onResponseB() {}
  public function onRequestSingle() {}
  public function notA() {}
  public function notB() {}

}
""",
}


ATTRIBUTE_LISTENERS = {
    str(MODULE / "src/Event/OrderEvents.php"): r"""<?php

namespace Drupal\my_module\Event;

final class OrderEvents {

  const PAID = 'my_module.paid';

}
""",
    str(MODULE / "src/EventSubscriber/CaseListener.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Symfony\Component\EventDispatcher\Attribute\AsEventListener;

#[AsEventListener(event: 'my_module.case_test')]
class CaseListener {

  public function onmymodulecasetest($event) {
  }

  public function __invoke($event) {
  }

}
""",
    str(MODULE / "src/EventSubscriber/ClassListener.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\my_module\Event\OrderEvents;
use Symfony\Component\EventDispatcher\Attribute\AsEventListener;
use Symfony\Component\HttpKernel\Event\RequestEvent;
use Symfony\Component\HttpKernel\KernelEvents;

#[AsEventListener(event: KernelEvents::EXCEPTION, method: 'handle', priority: 9)]
#[AsEventListener(event: 'kernel.terminate')]
#[AsEventListener(event: 'my_module.custom_thing', priority: 2)]
#[AsEventListener(event: OrderEvents::PAID)]
#[AsEventListener(method: 'onTypedClass')]
final class ClassListener {

  public function handle($event) {
  }

  public function onKernelTerminate($event) {
  }

  public function __invoke($event) {
  }

  public function onTypedClass(RequestEvent $event) {
  }

}
""",
    str(MODULE / "src/EventSubscriber/InvokeListener.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Symfony\Component\EventDispatcher\Attribute\AsEventListener;
use Symfony\Component\HttpKernel\Event\ResponseEvent;

#[AsEventListener]
class InvokeListener {

  public function __invoke(ResponseEvent $event) {
  }

}
""",
    str(MODULE / "src/EventSubscriber/LocalEvent.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Symfony\Contracts\EventDispatcher\Event;

class LocalEvent extends Event {
}
""",
    str(MODULE / "src/EventSubscriber/LocalEvents.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

final class LocalEvents {

  const LOCAL = 'my_module.local';

}
""",
    str(MODULE / "src/EventSubscriber/LostListener.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Symfony\Component\EventDispatcher\Attribute\AsEventListener;

#[AsEventListener(event: 'my_module.lost')]
class LostListener {

  public function other($event) {
  }

}
""",
    str(MODULE / "src/EventSubscriber/MethodListener.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\Core\Hook\Attribute\Hook;
use Drupal\my_module\Event\OrderEvents;
use Symfony\Component\EventDispatcher\Attribute\AsEventListener;
use Symfony\Component\HttpKernel\Event\RequestEvent;
use Symfony\Component\HttpKernel\KernelEvents;

class MethodListener {

  const MINE = 'my_module.mine_attr';

  #[AsEventListener(event: OrderEvents::PAID, priority: 20)]
  public function onPaid($event) {
  }

  #[AsEventListener(KernelEvents::REQUEST)]
  public function onRequest(RequestEvent $event) {
  }

  #[AsEventListener(event: 'kernel.response', priority: -5)]
  public function onResponse($event) {
  }

  #[AsEventListener]
  public function onTyped(RequestEvent $event) {
  }

  #[AsEventListener(priority: 3)]
  public function onTypedLocal(?LocalEvent $event): void {
  }

  #[AsEventListener(event: self::MINE)]
  public function onMine($event) {
  }

  #[AsEventListener(event: 'my_module.paid')]
  public function onPaidByName($event) {
  }

  #[AsEventListener(priority: 4, event: LocalEvents::LOCAL)]
  public function onLocal($event) {
  }

  // #[AsEventListener(event: 'my_module.commented')]
  #[Hook('cron')]
  #[AsEventListenerish(event: KernelEvents::REQUEST)]
  #[EventListener(event: 'kernel.view')]
  public function notAListener() {
  }

}
""",
    str(MODULE / "src/EventSubscriber/MoreListener.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\Core\Hook\Attribute\Hook;
use Drupal\my_module\Event\OrderEvents;
use Symfony\Component\EventDispatcher\Attribute\AsEventListener;
use Symfony\Component\HttpKernel\Event\RequestEvent;
use Symfony\Component\HttpKernel\Event\ResponseEvent;
use Symfony\Component\HttpKernel\Event\ViewEvent;

class MoreListener {

  const BASE = 10;

  #[Hook('cron'), AsEventListener(event: 'my_module.grouped')]
  public function onGrouped($event) {
  }

  #[AsEventListener(event: 'my_module.one'), AsEventListener(event: 'my_module.two', priority: 5)]
  public function onBoth($event) {
  }

  #[AsEventListener(event: OrderEvents::PAID, priority: (self::BASE + 1))]
  public function onParen($event) {
  }

  #[AsEventListener]
  public function onUnion(RequestEvent|ResponseEvent|null $event) {
  }

  #[AsEventListener]
  public function onTwo(ViewEvent $event, RequestEvent $other) {
  }

}
""",
    str(MODULE / "src/EventSubscriber/OwnConstantListener.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Symfony\Component\EventDispatcher\Attribute\AsEventListener;

#[AsEventListener(event: self::DONE, priority: -1)]
#[AsEventListener(event: LocalEvents::LOCAL)]
class OwnConstantListener {

  const DONE = 'my_module.done';

  public function __invoke($event) {
  }

}
""",
}


TAG_LISTENERS = {
    str(MODULE / "my_module.info.yml"): r"""name: My module
type: module
core_version_requirement: ^11
""",
    str(MODULE / "my_module.services.yml"): r"""services:
  my_module.flow_listener:
    class: Drupal\my_module\EventSubscriber\FlowListener
    tags:
      - { name: kernel.event_listener, event: kernel.request, method: onRequest, priority: 12 }
      - { name: kernel.event_listener, event: my_module.paid, method: onPaid }
      - { name: kernel.event_listener, event: kernel.response }
  my_module.block_listener:
    class: Drupal\my_module\EventSubscriber\BlockListener
    arguments: ['@current_user']
    tags:
      - name: kernel.event_listener
        event: kernel.exception
        method: onException
        priority: -20
      - name: kernel.event_listener
        method: onTyped
  Drupal\my_module\EventSubscriber\KeyListener:
    tags:
      - { name: 'kernel.event_listener', event: 'kernel.controller', method: 'onController' }
  my_module.core_class_listener:
    class: Drupal\Core\EventSubscriber\SomeCoreListener
    tags:
      - { name: kernel.event_listener, event: kernel.view, method: onView }
  my_module.inherits_listener:
    class: Drupal\my_module\EventSubscriber\ChildListener
    tags:
      - { name: kernel.event_listener, event: kernel.finish_request, method: onRequest }
  my_module.invoke_listener:
    class: Drupal\my_module\EventSubscriber\InvokeOnly
    tags:
      - { name: kernel.event_listener, event: my_module.thing }
  my_module.lost_listener:
    class: Drupal\my_module\EventSubscriber\KeyListener
    tags:
      - { name: kernel.event_listener, event: my_module.lost }
  # A child service with no class of its own.
  my_module.child_service:
    parent: my_module.flow_listener
    tags:
      - { name: kernel.event_listener, event: kernel.request, method: onChild, priority: 1 }
  my_module.inline_listener:
    class: Drupal\my_module\EventSubscriber\FlowListener
    tags: [{ name: event_subscriber }, { name: kernel.event_listener, event: kernel.term"""
    r"""inate, method: onPaid, priority: 3 }, { name: other_tag, method: onRequest }]
  my_module.const_listener:
    class: Drupal\my_module\EventSubscriber\FlowListener
    tags:
      - { name: kernel.event_listener, event: !php/const Drupal\my_module\Event\OrderEve"""
    r"""nts::PAID, method: onPaid, priority: 4 }
      - { name: kernel.event_listener, event: !php/const \Symfony\Component\HttpKernel\K"""
    r"""ernelEvents::VIEW, method: onMissing }
      - { name: kernel.event_listener, event: !php/const Drupal\my_module\Event\OrderEvents::PAID }
  my_module.not_listener:
    class: Drupal\my_module\EventSubscriber\FlowListener
    tags:
      - { name: some_other_tag, event: kernel.request, method: onRequest }
      - { name: event_subscriber }
      - name: some_block_tag
        event: kernel.request
        method: onRequest
""",
    str(MODULE / "src/Event/OrderEvents.php"): r"""<?php

namespace Drupal\my_module\Event;

final class OrderEvents {

  const PAID = 'my_module.paid';

}
""",
    str(MODULE / "src/EventSubscriber/BlockListener.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Symfony\Component\HttpKernel\Event\ViewEvent;

class BlockListener {

  public function onException($event) {
  }

  public function onTyped(ViewEvent $event) {
  }

}
""",
    str(MODULE / "src/EventSubscriber/ChildListener.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

class ChildListener extends FlowListener {
}
""",
    str(MODULE / "src/EventSubscriber/FlowListener.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

class FlowListener {

  public function onRequest($event) {
  }

  public function onPaid($event) {
  }

  public function onKernelResponse($event) {
  }

}
""",
    str(MODULE / "src/EventSubscriber/InvokeOnly.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

class InvokeOnly {

  public function __invoke($event) {
  }

}
""",
    str(MODULE / "src/EventSubscriber/KeyListener.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

class KeyListener {

  public function onController($event) {
  }

}
""",
}


EXCEPTION_PRIORITIES = {
    str(MODULE / "src/EventSubscriber/ChildOfComputedSubscriber.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

class ChildOfComputedSubscriber extends ComputedExceptionSubscriber {

  public function on401($event) {
  }

}
""",
    str(MODULE / "src/EventSubscriber/ChildOfLiteralSubscriber.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

class ChildOfLiteralSubscriber extends LiteralExceptionSubscriber {

  public function on5xx($event) {
  }

  public function onJson404($event) {
  }

  public function onward($event) {
  }

}
""",
    str(MODULE / "src/EventSubscriber/ComputedExceptionSubscriber.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\Core\EventSubscriber\HttpExceptionSubscriberBase;

class ComputedExceptionSubscriber extends HttpExceptionSubscriberBase {

  protected static function getPriority() {
    return parent::getPriority() + 1;
  }

  public function on4xx($event) {
  }

}
""",
    str(MODULE / "src/EventSubscriber/LiteralExceptionSubscriber.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\Core\EventSubscriber\HttpExceptionSubscriberBase;

class LiteralExceptionSubscriber extends HttpExceptionSubscriberBase {

  protected static function getPriority() {
    return 75;
  }

  public function on404($event) {
  }

}
""",
    str(MODULE / "src/EventSubscriber/NotAnExceptionSubscriber.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

class NotAnExceptionSubscriber {

  protected static function getPriority() {
    return 5;
  }

  public function on403($event) {
  }

}
""",
    str(MODULE / "src/EventSubscriber/OverridingChildSubscriber.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

class OverridingChildSubscriber extends LiteralExceptionSubscriber {

  protected static function getPriority(): int {
    return -10;
  }

  public function on410($event) {
  }

}
""",
    str(MODULE / "src/EventSubscriber/PlainExceptionSubscriber.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\Core\EventSubscriber\HttpExceptionSubscriberBase;

class PlainExceptionSubscriber extends HttpExceptionSubscriberBase {

  protected function getHandledFormats() {
    return ['html'];
  }

  public function on403($event) {
  }

}
""",
}


def _subscribed(document: dict[str, Any]) -> set[tuple[str, str, str | None]]:
    """Each subscribed_by edge as (event, listener, priority), the module's prefixes cut."""
    own = "Drupal\\my_module\\EventSubscriber\\"
    kernel = "Symfony\\Component\\HttpKernel\\"
    return {
        (
            e["from"].removeprefix("drupal.event::").replace(kernel, ""),
            e["to"].removeprefix("php.method::").replace(own, ""),
            _priority(e),
        )
        for e in document["edges"]
        if e["kind"] == "subscribed_by"
    }


def _priority(edge: dict[str, Any]) -> Any:
    """The edge's priority, or the sorted values of one that differs between places."""
    value = edge.get("attributes", {}).get("priority")
    if isinstance(value, dict):
        return tuple(sorted(place["value"] for place in value["differs"]))
    return value


_LISTENER_KINDS = (
    "subscribed_by",
    "subscribed_by_function",
    "registers_listener_at_runtime",
    "registers_subscriber",
    "alters_routes",
)


def _short(node: str) -> str:
    """The node's name after its namespace, the module's prefixes cut."""
    name = node.split("::", 1)[1]
    for prefix in (
        "Symfony\\Component\\HttpKernel\\",
        "Drupal\\my_module\\EventSubscriber\\",
        "Drupal\\my_module\\",
    ):
        name = name.replace(prefix, "")
    return name


def _registrations(document: dict[str, Any]) -> set[tuple[str, str, str, Any]]:
    """Each listener edge and runtime registration as (kind, from, to, priority), the module's
    prefixes cut."""
    return {
        (e["kind"], _short(e["from"]), _short(e["to"]), _priority(e))
        for e in document["edges"]
        if e["kind"] in _LISTENER_KINDS
    }


def test_each_listener_of_a_list_of_lists_is_subscribed_with_its_own_priority(
    tmp_path: Path,
) -> None:
    """X::NAME => [['a', 10], ['b'], ['c', -5]] gives every listener its edge, in each key form:
    a class through use, self::NAME, a class of the file's namespace, and $events[X::NAME] = [...].
    A list of lists outside getSubscribedEvents gives nothing."""
    _plant(tmp_path, LIST_LISTENERS)
    document, report = _map(tmp_path)
    assert _subscribed(document) == {
        ("KernelEvents::REQUEST", "ListSubscriber::onRequestSingle", "7"),
        ("KernelEvents::RESPONSE", "ListSubscriber::onResponseA", "3"),
        ("KernelEvents::RESPONSE", "ListSubscriber::onResponseB", "0"),
        ("my_module.local", "ListSubscriber::localFirst", "1"),
        ("my_module.local", "ListSubscriber::localSecond", "2"),
        ("my_module.mine", "ListSubscriber::mineFirst", "0"),
        ("my_module.mine", "ListSubscriber::mineSecond", "self::LATE"),
        ("my_module.paid", "ListSubscriber::first", "10"),
        ("my_module.paid", "ListSubscriber::second", "0"),
        ("my_module.paid", "ListSubscriber::third", "-5"),
    }
    assert report.skipped == ()


def test_an_as_event_listener_attribute_subscribes_its_method_as_symfony_reads_it(
    tmp_path: Path,
) -> None:
    """On a method: the event by constant, by quoted name or by the first parameter's type, the
    priority by name. On a class: the method argument, else on<Event> for a quoted event, then
    __invoke, then the unresolved derived name, for a constant event derived from the text a
    mapped file gives it, the runtime listener taken back; no event reads the first parameter's
    type, each class of a union and never a second parameter; a derived name meets its method in
    any letter case. An attribute in a group and arguments holding parentheses are read. Each
    listener method carries the mark listens_by_attribute. A comment, an attribute of another name
    and Hook give nothing."""
    _plant(tmp_path, ATTRIBUTE_LISTENERS)
    document, report = _map(tmp_path)
    assert _subscribed(document) == {
        ("Drupal\\my_module\\EventSubscriber\\LocalEvent", "MethodListener::onTypedLocal", "3"),
        ("Event\\RequestEvent", "ClassListener::onTypedClass", "0"),
        ("Event\\RequestEvent", "MethodListener::onTyped", "0"),
        ("Event\\RequestEvent", "MoreListener::onUnion", "0"),
        ("Event\\ResponseEvent", "InvokeListener::__invoke", "0"),
        ("Event\\ResponseEvent", "MoreListener::onUnion", "0"),
        ("Event\\ViewEvent", "MoreListener::onTwo", "0"),
        ("KernelEvents::EXCEPTION", "ClassListener::handle", "9"),
        ("KernelEvents::REQUEST", "MethodListener::onRequest", "0"),
        ("KernelEvents::RESPONSE", "MethodListener::onResponse", "-5"),
        ("KernelEvents::TERMINATE", "ClassListener::onKernelTerminate", "0"),
        ("my_module.case_test", "CaseListener::onmymodulecasetest", "0"),
        ("my_module.custom_thing", "ClassListener::__invoke", "2"),
        ("my_module.done", "OwnConstantListener::__invoke", "-1"),
        ("my_module.grouped", "MoreListener::onGrouped", "0"),
        ("my_module.local", "MethodListener::onLocal", "4"),
        ("my_module.local", "OwnConstantListener::__invoke", "0"),
        ("my_module.lost", "LostListener::onMyModuleLost", "0"),
        ("my_module.mine_attr", "MethodListener::onMine", "0"),
        ("my_module.one", "MoreListener::onBoth", "0"),
        ("my_module.paid", "ClassListener::__invoke", "0"),
        ("my_module.paid", "MethodListener::onPaid", "20"),
        ("my_module.paid", "MethodListener::onPaidByName", "0"),
        ("my_module.paid", "MoreListener::onParen", "(self::BASE + 1)"),
        ("my_module.two", "MoreListener::onBoth", "5"),
    }
    nodes = {n["id"]: n for n in document["nodes"]}
    own = "php.method::Drupal\\my_module\\EventSubscriber\\"
    assert own + "ClassListener|OrderEvents::PAID" not in nodes
    invoked = nodes[own + "ClassListener::__invoke"]["attributes"]
    assert invoked["listens_by_attribute"] == "AsEventListener"
    marked = {
        n["id"].removeprefix(own)
        for n in document["nodes"]
        if "listens_by_attribute" in n.get("attributes", {})
    }
    expected = {
        "MethodListener::onPaid",
        "MoreListener::onUnion",
        "CaseListener::onmymodulecasetest",
    }
    assert expected <= marked
    assert document["marks"]["listens_by_attribute"] == "AsEventListener, not wired by core"
    assert nodes[own + "LostListener::onMyModuleLost"]["state"] == "unresolved"
    assert report.skipped == ()


def test_a_kernel_event_listener_tag_subscribes_the_service_class_method(tmp_path: Path) -> None:
    """A tag in the flow or the block form gives its event, a core name meeting its constant, the
    method on the class or a mapped ancestor, else unresolved, its priority, on<Event> or
    __invoke with no method, and the parameter's type with no event. An inline list of tags and an
    event written !php/const are read; a child service takes its parent's class; a constant event
    with no method gets the method derived from its text, unresolved when undeclared. A tag of
    another name gives nothing."""
    _plant(tmp_path, TAG_LISTENERS)
    document, report = _map(tmp_path)
    assert _subscribed(document) == {
        ("Event\\ViewEvent", "BlockListener::onTyped", "0"),
        ("KernelEvents::CONTROLLER", "KeyListener::onController", "0"),
        ("KernelEvents::EXCEPTION", "BlockListener::onException", "-20"),
        ("KernelEvents::FINISH_REQUEST", "FlowListener::onRequest", "0"),
        ("KernelEvents::REQUEST", "FlowListener::onChild", "1"),
        ("KernelEvents::REQUEST", "FlowListener::onRequest", "12"),
        ("KernelEvents::RESPONSE", "FlowListener::onKernelResponse", "0"),
        ("KernelEvents::TERMINATE", "FlowListener::onPaid", "3"),
        ("KernelEvents::VIEW", "Drupal\\Core\\EventSubscriber\\SomeCoreListener::onView", "0"),
        ("KernelEvents::VIEW", "FlowListener::onMissing", "0"),
        ("my_module.lost", "KeyListener::onMyModuleLost", "0"),
        ("my_module.paid", "FlowListener::onMyModulePaid", "0"),
        ("my_module.paid", "FlowListener::onPaid", ("0", "4")),
        ("my_module.thing", "InvokeOnly::__invoke", "0"),
    }
    assert report.skipped == ()


def test_an_inherited_exception_handler_holds_the_priority_get_priority_gives(
    tmp_path: Path,
) -> None:
    """on<status> and on<digit>xx of an HttpExceptionSubscriberBase descendant listen to
    KernelEvents::EXCEPTION: with the base's 0 when no class of the line declares getPriority(),
    the nearest literal return otherwise, and no priority when the nearest one computes it.
    onJson404, onward and a class outside the line give nothing."""
    _plant(tmp_path, EXCEPTION_PRIORITIES)
    document, report = _map(tmp_path)
    assert _subscribed(document) == {
        ("KernelEvents::EXCEPTION", "ChildOfComputedSubscriber::on401", None),
        ("KernelEvents::EXCEPTION", "ChildOfLiteralSubscriber::on5xx", "75"),
        ("KernelEvents::EXCEPTION", "ComputedExceptionSubscriber::on4xx", None),
        ("KernelEvents::EXCEPTION", "LiteralExceptionSubscriber::on404", "75"),
        ("KernelEvents::EXCEPTION", "OverridingChildSubscriber::on410", "-10"),
        ("KernelEvents::EXCEPTION", "PlainExceptionSubscriber::on403", "0"),
    }
    assert report.skipped == ()


KEY_LISTENERS = {
    str(MODULE / "src/Event/OrderEvents.php"): r"""<?php

namespace Drupal\my_module\Event;

final class OrderEvents {

  const PAID = 'my_module.paid';

}
""",
    str(MODULE / "src/EventSubscriber/HelperSubscriber.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Symfony\Component\EventDispatcher\EventSubscriberInterface;

class HelperSubscriber implements EventSubscriberInterface {

  public static function getSubscribedEvents() {
    return static::buildEvents();
  }

  protected static function buildEvents() {
    return ['x' => 'y'];
  }

}
""",
    str(MODULE / "src/EventSubscriber/KeySubscriber.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\my_module\Event;
use Symfony\Component\EventDispatcher\EventSubscriberInterface;

class KeySubscriber implements EventSubscriberInterface {

  public static function getSubscribedEvents() {
    $events['kernel.request'][] = ['onNamedRequest', 8];
    $events['my_module.paid'] = 'onNamedPaid';
    $events[\Drupal\my_module\Event\OrderEvents::PAID][] = ['onQualifiedPaid', 3];
    $events[\Symfony\Component\HttpKernel\KernelEvents::VIEW] = 'onQualifiedView';
    $events[Event\OrderEvents::PAID] = 'onRelativePaid';
    return $events + [
      'kernel.response' => [['onNamedFirst', 4], ['onNamedSecond']],
      \Symfony\Component\HttpKernel\KernelEvents::TERMINATE => [['onTerminateA'], ['onTe"""
    r"""rminateB', -1]],
      'my_module.unknown' => 'onUnknownName',
    ];
  }

  public function helper() {
    return ['kernel.request' => 'notAListener', \Symfony\Component\HttpKernel\KernelEven"""
    r"""ts::VIEW => 'notEither'];
  }

  public function onNamedRequest() {}
  public function onNamedPaid() {}
  public function onQualifiedPaid() {}
  public function onQualifiedView() {}
  public function onRelativePaid() {}
  public function onNamedFirst() {}
  public function onNamedSecond() {}
  public function onTerminateA() {}
  public function onTerminateB() {}
  public function onUnknownName() {}
  public function notAListener() {}
  public function notEither() {}

}
""",
    str(MODULE / "src/EventSubscriber/LoopSubscriber.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Symfony\Component\EventDispatcher\EventSubscriberInterface;

class LoopSubscriber implements EventSubscriberInterface {

  const NAMES = ['a.one', 'a.two'];

  public static function getSubscribedEvents() {
    $events = [];
    foreach (static::NAMES as $name => $label) {
      $events[$name][] = ['onAny'];
    }
    $events['prefix.' . static::SUFFIX] = 'onBuilt';
    return $events;
  }

  public function onAny() {}
  public function onBuilt() {}

}
""",
}


INHERITED_LISTENERS = {
    str(MODULE / "my_module.services.yml"): r"""services:
  my_module.contrib_based:
    class: Drupal\my_module\EventSubscriber\ContribBased
    tags:
      - { name: event_subscriber }
  my_module.child:
    class: Drupal\my_module\EventSubscriber\ChildSubscriber
    tags:
      - { name: event_subscriber }
  my_module.route:
    class: Drupal\my_module\EventSubscriber\MyRouteSubscriber
    tags:
      - { name: event_subscriber }
  my_module.plain:
    class: Drupal\my_module\EventSubscriber\NotASubscriber
""",
    str(MODULE / "src/Event/OrderEvents.php"): r"""<?php

namespace Drupal\my_module\Event;

final class OrderEvents {

  const PAID = 'my_module.paid';

}
""",
    str(MODULE / "src/EventSubscriber/BaseSubscriber.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\my_module\Event\OrderEvents;
use Symfony\Component\EventDispatcher\EventSubscriberInterface;
use Symfony\Component\HttpKernel\KernelEvents;

abstract class BaseSubscriber implements EventSubscriberInterface {

  const OWN = 'my_module.own';

  public static function getSubscribedEvents() {
    $events[OrderEvents::PAID][] = ['onPaid', 5];
    $events[KernelEvents::REQUEST] = 'onRequest';
    $events[self::OWN] = 'onOwn';
    $events[LocalEvents::LOCAL] = ['onLocal', 2];
    $events['kernel.response'] = 'onResponse';
    return $events;
  }

  public function onPaid($event) {}
  public function onRequest($event) {}
  public function onOwn($event) {}
  public function onLocal($event) {}
  public function onResponse($event) {}

}
""",
    str(MODULE / "src/EventSubscriber/ChildSubscriber.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

class ChildSubscriber extends BaseSubscriber {

  public function onPaid($event) {}

}
""",
    str(MODULE / "src/EventSubscriber/ContribBased.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\contrib_thing\EventSubscriber\ThingSubscriberBase;

class ContribBased extends ThingSubscriberBase {

  public function onThing($event) {}

}
""",
    str(MODULE / "src/EventSubscriber/GrandchildSubscriber.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

class GrandchildSubscriber extends ChildSubscriber {

  public function onRequest($event) {}

}
""",
    str(MODULE / "src/EventSubscriber/LocalEvents.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

final class LocalEvents {

  const LOCAL = 'my_module.local';

}
""",
    str(MODULE / "src/EventSubscriber/MergingSubscriber.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

class MergingSubscriber extends BaseSubscriber {

  public static function getSubscribedEvents() {
    $events = parent::getSubscribedEvents();
    $events['my_module.extra'] = 'onExtra';
    return $events;
  }

  public function onExtra($event) {}

  public function onOwn($event) {}

}
""",
    str(MODULE / "src/EventSubscriber/MyConfigOverride.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\Core\Config\ConfigFactoryOverrideBase;

class MyConfigOverride extends ConfigFactoryOverrideBase {

  public function addCollections($info) {}
  public function onConfigSave($event) {}
  public function onConfigDelete($event) {}
  public function onConfigRename($event) {}

}
""",
    str(MODULE / "src/EventSubscriber/MyHtmlExceptions.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\Core\EventSubscriber\DefaultExceptionHtmlSubscriber;

class MyHtmlExceptions extends DefaultExceptionHtmlSubscriber {

  public function on410($event) {}

  public function on403($event) {}

}
""",
    str(MODULE / "src/EventSubscriber/MyRouteSubscriber.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\Core\Routing\RouteSubscriberBase;
use Symfony\Component\Routing\RouteCollection;

class MyRouteSubscriber extends RouteSubscriberBase {

  protected function alterRoutes(RouteCollection $collection) {
  }

}
""",
    str(MODULE / "src/EventSubscriber/MyStaticRoutes.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\Core\Routing\StaticRouteDiscoveryBase;

class MyStaticRoutes extends StaticRouteDiscoveryBase {

  protected static function getPriority(): int {
    return 12;
  }

}
""",
    str(MODULE / "src/EventSubscriber/NotASubscriber.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\contrib_thing\Something;

class NotASubscriber extends Something {

  public function onAlterRoutes($event) {}

}
""",
    str(MODULE / "src/EventSubscriber/OverrideRouteSubscriber.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

class OverrideRouteSubscriber extends MyRouteSubscriber {

  public function onAlterRoutes($event) {
  }

}
""",
    str(MODULE / "src/EventSubscriber/OverridingSubscriber.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

class OverridingSubscriber extends BaseSubscriber {

  public static function getSubscribedEvents() {
    return ['my_module.solo' => 'onSolo'];
  }

  public function onSolo($event) {}

  public function onPaid($event) {}

}
""",
}


ADDED_LISTENERS = {
    str(MODULE / "my_module.module"): r"""<?php

function my_module_boot() {
  \Drupal::service('event_dispatcher')->addListener('kernel.request', 'my_module_on_request');
}

function my_module_on_request($event) {
}

function my_module_terminate($event) {
}
""",
    str(MODULE / "my_module.services.yml"): r"""services:
  my_module.flow:
    class: Drupal\my_module\EventSubscriber\FlowListener
""",
    str(MODULE / "src/Event/OrderEvents.php"): r"""<?php

namespace Drupal\my_module\Event;

final class OrderEvents {

  const PAID = 'my_module.paid';

}
""",
    str(MODULE / "src/EventSubscriber/AddedListener.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

class AddedListener {

  public function onAdded($event) {}
  public function onView($event) {}
  public static function onStatic($event) {}
  public function onTyped(\Symfony\Component\HttpKernel\Event\ViewEvent $event) {}

}
""",
    str(MODULE / "src/EventSubscriber/DerivedListener.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

class DerivedListener {

  public function onMyModulePaid($event) {}

}
""",
    str(MODULE / "src/EventSubscriber/FlowListener.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

class FlowListener {

  public function onPaid($event) {}

}
""",
    str(MODULE / "src/EventSubscriber/KeyedSubscriber.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Symfony\Component\EventDispatcher\EventSubscriberInterface;

class KeyedSubscriber implements EventSubscriberInterface {

  public static function getSubscribedEvents() {
    return ['my_module.keyed' => 'onKeyed'];
  }

  public function onKeyed($event) {}

}
""",
    str(MODULE / "src/EventSubscriber/Wiring.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\my_module\Event\OrderEvents;
use Symfony\Component\HttpKernel\KernelEvents;

class Wiring {

  const LOCAL = 'my_module.wired';

  public function wire($dispatcher, $eventName) {
    $this->dispatcher->addListener(KernelEvents::REQUEST, [$this, 'onA'], 10);
    $dispatcher->addListener('my_module.paid', [AddedListener::class, 'onAdded']);
    $dispatcher->addListener(OrderEvents::PAID, 'Drupal\my_module\EventSubscriber\AddedL"""
    r"""istener::onStatic', -3);
    $dispatcher->addListener(self::LOCAL, $this->onB(...));
    $dispatcher->addListener('kernel.view', function ($event) { $x = [1, 2]; }, 5);
    $dispatcher->addListener('kernel.terminate', 'my_module_terminate');
    $dispatcher->addListener($eventName, [$this, 'onA']);
    $dispatcher->addSubscriber(new KeyedSubscriber());
    $dispatcher->addSubscriber($this->subscriber);
    $this->other->addListenerLater('kernel.request', [$this, 'onA']);
  }

  public function onA($event) {}
  public function onB($event) {}

}
""",
    str(MODULE / "src/MyModuleServiceProvider.php"): r"""<?php

namespace Drupal\my_module;

use Drupal\Core\DependencyInjection\ContainerBuilder;
use Drupal\Core\DependencyInjection\ServiceProviderBase;
use Drupal\my_module\Event\OrderEvents;
use Drupal\my_module\EventSubscriber\AddedListener;
use Drupal\my_module\EventSubscriber\DerivedListener;
use Symfony\Component\DependencyInjection\Definition;

class MyModuleServiceProvider extends ServiceProviderBase {

  public function register(ContainerBuilder $container) {
    $container->register('my_module.added', AddedListener::class)
      ->addTag('kernel.event_listener', ['event' => 'kernel.request', 'method' => 'onAdd"""
    r"""ed', 'priority' => 7]);
    $container->getDefinition('my_module.flow')->addTag('kernel.event_listener', ['event"""
    r"""' => OrderEvents::PAID, 'method' => 'onPaid']);
    $definition = new Definition(AddedListener::class);
    $definition->addTag('kernel.event_listener', ['event' => 'kernel.view', 'method' => 'onView']);
    $container->register('my_module.unknown_event', AddedListener::class)->addTag('kerne"""
    r"""l.event_listener', ['event' => $this->name, 'method' => 'onAdded']);
    $container->register('my_module.no_method', AddedListener::class)->addTag('kernel.ev"""
    r"""ent_listener', ['event' => 'kernel.finish_request']);
    $container->register('my_module.derived', DerivedListener::class)->addTag('kernel.ev"""
    r"""ent_listener', ['event' => 'my_module.paid', 'priority' => 2]);
    $container->register('my_module.typed', AddedListener::class)->addTag('kernel.event_"""
    r"""listener', ['method' => 'onTyped']);
    $container->register('my_module.other', AddedListener::class)->addTag('other_tag', ["""
    r"""'event' => 'kernel.request', 'method' => 'onAdded']);
  }

}
""",
}


def test_a_key_written_as_a_name_or_with_its_namespace_subscribes_and_a_built_key_is_marked(
    tmp_path: Path,
) -> None:
    """A getSubscribedEvents() key written as a name meets a core constant through the table or is
    the event of that name; one written \\A\\B::NAME or A\\B::NAME through an imported first segment
    is the constant's event; each listener of a list of lists counts. A key held in a variable,
    built in a loop or by concatenation, and a body returning a helper's result are runtime
    registrations from getSubscribedEvents. Keys outside getSubscribedEvents give nothing."""
    _plant(tmp_path, KEY_LISTENERS)
    document, report = _map(tmp_path)
    get = "::getSubscribedEvents"
    assert _registrations(document) == {
        (
            "registers_listener_at_runtime",
            "HelperSubscriber" + get,
            "HelperSubscriber" + get + "|static::buildEvents()",
            None,
        ),
        (
            "registers_listener_at_runtime",
            "LoopSubscriber" + get,
            "LoopSubscriber" + get + "|'prefix.'.static::SUFFIX",
            None,
        ),
        (
            "registers_listener_at_runtime",
            "LoopSubscriber" + get,
            "LoopSubscriber" + get + "|$name",
            None,
        ),
        ("subscribed_by", "KernelEvents::REQUEST", "KeySubscriber::onNamedRequest", "8"),
        ("subscribed_by", "KernelEvents::RESPONSE", "KeySubscriber::onNamedFirst", "4"),
        ("subscribed_by", "KernelEvents::RESPONSE", "KeySubscriber::onNamedSecond", "0"),
        ("subscribed_by", "KernelEvents::TERMINATE", "KeySubscriber::onTerminateA", "0"),
        ("subscribed_by", "KernelEvents::TERMINATE", "KeySubscriber::onTerminateB", "-1"),
        ("subscribed_by", "KernelEvents::VIEW", "KeySubscriber::onQualifiedView", "0"),
        ("subscribed_by", "my_module.paid", "KeySubscriber::onNamedPaid", "0"),
        ("subscribed_by", "my_module.paid", "KeySubscriber::onQualifiedPaid", "3"),
        ("subscribed_by", "my_module.paid", "KeySubscriber::onRelativePaid", "0"),
        ("subscribed_by", "my_module.unknown", "KeySubscriber::onUnknownName", "0"),
    }
    runtime = {
        n["attributes"]["resolution"]
        for n in document["nodes"]
        if n["type"] == "drupal.runtime_subscription"
    }
    assert runtime == {"runtime"}
    assert report.skipped == ()


def test_a_subclass_inherits_its_bases_subscriptions_on_the_methods_its_line_declares(
    tmp_path: Path,
) -> None:
    """A subclass of a mapped subscriber inherits each key, on the method it or its nearest mapped
    ancestor declares, unless its own getSubscribedEvents() leaves out the parent's. A subclass of
    a core base gets that base's keys from the rutter's data, on its own override or the base's
    method, with the base's priority or its getPriority() literal; a route subscriber keeps
    alters_routes. A tagged subscriber of a base outside the map is marked; an untagged class with
    a listener's name gives nothing."""
    _plant(tmp_path, INHERITED_LISTENERS)
    document, report = _map(tmp_path)
    core = "Drupal\\Core\\"
    html = core + "EventSubscriber\\DefaultExceptionHtmlSubscriber::"
    assert _registrations(document) == {
        ("alters_routes", "MyRouteSubscriber", "MyRouteSubscriber", None),
        ("registers_listener_at_runtime", "ContribBased", "ContribBased", None),
        (
            "subscribed_by",
            core + "Config\\ConfigCollectionEvents::COLLECTION_INFO",
            "MyConfigOverride::addCollections",
            "0",
        ),
        (
            "subscribed_by",
            core + "Config\\ConfigEvents::DELETE",
            "MyConfigOverride::onConfigDelete",
            "20",
        ),
        (
            "subscribed_by",
            core + "Config\\ConfigEvents::RENAME",
            "MyConfigOverride::onConfigRename",
            "20",
        ),
        (
            "subscribed_by",
            core + "Config\\ConfigEvents::SAVE",
            "MyConfigOverride::onConfigSave",
            "20",
        ),
        (
            "subscribed_by",
            core + "Routing\\RoutingEvents::ALTER",
            core + "Routing\\RouteSubscriberBase::onAlterRoutes",
            "0",
        ),
        (
            "subscribed_by",
            core + "Routing\\RoutingEvents::ALTER",
            "OverrideRouteSubscriber::onAlterRoutes",
            "0",
        ),
        (
            "subscribed_by",
            core + "Routing\\RoutingEvents::STATIC",
            core + "Routing\\StaticRouteDiscoveryBase::onRouteBuild",
            "12",
        ),
        ("subscribed_by", "KernelEvents::EXCEPTION", html + "on401", "-128"),
        ("subscribed_by", "KernelEvents::EXCEPTION", html + "on404", "-128"),
        ("subscribed_by", "KernelEvents::EXCEPTION", html + "on4xx", "-128"),
        ("subscribed_by", "KernelEvents::EXCEPTION", "MyHtmlExceptions::on403", "-128"),
        ("subscribed_by", "KernelEvents::EXCEPTION", "MyHtmlExceptions::on410", "-128"),
        ("subscribed_by", "KernelEvents::REQUEST", "BaseSubscriber::onRequest", "0"),
        ("subscribed_by", "KernelEvents::REQUEST", "GrandchildSubscriber::onRequest", "0"),
        ("subscribed_by", "KernelEvents::RESPONSE", "BaseSubscriber::onResponse", "0"),
        ("subscribed_by", "my_module.extra", "MergingSubscriber::onExtra", "0"),
        ("subscribed_by", "my_module.local", "BaseSubscriber::onLocal", "2"),
        ("subscribed_by", "my_module.own", "BaseSubscriber::onOwn", "0"),
        ("subscribed_by", "my_module.own", "MergingSubscriber::onOwn", "0"),
        ("subscribed_by", "my_module.paid", "BaseSubscriber::onPaid", "5"),
        ("subscribed_by", "my_module.paid", "ChildSubscriber::onPaid", "5"),
        ("subscribed_by", "my_module.solo", "OverridingSubscriber::onSolo", "0"),
    }
    assert report.skipped == ()


def test_a_listener_added_in_php_subscribes_its_callable_or_is_marked(tmp_path: Path) -> None:
    """addListener with a constant, self:: or a name, and a callable [$this, 'm'], $this->m(...),
    [Foo::class, 'm'], 'Foo::m' or a function name; addTag('kernel.event_listener') on a registered
    class or a mapped service, with a derived method or a typed event when one is left out; and
    addSubscriber(new Foo()). A closure or a definition in a variable ends at a runtime listener;
    an unknown event or subscriber is a runtime registration. Another tag and another method
    name give nothing."""
    _plant(tmp_path, ADDED_LISTENERS)
    document, report = _map(tmp_path)
    provider = "MyModuleServiceProvider::register"
    assert _registrations(document) == {
        ("registers_listener_at_runtime", provider, provider + "|$this->name", None),
        (
            "registers_listener_at_runtime",
            "Wiring::wire",
            "Wiring::wire|$eventName~v:dispatcher",
            None,
        ),
        (
            "registers_listener_at_runtime",
            "Wiring::wire",
            "Wiring::wire|$this->subscriber~v:dispatcher",
            None,
        ),
        ("registers_subscriber", "Wiring::wire", "KeyedSubscriber", None),
        ("subscribed_by", "Event\\ViewEvent", "AddedListener::onTyped", "0"),
        (
            "subscribed_by",
            "KernelEvents::FINISH_REQUEST",
            "AddedListener::onKernelFinishRequest",
            "0",
        ),
        ("subscribed_by", "KernelEvents::REQUEST", "AddedListener::onAdded", "7"),
        ("subscribed_by", "KernelEvents::REQUEST", "Wiring::onA", "10"),
        ("subscribed_by", "KernelEvents::VIEW", provider + "|$definition", "0"),
        ("subscribed_by", "KernelEvents::VIEW", "Wiring::wire|function($event){$x=[1,2];}", "5"),
        ("subscribed_by", "my_module.keyed", "KeyedSubscriber::onKeyed", "0"),
        ("subscribed_by", "my_module.paid", "AddedListener::onAdded", "0"),
        ("subscribed_by", "my_module.paid", "AddedListener::onStatic", "-3"),
        ("subscribed_by", "my_module.paid", "DerivedListener::onMyModulePaid", "2"),
        ("subscribed_by", "my_module.paid", "FlowListener::onPaid", "0"),
        ("subscribed_by", "my_module.wired", "Wiring::onB", "0"),
        ("subscribed_by_function", "KernelEvents::REQUEST", "my_module_on_request", "0"),
        ("subscribed_by_function", "KernelEvents::TERMINATE", "my_module_terminate", "0"),
    }
    assert report.skipped == ()


EXPRESSION_LISTENERS = {
    str(MODULE / "src/Event/OrderEvents.php"): r"""<?php

namespace Drupal\my_module\Event;

final class OrderEvents {
  const PAID = 'my_module.paid';
  const PREFIX = 'my_module';
}
""",
    str(MODULE / "src/EventSubscriber/ExprAttributes.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\my_module\Event\OrderEvents;
use Symfony\Component\EventDispatcher\Attribute\AsEventListener;

#[AsEventListener(event: 'kernel.' . 'view', method: 'onClassConcat')]
#[AsEventListener('kernel.request', 'on' . 'Request')]
#[AsEventListener(event: 'kernel.finish_request', method: 'onFinish', priority: """
    r"""self::BASE + 1)]
class ExprAttributes {

  const PREFIX = 'my_module';
  const BASE = 5;

  #[AsEventListener(event: self::PREFIX . '.saved')]
  public function onOwn($e) {}

  #[AsEventListener('kernel.' . 'response')]
  public function onPositional($e) {}

  #[AsEventListener(event: OrderEvents::PAID . '.late', priority: 3)]
  public function onConstConcat($e) {}

  #[AsEventListener(event: TRUE ? 'kernel.view' : 'kernel.request')]
  public function onTernary($e) {}

  #[AsEventListener(event: 'kernel.terminate', priority: -10)]
  public function onLiteral($e) {}

  #[AsEventListener(event: OrderEvents::PAID)]
  public function onConstant($e) {}

  public function onClassConcat($e) {}
  public function onRequest($e) {}
  public function onFinish($e) {}

}
""",
    str(MODULE / "src/EventSubscriber/ExprCalls.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\my_module\Event\OrderEvents;
use Symfony\Component\DependencyInjection\ContainerBuilder;
use Symfony\Component\EventDispatcher\EventDispatcherInterface;

class ExprCalls {

  const PREFIX = 'my_module';

  public function wire(EventDispatcherInterface $dispatcher, ContainerBuilder $c"""
    r"""ontainer) {
    $dispatcher->addListener('kernel.' . 'request', [$this, 'onA']);
    $dispatcher->addListener(self::PREFIX . '.saved', [$this, 'onA']);
    $dispatcher->addListener(OrderEvents::PAID, [$this, 'on' . 'A']);
    $dispatcher->addListener('kernel.view', 'Drupal\my_module\EventSubscriber\Ex"""
    r"""prCalls::' . 'onA');
    $dispatcher->addListener(TRUE ? 'kernel.view' : 'kernel.request', [$this, 'onA']);
    $dispatcher->addListener('kernel.terminate', [$this, 'onA'], self::BASE + 1);
    $container->register('my_module.expr', ExprCalls::class)
      ->addTag('kernel.event_listener', ['event' => 'kernel.' . 'response', 'met"""
    r"""hod' => 'onA']);
    $container->register('my_module.expr2', ExprCalls::class)
      ->addTag('kernel.event_listener', ['event' => 'kernel.exception', 'method'"""
    r""" => 'on' . 'A']);
    $container->register('my_module.expr3', ExprCalls::class)
      ->addTag('kernel.event_listener', ['event' => self::PREFIX . '.x', 'method"""
    r"""' => 'onA']);
    $container->register('my_module.expr4', ExprCalls::class)
      ->addTag('kernel.event_listener', ['event' => strtolower('KERNEL.VIEW'), '"""
    r"""method' => 'onA', 'priority' => max(1, 2)]);
    $container->register('my_module.lit', ExprCalls::class)
      ->addTag('kernel.event_listener', ['event' => 'kernel.controller', 'method"""
    r"""' => 'onA', 'priority' => 4]);
  }

  public function onA($e) {}

}
""",
    str(MODULE / "src/EventSubscriber/ExprSubscriber.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\my_module\Event\OrderEvents;
use Symfony\Component\EventDispatcher\EventSubscriberInterface;

class ExprSubscriber implements EventSubscriberInterface {

  const PREFIX = 'my_module';

  public static function getSubscribedEvents() {
    return [
      'kernel.' . 'request' => 'onConcat',
      self::PREFIX . '.saved' => 'onOwnPrefix',
      'pre.' . OrderEvents::PAID => 'onPreConstant',
      OrderEvents::PREFIX . '.x' => ['onList', 5],
      TRUE ? 'kernel.view' : 'kernel.response' => 'onTernary',
      strtolower('KERNEL.TERMINATE') => 'onCall',
      // A literal key after a comment.
      'kernel.exception' => 'onLiteral',
      OrderEvents::PAID => 'onConstant',
      'a.' . 'b' => [['onFirst', 1], ['onSecond']],
    ];
  }

  public function onConcat($e) {}
  public function onOwnPrefix($e) {}
  public function onPreConstant($e) {}
  public function onList($e) {}
  public function onTernary($e) {}
  public function onCall($e) {}
  public function onLiteral($e) {}
  public function onConstant($e) {}
  public function onFirst($e) {}
  public function onSecond($e) {}

}
""",
}

UNION_LISTENERS = {
    str(MODULE / "my_module.services.yml"): r"""services:
  my_module.tagged_union:
    class: Drupal\my_module\EventSubscriber\TaggedUnion
    tags:
      - { name: kernel.event_listener }
""",
    str(MODULE / "src/Event/EventA.php"): r"""<?php

namespace Drupal\my_module\Event;

class EventA extends \Symfony\Contracts\EventDispatcher\Event {}
""",
    str(MODULE / "src/Event/EventB.php"): r"""<?php

namespace Drupal\my_module\Event;

class EventB extends \Symfony\Contracts\EventDispatcher\Event {}
""",
    str(MODULE / "src/Event/EventC.php"): r"""<?php

namespace Drupal\my_module\Event;

class EventC extends \Symfony\Contracts\EventDispatcher\Event {}
""",
    str(MODULE / "src/Event/EventD.php"): r"""<?php

namespace Drupal\my_module\Event;

class EventD extends \Symfony\Contracts\EventDispatcher\Event {}
""",
    str(MODULE / "src/Event/EventE.php"): r"""<?php

namespace Drupal\my_module\Event;

class EventE extends \Symfony\Contracts\EventDispatcher\Event {}
""",
    str(MODULE / "src/Event/EventF.php"): r"""<?php

namespace Drupal\my_module\Event;

class EventF extends \Symfony\Contracts\EventDispatcher\Event {}
""",
    str(MODULE / "src/EventSubscriber/TaggedUnion.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\my_module\Event\EventA;
use Drupal\my_module\Event\EventB;
use Drupal\my_module\Event\EventC;
use Drupal\my_module\Event\EventD;

class TaggedUnion {

  public function __invoke(EventA|EventB|EventC|EventD $event) {}

}
""",
    str(MODULE / "src/EventSubscriber/UnionListener.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\my_module\Event\EventA;
use Drupal\my_module\Event\EventB;
use Drupal\my_module\Event\EventC;
use Drupal\my_module\Event\EventD;
use Drupal\my_module\Event\EventE;
use Symfony\Component\EventDispatcher\Attribute\AsEventListener;

class UnionListener {

  #[AsEventListener]
  public function onFive(EventA|EventB|EventC|EventD|EventE $event, EventD $late"""
    r"""r): void {}

  #[AsEventListener(priority: 4)]
  public function onNullable(?EventA $event) {}

  #[AsEventListener]
  public function onWithNull(EventB | null | EventC $event) {}

  #[AsEventListener]
  public function onSecondOnly(string $name, EventE|EventD $event) {}

  #[AsEventListener]
  public function onScalarUnion(string|int $x) {}

  #[AsEventListener]
  public function onIntersection(EventA&EventB $x) {}

  #[AsEventListener]
  public function onFull(\Drupal\my_module\Event\EventF|EventA $event) {}

  public function notAListener(EventA|EventB|EventC|EventD $event) {}

}
""",
}

DISPATCHER_LISTENERS = {
    str(MODULE / "my_module.services.yml"): r"""services:
  my_module.flow:
    class: Drupal\my_module\EventSubscriber\TagListener
    tags:
      - { name: kernel.event_listener, event: kernel.request, method: onFlow, di"""
    r"""spatcher: my_module.dispatcher }
      - { name: kernel.event_listener, event: kernel.response, method: onMain }
      - { name: kernel.event_listener, event: kernel.view, method: onLookAlike, """
    r"""my_dispatcher: other }
  my_module.block:
    class: Drupal\my_module\EventSubscriber\TagListener
    tags:
      - name: kernel.event_listener
        event: kernel.terminate
        dispatcher: 'my_module.dispatcher'
        priority: 5
  my_module.inline:
    class: Drupal\my_module\EventSubscriber\TagListener
    tags: [{ name: kernel.event_listener, event: kernel.exception, method: onInl"""
    r"""ine, dispatcher: inline.dispatcher }]
  my_module.typed:
    class: Drupal\my_module\EventSubscriber\TagListener
    tags:
      - { name: kernel.event_listener, method: onTyped, dispatcher: typed.dispatcher }
  my_module.const:
    class: Drupal\my_module\EventSubscriber\TagListener
    tags:
      - { name: kernel.event_listener, event: !php/const Drupal\my_module\Event"""
    r"""\OrderEvents::PAID, method: onConst, dispatcher: const.dispatcher }
""",
    str(MODULE / "src/Event/EventA.php"): r"""<?php

namespace Drupal\my_module\Event;

class EventA extends \Symfony\Contracts\EventDispatcher\Event {}
""",
    str(MODULE / "src/Event/OrderEvents.php"): r"""<?php

namespace Drupal\my_module\Event;

final class OrderEvents {
  const PAID = 'my_module.paid';
  const PREFIX = 'my_module';
}
""",
    str(MODULE / "src/EventSubscriber/AttrListener.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Symfony\Component\EventDispatcher\Attribute\AsEventListener;

class AttrListener {

  #[AsEventListener(event: 'kernel.request', dispatcher: 'attr.dispatcher')]
  public function onNamed($e) {}

  #[AsEventListener('kernel.response', null, 3, 'positional.dispatcher')]
  public function onPositional($e) {}

  #[AsEventListener('kernel.view')]
  public function onMain($e) {}

}
""",
    str(MODULE / "src/EventSubscriber/TagListener.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\my_module\Event\EventA;

class TagListener {

  public function onFlow($e) {}
  public function onMain($e) {}
  public function onLookAlike($e) {}
  public function onKernelTerminate($e) {}
  public function onInline($e) {}
  public function onTyped(EventA $e) {}
  public function onConst($e) {}

}
""",
    str(MODULE / "src/MyModuleServiceProvider.php"): r"""<?php

namespace Drupal\my_module;

use Drupal\Core\DependencyInjection\ContainerBuilder;
use Drupal\Core\DependencyInjection\ServiceProviderBase;
use Drupal\my_module\EventSubscriber\TagListener;

class MyModuleServiceProvider extends ServiceProviderBase {

  public function register(ContainerBuilder $container) {
    $container->register('my_module.php_tag', TagListener::class)
      ->addTag('kernel.event_listener', ['event' => 'kernel.request', 'method' ="""
    r"""> 'onMain', 'dispatcher' => 'php.dispatcher']);
    $container->register('my_module.php_main', TagListener::class)
      ->addTag('kernel.event_listener', ['event' => 'kernel.controller', 'method"""
    r"""' => 'onMain']);
    $container->register('my_module.php_expr', TagListener::class)
      ->addTag('kernel.event_listener', ['event' => 'kernel.finish_request', 'me"""
    r"""thod' => 'onMain', 'dispatcher' => $this->dispatcherId]);
  }

}
""",
}

RECEIVER_LISTENERS = {
    str(MODULE / "my_module.module"): r"""<?php

use Drupal\my_module\Registry;
use Symfony\Component\EventDispatcher\EventDispatcherInterface;

function my_module_wire(EventDispatcherInterface $d, Registry $r, $other) {
  $d->addListener('kernel.request', 'my_module_on_typed');
  $r->addListener('kernel.request', 'my_module_on_registry');
  $other->addListener('kernel.request', 'my_module_on_untyped');
}

function my_module_on_typed($e) {}
function my_module_on_registry($e) {}
function my_module_on_untyped($e) {}
""",
    str(MODULE / "src/EventSubscriber/KeyedSubscriber.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Symfony\Component\EventDispatcher\EventSubscriberInterface;

class KeyedSubscriber implements EventSubscriberInterface {

  public static function getSubscribedEvents() {
    return ['kernel.request' => 'onRequest'];
  }

  public function onRequest($event) {}

}
""",
    str(MODULE / "src/EventSubscriber/More.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\my_module\MyDispatcher;
use Drupal\my_module\Registry;
use Symfony\Component\EventDispatcher\EventDispatcherInterface;

class More {

  /**
   * @var \Symfony\Component\EventDispatcher\EventDispatcherInterface
   */
  protected $docDispatcher;

  /**
   * @var \Drupal\my_module\Registry
   */
  protected $docRegistry;

  protected $assigned;

  protected $assignedRegistry;

  public function __construct(EventDispatcherInterface $event_dispatcher, Regist"""
    r"""ry $registry) {
    $this->assigned = $event_dispatcher;
    $this->assignedRegistry = $registry;
  }

  public function wire(?EventDispatcherInterface $nullable, MyDispatcher $mine) {
    $this->docDispatcher->addListener('kernel.request', [$this, 'onDoc']);
    $this->docRegistry->addListener('kernel.request', [$this, 'onDocRegistry']);
    $this->assigned->addListener('kernel.request', [$this, 'onAssigned']);
    $this->assignedRegistry->addListener('kernel.request', [$this, 'onAssignedRe"""
    r"""gistry']);
    $nullable->addListener('kernel.view', [$this, 'onNullable']);
    $mine->addListener('kernel.view', [$this, 'onMine']);
    $this->undeclared->addListener('kernel.view', [$this, 'onUndeclared']);
  }

  public function onDoc($e) {}
  public function onDocRegistry($e) {}
  public function onAssigned($e) {}
  public function onAssignedRegistry($e) {}
  public function onNullable($e) {}
  public function onMine($e) {}
  public function onUndeclared($e) {}

}
""",
    str(MODULE / "src/EventSubscriber/Shadowed.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\my_module\Registry;
use Symfony\Component\EventDispatcher\EventDispatcherInterface;

class Shadowed {

  public function closure(Registry $d) {
    $wire = function ($d) {
      $d->addListener('kernel.request', [$this, 'onClosure']);
    };
  }

  public function reassigned(EventDispatcherInterface $d) {
    $d = $this->other();
    $d->addListener('kernel.request', [$this, 'onReassigned']);
  }

  public function onClosure($e) {}
  public function onReassigned($e) {}

}
""",
    str(MODULE / "src/EventSubscriber/Wiring.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Symfony\Component\EventDispatcher\EventDispatcherInterface;
use Drupal\my_module\Registry;

class Wiring {

  protected EventDispatcherInterface $dispatcher;

  public function __construct(protected Registry $registry, EventDispatcherInter"""
    r"""face $events) {
    $this->dispatcher = $events;
  }

  public function wire(EventDispatcherInterface $dispatcher, Registry $reg, $untyped) {
    $this->dispatcher->addListener('kernel.request', [$this, 'onTypedProperty'], 10);
    $this->registry->addListener('kernel.request', [$this, 'onOtherProperty']);
    $dispatcher->addListener('kernel.view', [$this, 'onTypedParameter']);
    $reg->addListener('kernel.view', [$this, 'onOtherParameter']);
    $untyped->addListener('kernel.finish_request', [$this, 'onUntyped']);
    $this->getDispatcher()->addListener('kernel.terminate', [$this, 'onCallResult']);
    \Drupal::service('event_dispatcher')
      ->addListener('kernel.exception', [$this, 'onService']);
    $reg->addListener($this->name, [$this, 'onOtherParameter']);
    $untyped->addListener($this->name, [$this, 'onUntyped']);
    $dispatcher->addListener($this->name, [$this, 'onTypedParameter']);
    $reg->addSubscriber(new KeyedSubscriber());
    $dispatcher->addSubscriber(new KeyedSubscriber());
    $untyped->addSubscriber($this);
    $reg->addSubscriber($this->subscriber);
    $untyped->addSubscriber($this->subscriber);
  }

  public function onTypedProperty($event) {}
  public function onOtherProperty($event) {}
  public function onTypedParameter($event) {}
  public function onOtherParameter($event) {}
  public function onUntyped($event) {}
  public function onCallResult($event) {}
  public function onService($event) {}

  public static function getSubscribedEvents() {
    return [];
  }

}
""",
    str(MODULE / "src/MyDispatcher.php"): r"""<?php

namespace Drupal\my_module;

use Symfony\Component\EventDispatcher\EventDispatcherInterface;

class MyDispatcher implements EventDispatcherInterface {

  public function boot() {
    $this->addListener('kernel.request', [$this, 'onSelf']);
  }

  public function onSelf($e) {}

}
""",
    str(MODULE / "src/Registry.php"): r"""<?php

namespace Drupal\my_module;

class Registry {

  public function addListener($a, $b) {}

  public function boot() {
    $this->addListener('kernel.request', [$this, 'onSelf']);
  }

  public function onSelf($e) {}

}
""",
}

OVERRIDE_LISTENERS = {
    str(MODULE / "my_module.module"): r"""<?php

use Drupal\my_module\Event\OrderEvents;

function my_module_fire($dispatcher, $event) {
  $dispatcher->dispatch($event, OrderEvents::PAID);
  $dispatcher->addListener('kernel.request', 'my_module_listen');
}

class MyModuleHelper {

  public function fire($dispatcher, $event) {
    $dispatcher->dispatch($event, OrderEvents::PAID);
    $dispatcher->addListener('kernel.request', 'my_module_listen');
    $dispatcher->addSubscriber(new \Drupal\my_module\EventSubscriber\BaseSubscriber());
  }

}

function my_module_listen($e) {}
""",
    str(MODULE / "src/Event/OrderEvents.php"): r"""<?php

namespace Drupal\my_module\Event;

final class OrderEvents {
  const PAID = 'my_module.paid';
  const PREFIX = 'my_module';
}
""",
    str(MODULE / "src/EventSubscriber/BaseSubscriber.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\my_module\Event\OrderEvents;
use Symfony\Component\EventDispatcher\EventSubscriberInterface;

class BaseSubscriber implements EventSubscriberInterface {

  public static function getSubscribedEvents() {
    return [OrderEvents::PAID => 'onPaid'];
  }

  public function onPaid($event) {}

}
""",
    str(MODULE / "src/EventSubscriber/BraceInString.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

class BraceInString extends BaseSubscriber {

  public static function getSubscribedEvents() {
    $label = '}';
    return parent::getSubscribedEvents();
  }

  public function onPaid($event) {}

}
""",
    str(MODULE / "src/EventSubscriber/ChildOfMerging.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

class ChildOfMerging extends MergingMiddle {

  public function onPaid($event) {}

}
""",
    str(MODULE / "src/EventSubscriber/ChildOfMiddle.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

class ChildOfMiddle extends MiddleSubscriber {

  public function onPaid($event) {}

}
""",
    str(MODULE / "src/EventSubscriber/DeepOverride.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

class DeepOverride extends BaseSubscriber {

  public static function getSubscribedEvents() {
    $events = [];
    if (TRUE) {
      foreach ([1] as $a) {
        if ($a) {
          while (FALSE) {
            $events = [];
          }
        }
      }
    }
    return $events;
  }

  public function onPaid($event) {}

}
""",
    str(MODULE / "src/EventSubscriber/MergingMiddle.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

class MergingMiddle extends BaseSubscriber {

  public static function getSubscribedEvents() {
    $events = parent::getSubscribedEvents();
    foreach (static::NAMES as $name) {
      $events[$name][] = ['onAny'];
    }
    return $events;
  }

  public function onAny($event) {}

}
""",
    str(MODULE / "src/EventSubscriber/MiddleSubscriber.php"): r"""<?php

namespace Drupal\my_module\EventSubscriber;

class MiddleSubscriber extends BaseSubscriber {

  public static function getSubscribedEvents() {
    $events = [];
    foreach (static::NAMES as $name) {
      $events[$name][] = ['onAny'];
    }
    return $events;
  }

  public function onAny($event) {}

}
""",
}


def _marked(document: dict[str, Any]) -> set[tuple[str, str, str, Any, Any, Any]]:
    """Each listener edge as _registrations gives it, with its dispatcher and receiver."""
    return {
        (*row, attributes.get("dispatcher"), attributes.get("receiver"))
        for row, attributes in (
            (
                (e["kind"], _short(e["from"]), _short(e["to"]), _priority(e)),
                e.get("attributes", {}),
            )
            for e in document["edges"]
            if e["kind"] in _LISTENER_KINDS
        )
    }


def test_an_argument_written_as_an_expression_is_a_runtime_registration_never_a_cut_name(
    tmp_path: Path,
) -> None:
    """A key, a listener value, an addListener event or callable, an addTag value and an
    AsEventListener argument written as an expression are runtime registrations with the
    expression in the id, never the name before the expression's first space; literals,
    constants and constant priorities keep their edges."""
    _plant(tmp_path, EXPRESSION_LISTENERS)
    document, report = _map(tmp_path)
    assert _registrations(document) == {
        (
            "registers_listener_at_runtime",
            "ExprAttributes",
            "ExprAttributes|'kernel.'.'view'",
            None,
        ),
        ("registers_listener_at_runtime", "ExprAttributes", "ExprAttributes|'on'.'Request'", None),
        (
            "registers_listener_at_runtime",
            "ExprAttributes::onConstConcat",
            "ExprAttributes::onConstConcat|OrderEvents::PAID.'.late'",
            None,
        ),
        (
            "registers_listener_at_runtime",
            "ExprAttributes::onOwn",
            "ExprAttributes::onOwn|self::PREFIX.'.saved'",
            None,
        ),
        (
            "registers_listener_at_runtime",
            "ExprAttributes::onPositional",
            "ExprAttributes::onPositional|'kernel.'.'response'",
            None,
        ),
        (
            "registers_listener_at_runtime",
            "ExprAttributes::onTernary",
            "ExprAttributes::onTernary|TRUE?'kernel.view':'kernel.request'",
            None,
        ),
        (
            "registers_listener_at_runtime",
            "ExprCalls::wire",
            "ExprCalls::wire|'kernel.'.'request'~v:dispatcher",
            None,
        ),
        (
            "registers_listener_at_runtime",
            "ExprCalls::wire",
            "ExprCalls::wire|'kernel.'.'response'",
            None,
        ),
        (
            "registers_listener_at_runtime",
            "ExprCalls::wire",
            "ExprCalls::wire|TRUE?'kernel.view':'kernel.request'~v:dispatcher",
            None,
        ),
        (
            "registers_listener_at_runtime",
            "ExprCalls::wire",
            "ExprCalls::wire|self::PREFIX.'.saved'~v:dispatcher",
            None,
        ),
        (
            "registers_listener_at_runtime",
            "ExprCalls::wire",
            "ExprCalls::wire|self::PREFIX.'.x'",
            None,
        ),
        (
            "registers_listener_at_runtime",
            "ExprCalls::wire",
            "ExprCalls::wire|strtolower('KERNEL.VIEW')",
            None,
        ),
        (
            "registers_listener_at_runtime",
            "ExprSubscriber::getSubscribedEvents",
            "ExprSubscriber::getSubscribedEvents|'a.'.'b'",
            None,
        ),
        (
            "registers_listener_at_runtime",
            "ExprSubscriber::getSubscribedEvents",
            "ExprSubscriber::getSubscribedEvents|'kernel.'.'request'",
            None,
        ),
        (
            "registers_listener_at_runtime",
            "ExprSubscriber::getSubscribedEvents",
            "ExprSubscriber::getSubscribedEvents|'pre.'.OrderEvents::PAID",
            None,
        ),
        (
            "registers_listener_at_runtime",
            "ExprSubscriber::getSubscribedEvents",
            "ExprSubscriber::getSubscribedEvents|OrderEvents::PREFIX.'.x'",
            None,
        ),
        (
            "registers_listener_at_runtime",
            "ExprSubscriber::getSubscribedEvents",
            "ExprSubscriber::getSubscribedEvents|TRUE?'kernel.view':'kernel.response'",
            None,
        ),
        (
            "registers_listener_at_runtime",
            "ExprSubscriber::getSubscribedEvents",
            "ExprSubscriber::getSubscribedEvents|self::PREFIX.'.saved'",
            None,
        ),
        (
            "registers_listener_at_runtime",
            "ExprSubscriber::getSubscribedEvents",
            "ExprSubscriber::getSubscribedEvents|strtolower('KERNEL.TERMINATE')",
            None,
        ),
        ("subscribed_by", "KernelEvents::CONTROLLER", "ExprCalls::onA", "4"),
        ("subscribed_by", "KernelEvents::EXCEPTION", "ExprCalls::wire|'on'.'A'", "0"),
        ("subscribed_by", "KernelEvents::EXCEPTION", "ExprSubscriber::onLiteral", "0"),
        (
            "subscribed_by",
            "KernelEvents::FINISH_REQUEST",
            "ExprAttributes::onFinish",
            "self::BASE + 1",
        ),
        ("subscribed_by", "KernelEvents::TERMINATE", "ExprAttributes::onLiteral", "-10"),
        ("subscribed_by", "KernelEvents::TERMINATE", "ExprCalls::onA", "self::BASE + 1"),
        ("subscribed_by", "KernelEvents::VIEW", "ExprCalls::wire|'ExprCalls::'.'onA'", "0"),
        ("subscribed_by", "my_module.paid", "ExprAttributes::onConstant", "0"),
        ("subscribed_by", "my_module.paid", "ExprCalls::wire|[$this,'on'.'A']", "0"),
        ("subscribed_by", "my_module.paid", "ExprSubscriber::onConstant", "0"),
    }
    assert report.skipped == ()


def test_a_union_of_any_length_gives_each_class_as_the_event(tmp_path: Path) -> None:
    """With no event, each class of the first parameter's union is an event, five as one; a
    nullable class is one, an intersection, a scalar union and a later parameter give none."""
    _plant(tmp_path, UNION_LISTENERS)
    document, report = _map(tmp_path)
    assert _registrations(document) == {
        ("subscribed_by", "Event\\EventA", "TaggedUnion::__invoke", "0"),
        ("subscribed_by", "Event\\EventA", "UnionListener::onFive", "0"),
        ("subscribed_by", "Event\\EventA", "UnionListener::onFull", "0"),
        ("subscribed_by", "Event\\EventA", "UnionListener::onNullable", "4"),
        ("subscribed_by", "Event\\EventB", "TaggedUnion::__invoke", "0"),
        ("subscribed_by", "Event\\EventB", "UnionListener::onFive", "0"),
        ("subscribed_by", "Event\\EventB", "UnionListener::onWithNull", "0"),
        ("subscribed_by", "Event\\EventC", "TaggedUnion::__invoke", "0"),
        ("subscribed_by", "Event\\EventC", "UnionListener::onFive", "0"),
        ("subscribed_by", "Event\\EventC", "UnionListener::onWithNull", "0"),
        ("subscribed_by", "Event\\EventD", "TaggedUnion::__invoke", "0"),
        ("subscribed_by", "Event\\EventD", "UnionListener::onFive", "0"),
        ("subscribed_by", "Event\\EventE", "UnionListener::onFive", "0"),
        ("subscribed_by", "Event\\EventF", "UnionListener::onFull", "0"),
    }
    assert report.skipped == ()


def test_a_dispatcher_a_listener_tag_or_attribute_names_is_on_its_edge(tmp_path: Path) -> None:
    """A dispatcher key of a tag in each services form and in PHP, and an attribute's named or
    fourth argument, is the edge attribute dispatcher; a tag or attribute without one, and a
    key named like it, write none."""
    _plant(tmp_path, DISPATCHER_LISTENERS)
    document, report = _map(tmp_path)
    assert _marked(document) == {
        ("subscribed_by", "Event\\EventA", "TagListener::onTyped", "0", "typed.dispatcher", None),
        ("subscribed_by", "KernelEvents::CONTROLLER", "TagListener::onMain", "0", None, None),
        (
            "subscribed_by",
            "KernelEvents::EXCEPTION",
            "TagListener::onInline",
            "0",
            "inline.dispatcher",
            None,
        ),
        (
            "subscribed_by",
            "KernelEvents::FINISH_REQUEST",
            "TagListener::onMain",
            "0",
            "$this->dispatcherId",
            None,
        ),
        (
            "subscribed_by",
            "KernelEvents::REQUEST",
            "AttrListener::onNamed",
            "0",
            "attr.dispatcher",
            None,
        ),
        (
            "subscribed_by",
            "KernelEvents::REQUEST",
            "TagListener::onFlow",
            "0",
            "my_module.dispatcher",
            None,
        ),
        (
            "subscribed_by",
            "KernelEvents::REQUEST",
            "TagListener::onMain",
            "0",
            "php.dispatcher",
            None,
        ),
        (
            "subscribed_by",
            "KernelEvents::RESPONSE",
            "AttrListener::onPositional",
            "3",
            "positional.dispatcher",
            None,
        ),
        ("subscribed_by", "KernelEvents::RESPONSE", "TagListener::onMain", "0", None, None),
        (
            "subscribed_by",
            "KernelEvents::TERMINATE",
            "TagListener::onKernelTerminate",
            "5",
            "my_module.dispatcher",
            None,
        ),
        ("subscribed_by", "KernelEvents::VIEW", "AttrListener::onMain", "0", None, None),
        ("subscribed_by", "KernelEvents::VIEW", "TagListener::onLookAlike", "0", None, None),
        ("subscribed_by", "my_module.paid", "TagListener::onConst", "0", "const.dispatcher", None),
    }
    assert report.skipped == ()


def test_a_registration_call_reads_the_type_of_the_object_it_runs_on(tmp_path: Path) -> None:
    """addListener and addSubscriber on a parameter, a property or $this typed as an event
    dispatcher, or a mapped class that implements one, register plainly; on a known type that
    is not a dispatcher they give nothing, runtime registrations included; on an object of no
    known type, a call's result or a shadowed parameter they hold the receiver mark."""
    _plant(tmp_path, RECEIVER_LISTENERS)
    document, report = _map(tmp_path)
    assert _marked(document) == {
        (
            "registers_listener_at_runtime",
            "Wiring::wire",
            "Wiring::wire|$this->name~v:dispatcher",
            None,
            None,
            None,
        ),
        (
            "registers_listener_at_runtime",
            "Wiring::wire",
            "Wiring::wire|$this->name~v:untyped",
            None,
            None,
            "not known to be an event dispatcher",
        ),
        (
            "registers_listener_at_runtime",
            "Wiring::wire",
            "Wiring::wire|$this->subscriber~v:untyped",
            None,
            None,
            "not known to be an event dispatcher",
        ),
        (
            "registers_subscriber",
            "Wiring::wire",
            "KeyedSubscriber",
            None,
            None,
            "an event dispatcher",
        ),
        (
            "registers_subscriber",
            "Wiring::wire",
            "Wiring",
            None,
            None,
            "not known to be an event dispatcher",
        ),
        (
            "subscribed_by",
            "KernelEvents::EXCEPTION",
            "Wiring::onService",
            "0",
            None,
            "not known to be an event dispatcher",
        ),
        (
            "subscribed_by",
            "KernelEvents::FINISH_REQUEST",
            "Wiring::onUntyped",
            "0",
            None,
            "not known to be an event dispatcher",
        ),
        ("subscribed_by", "KernelEvents::REQUEST", "KeyedSubscriber::onRequest", "0", None, None),
        (
            "subscribed_by",
            "KernelEvents::REQUEST",
            "More::onAssigned",
            "0",
            None,
            "an event dispatcher",
        ),
        ("subscribed_by", "KernelEvents::REQUEST", "More::onDoc", "0", None, "an event dispatcher"),
        (
            "subscribed_by",
            "KernelEvents::REQUEST",
            "MyDispatcher::onSelf",
            "0",
            None,
            "an event dispatcher",
        ),
        (
            "subscribed_by",
            "KernelEvents::REQUEST",
            "Shadowed::onClosure",
            "0",
            None,
            "not known to be an event dispatcher",
        ),
        (
            "subscribed_by",
            "KernelEvents::REQUEST",
            "Shadowed::onReassigned",
            "0",
            None,
            "not known to be an event dispatcher",
        ),
        (
            "subscribed_by",
            "KernelEvents::REQUEST",
            "Wiring::onTypedProperty",
            "10",
            None,
            "an event dispatcher",
        ),
        (
            "subscribed_by",
            "KernelEvents::TERMINATE",
            "Wiring::onCallResult",
            "0",
            None,
            "not known to be an event dispatcher",
        ),
        ("subscribed_by", "KernelEvents::VIEW", "More::onMine", "0", None, "an event dispatcher"),
        (
            "subscribed_by",
            "KernelEvents::VIEW",
            "More::onNullable",
            "0",
            None,
            "an event dispatcher",
        ),
        (
            "subscribed_by",
            "KernelEvents::VIEW",
            "More::onUndeclared",
            "0",
            None,
            "not known to be an event dispatcher",
        ),
        (
            "subscribed_by",
            "KernelEvents::VIEW",
            "Wiring::onTypedParameter",
            "0",
            None,
            "an event dispatcher",
        ),
        (
            "subscribed_by_function",
            "KernelEvents::REQUEST",
            "my_module_on_typed",
            "0",
            None,
            "an event dispatcher",
        ),
        (
            "subscribed_by_function",
            "KernelEvents::REQUEST",
            "my_module_on_untyped",
            "0",
            None,
            "not known to be an event dispatcher",
        ),
    }
    assert report.skipped == ()


def test_a_class_between_that_overrides_stops_inheritance_and_a_module_class_is_no_function(
    tmp_path: Path,
) -> None:
    """A subclass inherits no key past a class between that overrides getSubscribedEvents()
    without the parent's, however deep its braces; a parent:: call after a brace in a string
    still inherits. A dispatch or registration in a method of a class in a module file gives
    nothing."""
    _plant(tmp_path, OVERRIDE_LISTENERS)
    document, report = _map(tmp_path)
    assert _registrations(document) == {
        (
            "registers_listener_at_runtime",
            "MergingMiddle::getSubscribedEvents",
            "MergingMiddle::getSubscribedEvents|$name",
            None,
        ),
        (
            "registers_listener_at_runtime",
            "MiddleSubscriber::getSubscribedEvents",
            "MiddleSubscriber::getSubscribedEvents|$name",
            None,
        ),
        ("subscribed_by", "my_module.paid", "BaseSubscriber::onPaid", "0"),
        ("subscribed_by", "my_module.paid", "BraceInString::onPaid", "0"),
        ("subscribed_by", "my_module.paid", "ChildOfMerging::onPaid", "0"),
        ("subscribed_by_function", "KernelEvents::REQUEST", "my_module_listen", "0"),
    }
    dispatched = {
        (e["from"], e["to"]) for e in document["edges"] if e["kind"] == "dispatched_by_function"
    }
    assert dispatched == {("drupal.event::my_module.paid", "php.function::my_module_fire")}
    assert report.skipped == ()


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
        # Each filter and function belongs to the module of the class that provides it.
        ("twig_filter_in_module", "twig.filter::long", "drupal.module::my_module", "inferred"),
        ("twig_filter_in_module", "twig.filter::money", "drupal.module::my_module", "inferred"),
        ("twig_filter_in_module", "twig.filter::short", "drupal.module::my_module", "inferred"),
        (
            "twig_function_in_module",
            "twig.function::cart_count",
            "drupal.module::my_module",
            "inferred",
        ),
        (
            "twig_function_in_module",
            "twig.function::cart_total",
            "drupal.module::my_module",
            "inferred",
        ),
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


def test_code_and_templates_that_name_a_field_access_its_storage_its_shared_name_or_a_mark(
    tmp_path: Path,
) -> None:
    """get, set and hasField in a method or a function give accesses_field to the one storage of
    that name, and accesses_shared_field_name to the shared name when storages on two entity types
    hold it, inferred, at the method's line. node.field_y and content.field_y in a node template
    reach the node storage, at the read's line. A field_ name with no storage ends at an
    unresolved field.storage.<name>, or field.storage.<entity type>.<name> when the read names its
    entity type; any other unmapped name, a variable and a name in plain text give nothing."""
    _plant(tmp_path, FIELD_FILES)
    document, report = _map(tmp_path)
    assert report.skipped == (), report.skipped
    paint = "php.method::Drupal\\my_module\\Painter::paint"
    presave = "php.function::my_module_node_presave"
    template = "drupal.template::node--article--full"
    storage = "drupal.config::field.storage."
    found = {
        (e["kind"], e["from"], e["to"], e["locations"][0]["line"], p["rule"])
        for e in document["edges"]
        if e["kind"] in ("accesses_field", "accesses_shared_field_name")
        for p in e["provenance"]
    }
    shared = ("accesses_shared_field_name", "drupal.shared_field_name::field_color")
    assert found == {
        ("accesses_field", paint, storage + "field_size", 9, "code_accesses_field_mark"),
        ("accesses_field", paint, storage + "field_gone", 9, "code_accesses_field_mark"),
        (
            "accesses_field",
            paint,
            storage + "field_gone",
            9,
            "code_accesses_field_by_class_constant_mark",
        ),
        ("accesses_field", paint, storage + "node.body", 9, "code_accesses_field"),
        (shared[0], paint, shared[1], 9, "code_accesses_shared_field_name"),
        (shared[0], presave, shared[1], 3, "code_accesses_shared_field_name"),
        (
            "accesses_field",
            template,
            storage + "node.field_color",
            1,
            "template_accesses_entity_field",
        ),
        (
            "accesses_field",
            template,
            storage + "node.field_width",
            1,
            "template_accesses_entity_field",
        ),
    }
    marks = sorted((n["id"], n["type"]) for n in document["nodes"] if n["state"] == "unresolved")
    assert marks == [
        (storage + "field_gone", "drupal.field_storage"),
        (storage + "field_size", "drupal.field_storage"),
        (storage + "node.field_width", "drupal.field_storage"),
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
        # A theme template named <core hook>--<anything> suggests the core hook, as a node.
        ("suggests_theme_hook", "block--my-cart-block", "drupal.theme_hook::block", "inferred"),
        ("suggests_theme_hook", "block--my-theme-branding", "drupal.theme_hook::block", "inferred"),
        ("suggests_theme_hook", "block--system", "drupal.theme_hook::block", "inferred"),
        (
            "suggests_theme_hook",
            "block--system-menu-block--main",
            "drupal.theme_hook::block",
            "inferred",
        ),
        (
            "suggests_theme_hook",
            "block--views-block--recent-list",
            "drupal.theme_hook::block",
            "inferred",
        ),
        ("suggests_theme_hook", "field--entity-reference", "drupal.theme_hook::field", "inferred"),
        ("suggests_theme_hook", "field--field-color", "drupal.theme_hook::field", "inferred"),
        ("suggests_theme_hook", "field--node--article", "drupal.theme_hook::field", "inferred"),
        (
            "suggests_theme_hook",
            "field--node--field-color--article",
            "drupal.theme_hook::field",
            "inferred",
        ),
        (
            "suggests_theme_hook",
            "field--taxonomy-term--field-tags",
            "drupal.theme_hook::field",
            "inferred",
        ),
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
    # php_basic's variable_calls rules give each $account call its own unmarked site besides.
    marked = {
        n["id"] for n in document["nodes"] if n.get("attributes", {}).get("resolution") == "runtime"
    }
    runtime = {
        (e["from"], e["to"], e["locations"][0]["line"])
        for e in document["edges"]
        if e["kind"] == "has_call_site" and e["to"] in marked
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
    found = {(e["from"], e["to"]) for e in document["edges"] if e["kind"] == "accesses_field"}
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
        ("accesses_field", run, storage + "node.field_size", 7, "code_accesses_field", "inferred"),
        (
            "accesses_field",
            run,
            storage + "field_gone",
            7,
            "code_accesses_field_by_class_constant_mark",
            "inferred",
        ),
    }


# --- event rules: parameters, classes, inherited and contrib constants, derived methods ---

PARAMETER_EVENTS = {
    "web/modules/custom/my_module/my_module.info.yml": r"""name: My module
type: module
core_version_requirement: ^11
""",
    "web/modules/custom/my_module/my_module.services.yml": r"""parameters:
  my_module.paid_event: my_module.paid
  my_module.shipped_event: 'my_module.shipped'
  my_module.request_event: "kernel.request"
  my_module.twice: my_module.first
  my_module.list: [a, b]
  my_module.nested: '%other.param%'
services:
  my_module.param_listener:
    class: Drupal\my_module\EventSubscriber\ParamListener
    tags:
      - { name: kernel.event_listener, event: '%my_module.paid_event%', method: onPaid,"""
    r""" priority: 4 }
      - { name: kernel.event_listener, event: '%my_module.shipped_event%' }
      - { name: kernel.event_listener, event: "%my_module.request_event%" }
      - { name: kernel.event_listener, event: '%my_module.unknown%', method: onAnything }
      - { name: kernel.event_listener, event: '%my_module.twice%', method: onAnything }
      - { name: kernel.event_listener, event: '%my_module.list%', method: onAnything }
      - { name: kernel.event_listener, event: '%my_module.nested%', method: onAnything }
      - { name: kernel.event_listener, event: '%my_module.unknown%' }
  my_module.no_class:
    tags:
      - { name: kernel.event_listener, event: '%my_module.paid_event%', method: onPaid }
  my_module.not_param:
    class: Drupal\my_module\EventSubscriber\ParamListener
    arguments: ['%my_module.paid_event%']
    tags:
      - { name: kernel.event_listener, event: my_module.paid, method: onPaid }
""",
    "web/modules/custom/my_module/src/EventSubscriber/ParamListener.php": r"""<?php

namespace Drupal\my_module\EventSubscriber;

class ParamListener {

  public function onPaid() {}

  public function onMyModuleShipped() {}

  public function onKernelRequest() {}

  public function onAnything() {}

}
""",
    "web/modules/custom/other/other.info.yml": r"""name: Other
type: module
core_version_requirement: ^11
""",
    "web/modules/custom/other/other.services.yml": r"""parameters:
  my_module.twice: other.second
services:
  other.thing:
    class: Drupal\other\Thing
""",
}


def test_a_tag_event_written_as_a_parameter_is_its_mapped_value_else_a_runtime_mark(
    tmp_path: Path,
) -> None:
    """A tag's event written '%name%' is the value one mapped parameters block gives it, read as the
    tag's quoted event is, its method derived when none is written; a parameter no file gives a
    literal value, two files give different values, or whose value names another parameter is a
    runtime registration from the service. An argument naming a parameter gives nothing."""
    _plant(tmp_path, PARAMETER_EVENTS)
    document, report = _map(tmp_path)
    assert _registrations(document) == {
        (
            "registers_listener_at_runtime",
            "my_module.param_listener",
            "my_module.param_listener|%my_module.list%",
            None,
        ),
        (
            "registers_listener_at_runtime",
            "my_module.param_listener",
            "my_module.param_listener|%my_module.nested%",
            None,
        ),
        (
            "registers_listener_at_runtime",
            "my_module.param_listener",
            "my_module.param_listener|%my_module.twice%",
            None,
        ),
        (
            "registers_listener_at_runtime",
            "my_module.param_listener",
            "my_module.param_listener|%my_module.unknown%",
            None,
        ),
        ("subscribed_by", "KernelEvents::REQUEST", "ParamListener::onKernelRequest", "0"),
        ("subscribed_by", "my_module.paid", "ParamListener::onPaid", ("0", "4")),
        ("subscribed_by", "my_module.paid", "my_module.no_class::onPaid", "0"),
        ("subscribed_by", "my_module.shipped", "ParamListener::onMyModuleShipped", "0"),
    }
    runtime = {
        n["id"]: n.get("attributes", {}).get("resolution")
        for n in document["nodes"]
        if n["type"] == "drupal.runtime_subscription"
    }
    assert runtime == {
        f"drupal.runtime_subscription::my_module.param_listener|%my_module.{name}%": "runtime"
        for name in ("list", "nested", "twice", "unknown")
    }
    assert report.skipped == ()


CLASS_EVENTS = {
    "web/modules/custom/my_module/my_module.info.yml": r"""name: My module
type: module
core_version_requirement: ^11
""",
    "web/modules/custom/my_module/my_module.services.yml": r"""services:
  my_module.class_string:
    class: Drupal\my_module\EventSubscriber\AttributeListener
    tags:
      - { name: kernel.event_listener, event: Drupal\my_module\Event\PaidEvent, method: typed }
      - { name: kernel.event_listener, event: 'Drupal\my_module\Event\PaidEvent' }
""",
    "web/modules/custom/my_module/src/Event/PaidEvent.php": r"""<?php

namespace Drupal\my_module\Event;

use Symfony\Contracts\EventDispatcher\Event;

class PaidEvent extends Event {
}
""",
    "web/modules/custom/my_module/src/EventSubscriber/AttributeListener.php": r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\my_module\Event\PaidEvent;
use Symfony\Component\EventDispatcher\Attribute\AsEventListener;
use Symfony\Component\HttpKernel\Event\RequestEvent;

#[AsEventListener(event: PaidEvent::class)]
#[AsEventListener(RequestEvent::class)]
#[AsEventListener(event: \Drupal\other\Event\GoneEvent::class)]
class AttributeListener {

  public function onDrupalMyModuleEventPaidEvent() {}

  #[AsEventListener(event: PaidEvent::class, priority: 3)]
  public function typed(PaidEvent $event) {}

}
""",
    "web/modules/custom/my_module/src/EventSubscriber/ClassSubscriber.php": r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\my_module\Event\PaidEvent;
use Drupal\other\Event\ShippedEvent as Shipped;
use Symfony\Component\EventDispatcher\EventSubscriberInterface;
use Symfony\Component\HttpKernel\Event\RequestEvent;

class ClassSubscriber implements EventSubscriberInterface {

  public static function getSubscribedEvents() {
    $events[PaidEvent::class] = ['onPaid', 20];
    $events[Shipped::class][] = ['onShipped'];
    $events[LocalEvent::class] = 'onLocal';
    return $events + [
      \Drupal\other\Event\FullEvent::class => 'onFull',
      self::class => 'onSelf',
      RequestEvent::class => [['onRequestFirst', 5], ['onRequestSecond']],
    ];
  }

  public function onPaid(PaidEvent $event) {}
  public function onShipped() {}
  public function onLocal() {}
  public function onFull() {}
  public function onSelf() {}
  public function onRequestFirst() {}
  public function onRequestSecond() {}

  public function register($dispatcher) {
    $dispatcher->addListener(PaidEvent::class, [$this, 'onPaid']);
    $other = [PaidEvent::class => 'notASubscription'];
    $this->map = [PaidEvent::class, 'onPaid'];
  }

}
""",
    "web/modules/custom/my_module/src/EventSubscriber/InvokeListener.php": r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\my_module\Event\PaidEvent;
use Symfony\Component\EventDispatcher\Attribute\AsEventListener;

#[AsEventListener(PaidEvent::class)]
class InvokeListener {

  public function __invoke(PaidEvent $event) {}

}
""",
    "web/modules/custom/my_module/src/MyModuleServiceProvider.php": r"""<?php

namespace Drupal\my_module;

use Drupal\Core\DependencyInjection\ContainerBuilder;
use Drupal\Core\DependencyInjection\ServiceProviderBase;
use Drupal\my_module\Event\PaidEvent;
use Drupal\my_module\EventSubscriber\AttributeListener;

class MyModuleServiceProvider extends ServiceProviderBase {

  public function alter(ContainerBuilder $container) {
    $container->register('my_module.class_tag',"""
    r""" AttributeListener::class)->addTag('kernel.event_listener', ['event' =>"""
    r""" PaidEvent::class, 'method' => 'typed']);
    $container->register('my_module.class_tag_derived',"""
    r""" AttributeListener::class)->addTag('kernel.event_listener', ['event' => PaidEvent::class]);
    $container->register('my_module.parent',"""
    r""" AttributeListener::class)->addTag('kernel.event_listener', ['event' => parent::class,"""
    r""" 'method' => 'typed']);
  }

}
""",
}


def test_an_event_written_as_a_class_is_the_event_of_its_full_name(tmp_path: Path) -> None:
    """X::class names the event of the class's full name, through a use statement, an alias, the
    namespace or self, in a key, a list of lists, $events[X::class], an attribute, addListener and
    addTag, the node a typed listener reaches; with no method, on<Event> derived from the full
    name, then __invoke, then the unresolved derived name. A tag's class name is that event too.
    parent::class is a runtime registration; X::class as a plain array value gives nothing."""
    _plant(tmp_path, CLASS_EVENTS)
    document, report = _map(tmp_path)
    assert _registrations(document) == {
        (
            "registers_listener_at_runtime",
            "MyModuleServiceProvider::alter",
            "MyModuleServiceProvider::alter|parent::class",
            None,
        ),
        ("subscribed_by", "ClassSubscriber", "ClassSubscriber::onSelf", "0"),
        ("subscribed_by", "Drupal\\other\\Event\\FullEvent", "ClassSubscriber::onFull", "0"),
        (
            "subscribed_by",
            "Drupal\\other\\Event\\GoneEvent",
            "AttributeListener::onDrupalOtherEventGoneEvent",
            "0",
        ),
        ("subscribed_by", "Drupal\\other\\Event\\ShippedEvent", "ClassSubscriber::onShipped", "0"),
        (
            "subscribed_by",
            "Event\\PaidEvent",
            "AttributeListener::onDrupalMyModuleEventPaidEvent",
            "0",
        ),
        ("subscribed_by", "Event\\PaidEvent", "AttributeListener::typed", ("0", "0", "3")),
        ("subscribed_by", "Event\\PaidEvent", "ClassSubscriber::onPaid", ("0", "20")),
        ("subscribed_by", "Event\\PaidEvent", "InvokeListener::__invoke", "0"),
        (
            "subscribed_by",
            "Event\\RequestEvent",
            "AttributeListener::onSymfonyComponentHttpKernelEventRequestEvent",
            "0",
        ),
        ("subscribed_by", "Event\\RequestEvent", "ClassSubscriber::onRequestFirst", "5"),
        ("subscribed_by", "Event\\RequestEvent", "ClassSubscriber::onRequestSecond", "0"),
        ("subscribed_by", "LocalEvent", "ClassSubscriber::onLocal", "0"),
    }


DASH_ALONE_TAGS = {
    "web/modules/custom/my_module/my_module.info.yml": r"""name: My module
type: module
core_version_requirement: ^11
""",
    "web/modules/custom/my_module/my_module.services.yml": r"""services:
  my_module.dash_alone:
    class: Drupal\my_module\EventSubscriber\TagListener
    tags:
      -
        name: kernel.event_listener
        event: kernel.request
        method: onRequest
        priority: 7
      -
        event: my_module.paid
        name: kernel.event_listener
        method: onPaid
      -
        name: kernel.event_listener
        event: kernel.response
  my_module.dash_alone_other:
    class: Drupal\my_module\EventSubscriber\TagListener
    tags:
      -
        name: event_subscriber
      -
        name: kernel.event_listener_x
        event: kernel.terminate
        method: onTerminate
""",
    "web/modules/custom/my_module/src/EventSubscriber/TagListener.php": r"""<?php

namespace Drupal\my_module\EventSubscriber;

class TagListener {

  public function onRequest() {}
  public function onPaid() {}
  public function onKernelResponse() {}
  public function onTerminate() {}

}
""",
}


def test_a_tag_item_whose_dash_stands_alone_on_its_line_is_read(tmp_path: Path) -> None:
    """A tag item whose dash stands alone on its line, its keys on the lines below, is read as any
    block item; another tag name gives nothing."""
    _plant(tmp_path, DASH_ALONE_TAGS)
    document, report = _map(tmp_path)
    assert _registrations(document) == {
        ("subscribed_by", "KernelEvents::REQUEST", "TagListener::onRequest", "7"),
        ("subscribed_by", "KernelEvents::RESPONSE", "TagListener::onKernelResponse", "0"),
        ("subscribed_by", "my_module.paid", "TagListener::onPaid", "0"),
    }
    assert report.skipped == ()


SHARED_REGISTRATIONS = {
    "web/modules/custom/my_module/my_module.info.yml": r"""name: My module
type: module
core_version_requirement: ^11
""",
    "web/modules/custom/my_module/src/EventSubscriber/Registrar.php": r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Psr\Log\LoggerInterface;
use Symfony\Contracts\EventDispatcher\EventDispatcherInterface;

class Registrar {

  protected EventDispatcherInterface $dispatcher;

  public function register($untyped, LoggerInterface $logger, string $event) {
    $untyped->addListener('my_module.paid', [$this, 'onPaid']);
    $this->dispatcher->addListener('my_module.paid', [$this, 'onPaid']);
    $logger->addListener($event, [$this, 'onPaid']);
    $this->dispatcher->addListener($event, [$this, 'onPaid']);
    \Drupal::service('event_dispatcher')->addListener($event, [$this, 'onPaid']);
    $logger->addSubscriber($this->subscriber);
    $this->dispatcher->addSubscriber($this->subscriber);
  }

  public function onPaid() {}

}
""",
}


def test_registrations_on_objects_known_differently_keep_each_place_s_receiver(
    tmp_path: Path,
) -> None:
    """Two registrations of one event and listener in one method, on objects known differently,
    share one subscribed_by edge whose receiver differs by place; a runtime registration is one
    node per object its call runs on, and the one on an object known not to be a dispatcher is
    taken back alone."""
    _plant(tmp_path, SHARED_REGISTRATIONS)
    document, report = _map(tmp_path)
    path = "web/modules/custom/my_module/src/EventSubscriber/Registrar.php"
    assert _registrations(document) == {
        (
            "registers_listener_at_runtime",
            "Registrar::register",
            "Registrar::register|$event~p:dispatcher",
            None,
        ),
        (
            "registers_listener_at_runtime",
            "Registrar::register",
            "Registrar::register|$event~x",
            None,
        ),
        (
            "registers_listener_at_runtime",
            "Registrar::register",
            "Registrar::register|$this->subscriber~p:dispatcher",
            None,
        ),
        ("subscribed_by", "my_module.paid", "Registrar::onPaid", "0"),
    }
    edge = next(
        e
        for e in document["edges"]
        if e["kind"] == "subscribed_by" and e["to"].endswith("Registrar::onPaid")
    )
    assert edge["attributes"]["receiver"] == {
        "differs": [
            {"file": path, "line": 13, "value": "not known to be an event dispatcher"},
            {"file": path, "line": 14, "value": "an event dispatcher"},
        ]
    }
    assert report.skipped == ()


INHERITED_CONSTANTS = {
    "web/modules/custom/my_module/my_module.info.yml": r"""name: My module
type: module
core_version_requirement: ^11
""",
    "web/modules/custom/my_module/my_module.services.yml": r"""services:
  my_module.classed:
    class: Drupal\my_module\EventSubscriber\ShopSubscriber
    tags:
      - { name: kernel.event_listener, event: 'Drupal\my_module\Event\ClassedEvent', method:"""
    r""" onClassed }
      - { name: kernel.event_listener, event: "Drupal\\my_module\\Event\\EscapedEvent", method:"""
    r""" onEscaped }
""",
    "web/modules/custom/my_module/src/Event/BaseEvents.php": r"""<?php

namespace Drupal\my_module\Event;

class BaseEvents {

  const PAID = 'my_module.paid';

  const BUILT = self::PREFIX . 'built';

  const CLASSED = 'Drupal\my_module\Event\ClassedEvent';

  const ESCAPED = 'Drupal\\my_module\\Event\\EscapedEvent';

  const DOUBLED = "Drupal\\my_module\\Event\\DoubledEvent";

  const NEWLINE = "Drupal\node\Event";

}
""",
    "web/modules/custom/my_module/src/Event/OtherEvents.php": r"""<?php

namespace Drupal\my_module\Event;

class OtherEvents extends ShopEvents {

  const PAID = 'my_module.other_paid';

}
""",
    "web/modules/custom/my_module/src/Event/ShopEvents.php": r"""<?php

namespace Drupal\my_module\Event;

class ShopEvents extends BaseEvents {

  const OWN = 'my_module.own';

}
""",
    "web/modules/custom/my_module/src/EventSubscriber/ShopSubscriber.php": r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\my_module\Event\BaseEvents;
use Drupal\my_module\Event\OtherEvents;
use Drupal\my_module\Event\ShopEvents;
use Symfony\Component\EventDispatcher\EventSubscriberInterface;

class ShopSubscriber implements EventSubscriberInterface {

  public static function getSubscribedEvents() {
    return [
      ShopEvents::PAID => 'onPaid',
      BaseEvents::PAID => 'onBasePaid',
      OtherEvents::PAID => 'onOtherPaid',
      ShopEvents::BUILT => 'onBuilt',
      BaseEvents::BUILT => 'onBaseBuilt',
      ShopEvents::CLASSED => 'onClassed',
      ShopEvents::ESCAPED => 'onEscaped',
      ShopEvents::DOUBLED => 'onDoubled',
      ShopEvents::NEWLINE => 'onNewline',
      'my_module.paid' => 'onNamedPaid',
    ];
  }

  public function onPaid() {}
  public function onBasePaid() {}
  public function onOtherPaid() {}
  public function onBuilt() {}
  public function onBaseBuilt() {}
  public function onClassed() {}
  public function onEscaped() {}
  public function onDoubled() {}
  public function onNewline() {}
  public function onNamedPaid() {}

}
""",
}


def test_a_constant_read_through_a_child_or_holding_a_backslash_meets_its_event(
    tmp_path: Path,
) -> None:
    """Child::NAME, with NAME declared on a parent, names the parent's event: its text, or the
    parent's constant when it has none; an override of the child's own wins. A text holding a
    backslash is read as PHP reads the literal, in single or double quotes, so it meets a tag's
    class name; a double-quoted text with another escape keeps the constant."""
    _plant(tmp_path, INHERITED_CONSTANTS)
    document, report = _map(tmp_path)
    assert _registrations(document) == {
        ("subscribed_by", "Event\\BaseEvents::BUILT", "ShopSubscriber::onBaseBuilt", "0"),
        ("subscribed_by", "Event\\BaseEvents::BUILT", "ShopSubscriber::onBuilt", "0"),
        ("subscribed_by", "Event\\BaseEvents::NEWLINE", "ShopSubscriber::onNewline", "0"),
        ("subscribed_by", "Event\\ClassedEvent", "ShopSubscriber::onClassed", "0"),
        ("subscribed_by", "Event\\DoubledEvent", "ShopSubscriber::onDoubled", "0"),
        ("subscribed_by", "Event\\EscapedEvent", "ShopSubscriber::onEscaped", "0"),
        ("subscribed_by", "my_module.other_paid", "ShopSubscriber::onOtherPaid", "0"),
        ("subscribed_by", "my_module.paid", "ShopSubscriber::onBasePaid", "0"),
        ("subscribed_by", "my_module.paid", "ShopSubscriber::onNamedPaid", "0"),
        ("subscribed_by", "my_module.paid", "ShopSubscriber::onPaid", "0"),
    }
    names = {
        (e["from"].split("::", 1)[1], e["to"])
        for e in document["edges"]
        if e["kind"] == "names_event"
    }
    assert (
        "Drupal\\my_module\\Event\\BaseEvents::ESCAPED",
        "drupal.event::Drupal\\my_module\\Event\\EscapedEvent",
    ) in names
    assert (
        "Drupal\\my_module\\Event\\BaseEvents::DOUBLED",
        "drupal.event::Drupal\\my_module\\Event\\DoubledEvent",
    ) in names
    assert report.skipped == ()


LATER_CONSTANTS = {
    "web/modules/custom/my_module/my_module.info.yml": r"""name: My module
type: module
core_version_requirement: ^11
""",
    "web/modules/custom/my_module/src/Event/OrderEvents.php": r"""<?php

namespace Drupal\my_module\Event;

final class OrderEvents {

  const PLACED = 'my_module.placed',PAID = 'my_module.paid';

  const SHIPPED = 'my_module.shipped', CLOSED = 'my_module.closed';

  public const OPENED='my_module.opened',HELD="my_module.held",KEPT='my_module.kept';

}
""",
    "web/modules/custom/my_module/src/EventSubscriber/OrderSubscriber.php": r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\my_module\Event\OrderEvents;
use Symfony\Component\EventDispatcher\EventSubscriberInterface;

class OrderSubscriber implements EventSubscriberInterface {

  public static function getSubscribedEvents() {
    return [
      OrderEvents::PLACED => 'onPlaced',
      OrderEvents::PAID => 'onPaid',
      OrderEvents::CLOSED => 'onClosed',
      OrderEvents::HELD => 'onHeld',
      OrderEvents::KEPT => 'onKept',
      'my_module.second' => 'onSecond',
    ];
  }

  public function onPlaced() {}
  public function onPaid() {}
  public function onClosed() {}
  public function onHeld() {}
  public function onKept() {}
  public function onSecond() {}

}
""",
    "web/modules/custom/my_module/src/Settings.php": r"""<?php

namespace Drupal\my_module;

final class Settings {

  const FIRST = 'my_module.first',SECOND = 'my_module.second';

}
""",
}


def test_each_constant_of_one_const_statement_names_its_event(tmp_path: Path) -> None:
    """const A = 'a',B = 'b'; with or without spaces after the comma gives each constant its
    names_event edge; a class that is no event class gives none."""
    _plant(tmp_path, LATER_CONSTANTS)
    document, report = _map(tmp_path)
    assert _registrations(document) == {
        ("subscribed_by", "my_module.closed", "OrderSubscriber::onClosed", "0"),
        ("subscribed_by", "my_module.held", "OrderSubscriber::onHeld", "0"),
        ("subscribed_by", "my_module.kept", "OrderSubscriber::onKept", "0"),
        ("subscribed_by", "my_module.paid", "OrderSubscriber::onPaid", "0"),
        ("subscribed_by", "my_module.placed", "OrderSubscriber::onPlaced", "0"),
        ("subscribed_by", "my_module.second", "OrderSubscriber::onSecond", "0"),
    }
    names = {e["from"].rsplit("::", 1)[1] for e in document["edges"] if e["kind"] == "names_event"}
    assert names == {"CLOSED", "HELD", "KEPT", "OPENED", "PAID", "PLACED", "SHIPPED"}
    assert report.skipped == ()


DERIVED_FROM_TEXT = {
    "web/modules/custom/my_module/my_module.info.yml": r"""name: My module
type: module
core_version_requirement: ^11
""",
    "web/modules/custom/my_module/my_module.services.yml": r"""services:
  my_module.tagged:
    class: Drupal\my_module\EventSubscriber\TagListener
    tags:
      - { name: kernel.event_listener, event: !php/const Drupal\my_module\Event\ShopEvents::PAID }
      - { name: kernel.event_listener, event: !php/const Drupal\my_module\Event\MoreEvents::LOST }
      - { name: kernel.event_listener, event: !php/const Drupal\my_module\Event\ShopEvents::BUILT }
      - { name: kernel.event_listener, event: !php/const"""
    r""" Symfony\Component\HttpKernel\KernelEvents::REQUEST }
  my_module.no_class:
    tags:
      - { name: kernel.event_listener, event: !php/const Drupal\my_module\Event\ShopEvents::PAID }
""",
    "web/modules/custom/my_module/src/Event/MoreEvents.php": r"""<?php

namespace Drupal\my_module\Event;

class MoreEvents extends ShopEvents {
}
""",
    "web/modules/custom/my_module/src/Event/ShopEvents.php": r"""<?php

namespace Drupal\my_module\Event;

final class ShopEvents {

  const PAID = 'my_module.paid';

  const SHIPPED = 'my_module.order_shipped';

  const LOST = 'my_module.lost';

  const BUILT = self::PREFIX . 'built';

}
""",
    "web/modules/custom/my_module/src/EventSubscriber/LostListener.php": r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\my_module\Event\ShopEvents;
use Symfony\Component\EventDispatcher\Attribute\AsEventListener;
use Symfony\Component\HttpKernel\KernelEvents;

#[AsEventListener(event: ShopEvents::LOST)]
#[AsEventListener(event: KernelEvents::REQUEST)]
#[AsEventListener(event: ShopEvents::BUILT)]
#[AsEventListener(event: ShopEvents::PAID, method: 'named')]
class LostListener {

  public function named() {}

}
""",
    "web/modules/custom/my_module/src/EventSubscriber/PaidListener.php": r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\my_module\Event\ShopEvents;
use Symfony\Component\EventDispatcher\Attribute\AsEventListener;

#[AsEventListener(event: ShopEvents::PAID)]
class PaidListener {

  public function ONMYMODULEPAID() {}

}
""",
    "web/modules/custom/my_module/src/EventSubscriber/ShippedListener.php": r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\my_module\Event\MoreEvents;
use Symfony\Component\EventDispatcher\Attribute\AsEventListener;

#[AsEventListener(MoreEvents::SHIPPED, priority: 5)]
class ShippedListener {

  public function __invoke() {}

}
""",
    "web/modules/custom/my_module/src/EventSubscriber/TagListener.php": r"""<?php

namespace Drupal\my_module\EventSubscriber;

class TagListener {

  public function onMyModulePaid() {}

  public function onMyModuleOrderShipped() {}

}
""",
    "web/modules/custom/my_module/src/MyModuleServiceProvider.php": r"""<?php

namespace Drupal\my_module;

use Drupal\Core\DependencyInjection\ContainerBuilder;
use Drupal\Core\DependencyInjection\ServiceProviderBase;
use Drupal\my_module\Event\ShopEvents;
use Drupal\my_module\EventSubscriber\TagListener;

class MyModuleServiceProvider extends ServiceProviderBase {

  public function alter(ContainerBuilder $container) {
    $container->register('my_module.reg', TagListener::class)->addTag('kernel.event_listener',"""
    r""" ['event' => ShopEvents::SHIPPED, 'priority' => 3]);
    $container->getDefinition('my_module.tagged')->addTag('kernel.event_listener', ['event' =>"""
    r""" ShopEvents::LOST]);
    $container->getDefinition('other.service')->addTag('kernel.event_listener', ['event' =>"""
    r""" ShopEvents::PAID]);
    $container->getDefinition('my_module.tagged')->addTag('kernel.event_listener', ['event' =>"""
    r""" ShopEvents::BUILT]);
  }

}
""",
}


def test_a_constant_event_with_no_method_gets_the_method_derived_from_its_text(
    tmp_path: Path,
) -> None:
    """A class-level attribute, a services tag and a PHP tag naming a constant and no method get
    on<Event> derived from the constant's text, also through a child class, then __invoke, then
    the unresolved derived name, on the service id when the map holds no class; the runtime
    listener stays only where no mapped file gives the text."""
    _plant(tmp_path, DERIVED_FROM_TEXT)
    document, report = _map(tmp_path)
    assert _registrations(document) == {
        ("subscribed_by", "Event\\ShopEvents::BUILT", "LostListener|ShopEvents::BUILT", "0"),
        (
            "subscribed_by",
            "Event\\ShopEvents::BUILT",
            "MyModuleServiceProvider::alter|no-method",
            "0",
        ),
        (
            "subscribed_by",
            "Event\\ShopEvents::BUILT",
            "my_module.tagged|Event\\ShopEvents::BUILT",
            "0",
        ),
        ("subscribed_by", "KernelEvents::REQUEST", "LostListener|KernelEvents::REQUEST", "0"),
        ("subscribed_by", "KernelEvents::REQUEST", "my_module.tagged|KernelEvents::REQUEST", "0"),
        ("subscribed_by", "my_module.lost", "LostListener::onMyModuleLost", "0"),
        ("subscribed_by", "my_module.lost", "TagListener::onMyModuleLost", "0"),
        ("subscribed_by", "my_module.order_shipped", "ShippedListener::__invoke", "5"),
        ("subscribed_by", "my_module.order_shipped", "TagListener::onMyModuleOrderShipped", "3"),
        ("subscribed_by", "my_module.paid", "LostListener::named", "0"),
        ("subscribed_by", "my_module.paid", "PaidListener::ONMYMODULEPAID", "0"),
        ("subscribed_by", "my_module.paid", "TagListener::onMyModulePaid", "0"),
        ("subscribed_by", "my_module.paid", "my_module.no_class::onMyModulePaid", "0"),
        ("subscribed_by", "my_module.paid", "other.service::onMyModulePaid", "0"),
    }
    runtime = {n["id"] for n in document["nodes"] if n["type"] == "drupal.runtime_listener"}
    assert runtime == {
        "php.method::Drupal\\my_module\\EventSubscriber\\LostListener|KernelEvents::REQUEST",
        "php.method::Drupal\\my_module\\EventSubscriber\\LostListener|ShopEvents::BUILT",
        "php.method::Drupal\\my_module\\MyModuleServiceProvider::alter|no-method",
        "php.method::my_module.tagged|Drupal\\my_module\\Event\\ShopEvents::BUILT",
        "php.method::my_module.tagged|Symfony\\Component\\HttpKernel\\KernelEvents::REQUEST",
    }
    assert report.skipped == ()


CONTRIB_CONSTANTS = {
    "web/modules/contrib/contrib_mod/modules/sub_mod/src/SubEvents.php": r"""<?php

namespace Drupal\sub_mod;

interface SubEvents {

  const DONE = 'sub_mod.done';

}
""",
    "web/modules/contrib/contrib_mod/src/Event/ContribEvents.php": r"""<?php

namespace Drupal\contrib_mod\Event;

final class ContribEvents {

  const PLACED = 'contrib_mod.placed';

  const SHIPPED = 'contrib_mod.shipped',CLOSED = 'contrib_mod.closed';

}
""",
    "web/modules/contrib/contrib_mod/src/Event/Deep/DeepEvents.php": r"""<?php

namespace Drupal\contrib_mod\Event\Deep;

final class DeepEvents {

  const DEEP = 'contrib_mod.deep';

}
""",
    "web/modules/contrib/contrib_mod/src/Settings.php": r"""<?php

namespace Drupal\contrib_mod;

final class Settings {

  const NAME = 'contrib_mod.settings';

}
""",
    "web/modules/custom/my_module/my_module.info.yml": r"""name: My module
type: module
core_version_requirement: ^11
""",
    "web/modules/custom/my_module/my_module.services.yml": r"""services:
  my_module.placed_tag:
    class: Drupal\my_module\EventSubscriber\ContribSubscriber
    tags:
      - { name: kernel.event_listener, event: contrib_mod.placed, method: onPlaced }
""",
    "web/modules/custom/my_module/src/EventSubscriber/ContribSubscriber.php": r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\contrib_mod\Event\ContribEvents;
use Drupal\contrib_mod\Event\Deep\DeepEvents;
use Drupal\contrib_mod\Settings;
use Drupal\sub_mod\SubEvents;
use Symfony\Component\EventDispatcher\Attribute\AsEventListener;
use Symfony\Component\EventDispatcher\EventSubscriberInterface;

class ContribSubscriber implements EventSubscriberInterface {

  public static function getSubscribedEvents() {
    return [
      ContribEvents::PLACED => 'onPlaced',
      ContribEvents::CLOSED => 'onClosed',
      DeepEvents::DEEP => 'onDeep',
      SubEvents::DONE => 'onDone',
      Settings::NAME => 'onSettings',
      ContribEvents::MISSING => 'onMissing',
    ];
  }

  public function onPlaced() {}
  public function onClosed() {}
  public function onDeep() {}
  public function onDone() {}
  public function onSettings() {}
  public function onMissing() {}

}
""",
    "web/modules/custom/my_module/src/EventSubscriber/ShippedListener.php": r"""<?php

namespace Drupal\my_module\EventSubscriber;

use Drupal\contrib_mod\Event\ContribEvents;
use Symfony\Component\EventDispatcher\Attribute\AsEventListener;

#[AsEventListener(event: ContribEvents::SHIPPED)]
class ShippedListener {

  public function onContribModShipped() {}

}
""",
}


def test_a_contrib_constant_on_disk_names_the_event_of_its_text_and_nothing_else(
    tmp_path: Path,
) -> None:
    """A contributed module's constant in a file named *Event* under src or src/Event, at any depth
    of src/Event and in a submodule, gives its text to a custom key, which meets a tag of that
    text, and to a derived method; it makes no node of its own. A file of another name, and a
    constant no file declares, keep the constant."""
    _plant(tmp_path, CONTRIB_CONSTANTS)
    document, report = _map(tmp_path)
    assert _registrations(document) == {
        (
            "subscribed_by",
            "Drupal\\contrib_mod\\Event\\ContribEvents::MISSING",
            "ContribSubscriber::onMissing",
            "0",
        ),
        (
            "subscribed_by",
            "Drupal\\contrib_mod\\Settings::NAME",
            "ContribSubscriber::onSettings",
            "0",
        ),
        ("subscribed_by", "contrib_mod.closed", "ContribSubscriber::onClosed", "0"),
        ("subscribed_by", "contrib_mod.deep", "ContribSubscriber::onDeep", "0"),
        ("subscribed_by", "contrib_mod.placed", "ContribSubscriber::onPlaced", "0"),
        ("subscribed_by", "contrib_mod.shipped", "ShippedListener::onContribModShipped", "0"),
        ("subscribed_by", "sub_mod.done", "ContribSubscriber::onDone", "0"),
    }
    contrib = {
        n["id"] for n in document["nodes"] if "contrib_mod\\" in n["id"] or "sub_mod\\" in n["id"]
    }
    assert contrib == {
        "drupal.event::Drupal\\contrib_mod\\Event\\ContribEvents::MISSING",
        "drupal.event::Drupal\\contrib_mod\\Settings::NAME",
    }
    gone = {k: v for k, v in CONTRIB_CONSTANTS.items() if "/contrib/" not in k}
    (tmp_path / "absent").mkdir()
    _plant(tmp_path / "absent", gone)
    absent, _ = _map(tmp_path / "absent")
    assert (
        "subscribed_by",
        "Drupal\\contrib_mod\\Event\\ContribEvents::PLACED",
        "ContribSubscriber::onPlaced",
        "0",
    ) in _registrations(absent)
    assert report.skipped == ()
