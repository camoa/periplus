"""README.md as a landing page: its layout and its facts, read from the files they come from.

The page is read as text. The only subprocess is one ``pytest --collect-only -q`` run, for the
test count the page must state, shared by every test that needs it.
"""

from __future__ import annotations

import argparse
import re
import sys
import tomllib
from functools import cache
from pathlib import Path

import pytest
from test_packaging import PROJECT_ROOT, _run_or_fail

from periplus.cli import build_parser

README = PROJECT_ROOT / "README.md"
PACKS = PROJECT_ROOT / "src" / "periplus" / "packs"
DEMO_DIR = PROJECT_ROOT / "scripts" / "demo.d"

DIV_OPEN = '<div align="center">'
CHECKS_BADGE = "github/actions/workflow/status/camoa/periplus/checks.yml"
PYTHON_BADGE = "img.shields.io/badge/python-"
LICENCE_BADGE = "img.shields.io/github/license/"
STALE_PHRASES = ("pre-release", "Nothing is published", "has not run yet")
SEMVER = r"(?<![\d.])\d+\.\d+\.\d+(?![\d.])"
DESIGNED_ORDER = (
    "contents",
    "get started",
    "why periplus",
    "what the map holds",
    "write a rutter",
    "read the map",
    "cli reference",
    "troubleshooting",
    "license",
)


def _page() -> str:
    return README.read_text(encoding="utf-8")


