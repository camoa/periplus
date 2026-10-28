"""Calls through a property, which were once proved by demo scripts: a property a parent class
assigns, a property assigned in the calling class, and a property typed as a union. Each test
plants a small site and maps it in-process with the bundled php_basic and drupal_basic rutters."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from test_demo_b_support import clean_map, line_of, plant, settings

from periplus.map import MapReport

MODULE = "web/modules/custom/my_module"
NS = "Drupal\\my_module"

SERVICES = """\
services:
  my_module.helper:
    class: Drupal\\my_module\\Helper
"""


def _php(namespace: str, body: str) -> str:
    return f"<?php\n\nnamespace {namespace};\n\n{body}\n"


def _class(name: str, members: str, extends: str = "") -> str:
    tail = f" extends {extends}" if extends else ""
    return f"class {name}{tail}\n{{\n{members}}}"


def _method(name: str, statements: str = "") -> str:
    return f"    public function {name}()\n    {{\n{statements}    }}\n"


def _drupal_site(root: Path) -> None:
    src = f"{MODULE}/src"
    plant(
        root,
        {
            **settings("drupal_basic@0.3.0"),
            f"{MODULE}/my_module.services.yml": SERVICES,
            f"{src}/Helper.php": _php(NS, _class("Helper", _method("run"))),
            f"{src}/Tool.php": _php(NS, _class("Tool", _method("go") + "\n" + _method("work"))),
            f"{src}/ToolParent.php": _php(
                NS,
                _class(
                    "ToolParent",
                    "    protected $tool;\n\n"
                    + _method("useParent", "        $this->tool->go();\n"),
                ),
            ),
            f"{src}/ToolChild.php": _php(
                NS,
                _class(
                    "ToolChild",
                    "    public function __construct(Tool $tool)\n    {\n"
                    "        $this->tool = $tool;\n    }\n\n"
                    + _method("useTool", "        $this->tool->work();\n"),
                    extends="ToolParent",
                ),
            ),
            f"{src}/ToolOwner.php": _php(
                NS,
                _class(
                    "ToolOwner",
                    "    protected $tool;\n\n"
                    "    public function __construct(Tool $tool)\n    {\n"
                    "        $this->tool = $tool;\n    }\n\n"
                    + _method("useTool", "        $this->tool->work();\n"),
                ),
            ),
            f"{src}/Mail/Mailer.php": _php(f"{NS}\\Mail", _class("Mailer", _method("send"))),
            f"{src}/Controller/BaseController.php": _php(
                f"{NS}\\Controller",
                "use Drupal\\my_module\\Mail\\Mailer;\n\n"
                + _class(
                    "BaseController",
                    "    protected $mailer;\n\n    protected $helper;\n\n    protected $other;\n\n"
                    "    public function __construct(Mailer $mailer, $other)\n    {\n"
                    "        $this->mailer = $mailer;\n"
                    "        $this->helper = \\Drupal::service('my_module.helper');\n"
                    "        $this->other = $other;\n    }\n",
                ),
            ),
            f"{src}/Controller/ChildController.php": _php(
                f"{NS}\\Controller",
                _class(
                    "ChildController",
                    _method(
                        "notify",
                        "        $this->mailer->send();\n"
                        "        $this->helper->run();\n"
                        "        $this->other->go();\n",
                    ),
                    extends="BaseController",
                ),
            ),
        },
    )


@pytest.fixture(scope="module")
def drupal_map(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, MapReport, Any]:
    """One map of the planted module, shared by the two tests that read it."""
    root = tmp_path_factory.mktemp("property_calls")
    _drupal_site(root)
    report, document = clean_map(root)
    return root, report, document


def _calls_from(document: Any, caller: str) -> list[tuple[str, list[int], list[tuple[str, str]]]]:
    return sorted(
        (
            e["to"],
            [place["line"] for place in e["locations"]],
            sorted((row["rule"], row["confidence"]) for row in e["provenance"]),
        )
        for e in document["edges"]
        if e["kind"] == "calls" and e["from"] == caller
    )


def test_a_call_through_a_property_a_parent_assigns_ends_on_the_type_it_was_assigned(
    drupal_map: tuple[Path, MapReport, Any],
) -> None:
    """BaseController assigns $this->mailer from a parameter typed Mailer, and $this->helper from
    \\Drupal::service(), whose services file names Helper. ChildController::notify calls through
    both and through $this->other, assigned from an untyped parameter. The first two give calls
    edges at the calls' lines; go() keeps its call site and gets no edge."""
    root, report, document = drupal_map
    child = root / MODULE / "src/Controller/ChildController.php"
    assert report.skipped == ()

    notify = f"php.method::{NS}\\Controller\\ChildController::notify"
    assert _calls_from(document, notify) == [
        (
            f"php.method::{NS}\\Helper::run",
            [line_of(child, "$this->helper->run();")],
            [("calls_through_service_property", "inferred")],
        ),
        (
            f"php.method::{NS}\\Mail\\Mailer::send",
            [line_of(child, "$this->mailer->send();")],
            [("calls_through_assigned_property", "inferred")],
        ),
    ]

    prefix = f"php.call_site::{NS}\\Controller\\ChildController::notify::$this->"
    sites = {
        n["id"]: n["state"]
        for n in document["nodes"]
        if n["type"] == "php.call_site" and n["id"].startswith(prefix)
    }
    assert sites == {
        prefix + call: "mapped" for call in ("mailer->send", "helper->run", "other->go")
    }
    edges = {(e["kind"], e["from"], e["to"]) for e in document["edges"]}
    untyped = prefix + "other->go"
    assert ("has_call_site", notify, untyped) in edges
    assert ("call_site_in", untyped, notify) in edges
    parameter = f"{NS}\\Controller\\BaseController"
    assert (
        "parameter_typed_as",
        f"php.parameter::{parameter}::__construct::$mailer",
        f"php.parameter_type::{parameter}::$mailer::{NS}\\Mail\\Mailer",
    ) in edges

    parts = {
        "php.property",
        "php.parameter",
        "php.parameter_type",
        "php.member_assignment",
        "php.member_assignment_value",
        "php.call_site",
    }
    states = {(n["type"], n["state"]) for n in document["nodes"] if n["type"] in parts}
    assert states == {(kind, "mapped") for kind in parts}

    first, second = report.map_passes
    assert sorted(first[1]) == [
        ("drupal_basic", "calls_through_service_property", 1),
        ("php_basic", "calls_through_assigned_property", 2),
        ("php_basic", "calls_through_property_assigned_here", 2),
    ]
    assert second == (2, ())


