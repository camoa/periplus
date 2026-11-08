"""A component's own twig gives edges from the component node that mirror the template kinds."""

import json
from pathlib import Path

import pytest

from periplus.cli import main

CALLS = """\
{{ drupal_block('system_branding_block') }}
{{ drupal_menu('main') }}
{{ drupal_entity('node', 1) }}
{{ drupal_entity_form('node', 1) }}
{{ drupal_field('field_body', 'node', 1) }}
{% include 'partial.html.twig' %}
{% include 'm:other' %}
<a href="{{ path('entity.node.canonical', {'node': 1}) }}">read</a>
<a href="/node/add/page">add</a>
"""

FILES = {
    ".periplus/settings.yml": (
        "periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n"
        "  - twig_tweak_basic@0.0.1\n  - js_basic@0.0.1\n  - drupal_js_basic@0.0.1\n"
    ),
    "m.info.yml": "name: M\ntype: module\ncore_version_requirement: ^10\n",
    "m.libraries.yml": "card:\n  js:\n    card.js: {}\n",
    "components/card/card.component.yml": "name: Card\n",
    "components/card/card.twig": CALLS + "{{ attach_library('m/card') }}\n",
    "components/other/other.component.yml": "name: Other\n",
    "components/other/other.twig": "<p>other</p>\n",
    "templates/card-page.html.twig": CALLS,
}


def _map_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict:
    for rel, text in FILES.items():
        if not rel.startswith(".periplus"):
            rel = f"web/modules/custom/m/{rel}"
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    monkeypatch.chdir(tmp_path)
    assert main(["map"]) == 0
    return json.loads((tmp_path / ".periplus" / "map.json").read_text())


MIRROR = {
    "renders_block": "component_renders_block",
    "renders_menu": "component_renders_menu",
    "renders_entity_type": "component_renders_entity_type",
    "renders_entity_form": "component_renders_entity_form",
    "renders_field": "component_renders_field",
    "template_includes": "component_includes_template",
    "template_includes_component": "component_includes_component",
    "template_links_route": "component_links_route",
    "links_to_path": "component_links_path",
}


@pytest.mark.criterion(id="wo1")
def test_component_twig_gives_mirror_kind_edges_from_the_component_node_wo1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mapped = _map_module(tmp_path, monkeypatch)
    edges = mapped["edges"]

    def own(node: str) -> set[tuple[str, str]]:
        return {(e["kind"], e["to"]) for e in edges if e["from"] == node}

    template_edges = {(k, t) for k, t in own("drupal.template::card-page") if k in MIRROR}
    component_edges = own("drupal.component::card")

    assert {kind for kind, _ in template_edges} == set(MIRROR)
    assert {(MIRROR[k], t) for k, t in template_edges} <= component_edges
    assert "drupal.template::card" not in {n["id"] for n in mapped["nodes"]}
    attach = [
        e for e in edges
        if e["kind"] == "component_attaches_library" and e["from"] == "drupal.component::card"
    ]
    assert len(attach) == 1
