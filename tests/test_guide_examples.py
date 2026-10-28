"""Each runnable example of a guide page prints what the page shows.

A page marks the files of its example project with ``<!-- nav-file: PATH -->`` and each command
with ``<!-- nav-run -->``. The first line of a command block is ``$ periplus ARGS``, the rest is
the output it must print, and a last line ``(exit N)`` names a nonzero exit code. The project's
own path is printed as /path/to/project. A path whose first folder has its own
``F/.periplus/settings.yml`` block goes to a sibling project F, and ``<!-- nav-run: F -->`` runs
there.
"""

from __future__ import annotations

import contextlib
import io
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

import pytest
from _skills import ROOT, blocks

from periplus.cli import main

# Page name -> whether its project starts from the second-stack example and is mapped before the
# first command. The other page's first command is the map run itself.
PAGES = {"map-report-guide": False, "navigation": True}
SETTINGS = "/.periplus/settings.yml"
EXIT_LINE = re.compile(r"^\(exit (\d+)\)\n\Z", re.M)


class Example(NamedTuple):
    command: list[str]
    output: str
    code: int
    folder: str


def _page(name: str) -> Path:
    return ROOT / "docs" / f"{name}.md"


def _examples(name: str) -> list[Example]:
    found = []
    for folder, body in blocks(_page(name), "nav-run"):
        first, _, output = body.partition("\n")
        assert first.startswith("$ periplus "), first
        code = 0
        exit_line = EXIT_LINE.search(output)
        if exit_line:
            code, output = int(exit_line[1]), output[: exit_line.start()]
        found.append(Example(first[len("$ periplus "):].split(), output, code, folder))
    return found


def _invoke(command: list[str], here: Path, config: Path) -> tuple[int, str]:
    """Run the command in process from `here`; its two streams in order, the path made generic."""
    stream = io.StringIO()
    with (
        pytest.MonkeyPatch.context() as patch,
        contextlib.redirect_stdout(stream),
        contextlib.redirect_stderr(stream),
    ):
        patch.chdir(here)
        patch.setenv("PERIPLUS_CONFIG_DIR", str(config))
        code = int(main(command))
    return code, stream.getvalue().replace(str(here), "/path/to/project")


def _run_page(name: str, base: Path) -> list[tuple[int, str]]:
    """Plant the page's project, then run its commands in order, as the page shows them."""
    site = base / "project"
    config = base / "userconf"
    site.mkdir()
    config.mkdir()
    planted = blocks(_page(name), "nav-file")
    siblings = {
        path[: -len(SETTINGS)]
        for path, _ in planted
        if path.endswith(SETTINGS) and "/" not in path[: -len(SETTINGS)]
    }
    assert not siblings & {site.name, config.name}, siblings
    if PAGES[name]:
        (site / ".periplus").mkdir()
        example = ROOT / "examples" / "second-stack"
        shutil.copytree(example / "packs", site / ".periplus" / "packs")
        shutil.copy(example / "settings.yml", site / ".periplus" / "settings.yml")
    for path, body in planted:
        parts = Path(path).parts
        assert ".." not in parts, path
        target = base / path if parts[0] in siblings else site / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
    examples = _examples(name)
    if PAGES[name]:
        code, shown = _invoke(["map"], site, config)
        assert code == 0, shown
    else:
        assert examples[0].command == ["map"], examples[0].command

    mapped: set[str] = set()
    results = []
    for example in examples:
        assert not example.folder or example.folder in siblings, example.folder
        here = base / example.folder if example.folder else site
        # A sibling's map may be refused; the block that runs it shows the refusal.
        if example.folder and example.folder not in mapped and example.command[0] != "map":
            _invoke(["map"], here, config)
        mapped.add(example.folder)
        results.append(_invoke(example.command, here, config))
    return results


@pytest.fixture(scope="module")
def ran(
    tmp_path_factory: pytest.TempPathFactory,
) -> Callable[[str], list[tuple[int, str]]]:
    """The results of one page's commands, run once for the whole module."""
    cache: dict[str, list[tuple[int, str]]] = {}

    def results(name: str) -> list[tuple[int, str]]:
        if name not in cache:
            base = tmp_path_factory.mktemp(name).resolve()
            cache[name] = _run_page(name, base)
        return cache[name]

    return results


CASES = [(name, n) for name in PAGES for n in range(len(_examples(name)))]


@pytest.mark.parametrize(("name", "n"), CASES, ids=[f"{name}-{n}" for name, n in CASES])
def test_example_prints_what_the_page_shows(
    name: str, n: int, ran: Callable[[str], list[tuple[int, str]]]
) -> None:
    example = _examples(name)[n]
    code, output = ran(name)[n]
    command = " ".join(example.command)
    assert code == example.code, f"periplus {command} exited {code}, the page says {example.code}"
    assert output == example.output, f"periplus {command} printed what the page does not show"
