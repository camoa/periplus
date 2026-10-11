"""A form class links to the form id its getFormId returns, and configuration that names a form id
links to the same node, so the configuration reaches the class in two steps."""

from __future__ import annotations

import json
from pathlib import Path

from periplus.map import run
from periplus.preflight import check_runtime_dependencies

MODULE = Path("web/modules/custom/mymodule")

FORM = """\
<?php

namespace Drupal\\mymodule\\Form;

use Drupal\\Core\\Form\\FormBase;

final class MyForm extends FormBase {

  public function getFormId() {
    return 'my_form';
  }

  public function buildForm(array $form, $form_state) {
    return $form;
  }

}
"""

CAPTCHA_POINT = "langcode: en\nstatus: true\nformId: my_form\ncaptchaType: default\n"

HONEYPOT = """\
protect_all_forms: false
unprotected_forms:
  - user_login_form
form_settings:
  my_form: true
  contact_message_feedback_form: false
"""


def _plant(root: Path) -> None:
    module = root / MODULE
    (module / "src" / "Form").mkdir(parents=True)
    sync = root / "config" / "sync"
    sync.mkdir(parents=True)
    (root / ".periplus").mkdir()
    (root / ".periplus" / "settings.yml").write_text(
        "periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n"
    )
    (module / "mymodule.info.yml").write_text(
        "name: My module\ntype: module\ncore_version_requirement: ^10\n"
    )
    (module / "src" / "Form" / "MyForm.php").write_text(FORM)
    (sync / "captcha.captcha_point.my_form.yml").write_text(CAPTCHA_POINT)
    (sync / "honeypot.settings.yml").write_text(HONEYPOT)


def _map(root: Path) -> dict[str, list[dict[str, object]]]:
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "periplus-config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    assert report.problems == (), report.problems
    assert report.map_path is not None
    return json.loads(Path(report.map_path).read_text())  # type: ignore[no-any-return]


def _edges(document: dict[str, list[dict[str, object]]], kind: str) -> set[tuple[str, str]]:
    return {(str(e["from"]), str(e["to"])) for e in document["edges"] if e["kind"] == kind}


def test_a_form_class_links_to_the_form_id_its_get_form_id_returns(tmp_path: Path) -> None:
    _plant(tmp_path)
    document = _map(tmp_path)
    nodes = {str(n["id"]): n["state"] for n in document["nodes"]}
    assert nodes["drupal.form_id::my_form"] == "mapped"
    assert _edges(document, "form_has_id") == {
        ("php.type::Drupal\\mymodule\\Form\\MyForm", "drupal.form_id::my_form"),
    }


def test_configuration_that_names_a_form_id_links_to_that_form_id(tmp_path: Path) -> None:
    _plant(tmp_path)
    document = _map(tmp_path)
    assert _edges(document, "config_names_form") == {
        ("drupal.config::captcha.captcha_point.my_form", "drupal.form_id::my_form"),
        ("drupal.config::honeypot.settings", "drupal.form_id::user_login_form"),
        ("drupal.config::honeypot.settings", "drupal.form_id::my_form"),
        ("drupal.config::honeypot.settings", "drupal.form_id::contact_message_feedback_form"),
    }
    nodes = {str(n["id"]): n["state"] for n in document["nodes"]}
    assert nodes["drupal.form_id::user_login_form"] == "referenced"


def test_a_captcha_point_reaches_the_form_class_in_two_steps(tmp_path: Path) -> None:
    _plant(tmp_path)
    document = _map(tmp_path)
    named = {
        to
        for frm, to in _edges(document, "config_names_form")
        if frm == "drupal.config::captcha.captcha_point.my_form"
    }
    classes = {frm for frm, to in _edges(document, "form_has_id") if to in named}
    assert classes == {"php.type::Drupal\\mymodule\\Form\\MyForm"}
