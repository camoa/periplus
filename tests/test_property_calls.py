"""A call on a property of the enclosing object, ``$this->prop->m()``, resolved by the type the
enclosing class declares for that property: a typed property, a promoted constructor parameter or a
``@var`` docblock. php_basic emits ``calls`` to that type's method at ``inferred``."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

import periplus
from periplus.engine.packload import _read_rule
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
    """Each calls edge from run that calls_property_method made: its target, its one line and the
    rule's confidence."""
    found = []
    for edge in document["edges"]:
        rules = [p for p in edge["provenance"] if p["rule"] == "calls_property_method"]
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


def test_an_untyped_property_makes_no_edge_and_a_skipped_row(tmp_path: Path) -> None:
    """$this->plain has no declared type: no edge and one skipped row at its line. $other->send()
    is no property of the enclosing object: no edge and no row."""
    report, document = _map(tmp_path)
    rows = [(line, why) for _, line, rule, why in report.skipped if rule == "calls_property_method"]
    assert rows == [(23, "object has no declared type")], report.skipped
    assert [line for _, line, _ in _calls(document)] == [21, 20, 22], _calls(document)


def test_a_receiver_the_engine_does_not_run_is_refused() -> None:
    """typed_parameter is accepted by the schema and not executed, so the rule is not run."""
    rule = _read_rule(
        "own",
        {
            "rule": "r",
            "reads": "file",
            "in": ["code"],
            "match": {
                "reference": "member_call_expression",
                "name_child": ["object", "name"],
                "filetype": "php",
                "where": [{"receiver": "typed_parameter"}],
            },
            "emits": [
                {"edge": {"kind": "calls", "from": "enclosing_declaration", "to": {"types": ["m"]}}}
            ],
            "confidence": "inferred",
        },
    )
    assert not rule.supported and "typed_parameter" in rule.reason, rule


def test_a_project_local_pack_with_the_same_grammar_gives_the_same_edges(tmp_path: Path) -> None:
    """php_basic copied into the project's .periplus/packs as own@0.0.1: its receiver conditions and
    identity.property_receiver give the same three calls edges a bundled pack gives (property 5)."""
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


def test_a_receiver_rule_in_a_grammar_with_no_property_receiver_is_refused(tmp_path: Path) -> None:
    """The same copy with identity.property_receiver taken out of its manifest: the map is refused
    with exit 26, naming the rule and the missing manifest key."""
    pack = tmp_path / ".periplus" / "packs" / "own@0.0.1"
    shutil.copytree(Path(periplus.__file__).parent / "packs" / "php_basic@0.2.0", pack)
    yaml = YAML()
    manifest = yaml.load((pack / "pack.yaml").read_text())
    manifest["pack"], manifest["version"] = "own", "0.0.1"
    del manifest["identity"]["property_receiver"]
    with (pack / "pack.yaml").open("w") as handle:
        yaml.dump(manifest, handle)
    (tmp_path / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks: [own@0.0.1]\n"
    )
    (tmp_path / "src" / "Web").mkdir(parents=True)
    (tmp_path / "src" / "Web" / "Page.php").write_text(PAGE)
    report = run(
        start=tmp_path,
        env={"PERIPLUS_CONFIG_DIR": str(tmp_path / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert [(p.code, p.detail) for p in report.problems] == [
        (26, {"pack": "own", "rule": "calls_property_method"})
    ], report.problems
    assert "declares no identity.property_receiver" in report.problems[0].message
