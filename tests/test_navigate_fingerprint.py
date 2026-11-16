"""``periplus stamp`` and ``periplus stale``: a fingerprint of the code each entry describes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from _navigate import _document, _edge, _node
from jsonschema import Draft202012Validator

from periplus.cli import main
from periplus.navigate import fingerprint, show

SCHEMA = Path(__file__).parents[1] / "src/periplus/contract/schema/navigation.schema.json"

SOURCE = """\
<?php

class C {
  function run($x) {
    go();
  }

  function go() {
    return 1;
  }
}
"""
NODES = [
    _node("mod::m", "t.module", line=1, file="m/m.info"),
    _node("cls::C", "t.class", line=3, file="m/C.php"),
    _node("meth::C::run", "t.method", line=4, file="m/C.php"),
    _node("par::C::run::$x", "t.param", line=4, file="m/C.php"),
    _node("call::C::run::go", "t.call", line=5, file="m/C.php"),
    _node("meth::C::go", "t.method", line=8, file="./m/C.php"),
    _node("fn::far", "t.function", "boundary", line=6, file="m/C.php"),
]
DESCRIBED = """\
# Written by hand; this comment stays.
nodes:
  meth::C::run:
    text: Runs the
      cart.
    file: m/C.php
    line: 4
  "meth::C::go":
    file: m/C.php
    line: 8   # where it starts
    text: Returns one.
  gone::x:
    text: Gone.
    file: m/old.php
    line: 1
edges:
- from: meth::C::run
  kind: calls
  to: meth::C::go
  text: Calls go.
  file: m/C.php
  line: 5
