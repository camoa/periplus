"""The two renderers: what they emit, what they escape, and what they must not vary with.

The determinism test here runs two operating-system processes. Two calls inside one pytest process
share one hash seed, one locale and one dict ordering by construction, so a byte-comparison of two
in-process renders cannot fail for the reason its name gives — a set iterated into the output
produces identical bytes both times and the test passes with the defect present.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from periplus.resolution import ResolutionReport

SRC = Path(__file__).resolve().parent.parent / "src"

# Three names whose code-point order differs from both case-folded order and locale order, created
# in reverse code-point order so filesystem order, sorted order and creation order are three
# different things. Code point: Zebra (0x5A), apple (0x61), Emile (0xC9). A `.lower()` key or a
# locale collation gives apple, Emile, Zebra. A fixture of a@1, b@1, c@1 distinguishes none of the
# three mechanisms, and it is the fixture that has produced three proxies in this project already.
HOSTILE_NAMES = ("Émile@1.0.0", "apple@1.0.0", "Zebra@1.0.0")

# The same three in code-point order, spelled as each form renders them. The two forms differ here
# deliberately: the text form is read by a person and prints the name the filesystem holds, while
# JSON is parsed by a consumer and escapes under `ensure_ascii` so a lone surrogate cannot break
# the encode.
# Where the candidate listing starts in each form, so the order assertion reads that section and
# not an earlier one that happens to mention the same name.
FIRST_CANDIDATE_MARK = {"text": "Candidates:", "json": '"candidates"'}

CODE_POINT_ORDER = {
    "text": ["Zebra@1.0.0", "apple@1.0.0", "Émile@1.0.0"],
    "json": ["Zebra@1.0.0", "apple@1.0.0", "\\u00c9mile@1.0.0"],
}

# Written in reverse alphabetical order, so that the renderer's own sort is observable rather than
# coincident with the file's order. The real worked example writes its folders alphabetically and
# cannot test this.
SETTINGS = """
periplus_version: 0
packs:
  - Zebra@1.0.0
folders:
  custom_theme: ./themes
  custom_module: ./modules
  config: ./config
re_include: []
accepted_unknowns:
  - id: x
    accepted_on: 2026-08-28
"""

_CHILD = """
import os, sys
from pathlib import Path

from periplus.preflight import DependencyStatus
from periplus.report import RENDERERS
from periplus.resolution import resolve

