"""A call whose method name or callee is a variable keeps a marked call site."""

import json
from pathlib import Path
from typing import Any

from periplus.map import run
from periplus.preflight import check_runtime_dependencies

PACK = "php_basic@0.2.0"
METHOD = "php.method::App\\Page::run"

DIRECT = """<?php
namespace App;

class Page {
    public function run(string $name): void {
        $this->$name();
    }
}
"""

MAILER = """<?php
namespace App\\Service;

class Mailer {
    public function send(): void {
    }
}
"""

TYPED = """<?php
namespace App\\Web;

use App\\Service\\Mailer;

class Page {
    private Mailer $mailer;

    public function run(string $name): void {
        $this->mailer->send();
        $this->mailer->$name();
    }
}
"""

OTHER_SHAPES = """<?php
namespace App;

class Page {
    public function run($fn, $obj, string $name): void {
        $fn();
        $fn();
        self::$name();
        $obj?->$name();
    }
}
"""


def _map_files(root: Path, files: dict[str, str]) -> dict[str, Any]:
    settings = root / ".periplus" / "settings.yml"
    settings.parent.mkdir(parents=True)
    settings.write_text(f"periplus_version: 0\npacks: [{PACK}]\n")
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
    assert report.problems == ()
    return json.loads((root / "map.json").read_text())


def _sites(document: dict[str, Any]) -> list[dict[str, Any]]:
    return [n for n in document["nodes"] if n["type"] == "php.call_site"]


def _lines(node: dict[str, Any]) -> list[int]:
    return sorted(loc["line"] for loc in node.get("locations", []))


def _resolution(node: dict[str, Any]) -> Any:
    return node.get("attributes", {}).get("resolution")


def _calls_from(document: dict[str, Any], source: str) -> list[str]:
    return [e["to"] for e in document["edges"] if e["kind"] == "calls" and e["from"] == source]


def test_variable_method_name_on_this_is_a_marked_call_site_c1(tmp_path: Path) -> None:
    document = _map_files(tmp_path, {"Page.php": DIRECT})
    sites = _sites(document)
    assert [(_lines(s), _resolution(s)) for s in sites] == [([6], "runtime")]
    assert _calls_from(document, sites[0]["id"]) == []


def test_variable_method_name_on_typed_property_is_marked_and_literal_sibling_resolves_c2(
    tmp_path: Path,
) -> None:
    document = _map_files(tmp_path, {"Service/Mailer.php": MAILER, "Web/Page.php": TYPED})
    page = "php.method::App\\Web\\Page::run"
    marked = [s for s in _sites(document) if _resolution(s) == "runtime"]
    assert [_lines(s) for s in marked] == [[11]]
    assert _calls_from(document, marked[0]["id"]) == []
    assert _calls_from(document, page) == ["php.method::App\\Service\\Mailer::send"]


def test_variable_function_scoped_and_nullsafe_calls_give_one_marked_site_per_callee_wo2(
    tmp_path: Path,
) -> None:
    document = _map_files(tmp_path, {"Page.php": OTHER_SHAPES})
    sites = _sites(document)
    assert sorted((_lines(s), _resolution(s)) for s in sites) == [
        ([6, 7], "runtime"),
        ([8], "runtime"),
        ([9], "runtime"),
    ]
    back = {
        e["from"] for e in document["edges"] if e["kind"] == "call_site_in" and e["to"] == METHOD
    }
    assert back == {s["id"] for s in sites}


LITERAL_SHAPES = """<?php
namespace App;

class Page {
    public function run($obj): void {
        $this->go();
        foo();
        self::go();
        $obj?->go();
    }

    public function go(): void {
    }
}
"""


def test_no_calls_edge_leaves_a_marked_site_of_any_shape_wo2(tmp_path: Path) -> None:
    document = _map_files(tmp_path, {"Page.php": OTHER_SHAPES})
    marked = [s["id"] for s in _sites(document) if _resolution(s) == "runtime"]
    assert len(marked) == 3
    assert [e for e in document["edges"] if e["kind"] == "calls" and e["from"] in marked] == []
    assert _calls_from(document, METHOD) == []


def test_literal_named_calls_get_no_marked_site_wo2(tmp_path: Path) -> None:
    document = _map_files(tmp_path, {"Page.php": LITERAL_SHAPES})
    assert [n["id"] for n in document["nodes"] if _resolution(n) == "runtime"] == []
    assert [s["id"] for s in _sites(document)] == []