def _outside_fences(text: str) -> list[str]:
    """The lines of ``text`` that are not inside a fenced block."""
    lines, inside = [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            inside = not inside
            continue
        if not inside:
            lines.append(line)
    return lines


def _h2_headings(text: str) -> list[str]:
    return [line[3:].strip() for line in _outside_fences(text) if line.startswith("## ")]


def _section(text: str, title: str) -> str:
    """The raw text under the ``## `` heading that starts with ``title``, up to the next ``## ``."""
    out, inside, fenced = [], False, False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        if line.startswith("## ") and not fenced:
            if inside:
                break
            inside = line[3:].strip().lower().startswith(title)
            continue
        if inside:
            out.append(line)
    return "\n".join(out)


def _slug(heading: str) -> str:
    kept = re.sub(r"[^\w\s-]", "", heading.lower())
    return re.sub(r"\s", "-", kept.strip())


@cache
def _collected_tests() -> int:
    # The runner beside the interpreter running the tests: CI installs the package into the
    # runner's own interpreter and has no .venv.
    runner = str(Path(sys.executable).parent / "pytest")
    result = _run_or_fail(
        [runner, "-o", "addopts=", "--collect-only", "-q"],
        "pytest --collect-only -q",
        cwd=PROJECT_ROOT,
    )
    match = re.search(r"(\d+)(?:/\d+)? tests? collected", result.stdout)
    assert match, f"no collected count in:\n{result.stdout[-400:]}"
    return int(match.group(1))


def _subcommands() -> list[str]:
    for action in build_parser()._actions:
        if isinstance(action, argparse._SubParsersAction):
            return sorted(action.choices)
    return []


def _bundled_packs() -> list[tuple[str, str]]:
    found = []
    for manifest in sorted(PACKS.glob("*@*/pack.yaml")):
        text = manifest.read_text(encoding="utf-8")
        name = re.search(r"^pack:\s*(\S+)", text, flags=re.MULTILINE)
        version = re.search(r"^version:\s*(\S+)", text, flags=re.MULTILINE)
        assert name and version, f"{manifest} has no pack or version line"
        found.append((name.group(1), version.group(1)))
    return found


def _hero_block(page: str) -> str:
    return page[: page.index("</div>") + len("</div>")] if "</div>" in page else ""


def _strip_markup(line: str) -> str:
    """A line with its images and links removed, so alt text and link text do not count."""
    line = re.sub(r"<img\b[^>]*>", "", line)
    line = re.sub(r"<a\b[^>]*>.*?</a>", "", line)
    line = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", line)
    return re.sub(r"\[[^\]]*\]\([^)]*\)", "", line)


def _first_fenced_block(text: str) -> str:
    block = re.search(r"```[^\n]*\n(.*?)```", text, flags=re.DOTALL)
    return block.group(1) if block else ""


@pytest.mark.criterion(id="c1")
def test_readme_opens_with_a_centred_hero_of_badges_and_a_dotted_tagline() -> None:
    page = _page()
    assert page.lstrip().startswith(DIV_OPEN), "README.md does not start with a centred div"
    close = page.index("</div>")
    first_h2 = min(
        (m.start() for m in re.finditer(r"^## ", page, flags=re.MULTILINE)), default=len(page)
    )
    assert close < first_h2, "the centred block does not close before the first ## heading"
    block = _hero_block(page)
    assert "# Periplus" in block
    badges = re.findall(r"https://img\.shields\.io/[^\s)\"']+", block)
    assert len(badges) >= 3, f"{len(badges)} shields.io links in the hero, want three or more"
    assert any(CHECKS_BADGE in badge for badge in badges), "no checks.yml workflow status badge"
    assert any(PYTHON_BADGE in badge for badge in badges), "no static python-versions badge"
    assert any(LICENCE_BADGE in badge for badge in badges), "no licence badge"
    tagline = [
        ln for ln in block.splitlines() if re.search(r"\w[^·\n]*\s·\s[^·\n]*\w", _strip_markup(ln))
    ]
    assert tagline, "no tagline line joined by ' · ' outside badge and link markup"


@pytest.mark.criterion(id="c2")
def test_readme_sections_follow_the_designed_order_and_shape() -> None:
    page = _page()
    headings = _h2_headings(page)
    lowered = [h.lower() for h in headings]
    positions = []
    for wanted in DESIGNED_ORDER:
        hits = [i for i, h in enumerate(lowered) if h.startswith(wanted)]
        assert hits, f"no ## heading starting with {wanted!r}; headings are {headings}"
        positions.append(hits[0])
    assert positions == sorted(positions), f"## headings out of order: {headings}"

    after = headings[positions[0] + 1 :]
    anchors = re.findall(r"^\s*[-*] \[[^\]]*\]\(#([^)]+)\)", _section(page, "contents"), re.M)
    assert anchors == [_slug(h) for h in after], "Contents anchors differ from the later headings"

    started = _section(page, "get started")
    if re.search(r"^### ", started, flags=re.MULTILINE):
        steps = re.split(r"^### (?=\d+[.)]?\s)", started, flags=re.MULTILINE)[1:]
    else:
        steps = re.split(r"^(?=\d+\.\s)", started, flags=re.MULTILINE)[1:]
    numbers = [int(m.group()) for m in (re.match(r"\d+", s) for s in steps) if m]
    assert len(steps) >= 2, "Get started holds fewer than two numbered steps"
    assert numbers == list(range(1, len(steps) + 1)), f"steps are numbered {numbers}"
    for step in steps:
        assert "```" in step, f"step has no fenced block: {step[:40]!r}"

    assert re.search(r"^\|[\s:|-]*---[\s:|-]*\|?\s*$", _section(page, "why periplus"), re.M)
    assert any("<details" in line for line in _outside_fences(page)), "no <details> element"

    block = _first_fenced_block(_section(page, "cli reference"))
    assert block, "CLI reference holds no fenced block"
    assert len(_subcommands()) == 13
    for name in _subcommands():
        assert any(
            re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", line) and " # " in line
            for line in block.splitlines()
        ), f"CLI reference block has no commented line for {name}"


@pytest.mark.criterion(id="c3")
def test_readme_states_the_true_version_and_test_count_and_no_stale_phrase() -> None:
    page = _page()
    version = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())["project"]["version"]
    status = [ln for ln in _outside_fences(page) if "beta" in ln.lower()]
    assert status, "no status line says beta"
    status_text = "\n".join(status)
    stated_versions = re.findall(SEMVER, status_text)
    assert stated_versions, "the status line states no version"
    assert set(stated_versions) == {version}, f"status line versions {stated_versions} != {version}"
    for versioned in re.findall(SEMVER, _hero_block(page)):
        assert versioned == version, f"hero states version {versioned}, pyproject has {version}"
    stated_counts = re.findall(r"(\d[\d,]*) (?:end-to-end )?tests?\b", status_text)
    assert stated_counts, "the status line states no test count"
    count = _collected_tests()
    assert {int(c.replace(",", "")) for c in stated_counts} == {count}, (
        f"status line test counts {stated_counts} != the {count} pytest collects"
    )
    prose = "\n".join(_outside_fences(page))
    for found in re.findall(r"\b(\d[\d,]*)\s+tests\b", prose):
        assert int(found.replace(",", "")) == count, f"page states {found} tests, not {count}"
    for found in re.findall(r"\bversion\s+(\d+\.\d+\.\d+)", prose, flags=re.IGNORECASE):
        assert found == version, f"page states version {found}, pyproject has {version}"
    for phrase in STALE_PHRASES:
        assert phrase.lower() not in page.lower(), f"stale phrase {phrase!r} is on the page"


