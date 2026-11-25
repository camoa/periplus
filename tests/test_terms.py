"""Terms: the ``terms`` section of the descriptions file, what ``find`` and ``stale`` do with it,
and a top-level key this version does not know."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from _find_site import DESCRIBED, site
from jsonschema import Draft202012Validator

from periplus.cli import main
from periplus.navigate import find, fingerprint

SCHEMA = Path(__file__).parents[1] / "src/periplus/contract/schema/navigation.schema.json"

TERMS = """\
terms:
  sign-in:
    text: A person proving who they are with a password.
    words: [sign in, account]
    old: [logon]
    ids: [cls::Login]
    origin: person
  audit-trail:
    text: The record of every attempt to sign in.
    words: [audit trail, account]
    ids: ['meth::Audit::record', 'fn::gone']
  invoice:
    text: A request for payment.
    words: [invoice]
    old: [bill]
    ids: [cls::Audit]
"""

# What the code on main printed for these two searches over the same tree, before terms.
BEFORE_LOGIN = """\
periplus find: 9 things (4 main, 3 parts, 1 in supporting code, 1 not mapped or with no location), 0 edges
main by type: t.method 3, t.class 1
not main by type: t.call 2, t.class 1, t.function 1, t.param 1

cls::Login  t.class  mapped  shop/Login.php:3
meth::Login::form  t.method  mapped  shop/Login.php:20
meth::Login::submit  t.method  mapped  shop/Login.php:5
      # Checks the password; blocks the account after five failures.
meth::Audit::record  t.method  mapped  shop/Audit.php:3  [description]
      # Writes a login attempt to the log.
not main:
call::Login::form::render  t.call  mapped  shop/Login.php:22
call::Login::submit::lock  t.call  mapped  shop/Login.php:8
par::Login::submit::$name  t.param  mapped  shop/Login.php:5
fn::login_check  t.function  unresolved  no location
cls::LoginTest  t.class  mapped  tests/LoginTest.php:1  [supporting code]
"""  # noqa: E501
BEFORE_ACCOUNT = """\
periplus find: 1 thing (1 main), 0 edges
main by type: t.method 1

meth::Login::submit  t.method  mapped  shop/Login.php:5  [description]
      # Checks the password; blocks the account after five failures.
