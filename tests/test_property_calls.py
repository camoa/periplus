"""A call on a property of the enclosing object, ``$this->prop->m()``, resolved by the type the
enclosing class declares for that property: a typed property, a promoted constructor parameter or a
``@var`` docblock. php_basic's map rule calls_through_typed_property emits ``calls`` to that type's
method at ``inferred``."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import periplus
from periplus.map import MapReport, run
from periplus.preflight import check_runtime_dependencies

SERVICE = "<?php\nnamespace App\\Service;\n\nclass {0}\n{{\n  public function {1}() {{}}\n}}\n"
SERVICES = {
    "Mailer.php": SERVICE.format("Mailer", "send"),
    "Clock.php": SERVICE.format("Clock", "now"),
    "Store.php": SERVICE.format("Store", "get"),
}

PAGE = """\
<?php
namespace App\\Web;

use App\\Service\\Mailer;
use App\\Service\\{Clock, Store as Box};

class Page
{
  private Mailer $mailer;

  /** @var Box */
  protected $box;

  protected $plain;

  public function __construct(private readonly Clock $clock) {}

  public function run(): void
  {
    $this->mailer->send();
    $this->clock->now();
    $this->box->get();
    $this->plain->go();
    $other->send();
  }
}
"""

RUN = "php.method::App\\Web\\Page::run"


def _map(root: Path) -> tuple[MapReport, dict[str, Any]]:
    (root / ".periplus").mkdir()
    (root / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks: [php_basic@0.2.0]\n"
    )
    (root / "src" / "Service").mkdir(parents=True)
    (root / "src" / "Web").mkdir()
    for name, text in SERVICES.items():
        (root / "src" / "Service" / name).write_text(text)
    (root / "src" / "Web" / "Page.php").write_text(PAGE)
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == (), report
    return report, json.loads((root / "map.json").read_text())


def _calls(document: dict[str, Any]) -> list[tuple[str, int, str]]:
    """Each calls edge from run that calls_through_typed_property made: its target, its one line
    and the rule's confidence."""
    found = []
    for edge in document["edges"]:
        rules = [p for p in edge["provenance"] if p["rule"] == "calls_through_typed_property"]
        if edge["kind"] == "calls" and edge["from"] == RUN and rules:
            [location], [made] = edge["locations"], rules
            found.append((str(edge["to"]), int(location["line"]), str(made["confidence"])))
    return sorted(found)


def test_each_declared_property_type_gives_one_inferred_call(tmp_path: Path) -> None:
    """A typed property, a promoted constructor parameter and a @var property: one edge each, to a
    method node a class declaration in another file made, at inferred."""
    _, document = _map(tmp_path)
    assert _calls(document) == [
        ("php.method::App\\Service\\Clock::now", 21, "inferred"),
        ("php.method::App\\Service\\Mailer::send", 20, "inferred"),
        ("php.method::App\\Service\\Store::get", 22, "inferred"),
    ], _calls(document)


def test_the_short_type_resolves_to_the_declared_class(tmp_path: Path) -> None:
    """Mailer, Clock and the alias Box resolve through the use statements to the full names the
    class declarations in src/Service have, so each target is a mapped method, not unresolved."""
    _, document = _map(tmp_path)
    methods = {n["id"] for n in document["nodes"] if n["type"] == "php.method"}
    targets = {to for to, _, _ in _calls(document)}
    assert targets and targets <= methods, (targets, methods)
    unresolved = [n["id"] for n in document["nodes"] if n.get("state") == "unresolved"]
    assert unresolved == [], unresolved


def test_an_untyped_property_keeps_its_call_site_and_makes_no_edge_and_no_row(
    tmp_path: Path,
) -> None:
    """$this->plain has no declared type: its call site is mapped, no calls edge leaves run for
    go(), and no rule lists a skipped row in Page.php. $other->send() is no property of the
    enclosing object: no edge."""
    report, document = _map(tmp_path)
    assert [row for row in report.skipped if row[0].endswith("Page.php")] == [], report.skipped
    sites = {n["id"] for n in document["nodes"] if n["type"] == "php.call_site"}
    assert "php.call_site::App\\Web\\Page::run::$this->plain->go" in sites, sites
    targets = [e["to"] for e in document["edges"] if e["kind"] == "calls" and e["from"] == RUN]
    assert not [t for t in targets if t.endswith("::go")], targets
    assert [line for _, line, _ in _calls(document)] == [21, 20, 22], _calls(document)


