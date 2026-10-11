"""A template links to the templates it includes, extends, embeds or imports, and to components."""

from __future__ import annotations

import json
from pathlib import Path

from periplus.map import run
from periplus.preflight import check_runtime_dependencies

THEME = Path("web/themes/custom/mytheme")
TEMPLATES = {
    "page.html.twig": (
        "{% extends '@mytheme/base.html.twig' %}\n"
        "{% include 'header.html.twig' %}\n"
        "{{ include('@mytheme/partials/footer.html.twig') }}\n"
        "{% embed 'card.html.twig' %}{% endembed %}\n"
        "{% import 'macros.html.twig' as m %}\n"
        "{% include 'mytheme:button' %}\n"
        "{{ include('mytheme:alert') }}\n"
        "{% include 'missing.html.twig' %}\n"
        "{# {% include 'commented.html.twig' %} #}\n"
    ),
    "base.html.twig": "<html></html>\n",
    "header.html.twig": "<header></header>\n",
    "footer.html.twig": "<footer></footer>\n",
    "card.html.twig": "<div></div>\n",
    "macros.html.twig": "{% macro x() %}{% endmacro %}\n",
    "commented.html.twig": "<p></p>\n",
}


def _plant(root: Path) -> None:
    theme = root / THEME
    (theme / "templates").mkdir(parents=True)
    (theme / "components" / "button").mkdir(parents=True)
    (root / ".periplus").mkdir()
    (root / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n"
    )
    (theme / "mytheme.info.yml").write_text("name: My theme\ntype: theme\nbase theme: false\n")
    for name, text in TEMPLATES.items():
        (theme / "templates" / name).write_text(text)
    (theme / "components" / "button" / "button.component.yml").write_text("name: Button\n")


def _map(root: Path) -> dict[str, list[dict[str, object]]]:
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == (), report.problems
    assert report.map_path is not None
    document: dict[str, list[dict[str, object]]] = json.loads(Path(report.map_path).read_text())
    return document


def test_a_template_links_to_each_template_and_component_it_names(tmp_path: Path) -> None:
    _plant(tmp_path)
    document = _map(tmp_path)
    nodes = {str(n["id"]): n["state"] for n in document["nodes"]}
    edges = sorted(
        (str(e["kind"]), str(e["to"]))
        for e in document["edges"]
        if e["from"] == "drupal.template::page" and str(e["kind"]).startswith("template_includes")
    )
    assert edges == [
        ("template_includes", "drupal.template::base"),
        ("template_includes", "drupal.template::card"),
        ("template_includes", "drupal.template::footer"),
        ("template_includes", "drupal.template::header"),
        ("template_includes", "drupal.template::macros"),
        ("template_includes", "drupal.template::missing"),
        ("template_includes_component", "drupal.component::alert"),
        ("template_includes_component", "drupal.component::button"),
    ]
    assert nodes["drupal.template::base"] == "mapped"
    assert nodes["drupal.component::button"] == "mapped"
    assert nodes["drupal.template::missing"] == "referenced"
    assert nodes["drupal.component::alert"] == "referenced"
    assert "commented" not in {t.rsplit("::", 1)[-1] for k, t in edges}