"""
BEFORE_ACCOUNT_JSON = """\
{
  "by_type": {
    "t.method": 1
  },
  "edges": [],
  "items": [
    {
      "description": "Checks the password; blocks the account after five failures.",
      "group": "main",
      "id": "meth::Login::submit",
      "location": "shop/Login.php:5",
      "marks": [],
      "matched": "description",
      "matched_attribute": null,
      "source": "",
      "state": "mapped",
      "supporting": false,
      "type": "t.method"
    }
  ],
  "problems": [],
  "shown": 1,
  "total": 1,
  "truncated": false,
  "warnings": []
}
"""


def _find(root: Path, text: str, described: str = DESCRIBED + TERMS) -> find.FindReport:
    path = root / "map.json"
    return find.run(root, {}, text, (), 0, path if path.exists() else site(root, described))


def _valid(document: object) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(document)) == []


@pytest.mark.parametrize(("text", "before"), [("login", BEFORE_LOGIN), ("account", BEFORE_ACCOUNT)])
def test_no_terms_section_prints_what_main_printed(tmp_path: Path, text: str, before: str) -> None:
    report = find.run(tmp_path, {}, text, (), find.BUDGET, site(tmp_path))

    assert find.render_text(report) == before


def test_no_terms_section_prints_the_json_main_printed(tmp_path: Path) -> None:
    report = find.run(tmp_path, {}, "account", (), find.BUDGET, site(tmp_path))

    assert find.render_json(report) == BEFORE_ACCOUNT_JSON


def test_a_term_word_matches_whole_words_only(tmp_path: Path) -> None:
    inside = _find(tmp_path, "billing")
    whole = _find(tmp_path, "BILL")

    assert (inside.terms, [row.id for row in inside.matches.items]) == ((), [])
    assert [term.name for term in whole.terms] == ["invoice"]
    assert [row.id for row in whole.matches.items] == ["cls::Audit"]


def test_a_phrase_matches_when_the_words_hold_it_in_order(tmp_path: Path) -> None:
    said = _find(tmp_path, "who can sign in")
    apart = _find(tmp_path, "sign who in")

    assert [term.name for term in said.terms] == ["sign-in"]
    assert apart.terms == ()


def test_a_word_in_two_entries_prints_both_meanings(tmp_path: Path) -> None:
    text = find.render_text(_find(tmp_path, "account"))

    assert "'account' has 2 meanings: audit-trail, sign-in\n" in text
    assert "  audit-trail: The record of every attempt to sign in.\n" in text
    assert "  sign-in: A person proving who they are with a password.\n" in text


def test_an_old_name_and_its_origin_are_named(tmp_path: Path) -> None:
    text = find.render_text(_find(tmp_path, "logon"))

    assert "    old name: logon; origin: person; ids: cls::Login\n" in text


def test_the_things_of_a_term_join_the_results_marked(tmp_path: Path) -> None:
    report = _find(tmp_path, "sign in")
    rows = {row.id: row for row in report.matches.items}

    assert rows["cls::Login"].matched == "term"
    assert "cls::Login  t.class  mapped  shop/Login.php:3  [term sign-in]\n" in find.render_text(
        report
    )
    assert "cls::Login" in find.listed(report)


def test_a_thing_found_by_its_words_is_marked_with_its_term_too(tmp_path: Path) -> None:
    report = _find(tmp_path, "account")
    rows = {row.id: row for row in report.matches.items}

    # submit matched by its description; record joined by the term audit-trail.
    assert (rows["meth::Login::submit"].matched, rows["meth::Audit::record"].matched) == (
        "description",
        "term",
    )
    assert list(rows) == ["meth::Login::submit", "cls::Login", "meth::Audit::record"]
    assert "meth::Audit::record  t.method  mapped  shop/Audit.php:3  [term audit-trail]\n" in (
        find.render_text(report)
    )


def test_the_json_lists_the_terms_and_matches_the_schema(tmp_path: Path) -> None:
    document = json.loads(find.render_json(_find(tmp_path, "account")))

    _valid(document)
    assert [(t["name"], t["matched_words"]) for t in document["terms"]] == [
        ("audit-trail", ["account"]),
        ("sign-in", ["account"]),
    ]
    assert document["terms"][1]["origin"] == "person"


def test_an_unknown_top_level_key_warns_once_and_the_rest_still_loads(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    report = _find(tmp_path, "account", DESCRIBED + TERMS + "later:\n  anything: [1]\n")

    assert report.problems == ()
    assert [term.name for term in report.terms] == ["audit-trail", "sign-in"]
    assert "meth::Login::submit" in [row.id for row in report.matches.items]
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert "'later'" in err


@pytest.mark.parametrize("command", ["find account", "show cls::Login", "undescribed", "stale"])
def test_every_reader_of_the_file_warns_and_succeeds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], command: str
) -> None:
    path = site(tmp_path, DESCRIBED + "later: 1\n")

    code = main([*command.split(), "--map", str(path)])

    assert code == 0
    assert capsys.readouterr().err.count("'later'") == 1


STAMPED = """\
<?php

class C {
  function run() {
    return 1;
  }
}
"""


def _stamp_project(root: Path, described: str) -> Path:
    from _navigate import _document, _node

    (root / ".periplus").mkdir()
    (root / "m").mkdir()
    (root / "m/C.php").write_text(STAMPED, encoding="utf-8")
    document = _document(
        [
            _node("cls::C", "t.class", line=3, file="m/C.php"),
            _node("meth::C::run", "t.method", line=4, file="m/C.php"),
        ],
        [],
    )
    path = root / ".periplus/map.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    (root / ".periplus/descriptions.yaml").write_text(described, encoding="utf-8")
    return path


NODE_ENTRY = """\
nodes:
  meth::C::run:
    text: Returns one.
    file: m/C.php
    line: 4
"""
STAMP_TERMS = """\
terms:
  cart:  # what people call the class
    text: The basket a shopper fills.
    words: [cart, basket]
    ids: [cls::C, 'cls::Gone', meth::C::run]
