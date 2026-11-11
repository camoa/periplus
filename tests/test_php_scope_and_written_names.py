"""php_basic's calls on self, static and parent, its unqualified function calls inside a
namespace, and its @var names written with a backslash inside and none in front."""

import json
from pathlib import Path
from typing import Any

from periplus.map import MapReport, run
from periplus.preflight import check_runtime_dependencies

M, F = "php.method::", "php.function::"

BASE = """<?php
namespace App;

class Base extends \\Vendor\\Outside {
    public function hello() {
    }

    public static function make() {
    }
}
"""

CHILD = """<?php
namespace App;

class Child extends Base {
    public function hello() {
        parent::hello();
        self::helper();
        static::make();
        self::absent();
        parent::__construct();
        self::$name();
    }

    private static function helper() {
    }
}
"""

ALONE = """<?php
namespace App;

class Alone {
    public function run() {
        parent::run();
    }
}
"""


def _map(root: Path, files: dict[str, str]) -> tuple[dict[str, Any], MapReport]:
    settings = root / ".periplus" / "settings.yml"
    settings.parent.mkdir(parents=True)
    settings.write_text("periplus_version: 0\npacks: [php_basic@0.2.0]\n")
    for name, text in files.items():
        path = root / "src" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == (), report
    return json.loads((root / "map.json").read_text()), report


def _calls(document: dict[str, Any]) -> dict[tuple[str, str], tuple[list[int], str, str]]:
    return {
        (e["from"], e["to"]): (
            sorted(loc["line"] for loc in e["locations"]),
            e["provenance"][0]["rule"],
            e["provenance"][0]["confidence"],
        )
        for e in document["edges"]
        if e["kind"] == "calls"
    }


def _state(document: dict[str, Any], node_id: str) -> str:
    (node,) = [n for n in document["nodes"] if n["id"] == node_id]
    return str(node["state"])


def test_self_static_and_parent_calls_end_at_the_class_or_ancestor_method(tmp_path: Path) -> None:
    """self and static look on the enclosing class, then its ancestors; parent on the parent, then
    its ancestors; a method no mapped class declares is unresolved under the class the walk
    started from; a variable name keeps only its runtime site; no scope row is skipped."""
    document, report = _map(tmp_path, {"Base.php": BASE, "Child.php": CHILD, "Alone.php": ALONE})
    hello = M + "App\\Child::hello"
    self_rule, parent_rule = "calls_self_method", "calls_parent_method"
    assert _calls(document) == {
        (hello, M + "App\\Base::hello"): ([6], parent_rule, "inferred"),
        (hello, M + "App\\Child::helper"): ([7], self_rule, "inferred"),
        (hello, M + "App\\Base::make"): ([8], self_rule, "inferred"),
        (hello, M + "App\\Child::absent"): ([9], self_rule, "inferred"),
        (hello, M + "App\\Base::__construct"): ([10], parent_rule, "inferred"),
    }
    assert _state(document, M + "App\\Child::absent") == "unresolved"
    assert _state(document, M + "App\\Base::__construct") == "unresolved"
    sites = {n["id"] for n in document["nodes"] if n["type"] == "php.call_site"}
    assert "php.call_site::App\\Alone::run::parent::run" in sites
    assert not [r for r in report.skipped if r[2] == "calls_static_method"], report.skipped


def test_a_parent_call_to_a_class_outside_the_map_stays_unresolved_under_the_parent(
    tmp_path: Path,
) -> None:
    opening = "public function hello() {\n"
    child = BASE.replace(opening, opening + "        parent::boot();\n")
    document, _ = _map(tmp_path, {"Base.php": child})
    assert _calls(document) == {
        (M + "App\\Base::hello", M + "Vendor\\Outside::boot"): (
            [6],
            "calls_parent_method",
            "inferred",
        ),
    }
    assert _state(document, M + "Vendor\\Outside::boot") == "unresolved"


FUNCTIONS = """<?php
namespace App;

function local() {
}

function caller() {
    local();
    t('x');
    both();
}
"""

GLOBAL = """<?php

function both() {
}
"""

NAMESPACED_BOTH = """<?php
namespace App;

function both() {
}
"""


def test_an_unqualified_call_tries_the_global_name_first_and_the_namespaced_one_second(
    tmp_path: Path,
) -> None:
    """A function outside the map is unresolved under its global name. When both a global and a
    namespaced function of one name are mapped, the call ends at the global one: the known limit."""
    document, _ = _map(
        tmp_path,
        {"App/f.php": FUNCTIONS, "global.php": GLOBAL, "App/both.php": NAMESPACED_BOTH},
    )
    caller = F + "App\\caller"
    assert _calls(document) == {
        (caller, F + "App\\local"): ([8], "calls_function", "declared"),
        (caller, F + "t"): ([9], "calls_function", "declared"),
        (caller, F + "both"): ([10], "calls_function", "declared"),
    }
    assert _state(document, F + "t") == "unresolved"
    assert not [n for n in document["nodes"] if n["id"] == F + "App\\t"]


HOLDER = """<?php
namespace App;

use Ext\\Kit;

class Holder {
    /** @var Lib\\Mailer */
    protected $mailer;

    /** @var Other\\Thing */
    protected $thing;

    /** @var Lib\\Gone */
    protected $gone;

    /** @var Kit\\Tool */
    protected $tool;

    public function run() {
        $this->mailer->send();
        $this->thing->go();
        $this->gone->stop();
        $this->tool->make();
    }
}
"""

MAILER = "<?php\nnamespace Lib;\n\nclass Mailer {\n    public function send() {\n    }\n}\n"
THING = "<?php\nnamespace App\\Other;\n\nclass Thing {\n    public function go() {\n    }\n}\n"


def test_a_var_name_written_without_a_leading_backslash_joins_as_written_else_resolved(
    tmp_path: Path,
) -> None:
    """Lib\\Mailer is mapped as written; Other\\Thing only resolved in the namespace; Lib\\Gone is
    neither and stays unresolved under the resolved name; Kit\\Tool resolves through the import.
    None of the four makes a php.property_type node."""
    document, _ = _map(
        tmp_path, {"App/Holder.php": HOLDER, "Lib/Mailer.php": MAILER, "Other/Thing.php": THING}
    )
    run_ = M + "App\\Holder::run"
    rule = "calls_through_written_var_type"
    assert _calls(document) == {
        (run_, M + "Lib\\Mailer::send"): ([20], rule, "inferred"),
        (run_, M + "App\\Other\\Thing::go"): ([21], rule, "inferred"),
        (run_, M + "App\\Lib\\Gone::stop"): ([22], rule, "inferred"),
        (run_, M + "Ext\\Kit\\Tool::make"): ([23], rule, "inferred"),
    }
    assert _state(document, M + "App\\Lib\\Gone::stop") == "unresolved"
    types = {n["type"] for n in document["nodes"]}
    internal = {"php.property_written_type", "php.property_resolved_type"}
    assert not types & ({"php.property_type"} | internal)
