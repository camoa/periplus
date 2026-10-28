"""Every path, guide section and periplus command a skill body names is real."""

from __future__ import annotations

import argparse
import contextlib
import io
import re
import shlex
import tomllib
from pathlib import Path

import pytest

from periplus.cli import build_parser

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ("periplus-rutter", "periplus-map", "periplus-gaps")
_PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
_VERSION = _PYPROJECT["project"]["version"]
_LINK_PREFIX = f"https://github.com/camoa/periplus/blob/v{_VERSION}/"
RAW = {
    s: (ROOT / "src/periplus/skills" / s / "SKILL.md").read_text(encoding="utf-8") for s in SKILLS
}
# An installed skill points at the pages of its own version; the checks below read each link as the
# repository path it names.
BODIES = {s: body.replace(_LINK_PREFIX, "") for s, body in RAW.items()}

_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_EXAMPLE_BLOCK = re.compile(r"<!-- example [^>]*-->\s*\n```.*?\n```", re.DOTALL)
_FENCE = re.compile(r"```.*?\n```", re.DOTALL)
_PATH = re.compile(
    r"(?<![\w./-])((?:docs|examples|src/periplus|tests|scripts|references)/[\w./@-]*[\w/]"
    r"|[\w-]+\.(?:md|toml|lock))"
)
_ANCHOR = re.compile(r"(?<![\w./-])((?:docs/)?[\w./-]+\.md)#([\w-]+)")
_MD = re.compile(r"(?<![\w./-])((?:docs/)?[\w./-]+\.md)\b")
_OPTION = re.compile(r"(?<![\w-])(--[a-z][\w-]*)")
_QUOTED = re.compile(r"[\"“]([^\"”\n]+)[\"”]")


def _without_example_projects(body: str) -> str:
    """Example blocks hold project files; their PATH is project-relative."""
    return _COMMENT.sub("", _EXAMPLE_BLOCK.sub("", body))


def _slug(heading: str) -> str:
    text = re.sub(r"[`*_]", "", heading).strip().lower()
    return re.sub(r"\s", "-", re.sub(r"[^\w\s-]", "", text))


def _headings(path: Path) -> list[str]:
    return re.findall(r"^#{1,6}\s+(.*?)\s*$", path.read_text(encoding="utf-8"), re.MULTILINE)


def _norm(text: str) -> str:
    return " ".join(re.sub(r"[`*_]", "", text).lower().split())


def _resolve(skill: str, name: str) -> Path:
    """A path under references/, and SKILL.md itself, belong to the skill's own folder."""
    if name.startswith("references/") or name == "SKILL.md":
        return ROOT / "src/periplus/skills" / skill / name
    return ROOT / name


def _dead_paths(bodies: dict[str, str]) -> tuple[int, list[str]]:
    named: set[tuple[str, str]] = set()
    for skill, body in bodies.items():
        for found in _PATH.findall(_without_example_projects(body)):
            named.add((skill, found.rstrip("./,;:)")))
    return len(named), sorted(f"{s}: {p}" for s, p in named if not _resolve(s, p).exists())


def _dead_sections(bodies: dict[str, str]) -> tuple[int, list[str]]:
    checked = 0
    dead: list[str] = []
    for skill, body in bodies.items():
        text = _without_example_projects(body)
        for md, anchor in _ANCHOR.findall(text):
            checked += 1
            path = _resolve(skill, md)
            if not path.is_file() or anchor not in {_slug(h) for h in _headings(path)}:
                dead.append(f"{skill}: {md}#{anchor}")
        for paragraph in re.split(r"\n\s*\n", text):
            guides = {_resolve(skill, m) for m in _MD.findall(paragraph)}
            if re.search(r"\bREADME\b", paragraph):
                guides.add(ROOT / "README.md")
            for missing in sorted(g for g in guides if not g.is_file()):
                checked += 1
                dead.append(f"{skill}: guide {missing.name} does not exist")
            guides = {g for g in guides if g.is_file()}
            if not guides:
                continue
            known = {_norm(h) for g in guides for h in _headings(g)}
            for quoted in _QUOTED.findall(paragraph):
                checked += 1
                if _norm(quoted) not in known:
                    dead.append(f'{skill}: "{quoted}" beside {sorted(g.name for g in guides)}')
    return checked, dead