def test_a_project_local_pack_with_the_same_grammar_gives_the_same_edges(tmp_path: Path) -> None:
    """php_basic copied into the project's .periplus/packs as own@0.0.1: its declaration rules and
    map rules give the same three calls edges a bundled pack gives (property 5)."""
    pack = tmp_path / ".periplus" / "packs" / "own@0.0.1"
    shutil.copytree(Path(periplus.__file__).parent / "packs" / "php_basic@0.2.0", pack)
    manifest = (pack / "pack.yaml").read_text()
    manifest = manifest.replace("pack: php_basic\nversion: 0.2.0\n", "pack: own\nversion: 0.0.1\n")
    assert "pack: own\n" in manifest
    (pack / "pack.yaml").write_text(manifest)
    (tmp_path / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks: [own@0.0.1]\n"
    )
    (tmp_path / "src" / "Service").mkdir(parents=True)
    (tmp_path / "src" / "Web").mkdir()
    for name, text in SERVICES.items():
        (tmp_path / "src" / "Service" / name).write_text(text)
    (tmp_path / "src" / "Web" / "Page.php").write_text(PAGE)
    report = run(
        start=tmp_path,
        env={"PERIPLUS_CONFIG_DIR": str(tmp_path / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == () and report.not_executed == (), report
    document = json.loads((tmp_path / "map.json").read_text())
    assert _calls(document) == [
        ("php.method::App\\Service\\Clock::now", 21, "inferred"),
        ("php.method::App\\Service\\Mailer::send", 20, "inferred"),
        ("php.method::App\\Service\\Store::get", 22, "inferred"),
    ], _calls(document)


VAR_FORMS = """\
<?php
namespace App\\Web;

use App\\Service\\{Mailer, Clock, Store};

class Forms
{
  /** @var ?Mailer */
  protected $optional;

  /** @var \\App\\Service\\Clock|null */
  protected $union;

  /** @var Store*/
  protected $tight;

  public function run(): void
  {
    $this->optional->send();
    $this->union->now();
    $this->tight->get();
  }
}
"""

TWICE_SERVICE = "<?php\nnamespace App\\Service;\n\nclass Tool\n{\n  public function work() {}\n}\n"
TWICE_PAGE = """\
<?php
namespace App\\Web;

use App\\Service\\Tool;

class Twice
{
  private Tool $tool;

  public function run(): void
  {
    $this->tool->work();
    $this->tool->work();
  }
}
"""


def _map_files(root: Path, files: dict[str, str]) -> dict[str, Any]:
    (root / ".periplus").mkdir()
    (root / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks: [php_basic@0.2.0]\n"
    )
    for name, text in files.items():
        (root / "src" / name).parent.mkdir(parents=True, exist_ok=True)
        (root / "src" / name).write_text(text)
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == (), report
    return json.loads((root / "map.json").read_text())  # type: ignore[no-any-return]


def test_each_var_docblock_form_gives_type_node_typed_as_edge_and_call_c2(
    tmp_path: Path,
) -> None:
    """?Box, a namespaced name or null, and no space before the comment end: each property gets a
    property type node, a typed-as edge and a calls edge through it."""
    document = _map_files(
        tmp_path, {**{f"Service/{n}": t for n, t in SERVICES.items()}, "Web/Forms.php": VAR_FORMS}
    )
    types = [n for n in document["nodes"] if n["type"] == "php.property_type"]
    typed_as = [e for e in document["edges"] if e["kind"] == "property_typed_as"]
    run_id = "php.method::App\\Web\\Forms::run"
    calls = sorted(
        str(e["to"])
        for e in document["edges"]
        if e["kind"] == "calls"
        and e["from"] == run_id
        and any(p["rule"] == "calls_through_typed_property" for p in e["provenance"])
    )
    assert len(types) == 3, types
    assert len(typed_as) == 3, typed_as
    assert calls == [
        "php.method::App\\Service\\Clock::now",
        "php.method::App\\Service\\Mailer::send",
        "php.method::App\\Service\\Store::get",
    ], calls


def test_the_same_call_on_two_lines_lists_both_lines_c3(tmp_path: Path) -> None:
    """$this->tool->work(); on two lines of one method: one calls edge from the method, listing
    both lines."""
    document = _map_files(
        tmp_path, {"Service/Tool.php": TWICE_SERVICE, "Web/Twice.php": TWICE_PAGE}
    )
    edges = [
        e
        for e in document["edges"]
        if e["kind"] == "calls"
        and e["from"] == "php.method::App\\Web\\Twice::run"
        and e["to"] == "php.method::App\\Service\\Tool::work"
    ]
    assert len(edges) == 1, edges
    assert sorted(loc["line"] for loc in edges[0]["locations"]) == [12, 13], edges[0]
