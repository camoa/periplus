"""Release checks for 0.2.0: the beta classifier, the changelog page and the README status."""

import argparse
import datetime
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from periplus.cli import build_parser

ROOT = Path(__file__).resolve().parent.parent
STATUS_PREFIX = "Development Status ::"


def _text(name: str) -> str:
    path = ROOT / name
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def _project() -> dict:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]


def _classifiers() -> list[str]:
    return _project()["classifiers"]


def _subcommands() -> set[str]:
    parser = build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    return set()


def _first_version_section(text: str) -> tuple[str, str]:
    """Return (heading, body) of the first "## [" heading that is not Unreleased, else ("", "")."""
    for heading in re.finditer(r"^## \[([^\]]*)\].*$", text, re.M):
        if heading.group(1) == "Unreleased":
            continue
        rest = text[heading.end():]
        following = re.search(r"^## ", rest, re.M)
        return heading.group(0), rest[: following.start()] if following else rest
    return "", ""


@pytest.mark.criterion(id="c1")
def test_exactly_one_status_classifier_and_it_is_beta_c1():
    statuses = [c for c in _classifiers() if c.startswith(STATUS_PREFIX)]
    assert statuses == ["Development Status :: 4 - Beta"]


@pytest.mark.criterion(id="c3")
def test_readme_status_and_classifier_status_both_say_beta_c3():
    readme = re.search(r"^Status:\s*\*\*([^*]+)\*\*", _text("README.md"), re.M)
    assert readme is not None
    statuses = [c for c in _classifiers() if c.startswith(STATUS_PREFIX)]
    assert len(statuses) == 1
    classifier_word = statuses[0].split(" - ", 1)[1]
    assert readme.group(1).strip().lower() == "beta"
    assert classifier_word.strip().lower() == "beta"


@pytest.mark.criterion(id="c2")
def test_changelog_first_version_is_dated_release_with_real_commands_c2():
    text = _text("CHANGELOG.md")
    assert text.strip(), "CHANGELOG.md is missing or empty"
    assert text.lstrip().startswith("# "), "no top heading"

    line, body = _first_version_section(text)
    version = _project()["version"]
    full = re.fullmatch(r"## \[" + re.escape(version) + r"\] - (\d{4}-\d{2}-\d{2})", line)
    assert full is not None, (
        f"first versioned heading is not '## [{version}] - YYYY-MM-DD': {line!r}"
    )
    datetime.date.fromisoformat(full.group(1))

    unreleased = re.search(r"^## \[Unreleased\]", text, re.M)
    first_version = re.search(r"^## \[" + re.escape(version) + r"\]", text, re.M)
    assert unreleased is not None and first_version is not None
    assert unreleased.start() < first_version.start()

    parts = re.split(r"^(### .*)$", body, flags=re.M)
    headings = parts[1::2]
    sections = parts[2::2]
    assert headings, "the release section has no ### heading"
    for heading, section in zip(headings, sections, strict=True):
        assert re.search(r"^- \S", section, re.M), f"{heading} holds no bullet"

    named = re.findall(r"`periplus (\w[\w-]*)", body)
    choices = _subcommands()
    assert choices, "the parser registers no subcommands"
    unknown = sorted(set(named) - choices)
    assert not unknown, f"not registered by the parser: {unknown}"


@pytest.mark.criterion(id="n7")
def test_changelog_makes_no_verification_claim_n7():
    text = _text("CHANGELOG.md")
    assert text.strip(), "CHANGELOG.md is missing or empty"
    # The owner's closed list: exactly these three phrases, nothing else.
    for word in ("checked by", "proven", "audited"):
        assert word not in text.lower(), word


def _unreleased_body(text: str) -> str:
    match = re.search(r"^## \[Unreleased\][^\n]*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert match is not None, "CHANGELOG.md has no Unreleased section"
    return match.group(1)


@pytest.mark.criterion(id="c7")
def test_release_is_numbered_0_2_1_everywhere_and_unreleased_is_empty_c7() -> None:
    version = _project()["version"]

    script = shutil.which("periplus", path=str(Path(sys.executable).parent))
    if script is None:
        pytest.fail("the periplus console script is not installed beside the test interpreter")
    shown = subprocess.run(  # noqa: S603 - list argv, shell unset, nothing interpolated
        [script, "--version"], capture_output=True, text=True, check=False
    )
    assert shown.returncode == 0, shown.stdout + shown.stderr
    assert shown.stdout.strip() == version

    text = _text("CHANGELOG.md")
    line, body = _first_version_section(text)
    assert re.fullmatch(r"## \[" + re.escape(version) + r"\] - \d{4}-\d{2}-\d{2}", line), line
    added = re.search(r"^### Added\s*$(.*?)(?=^### |\Z)", body, re.M | re.S)
    assert added is not None, "the 0.2.1 entry has no ### Added section"
    assert "pypi" in added.group(1).lower() and "readme" in added.group(1).lower()
    assert not re.search(r"^\s*[-*] \S", _unreleased_body(text), re.M)

    inside, status = False, []
    for row in _text("README.md").splitlines():
        if row.lstrip().startswith("```"):
            inside = not inside
        elif not inside and "beta" in row.lower():
            status.append(row)
    assert status, "no README status line says beta"
    assert version in "\n".join(status)
