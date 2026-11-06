"""The no-checkout check: a skill names no place that exists only in a repository checkout."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

VERSION = tomllib.loads((Path(__file__).resolve().parent.parent / "pyproject.toml").read_text())[
    "project"
]["version"]
LINK_PREFIX = f"https://github.com/camoa/periplus/blob/v{VERSION}/"

_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_EXAMPLE_BLOCK = re.compile(r"<!-- example [^>]*-->\s*\n```.*?\n```", re.DOTALL)
_PINNED_LINK = re.compile(re.escape(LINK_PREFIX) + r"[^\s)]*")
_OWN_FOLDER = re.compile(r"\$\{CLAUDE_SKILL_DIR\}/[^\s)]*")
_TMP_PATH = re.compile(
    r"(?<![\w./~}])(?<!\b[A-Za-z]:)/tmp(?![\w-]|\.[\w./-])"
    r"(?:/(?!\.\.(?![\w.-]))(?:[^\s/:;,|&<>()'\"`]|<[^<>/\n]+>)+)*"
)
# `<folder>/x` is relative; a plain word in the placeholder's place keeps the slash from a root.
_PLACEHOLDER = re.compile(r"<[^<>\n]+>(?=/)")
_LOCAL_PATH = re.compile(
    r"(?:~|\$\{?HOME\}?)(?:/[\w./~@-]*)?"
    r"|(?<![\w./~$})])(?!(?<=<)/[\w-]+>)/[\w.-]+(?:/[\w./~@-]*)?"
    r"|\b[A-Za-z]:[\\/][^\s)]*"
    r"|(?<![\w.-])(?:\./)?(?:[\w.-]+/)*(?:docs|examples|src/periplus|tests|scripts)/[\w./@*-]*"
    r"|(?<![\w./-])(?:\.{1,2}/)*(?!SKILL\.md\b)[\w.-]+\.(?:md|toml|lock)\b"
)


def without_example_projects(body: str) -> str:
    """Example blocks hold project files; their PATH is project-relative."""
    return _COMMENT.sub("", _EXAMPLE_BLOCK.sub("", body))


def local_repository_paths(bodies: dict[str, str]) -> list[str]:
    """Paths a skill step names as a local place to open; a tag-pinned link is no such place."""
    found: set[str] = set()
    for skill, body in bodies.items():
        text = _PLACEHOLDER.sub(
            "folder",
            without_example_projects(
                _TMP_PATH.sub("", _OWN_FOLDER.sub("", _PINNED_LINK.sub("", body)))
            ),
        )
        found.update(f"{skill}: {p.rstrip('./,;:)')}" for p in _LOCAL_PATH.findall(text))
    return sorted(found)