@pytest.mark.criterion(id="c4")
def test_readme_keeps_every_command_pack_and_working_link() -> None:
    page = _page()
    names = _subcommands()
    assert len(names) == 13, f"parsed {len(names)} subcommands from cli.py: {names}"
    block = _first_fenced_block(_section(page, "cli reference"))
    for name in names:
        assert re.search(rf"periplus {re.escape(name)}(?![\w-])", block), (
            f"CLI reference block does not show `periplus {name}`"
        )

    lines = page.splitlines()
    for pack, version in _bundled_packs():
        assert any(
            re.search(rf"(?<![\w-]){re.escape(pack)}(?![\w-])", line)
            and re.search(rf"(?<![\d.]){re.escape(version)}(?![\d.])", line)
            for line in lines
        ), f"no line names pack {pack} with version {version}"

    prose = "\n".join(_outside_fences(page))
    targets = re.findall(r"\]\(([^)\s]+)", prose)
    targets += re.findall(r"href=\"([^\"]+)\"", prose)
    targets += re.findall(r"^\s*\[[^\]]+\]:\s*(\S+)", prose, flags=re.MULTILINE)
    relative = [t for t in targets if not re.match(r"[a-z][a-z0-9+.-]*:|#", t, re.I)]
    for target in relative:
        path = Path(target.split("#", 1)[0])
        resolved = (PROJECT_ROOT / path).resolve()
        assert resolved.is_file() and resolved.is_relative_to(PROJECT_ROOT.resolve()), (
            f"relative link {target} does not resolve"
        )
    for guide in ("docs/rutter-author-guide-abilities.md", "docs/rutter-author-guide-map-rules.md"):
        assert guide in relative, f"{guide} is not linked"


def test_readme_makes_no_verification_pypi_or_speed_claims() -> None:
    prose = "\n".join(_outside_fences(_page()))
    for word in ("checked by", "proven", "audited", "pypi"):
        assert not re.search(rf"\b{word}\b", prose, re.IGNORECASE), f"the page says {word!r}"
    figures = (
        r"\d+(?:\.\d+)?\s?x faster",
        r"\d+(?:\.\d+)?\s?ms\b",
        r"\d+(?:\.\d+)?\s?s faster",
    )
    for line in prose.splitlines():
        low = line.lower()
        for figure in figures:
            assert not re.search(figure, low), f"timing or speed figure: {line.strip()!r}"
        if re.search(r"\d+\s?%", low):
            assert not re.search(r"faster|fewer|cheaper", low), (
                f"percentage claim: {line.strip()!r}"
            )


def test_readme_stale_counts_and_limits_are_corrected() -> None:
    page = _page()
    prose = "\n".join(_outside_fences(page))
    demo_files = len([p for p in DEMO_DIR.iterdir() if p.is_file()])
    stated = re.findall(r"(\d+) end-to-end", prose)
    assert stated, "the page states no end-to-end check count"
    assert {int(n) for n in stated} == {demo_files}, (
        f"page says {stated} end-to-end checks, scripts/demo.d holds {demo_files}"
    )

    limits = _section(page, "known limitations")
    assert not re.search(r"no\s+`?(find|show|path)`?", limits, re.I), (
        "Known limitations still says there is no find, show or path command"
    )

    rows = prose.splitlines()
    anchor = next(
        (i for i, r in enumerate(rows) if r.startswith("|") and "drupal_basic" in r.split("|")[1]),
        None,
    )
    assert anchor is not None, "no Drupal rutter table with a drupal_basic row"
    start, end = anchor, anchor
    while start > 0 and rows[start - 1].startswith("|"):
        start -= 1
    while end + 1 < len(rows) and rows[end + 1].startswith("|"):
        end += 1
    body = [
        r
        for r in rows[start + 2 : end + 1]
        if not re.search(r"\bdrupal(_js)?_basic\b", r.split("|")[1])
    ]
    counts = re.findall(r"(\d+) contributed", prose)
    assert counts, "the page states no count of contributed-module rutters"
    assert {int(n) for n in counts} == {len(body)}, (
        f"page says {counts} contributed-module rutters, the Drupal table holds {len(body)}"
    )