later: kept
"""


def test_stamp_keeps_the_terms_section_and_unknown_keys(tmp_path: Path) -> None:
    path = _stamp_project(tmp_path, NODE_ENTRY + STAMP_TERMS)

    report = fingerprint.stamp(tmp_path, {}, False, path)

    assert (report.stamped, report.problems) == (1, ())
    written = (tmp_path / ".periplus/descriptions.yaml").read_text(encoding="utf-8")
    assert written.startswith(NODE_ENTRY + "    fingerprint: '")
    assert written.endswith("'\n" + STAMP_TERMS)


def test_stale_names_a_term_whose_id_is_gone(tmp_path: Path) -> None:
    path = _stamp_project(tmp_path, NODE_ENTRY + STAMP_TERMS)

    report = fingerprint.stale(tmp_path, {}, path)

    assert report.terms_gone == (("cart", "cls::Gone"),)
    text = fingerprint.render_stale_text(report)
    assert "terms with gone ids:\n  cart  cls::Gone\n" in text
    document = json.loads(fingerprint.render_stale_json(report))
    _valid(document)
    assert document["terms_gone"] == [{"term": "cart", "id": "cls::Gone"}]
    assert fingerprint.listed(report)[-1] == "cls::Gone"


def test_joined_things_are_narrowed_by_type_and_path(tmp_path: Path) -> None:
    path = site(tmp_path, DESCRIBED + TERMS)

    def ids(types: tuple[str, ...], paths: tuple[str, ...] = ()) -> list[str]:
        report = find.run(tmp_path, {}, "sign in", types, 0, path, paths)
        return [row.id for row in report.matches.items]

    assert ids(("t.class",)) == ["cls::Login"]
    assert ids(("t.method",)) == []
    assert ids((), ("shop/Login",)) == ["cls::Login"]
    assert ids((), ("tests",)) == []


def test_matched_words_are_written_as_the_file_writes_them(tmp_path: Path) -> None:
    terms = (
        "terms:\n  sign-in:\n    text: Signing in.\n    words: [Sign In]\n    ids: [cls::Login]\n"
    )

    document = json.loads(find.render_json(_find(tmp_path, "SIGN in", DESCRIBED + terms)))

    assert document["terms"][0]["matched_words"] == ["Sign In"]


AUDIT_TERM = """\
terms:
  audit:
    text: The record of what people did.
    words: [audit]
    ids: [cls::Audit, cls::Audit]
"""


def test_a_row_found_by_its_words_carries_its_term_in_text_and_json(tmp_path: Path) -> None:
    report = _find(tmp_path, "audit", DESCRIBED + AUDIT_TERM)
    rows = {row.id: row for row in report.matches.items}

    assert rows["cls::Audit"].matched == "id"
    assert "cls::Audit  t.class  mapped  shop/Audit.php:1  [term audit]\n" in find.render_text(
        report
    )
    document = json.loads(find.render_json(report))
    _valid(document)
    items = {item["id"]: item for item in document["items"]}
    assert items["cls::Audit"]["terms"] == ["audit"]
    assert "terms" not in items["meth::Audit::record"]


def test_an_id_listed_twice_in_one_term_prints_once(tmp_path: Path) -> None:
    text = find.render_text(_find(tmp_path, "audit", DESCRIBED + AUDIT_TERM))

    assert text.count("[term audit]") == 1
    assert "    word: audit; ids: cls::Audit\n" in text


def test_the_same_word_in_two_cases_is_one_word_with_two_meanings(tmp_path: Path) -> None:
    terms = (
        "terms:\n"
        "  a:\n    text: One.\n    words: [Account]\n    ids: [cls::Login]\n"
        "  b:\n    text: Two.\n    words: [account]\n    ids: [cls::Audit]\n"
    )

    text = find.render_text(_find(tmp_path, "account", DESCRIBED + terms))

    assert "  'account' has 2 meanings: a, b\n" in text


@pytest.mark.parametrize("word", ["'  '", "''"])
@pytest.mark.parametrize("key", ["words", "old"])
def test_a_word_with_no_letters_is_refused(tmp_path: Path, word: str, key: str) -> None:
    extra = "    words: [x]\n" if key == "old" else ""
    terms = f"terms:\n  t:\n    text: T.\n{extra}    {key}: [{word}]\n    ids: [cls::Login]\n"

    report = _find(tmp_path, "zzzqqq", DESCRIBED + terms)

    assert (report.terms, [p.code for p in report.problems]) == ((), [30])


def test_a_word_with_no_parts_never_matches() -> None:
    told = {"terms": {"t": {"text": "T.", "words": ["  "], "ids": ["cls::Login"]}}}

    assert find._terms(told, "zzzqqq") == ()


@pytest.mark.parametrize("name", ["42", "true"])
@pytest.mark.parametrize("command", ["find account", "stale"])
def test_a_term_name_that_is_not_text_is_refused_with_exit_30(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], name: str, command: str
) -> None:
    terms = f"terms:\n  {name}:\n    text: T.\n    words: [account]\n    ids: [cls::Gone]\n"
    path = site(tmp_path, DESCRIBED + terms)

    code = main([*command.split(), "--map", str(path)])

    out = capsys.readouterr().out
    assert code == 30
    assert "does not match the descriptions schema" in out
    assert "is not of type 'string'" in out


def test_stale_ids_print_a_gone_id_once(tmp_path: Path) -> None:
    terms = STAMP_TERMS.replace(
        "later: kept\n",
        "  trolley:\n    text: The cart.\n    words: [trolley]\n    ids: ['cls::Gone']\n",
    )
    path = _stamp_project(tmp_path, NODE_ENTRY + terms)

    report = fingerprint.stale(tmp_path, {}, path)

    assert report.terms_gone == (("cart", "cls::Gone"), ("trolley", "cls::Gone"))
    assert fingerprint.listed(report).count("cls::Gone") == 1
