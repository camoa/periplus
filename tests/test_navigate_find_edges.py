"""``periplus find``: edges found by their description, their kind's meaning or their code line."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from _find_site import DESCRIBED, FORM, LOGIN, RECORD, SUBMIT, site
from jsonschema import Draft202012Validator

from periplus.cli import main
from periplus.navigate import find, fingerprint, undescribed

SCHEMA = Path(__file__).parents[1] / "src/periplus/contract/schema/navigation.schema.json"


def _edges(report: find.FindReport) -> list[tuple[str, str, str, str]]:
    return [(e.kind, e.source, e.target, e.matched) for e in report.edges]


def test_an_edge_is_found_by_its_description(tmp_path: Path) -> None:
    report = find.run(tmp_path, {}, "lockout", (), 0, site(tmp_path))

    assert _edges(report) == [("calls", SUBMIT, RECORD, "description")]
    lines = find.render_text(report).splitlines()
    assert lines[0] == "periplus find: 0 things, 1 edge"
    assert lines[lines.index("edges:") + 1 :] == [
        "  calls  submit -> record  shop/Login.php:9  [description]",
        "      | $this->audit->record($name);",
        "      # Records the failed attempt for the lockout count.",
    ]


def test_several_words_must_each_be_in_the_edge_description(tmp_path: Path) -> None:
    path = site(tmp_path)

    assert _edges(find.run(tmp_path, {}, "lockout failed", (), 0, path)) != []
    assert _edges(find.run(tmp_path, {}, "lockout nowhere", (), 0, path)) == []
    assert _edges(find.run(tmp_path, {}, "lockout nowhere", (), 0, path, any_word=True)) != []


def test_a_kind_meaning_matches_only_with_kinds_or_when_no_thing_matches(tmp_path: Path) -> None:
    path = site(tmp_path)

    # "audit" names things, so the meaning of calls is not searched unless asked. Its code
    # lines hold "audit" too, so the code is not searched here.
    assert _edges(find.run(tmp_path, {}, "audit", (), 0, path, source=False)) == []
    assert _edges(find.run(tmp_path, {}, "audit", (), 0, path, kinds=True, source=False)) == [
        ("calls", SUBMIT, RECORD, "kind"),
        ("calls", FORM, RECORD, "kind"),
    ]
    # "belongs" names nothing, so the kinds are searched.
    assert [e[:3] for e in _edges(find.run(tmp_path, {}, "belongs", (), 0, path))] == [
        ("in_module", "cls::Audit", "mod::shop"),
        ("in_module", LOGIN, "mod::shop"),
    ]


def test_a_code_line_matches_an_edge_unless_source_is_off(tmp_path: Path) -> None:
    path = site(tmp_path)

    assert _edges(find.run(tmp_path, {}, "blocked_admin", (), 0, path, source=False)) == []
    report = find.run(tmp_path, {}, "blocked_admin", (), 0, path)
    assert _edges(report) == [("calls", FORM, RECORD, "source")]
    text = find.render_text(report).splitlines()
    assert text[text.index("edges:") + 1 :] == [
        "  calls  form -> record  shop/Login.php:23  [source]",
        "      | $this->audit->record('blocked_admin');",
    ]


def test_no_edges_leaves_the_edges_out(tmp_path: Path) -> None:
    report = find.run(tmp_path, {}, "lockout", (), 0, site(tmp_path), edges=False)

    assert report.edges == ()
    assert "no matches" in find.render_text(report)


def test_an_edge_is_kept_when_an_end_passes_the_narrowing(tmp_path: Path) -> None:
    path = site(tmp_path)

    assert _edges(find.run(tmp_path, {}, "lockout", ("t.method",), 0, path)) != []
    assert _edges(find.run(tmp_path, {}, "lockout", ("t.call",), 0, path)) == []
    assert _edges(find.run(tmp_path, {}, "lockout", (), 0, path, paths=["tests/"])) == []


def test_over_the_budget_edges_fold_into_counts_by_kind(tmp_path: Path) -> None:
    path = site(tmp_path)
    whole = find.render_text(find.run(tmp_path, {}, "belongs", (), 0, path))

    text = find.render_text(find.run(tmp_path, {}, "belongs", (), len(whole) - 1, path))

    assert "  in_module  " not in text
    assert "edges, not listed: 2" in text
    assert "  by kind: in_module 2" in text


def test_json_carries_the_edges_and_matches_the_schema(tmp_path: Path) -> None:
    report = find.run(tmp_path, {}, "lockout", (), 0, site(tmp_path))
    document = json.loads(find.render_json(report))

    assert document["edges"] == [
        {
            "kind": "calls",
            "from": SUBMIT,
            "to": RECORD,
            "location": "shop/Login.php:9",
            "source": "$this->audit->record($name);",
            "matched": "description",
            "description": "Records the failed attempt for the lockout count.",
        }
    ]
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    find_schema = {**schema, "$ref": "#/$defs/find"}
    find_schema.pop("anyOf")
    assert list(Draft202012Validator(find_schema).iter_errors(document)) == []


def test_ids_print_the_ends_of_matched_edges_after_the_things_each_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    path = site(tmp_path)
    monkeypatch.chdir(tmp_path)

    assert main(["find", "audit", "--kinds", "--ids", "--map", str(path)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "cls::Audit",
        RECORD,
        "call::Audit::record::write",
        SUBMIT,
        FORM,
    ]


def test_stamp_stale_and_undescribed_skip_edge_entries(tmp_path: Path) -> None:
    path = site(tmp_path)

    counted = undescribed.run(tmp_path, {}, [], "file", path)
    assert (counted.problems, counted.described) == ((), 2)
    stamped = fingerprint.stamp(tmp_path, {}, False, path)
    assert stamped.problems == ()
    written = (tmp_path / "descriptions.yaml").read_text(encoding="utf-8")
    assert written.endswith(DESCRIBED[DESCRIBED.index("edges:") :])
    assert fingerprint.stale(tmp_path, {}, path).problems == ()
