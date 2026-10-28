"""php_basic's reference rules on a planted project: plain and static calls, the PHP internal
functions it leaves out, and a rutter that narrows php_basic's source."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from periplus.map import MapReport, run
from periplus.preflight import check_runtime_dependencies

UTIL = """\
<?php

namespace App\\Lib;

function helper()
{
}

class Util
{
    public static function make()
    {
        helper();
    }
}
"""

# Every call sits past line 256, where tree-sitter 0.26.0 once lost its reference to a point.
PADDING = "".join(f"// padding line {i}\n" for i in range(1, 281))
MAIN = (
    "<?php\n\n"
    + PADDING
    + """\
namespace App;

use App\\Lib\\Util;
use App\\Lib as L;
use function App\\Lib\\helper as h;

local();

function local()
{
}

function caller($obj)
{
    local();
    L\\helper();
    \\App\\Lib\\helper();
    Util::make();
    \\Drupal::service('x');
    missing();
    strlen('x');
    h();
    isset($x);
    empty($y);
    $obj->m();
    $f = function () {
        local();
    };
}

class Main
{
    public function run()
    {
        local();
        $this->other();
        self::other();
        static::other();
        Util::make();
        Util::absent();
    }

    public function other()
    {
    }
}
"""
)

F, M = "php.function::", "php.method::"
CALLER, RUN = F + "App\\caller", M + "App\\Main::run"
MAKE = M + "App\\Lib\\Util::make"


def _plant(root: Path, settings: str = "  - php_basic@0.2.0\n") -> list[str]:
    (root / ".periplus").mkdir(exist_ok=True)
    (root / ".periplus" / "settings.yml").write_text("periplus_version: 0\npacks:\n" + settings)
    (root / "src" / "App").mkdir(parents=True, exist_ok=True)
    (root / "src" / "Lib").mkdir(parents=True, exist_ok=True)
    (root / "src" / "Lib" / "Util.php").write_text(UTIL)
    (root / "src" / "App" / "Main.php").write_text(MAIN)
    return MAIN.splitlines()


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


def _at(lines: list[str], pattern: str) -> list[int]:
    found = [n for n, text in enumerate(lines, 1) if re.fullmatch(pattern, text)]
    assert found, pattern
    return found


def _calls(document: dict[str, Any], kind: str = "calls") -> dict[tuple[str, str], list[int]]:
    return {
        (e["from"], e["to"]): sorted(loc["line"] for loc in e["locations"])
        for e in document["edges"]
        if e["kind"] == kind
    }


def test_plain_and_static_calls_give_a_calls_edge_by_exact_value(tmp_path: Path) -> None:
    """Through an alias, a full name and a used class; a miss ends at an unresolved node that
    keeps what was searched for; the function imported as h() resolves under the namespace."""
    lines = _plant(tmp_path)
    document, _ = _map(tmp_path)
    closure, method = _at(lines, r"        local\(\);")
    expected = {  # (from, to): (lines, searched_for when unresolved)
        (CALLER, F + "App\\local"): (_at(lines, r"    local\(\);") + [closure], None),
        (CALLER, F + "App\\Lib\\helper"): (
            _at(lines, r"    L\\helper\(\);") + _at(lines, r"    \\App\\Lib\\helper\(\);"),
            None,
        ),
        (CALLER, MAKE): (_at(lines, r"    Util::make\(\);"), None),
        (CALLER, M + "Drupal::service"): (
            _at(lines, r"    \\Drupal::service\('x'\);"),
            "Drupal::service",
        ),
        (CALLER, F + "App\\missing"): (_at(lines, r"    missing\(\);"), "App\\missing"),
        (CALLER, F + "App\\h"): (_at(lines, r"    h\(\);"), "App\\h"),
        (RUN, F + "App\\local"): ([method], None),
        (RUN, MAKE): (_at(lines, r"        Util::make\(\);"), None),
        (RUN, M + "App\\Lib\\Util::absent"): (
            _at(lines, r"        Util::absent\(\);"),
            "App\\Lib\\Util::absent",
        ),
        (MAKE, F + "App\\Lib\\helper"): (
            [n for n, text in enumerate(UTIL.splitlines(), 1) if text == "        helper();"],
            None,
        ),
    }
    assert min(n for ls, _ in expected.values() for n in ls if n > 20) > 256
    assert _calls(document) == {k: sorted(ls) for k, (ls, _) in expected.items()}
    for edge in (e for e in document["edges"] if e["kind"] == "calls"):
        rule = "calls_static_method" if "::" in edge["to"].split("::", 1)[1] else "calls_function"
        assert edge["provenance"] == [{"confidence": "declared", "pack": "php_basic", "rule": rule}]
    nodes = {n["id"]: n for n in document["nodes"]}
    for (_, end), (_, searched) in expected.items():
        if searched is None:
            assert nodes[end]["state"] == "mapped", nodes[end]
        else:
            assert nodes[end]["state"] == "unresolved", nodes[end]
            assert nodes[end]["type"] == end.split("::")[0], nodes[end]
            assert nodes[end]["unresolved_detail"]["searched_for"] == searched, nodes[end]


def test_language_constructs_and_object_calls_give_no_edge_and_scope_calls_are_skipped(
    tmp_path: Path,
) -> None:
    """isset, empty and strlen are skip_names; a call on an object gives nothing; self:: and
    static:: and a call outside any function are listed as skipped, each with its reason."""
    lines = _plant(tmp_path)
    document, report = _map(tmp_path)
    calls = [e for e in document["edges"] if e["kind"] == "calls"]
    constructs = (
        _at(lines, r"    isset\(\$x\);")
        + _at(lines, r"    empty\(\$y\);")
        + _at(lines, r"    strlen\('x'\);")
    )
    objects = _at(lines, r"    \$obj->m\(\);") + _at(lines, r"        \$this->other\(\);")
    for edge in calls:
        assert not {loc["line"] for loc in edge["locations"]} & set(constructs + objects), edge
    names = {n["id"].rsplit("\\", 1)[-1] for n in document["nodes"]}
    assert not names & {"isset", "empty", "strlen"}, names
    assert sorted(report.skipped) == sorted(
        [
            (
                "src/App/Main.php",
                _at(lines, r"local\(\);")[0],
                "calls_function",
                "no enclosing declaration is mapped",
            ),
            (
                "src/App/Main.php",
                _at(lines, r"        self::other\(\);")[0],
                "calls_static_method",
                "scope is not a written name",
            ),
            (
                "src/App/Main.php",
                _at(lines, r"        static::other\(\);")[0],
                "calls_static_method",
                "scope is not a written name",
            ),
        ]
    )


def test_a_rutter_can_narrow_php_basics_source_and_read_an_extra_folder_by_its_own_rule(
    tmp_path: Path,
) -> None:
    """The rule reads src and extra; the declaration rules read only src, so the call in extra
    is skipped and gets no phantom source node. The rule writes its end as to: {type: ...}."""
    _plant(tmp_path)
    plain, _ = _map(tmp_path, "plain.json")
    pack = tmp_path / ".periplus" / "packs" / "calls@0.0.1"
    (pack / "rules").mkdir(parents=True)
    (tmp_path / "extra").mkdir()
    (tmp_path / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks:\n  - calls@0.0.1\n"
    )
    (pack / "pack.yaml").write_text(
        "pack: calls\nversion: 0.0.1\ndepends: [php_basic]\nfolders:\n  code: ./src/**\n"
        "  extra: ./extra/**\n  source: ./src/**\n"
    )
    (pack / "rules" / "calls.yaml").write_text(
        "edge_kinds:\n- kind: calls_planted\n  from: [php.function, php.method]\n"
        "  to: [php.function, php.method]\nrules:\n- rule: call_function\n  reads: file\n"
        "  in: [code, extra]\n  match: {reference: function_call_expression, name_child: function,"
        " filetype: php, skip_names: [isset, empty, strlen]}\n  emits:\n  - edge:\n"
        "      kind: calls_planted\n      from: enclosing_declaration\n"
        "      to: {type: php.function, on_miss: unresolved}\n  confidence: declared\n"
    )
    (tmp_path / "extra" / "Side.php").write_text("<?php\n\nfunction side()\n{\n    local();\n}\n")
    document, report = _map(tmp_path, "planted.json")
    want = {
        (e["from"], e["to"]): sorted(loc["line"] for loc in e["locations"])
        for e in plain["edges"]
        if e["kind"] == "calls" and e["provenance"][0]["rule"] == "calls_function"
    }
    assert _calls(document, "calls_planted") == want
    nodes = {n["id"]: n for n in document["nodes"]}
    assert nodes["php.function::App\\missing"]["type"] == "php.function"
    assert not [n for n in nodes if n.endswith("::side")], "phantom source"
    assert all("extra/" not in place["file"] for e in document["edges"] for place in e["locations"])
    assert ("extra/Side.php", 5, "call_function") in {(s[0], s[1], s[2]) for s in report.skipped}


BUILTINS = """\
<?php

namespace App;

function own()
{
}

function caller($text, $list)
{
    $data = json_decode($text);
    $n = count($list);
    $len = strlen($text);
    $has = in_array('x', $list);
    own();
}
"""


def test_functions_php_reports_as_internal_make_no_node_and_a_declared_function_keeps_its_edge(
    tmp_path: Path,
) -> None:
    (tmp_path / ".periplus").mkdir()
    (tmp_path / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks:\n  - php_basic@0.2.0\n"
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "Main.php").write_text(BUILTINS)
    document, report = _map(tmp_path)
    own_call = BUILTINS.splitlines().index("    own();") + 1
    functions = sorted(n["id"] for n in document["nodes"] if n["type"] == "php.function")
    assert functions == ["php.function::App\\caller", "php.function::App\\own"]
    assert _calls(document) == {("php.function::App\\caller", "php.function::App\\own"): [own_call]}
    assert not [row for row in report.skipped if row[2] == "calls_function"], report.skipped