"""


def _hash(*lines: str) -> str:
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest()[:16]


RUN = _hash("  function run($x) {", "    go();", "  }")
GO = _hash("  function go() {", "    return 1;", "  }", "}")


def _project(root: Path, described: str = DESCRIBED) -> Path:
    (root / ".periplus").mkdir()
    (root / "m").mkdir()
    (root / "m/C.php").write_text(SOURCE, encoding="utf-8")
    document = _document(
        NODES[::-1],
        [_edge("class_in_module", "cls::C", "mod::m", 3)],
        grouping_kinds=["class_in_module"],
    )
    path = root / ".periplus/map.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    (root / ".periplus/descriptions.yaml").write_bytes(described.encode("utf-8"))
    return path


def _described(root: Path) -> str:
    return (root / ".periplus/descriptions.yaml").read_bytes().decode("utf-8")


def _valid(text: str) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(json.loads(text))) == []


def test_stamp_adds_one_line_per_entry_and_changes_no_other_byte(tmp_path: Path) -> None:
    report = fingerprint.stamp(tmp_path, {}, False, _project(tmp_path))

    at_go = "    line: 8   # where it starts\n"
    expected = DESCRIBED.replace("    line: 4\n", f"    line: 4\n    fingerprint: '{RUN}'\n")
    expected = expected.replace(at_go, f"{at_go}    fingerprint: '{GO}'\n")
    assert _described(tmp_path) == expected
    assert (report.stamped, report.kept, report.skipped) == (2, 0, (("gone::x", "not in the map"),))


def test_the_span_ends_before_the_next_mapped_thing_it_does_not_hold(tmp_path: Path) -> None:
    fingerprint.stamp(tmp_path, {}, False, _project(tmp_path))

    # run holds the call on line 5; the boundary node on line 6 is not mapped; go starts line 8.
    assert f"fingerprint: '{RUN}'" in _described(tmp_path)


def test_a_stamped_file_still_matches_the_schema_and_keeps_its_line_endings(
    tmp_path: Path,
) -> None:
    path = _project(tmp_path, DESCRIBED.replace("\n", "\r\n"))

    fingerprint.stamp(tmp_path, {}, False, path)

    assert f"    fingerprint: '{RUN}'\r\n" in _described(tmp_path)
    assert "\n" not in _described(tmp_path).replace("\r\n", "")
    assert show.read_descriptions(tmp_path, path)[2] == ()


def test_stamp_keeps_a_fingerprint_unless_all(tmp_path: Path) -> None:
    old = DESCRIBED.replace("    line: 4\n", "    line: 4\n    fingerprint: '0000000000000000'\n")
    path = _project(tmp_path, old)

    kept = fingerprint.stamp(tmp_path, {}, False, path)
    assert (kept.stamped, kept.kept) == (1, 1)
    assert "fingerprint: '0000000000000000'" in _described(tmp_path)

    fingerprint.stamp(tmp_path, {}, True, path)
    assert f"    fingerprint: '{RUN}'\n" in _described(tmp_path)
    assert "0000000000000000" not in _described(tmp_path)


def test_the_fingerprint_line_takes_the_indent_of_the_entry_keys(tmp_path: Path) -> None:
    wide = (
        "nodes:\n    meth::C::go:\n        text: Returns one.\n        file: m/C.php\n"
        "        line: 8\n"
    )
    fingerprint.stamp(tmp_path, {}, False, _project(tmp_path, wide))

    assert _described(tmp_path) == wide + f"        fingerprint: '{GO}'\n"


def test_nothing_is_written_when_other_text_would_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _project(tmp_path)
    placed = fingerprint._stamp_one

    def careless(*args: object) -> str | None:
        lines = args[3]
        assert isinstance(lines, list)
        lines[0] = "# Rewritten.\nextra: 1\n"
        return placed(*args)  # type: ignore[arg-type]

    monkeypatch.setattr(fingerprint, "_stamp_one", careless)
    report = fingerprint.stamp(tmp_path, {}, False, path)

    assert report.exit_code == 30
    assert _described(tmp_path) == DESCRIBED


def test_a_fingerprint_of_digits_alone_stays_a_string(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = _project(tmp_path)
    monkeypatch.setattr(fingerprint, "_fingerprint", lambda *args: "1234567890123456")

    assert fingerprint.stamp(tmp_path, {}, False, path).stamped == 2
    entries = show.read_descriptions(tmp_path, path)[1]["nodes"]
    assert entries["meth::C::go"]["fingerprint"] == "1234567890123456"


def test_stamp_skips_an_entry_written_inline(tmp_path: Path) -> None:
    inline = "nodes:\n  meth::C::go: {text: Returns one., file: m/C.php, line: 8}\n"
    report = fingerprint.stamp(tmp_path, {}, False, _project(tmp_path, inline))

    assert report.skipped == (("meth::C::go", "written inline"),)
    assert _described(tmp_path) == inline


def test_stale_lists_changed_code_and_gone_nodes(tmp_path: Path) -> None:
    path = _project(tmp_path)
    fingerprint.stamp(tmp_path, {}, False, path)
    (tmp_path / "m/C.php").write_text(SOURCE.replace("return 1;", "return 2;"), encoding="utf-8")

    report = fingerprint.stale(tmp_path, {}, path)

    assert fingerprint.render_stale_text(report).splitlines() == [
        "periplus stale",
        "3 node entries: 1 fresh, 1 changed, 1 gone, 0 unreadable, 0 not stamped",
        "changed:",
        "  C::go  t.method  mapped  ./m/C.php:8",
        "gone:",
        "  gone::x",
    ]
    assert fingerprint.listed(report) == ("meth::C::go", "gone::x")


def test_blank_lines_after_a_thing_do_not_make_it_stale(tmp_path: Path) -> None:
    path = _project(tmp_path)
    fingerprint.stamp(tmp_path, {}, False, path)
    (tmp_path / "m/C.php").write_text(SOURCE.replace("  }\n\n", "  }\n   \n"), encoding="utf-8")

    assert fingerprint.stale(tmp_path, {}, path).changed == ()


def test_stale_counts_entries_with_no_fingerprint(tmp_path: Path) -> None:
    report = fingerprint.stale(tmp_path, {}, _project(tmp_path))

    assert (report.unstamped, report.changed, report.gone) == (2, (), ("gone::x",))


def test_stale_json_and_stamp_json_match_the_schema(tmp_path: Path) -> None:
    path = _project(tmp_path)

    _valid(fingerprint.render_stamp_json(fingerprint.stamp(tmp_path, {}, False, path)))
    _valid(fingerprint.render_stale_json(fingerprint.stale(tmp_path, {}, path)))


def test_the_map_is_not_read_for_descriptions_and_a_file_without_one_is_fine(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = _project(tmp_path)
    (tmp_path / ".periplus/descriptions.yaml").unlink()

    assert main(["stale", "--map", str(path)]) == 0
    assert main(["stamp", "--map", str(path)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "periplus stale",
        "no descriptions file",
        "periplus stamp",
        "no descriptions file",
    ]