def test_a_property_assigned_in_the_calling_class_gives_an_edge_a_parent_declaration_does_not(
    drupal_map: tuple[Path, MapReport, Any],
) -> None:
    """ToolParent declares $tool untyped and calls $this->tool->go(): no edge. ToolChild assigns
    it from a parameter typed Tool and calls $this->tool->work(): an edge, from the rule for a
    property assigned here. ToolOwner declares and assigns its own: its one edge carries a row from
    both rules."""
    root, _, document = drupal_map
    src = root / MODULE / "src"

    work = f"php.method::{NS}\\Tool::work"
    assert _calls_from(document, f"php.method::{NS}\\ToolParent::useParent") == []
    assert _calls_from(document, f"php.method::{NS}\\ToolChild::useTool") == [
        (
            work,
            [line_of(src / "ToolChild.php", "$this->tool->work();")],
            [("calls_through_property_assigned_here", "inferred")],
        )
    ]
    assert _calls_from(document, f"php.method::{NS}\\ToolOwner::useTool") == [
        (
            work,
            [line_of(src / "ToolOwner.php", "$this->tool->work();")],
            [
                ("calls_through_assigned_property", "inferred"),
                ("calls_through_property_assigned_here", "inferred"),
            ],
        )
    ]


def test_a_property_typed_as_a_union_of_one_class_gives_a_call_and_of_two_gives_none(
    tmp_path: Path,
) -> None:
    """$a Helper|null, $b null|Helper, $d Helper|false|null, $e string|Helper, the promoted $f
    Helper|null and the spaced $g Helper | null and promoted $h null | Helper each mint one
    property type ending in Helper and a calls edge to Helper's method of that name. $c is
    Helper|Other, which names two classes: no property type, no edge and no skipped row, but its
    call site is kept."""
    methods = "".join(f"    public function {name}() {{}}\n" for name in "abcdefgh")
    plant(
        tmp_path,
        {
            **settings("php_basic@0.2.0"),
            "src/Service/Helper.php": _php("App\\Service", _class("Helper", methods)),
            "src/Service/Other.php": _php(
                "App\\Service", _class("Other", "    public function c() {}\n")
            ),
            "src/Web/Page.php": """\
<?php

namespace App\\Web;

use App\\Service\\Helper;
use App\\Service\\Other;

class Page
{
    private Helper|null $a;

    private null|Helper $b;

    private Helper|Other $c;

    private Helper|false|null $d;

    private string|Helper $e;

    private Helper | null $g;

    public function __construct(private Helper|null $f, private null | Helper $h)
    {
    }

    public function run(): void
    {
        $this->a->a();
        $this->b->b();
        $this->c->c();
        $this->d->d();
        $this->e->e();
        $this->f->f();
        $this->g->g();
        $this->h->h();
    }
}
""",
        },
    )
    page = tmp_path / "src/Web/Page.php"
    report, document = clean_map(tmp_path)

    made = [("calls_through_typed_property", "inferred")]
    assert _calls_from(document, "php.method::App\\Web\\Page::run") == [
        (
            f"php.method::App\\Service\\Helper::{name}",
            [line_of(page, f"$this->{name}->{name}();")],
            made,
        )
        for name in "abdefgh"
    ]
    types = sorted(n["id"] for n in document["nodes"] if n["type"] == "php.property_type")
    assert types == [
        f"php.property_type::App\\Web\\Page::${name}::App\\Service\\Helper" for name in "abdefgh"
    ]
    sites = {n["id"]: n["state"] for n in document["nodes"] if n["type"] == "php.call_site"}
    assert sites["php.call_site::App\\Web\\Page::run::$this->c->c"] == "mapped"
    assert [row for row in report.skipped if "Page.php" in row[0]] == []
