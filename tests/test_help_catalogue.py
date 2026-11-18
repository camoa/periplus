"""`periplus --help` is a catalogue of the commands by purpose, and the map skill quotes it."""

from __future__ import annotations

import argparse
import contextlib
import io
import re
from pathlib import Path

import pytest

from periplus.cli import CATALOGUE, build_parser, main

SKILL = Path(__file__).resolve().parent.parent / "src/periplus/skills/periplus-map/SKILL.md"
GROUPS = (
    "set up and build",
    "learn the map's words",
    "cheap counts: ask these before pulling rows",
    "fetch things and their links",
    "macros: several answers in one reply",
    "sets and map files",
    "descriptions",
)


def _commands() -> set[str]:
    parser = build_parser()
    action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    return set(action.choices)


def _catalogue(text: str) -> str:
    """The help's lines from the first group title to the end."""
    return text[text.index(GROUPS[0] + ":") :]


def test_every_subcommand_is_in_exactly_one_group() -> None:
    listed = [name for _, names in CATALOGUE for name in names]
    assert sorted(listed) == sorted(set(listed)), "a command is in two groups"
    assert set(listed) == _commands()


def test_the_groups_come_in_a_fixed_order() -> None:
    assert tuple(title for title, _ in CATALOGUE) == GROUPS


def test_the_help_lists_each_group_with_one_line_per_command_in_catalogue_order() -> None:
    text = build_parser().format_help()
    # Over the whole help, so the flat list argparse prints by itself would show as a second row.
    rows = [r for r in re.findall(r"^ +(\S+)  +\S", text, re.MULTILINE) if not r.startswith("-")]
    assert rows == [name for _, names in CATALOGUE for name in names]
    titles = re.findall(r"^(\S.*):$", _catalogue(text), re.MULTILINE)
    assert tuple(titles) == GROUPS
    assert "{init," not in text


def test_the_help_ends_with_the_shared_conventions() -> None:
    tail = build_parser().format_help().rstrip("\n").split("\n\n")[-1]
    for convention in ("--ids", " - ", "--format json", "--limit 0", "--map PATH", "--help"):
        assert convention in tail, convention


def test_the_help_names_exactly_the_commands_that_take_a_limit() -> None:
    parser = build_parser()
    commands = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    takes = {n for n, sub in commands.choices.items() if "--limit" in sub._option_string_actions}
    tail = " ".join(parser.format_help().rstrip("\n").split("\n\n")[-1].split())
    named = re.search(r"--limit 0 lifts the budget of (.+?);", tail)
    assert named is not None
    assert set(re.findall(r"[a-z-]+", named.group(1))) - {"and"} == takes
    assert "take no --limit" in tail


def test_the_help_text_does_not_depend_on_the_terminal_width(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COLUMNS", "40")
    narrow = build_parser().format_help()
    monkeypatch.setenv("COLUMNS", "240")
    assert build_parser().format_help() == narrow


def test_a_command_help_names_periplus_and_the_command_alone() -> None:
    parser = build_parser()
    action = next(a for a in parser._actions if isinstance(a, argparse._SubParsersAction))
    assert action.choices["reach"].format_usage().startswith("usage: periplus reach [-h]")


def test_periplus_help_prints_the_catalogue() -> None:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), pytest.raises(SystemExit):
        main(["--help"])
    assert _catalogue(out.getvalue()) == _catalogue(build_parser().format_help())


def test_the_map_skill_quotes_the_help_catalogue_as_it_prints() -> None:
    body = SKILL.read_text(encoding="utf-8")
    quoted = re.search(r"<!-- periplus-help -->\n```text\n(.*?)```", body, re.DOTALL)
    assert quoted, "the map skill holds no <!-- periplus-help --> block"
    assert quoted[1] == _catalogue(build_parser().format_help())