@pytest.mark.criterion(id="c7")
def test_every_repository_path_a_skill_names_exists_c7() -> None:
    count, dead = _dead_paths(BODIES)
    assert count, "no repository path found in any skill body"
    assert dead == [], f"paths named in skills that do not exist: {dead}"


@pytest.mark.criterion(id="c7")
def test_every_repository_page_a_skill_names_is_a_tag_pinned_link_c7() -> None:
    """The wheel ships only src/periplus, so a bare repository path would point at nothing."""
    bare = {
        s: _PATH.findall(_without_example_projects(body.replace(_LINK_PREFIX, "")))
        for s, body in RAW.items()
    }
    unlinked = {
        s: [p for p in paths if f"({_LINK_PREFIX}{p}" not in RAW[s] and "references/" not in p]
        for s, paths in bare.items()
    }
    assert {s: p for s, p in unlinked.items() if p} == {}


@pytest.mark.criterion(id="c7")
def test_every_skill_link_carries_the_package_version_c7() -> None:
    """A version bump without a link change would leave an installed skill on old pages."""
    links = {
        s: re.findall(r"https://github\.com/camoa/periplus/blob/(v[^/]+)/", body)
        for s, body in RAW.items()
    }
    assert all(links.values()), "a skill holds no repository link"
    stale = {s: sorted(set(v) - {f"v{_VERSION}"}) for s, v in links.items()}
    assert {s: v for s, v in stale.items() if v} == {}


@pytest.mark.criterion(id="c7")
def test_every_guide_section_a_skill_names_matches_a_heading_c7() -> None:
    checked, dead = _dead_sections(BODIES)
    assert checked, "no guide section found in any skill body"
    assert dead == [], f"guide sections that match no heading: {dead}"


def _parse(line: str) -> tuple[int, str]:
    argv = shlex.split(line)[1:]
    err = io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
        try:
            build_parser().parse_args(argv)
        except SystemExit as stop:
            return int(stop.code or 0), err.getvalue()
    return 0, ""


def _all_parsers(parser: argparse.ArgumentParser) -> list[argparse.ArgumentParser]:
    found = [parser]
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for sub in action.choices.values():
                found.extend(_all_parsers(sub))
    return found


def _unknown_options(span: str) -> list[str]:
    """Options a span names that the parser reached by its command words does not declare."""
    parser = build_parser()
    unknown: list[str] = []
    for token in shlex.split(span)[1:]:
        if token.startswith("-"):
            if token.split("=", 1)[0] not in parser._option_string_actions:
                unknown.append(token)
            continue
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction) and token in action.choices:
                parser = action.choices[token]
    return unknown


def _rejected_commands(bodies: dict[str, str]) -> tuple[int, list[str]]:
    rejected: list[str] = []
    checked = 0
    declared = {o for p in _all_parsers(build_parser()) for o in p._option_string_actions}
    for skill, body in bodies.items():
        for line in re.findall(r"^\s*\$ (periplus .*)$", body, re.MULTILINE):
            checked += 1
            code, _ = _parse(line)
            if code != 0:
                rejected.append(f"{skill}: {line}")
        prose = _FENCE.sub("", body)
        for span in re.findall(r"`(periplus [^`]+)`", prose):
            checked += 1
            code, message = _parse(span)
            # A command named without its arguments is prose, so a missing argument is allowed;
            # an unknown command is not, and neither is an option the command does not declare.
            if code != 0 and "arguments are required" not in message:
                rejected.append(f"{skill}: {span}")
            elif _unknown_options(span):
                rejected.append(f"{skill}: {span} (option {_unknown_options(span)})")
        for option in _OPTION.findall(prose):
            checked += 1
            if option not in declared:
                rejected.append(f"{skill}: option {option} belongs to no periplus command")
    return checked, rejected


@pytest.mark.criterion(id="c7")
def test_every_periplus_command_line_in_a_skill_is_accepted_by_the_parser_c7() -> None:
    checked, rejected = _rejected_commands(BODIES)
    assert checked, "no periplus command found in any skill body"
    assert rejected == [], f"command lines the parser refuses: {rejected}"
