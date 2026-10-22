"""The three decision sections of docs/map-report-guide.md (order wo2), seen through the check."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "docs" / "map-report-guide.md"
CHECK = ROOT / "scripts" / "demo.d" / "99zd-map-report-guide.sh"
PERIPLUS = Path(sys.executable).parent / "periplus"

_FILE = re.compile(r"<!--\s*nav-file:\s*(\S+)\s*-->\s*\n```[^\n]*\n(.*?)\n```", re.S)
_RUN = re.compile(r"<!--\s*nav-run(?::\s*(\S+))?\s*-->\s*\n```[^\n]*\n(.*?)\n```", re.S)


def _page() -> str:
    return PAGE.read_text(encoding="utf-8") if PAGE.exists() else ""


def _prose_of(part: str) -> str:
    """The text of `part` outside fenced blocks and HTML comment lines."""
    kept = [
        line
        for chunk in _FENCE.split(part)
        if not chunk.startswith("```")
        for line in chunk.splitlines()
        if not line.lstrip().startswith("<!--")
    ]
    return "\n".join(kept)


def _section_with(needle: str) -> str:
    """The last `##` section whose prose holds `needle`, or an empty string."""
    parts = re.split(r"(?m)^(?=## )", _page())
    matching = [part for part in parts if needle in _prose_of(part)]
    return matching[-1] if matching else ""


def _files(text: str) -> list[tuple[str, str]]:
    return [(m.group(1), m.group(2)) for m in _FILE.finditer(text)]


def _runs(text: str) -> list[tuple[str | None, str]]:
    return [(m.group(1), m.group(2)) for m in _RUN.finditer(text)]


_FENCE = re.compile(r"(```.*?```)", re.S)


def _prose_replace(text: str, old: str, new: str, *, word: bool = False) -> str:
    """Replace `old` in prose only: no fenced block and no HTML comment line changes."""
    pattern = re.compile(rf"\b{re.escape(old)}\b" if word else re.escape(old))

    def prose(part: str) -> str:
        return "".join(
            line if line.lstrip().startswith("<!--") else pattern.sub(new, line)
            for line in part.splitlines(keepends=True)
        )

    parts = _FENCE.split(text)
    return "".join(part if part.startswith("```") else prose(part) for part in parts)


def _in_section(needle: str, *pairs: tuple[str, str], word: bool = False) -> str:
    page = _page()
    section = _section_with(needle)
    assert section, f"no section holds {needle}"
    mutated = section
    for old, new in pairs:
        mutated = _prose_replace(mutated, old, new, word=word)
    return page.replace(section, mutated, 1)


def _check_rc(text: str) -> int:
    bash = shutil.which("bash")
    if bash is None:
        pytest.fail("bash is not on PATH")
    with tempfile.TemporaryDirectory() as tmp:
        doc = Path(tmp) / "page.md"
        doc.write_text(text, encoding="utf-8")
        env = {**os.environ, "ROOT": str(ROOT), "PERIPLUS": str(PERIPLUS), "GUIDE_DOC": str(doc)}
        run = subprocess.run(  # noqa: S603 - fixed argv built here
            [bash, str(CHECK)],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
        )
    return run.returncode


def _assert_fails(text: str, label: str) -> None:
    rc = _check_rc(text)
    assert rc not in (0, 127), f"check did not fail when {label} (exit {rc})"


@pytest.mark.criterion(id="c2")
def test_check_fails_when_a_limits_item_is_missing_from_the_section_c2() -> None:
    page = _page()
    anchor = "known-limitations.md"
    assert _check_rc(page) == 0, "check fails on the real page"
    _assert_fails(_prose_replace(page, anchor, "known-limits-x.md"), "the link is gone")
    _assert_fails(_in_section(anchor, ("skipped", "omitted"), word=True), "skipped is not named")
    _assert_fails(_in_section(anchor, ("zero_fires", "no_fires")), "zero_fires is not named")
    _assert_fails(
        _in_section(anchor, ("path_in_script_string", "rule_one")), "path_in_script_string is gone"
    )
    _assert_fails(
        _in_section(anchor, ("setting_attached_in_array", "rule_two")),
        "setting_attached_in_array is gone",
    )


@pytest.mark.criterion(id="c3")
def test_check_fails_when_a_placement_item_is_missing_from_the_section_c3() -> None:
    page = _page()
    anchor = "event_from_data_track"
    assert _check_rc(page) == 0, "check fails on the real page"
    _assert_fails(_in_section(anchor, (".periplus/packs", ".periplus/rutters")), "packs is gone")
    _assert_fails(
        _in_section(anchor, ("drupal_js_basic", "other_pack"), ("drupal_basic", "other_base")),
        "no bundled rutter is named",
    )
    _assert_fails(
        _in_section(anchor, ("path_in_script_string", "rule_one")), "bundled example gone"
    )
    _assert_fails(_in_section(anchor, (anchor, "rule_two")), "project-only example gone")


def _broken_run(page: str) -> str:
    for match in _RUN.finditer(page):
        if match.group(1) == "broken":
            return match.group(0)
    return ""


@pytest.mark.criterion(id="c4")
def test_check_fails_when_the_quoted_refusal_or_exit_code_differs_c4() -> None:
    page = _page()
    block = _broken_run(page)
    assert _check_rc(page) == 0, "check fails on the real page"
    assert "(exit 26)" in block, "page does not name exit 26"
    lines = block.split("\n")
    assert len(lines) >= 6, "block holds no message line"
    changed = [*lines[:-3], lines[-3] + " (altered)", *lines[-2:]]
    _assert_fails(page.replace(block, "\n".join(changed), 1), "the quoted message differs")
    _assert_fails(
        page.replace(block, block.replace("(exit 26)", "(exit 27)"), 1), "exit code differs"
    )


def test_main_project_pins_myproject_and_shows_its_node_wo2() -> None:
    files = dict(_files(_page()))
    settings = files.get(".periplus/settings.yml", "")
    for pin in ("drupal_basic@0.3.0", "js_basic@0.0.1", "drupal_js_basic@0.0.1", "myproject@0.0.1"):
        assert pin in settings, pin
    template = [b for p, b in files.items() if p.endswith("templates/card.html.twig")]
    assert template and 'data-track="card-open"' in template[0]
    pack = [b for p, b in files.items() if ".periplus/packs" in p and "myproject" in b]
    assert pack and "drupal_basic" in pack[0] and "myproject.event" in pack[0]
    assert "drupal_template_text" in pack[0] and "data-track" in pack[0]
    assert any("myproject.event::card-open" in body for _, body in _runs(_page()))


def test_check_runs_folder_blocks_and_fails_on_altered_output_wo2() -> None:
    page = _page()
    folder_blocks = [m.group(0) for m in _RUN.finditer(page) if m.group(1) == "joined-only"]
    assert folder_blocks, "page uses no folder marker"
    assert _check_rc(page) == 0, "check fails on the real page"
    block = folder_blocks[0]
    altered = block[: block.rindex("\n```")] + "\naltered line" + block[block.rindex("\n```") :]
    _assert_fails(page.replace(block, altered, 1), "a folder block's output is altered")
    marker = "<!-- nav-run: joined-only -->"
    assert marker in block
    _assert_fails(page.replace(marker, "<!-- nav-run -->", 1), "the folder is stripped")
    _assert_fails(page.replace(marker, "<!-- nav-run: nowhere -->", 1), "the folder does not exist")


@pytest.mark.slow
def test_whole_demo_suite_exits_zero_wo2() -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.fail("bash is not on PATH")
    env = {**os.environ, "ROOT": str(ROOT), "PERIPLUS": str(PERIPLUS)}
    run = subprocess.run(  # noqa: S603 - fixed argv built here
        [bash, str(ROOT / "scripts" / "demo.sh")],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    assert run.returncode == 0, run.stdout[-2000:] + run.stderr[-2000:]