deps = (
    DependencyStatus(distribution="platformdirs", installed="4.11.5", present=True),
    DependencyStatus(distribution="ruamel.yaml", installed="0.19.1", present=True),
)
report = resolve(Path(sys.argv[1]), os.environ, deps)
sys.stdout.write(RENDERERS[sys.argv[2]](report))
"""


def _render_in_a_child(root: Path, config: Path, fmt: str, **overrides: str) -> str:
    """Render in a fresh interpreter, so hash seed and locale are this call's to choose."""
    env = {
        "PYTHONPATH": str(SRC),
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PERIPLUS_CONFIG_DIR": str(config),
        **overrides,
    }
    result = subprocess.run(  # noqa: S603 - list argv, shell unset, nothing interpolated
        [sys.executable, "-c", _CHILD, str(root), fmt],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, f"{result.stdout}{result.stderr}"
    return result.stdout


@pytest.fixture
def tree(tmp_path: Path) -> tuple[Path, Path]:
    """A project root with the hostile names under its own pack root, and an empty user config."""
    root = tmp_path / "project"
    packs = root / ".periplus" / "packs"
    packs.mkdir(parents=True)
    (root / ".periplus" / "settings.yml").write_text(SETTINGS, encoding="utf-8")
    for name in HOSTILE_NAMES:
        (packs / name).mkdir()
    config = tmp_path / "userconf"
    config.mkdir()
    return root, config


@pytest.mark.parametrize("fmt", ["text", "json"])
def test_two_processes_with_different_hash_seeds_and_locales_render_the_same_bytes(
    tree: tuple[Path, Path], fmt: str
) -> None:
    """Byte-identical across two hash seeds and across a third run under a different locale.

    Three mechanisms are killed by three properties of this fixture, and no two of them by one:

    * A **set** iterated into the output. Python randomises string hashing per process, so a set of
      strings lists in one order under one seed and another under the next. Nothing but two
      processes can observe this.

      The seeds are **0 and 2**, and which pair is used is part of the fixture rather than an
      arbitrary choice. Under 0 and 1 the three folder names in this file's settings — `config`,
      `custom_module`, `custom_theme` — happen to land in the same relative order in a set's table,
      so a set iterated in place of `sorted()` renders identical bytes under both and this test
      passes with the defect present. Verified: the same plant produces seven distinct outputs over
      ten seeds, and seed 2 is one that differs from 0. Two seeds are two samples, not a proof — a
      differently shaped fixture could need a different pair.
    * **Filesystem order.** Three entries under one root, created in reverse code-point order, so
      ``iterdir`` order, creation order and sorted order are three different sequences.
    * A **locale or case-folding sort key.** The three names order differently under code points
      than under ``.lower()`` or a collation, and the third run uses a locale that is installed on
      this machine rather than a hypothetical one.
    """
    root, config = tree
    first = _render_in_a_child(root, config, fmt, PYTHONHASHSEED="0", LC_ALL="C")
    second = _render_in_a_child(root, config, fmt, PYTHONHASHSEED="2", LC_ALL="C")
    third = _render_in_a_child(root, config, fmt, PYTHONHASHSEED="0", LC_ALL="es_ES.utf8")

    assert first == second
    assert first == third

    # And the order in the output is code-point order rather than creation order or a collation.
    #
    # Searched inside the candidate listing and not in the whole document, which is where the first
    # version of this assertion was a proxy: `Zebra@1.0.0` is also the `packs:` pin, printed in an
    # earlier section, so `first.index` found that occurrence and reported a stable position
    # whatever order the candidates came out in. A re-sort with a case-folding key passed.
    listing = first[first.index(FIRST_CANDIDATE_MARK[fmt]) :]
    positions = [listing.index(name) for name in CODE_POINT_ORDER[fmt]]
    assert positions == sorted(positions), listing


def _resolve(root: Path, config: Path) -> ResolutionReport:
    """Resolve in this process. Only the determinism test needs a child interpreter."""
    from periplus.preflight import DependencyStatus
    from periplus.resolution import resolve

    deps = (
        DependencyStatus(distribution="platformdirs", installed="4.11.5", present=True),
        DependencyStatus(distribution="ruamel.yaml", installed="0.19.1", present=True),
    )
    return resolve(root, {"PERIPLUS_CONFIG_DIR": str(config)}, deps)


def _section(rendered: str, heading: str) -> list[str]:
    """The rows of one section of the text form, without its heading or its blank separator."""
    lines = rendered.split("\n")
    start = lines.index(f"{heading}:") + 1
    end = start
    while end < len(lines) and lines[end].startswith("  "):
        end += 1
    return lines[start:end]


def test_a_date_in_accepted_unknowns_renders_as_json_rather_than_crashing_the_encoder(
    tree: tuple[Path, Path],
) -> None:
    """``render_json`` returns a document that parses, on a settings file that is entirely legal.

    An unquoted ``accepted_on: 2026-08-28`` loads as a ``datetime.date`` under ``typ='safe'``, and
    ``settings.py`` deliberately keeps it rather than deleting a legitimate entry to satisfy an
    annotation. ``dataclasses.asdict`` or a bare ``json.dumps`` raises ``TypeError`` here and
    nowhere else in this suite — the real worked example writes ``accepted_unknowns: []``, so no
    fixture derived from it can reach this.
    """
    from periplus.report import render_json

    root, config = tree
    document = json.loads(render_json(_resolve(root, config)))

    unknowns = document["settings"]["accepted_unknowns"]["value"]
    assert unknowns == [{"accepted_on": "2026-08-28", "id": "x"}]


def test_a_directory_name_holding_a_newline_cannot_forge_a_line(tmp_path: Path) -> None:
    """One row per candidate, whatever the candidates are named.

    A directory name on Linux is any byte sequence but ``/`` and NUL, and one holding a newline is
    creatable on this filesystem — verified rather than assumed. Escaping happens in this module and
    never in ``packs.py``, because escaping where the value is read makes the escaped form the value
    and lets a second renderer escape it again.

    The assertion is a line count and not one expected string. A count survives a change to the
    escape sequence; an expected string only asserts that today's escape is today's escape.
    """
    from periplus.report import render_json, render_text

    root = tmp_path / "project"
    packs = root / ".periplus" / "packs"
    packs.mkdir(parents=True)
    (root / ".periplus" / "settings.yml").write_text("packs: []\n", encoding="utf-8")
    config = tmp_path / "userconf"
    config.mkdir()
    for name in ("evil\npack@1.0.0", "esc\x1b[2K@1.0.0", "quiet@1.0.0"):
        (packs / name).mkdir()
    # A name that is not valid UTF-8 at all. `os.listdir` hands it back with surrogate escapes, and
    # a surrogate is what a UTF-8 stdout refuses to encode — so this is the fixture that makes both
    # the text escape and `ensure_ascii=True` load-bearing rather than defensive.
    # `os.mkdir` on raw bytes, not `Path.mkdir`: the name is deliberately not decodable, and
    # `Path` would have to hold it as a surrogate-escaped `str` to carry it here.
    os.mkdir(os.fsencode(packs) + b"/raw\xff@1.0.0")  # noqa: PTH102

    report = _resolve(root, config)
    text = render_text(report)
    rows = _section(text, "Candidates")

    bundled_dir = Path(__file__).parent.parent / "src" / "periplus" / "packs"
    bundled = [d for d in bundled_dir.iterdir() if d.is_dir()]
    assert len(report.candidates) == len(bundled) + 4, [c.entry for c in report.candidates]
    assert len(rows) == len(report.candidates), rows
    assert "evil\npack" not in text
    assert "evil\\npack@1.0.0" in text

    # No control character reaches the reader. An ESC is the one that matters: a directory named
    # `esc\x1b[2K@1.0.0` otherwise writes a raw ANSI erase-line into the report, which forges
    # output exactly as a newline forges a line. ESC and BEL encode cleanly to both ASCII and
    # UTF-8, so no codec's `backslashreplace` will ever touch them.
    assert not any(character < " " and character != "\n" for character in text), repr(text)
    assert "esc\\x1b[2K@1.0.0" in text

    # Neither form may raise on the way to a UTF-8 stream. Without the escape the text form carries
    # a lone surrogate; with `ensure_ascii=False` the JSON form does. Both raise here.
    assert text.encode("utf-8")
    assert render_json(report).encode("utf-8")
    assert json.loads(render_json(report))["candidates"]


def test_a_key_a_file_declared_empty_is_not_reported_as_a_key_nobody_declared(
    tree: tuple[Path, Path],
) -> None:
    """``re_include: []`` names the file that declared it; ``exclude``, absent, names nobody.

    Presence is what makes a file a source, which is ``settings.py``'s recorded rule. The two cases
    reach the record as different values — an empty tuple with a source, against ``None`` — and a
    renderer that printed both as "none" would erase the distinction the merge exists to keep.
    """
    from periplus.report import render_json, render_text

    root, config = tree
    report = _resolve(root, config)
    rows = _section(render_text(report), "Effective settings")

    declared = [row for row in rows if row.strip().startswith("re_include")]
    absent = [row for row in rows if row.strip().startswith("exclude")]
    assert len(declared) == 1 and "declared empty" in declared[0], rows
    assert str(root) in declared[0], declared
    assert len(absent) == 1 and "not declared" in absent[0], rows

    document = json.loads(render_json(report))
    assert document["settings"]["re_include"]["value"] == []
    assert document["settings"]["re_include"]["sources"] != []
    assert document["settings"]["exclude"] is None


def test_the_json_form_names_a_root_inside_a_candidate_rather_than_repeating_it(
    tree: tuple[Path, Path],
) -> None:
    """A candidate carries which root it came from, not a second copy of the whole root record.

    ``PackCandidate.root`` embeds a whole ``PackRoot``, so a mechanical walk emits every root once
    per candidate — eight copies on the run this fixture produces. It also emits
    ``PackRoot.traversable``, which is a ``Traversable`` that ``json.dumps`` refuses and whose
    ``repr`` is implementation-defined for a zip install.
    """
    from periplus.report import render_json

    root, config = tree
    document = json.loads(render_json(_resolve(root, config)))

    assert all(set(c["root"]) == {"kind", "display"} for c in document["candidates"])
    assert all("traversable" not in r for r in document["pack_roots"])


def test_the_json_document_parses_on_a_failing_run(tmp_path: Path) -> None:
    """One document on stdout on a run that failed, problems included.

    A consumer parsing this form reads one stream and gets one document whether the run succeeded
    or failed, which is the whole reason the problems belong inside it rather than on stderr.
    """
    from periplus.report import render_json

    config = tmp_path / "userconf"
    config.mkdir()

    # A genuinely failing run, which an unconfigured one no longer is. A settings file that
    # exists and will not parse is exit 4; "no settings file anywhere" stopped being a problem
    # when `status` stopped reporting a fresh machine as broken, so using it here would have left
    # this test asserting the empty case twice and the failing case not at all.
    broken = tmp_path / "broken"
    (broken / ".periplus").mkdir(parents=True)
    (broken / ".periplus" / "settings.yml").write_text("- not a mapping\n", encoding="utf-8")
    failing = json.loads(render_json(_resolve(broken, config)))
    assert [problem["code"] for problem in failing["problems"]] == [4]
    assert failing["settings"] is None
    assert failing["pack_roots"] != []


def test_a_section_whose_stage_did_not_run_says_so_rather_than_reading_empty(
    tmp_path: Path,
) -> None:
    """ "Matching never ran" and "no pins matched" are different facts, and both forms carry which.

    An empty ``Matched packs`` section is what a run with three unmatched pins also produces. A
    reader who cannot tell the two apart concludes that the pins matched nothing, when in fact no
    settings file declared any.
    """
    from periplus.report import render_json, render_text

    config = tmp_path / "userconf"
    config.mkdir()
    report = _resolve(tmp_path / "nowhere", config)

    rows = _section(render_text(report), "Matched packs")
    assert len(rows) == 1
    assert rows[0].strip().startswith("skipped - "), rows

    assert json.loads(render_json(report))["skipped"]["packs"]
