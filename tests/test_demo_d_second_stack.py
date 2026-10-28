"""The second stack: three third-party rutters copied into a project, run as the guide says."""

from __future__ import annotations

import contextlib
import io
import json
import re
import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from periplus.cli import main

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "second-stack"

# The planted project. The expectations below are read from these files.
PLANTED = {
    'shop/__init__.py': r'''"""The shop package. These words are not a call: app.add_typer(sub)."""
from .tools import helper
from . import cli
''',
    'shop/tools.py': r'''import typer

app = typer.Typer()


def helper():
    return app


@app.command()
def run_all():
    pass
''',
    'shop/sub/jobs.py': r'''from typer import Typer
from ..tools import helper
from .. import tools as parent_tools

jobs = Typer()
helper()
parent_tools.helper()


@jobs.command("sweep")
def sweep_all():
    return helper


def plain():
    pass


jobs.command()(plain)
''',
    'shop/cli.py': r'''"""Commands. The words @app.command("ghost") and app.add_typer(phantom) are not calls."""
import typer
import os, json
import shop.tools as tools_module
from shop import tools
from shop.sub.jobs import (
    jobs,
    plain,
)

LABEL = "tagged"
NOTE = "@app.command('quoted') and app.add_typer(spirit)"
app = typer.Typer()
sub = typer.Typer(help="sub")
child: typer.Typer = typer.Typer()


class Config:
    def method(self):
        return LABEL


def build():
    class Inner:
        pass

    def nested(group):
        @group.command()
        def from_group():
            return Inner

    return nested


async def fetch():
    """Fetch. An example in a docstring, not a command:

    @app.command("example")
    def example():
        pass
    """
    return os, json


# @app.command("commented") and app.add_typer(shade)
@app.command("hello")
def greet():
    """Text: app.add_typer(wraith) and @app.command("x")."""


@sub.command()
def Show_Items():
    pass


@app.command(name="named", help="by keyword")
def by_keyword():
    pass


@app.command(LABEL)
def labelled():
    pass


@app.command("show")
@app.command("get", hidden=True)
def stacked():
    pass


@app.command("synthesize", help=(
    "Synthesize by kind (Q2-A).\n"
    "Exits (exit 1) on failure."
))
def synthesize_cmd():
    pass


@app.command(context_settings={"help_option_names": ["-h"]}, name="ctx")
def with_context():
    pass


app.command("bare")(tools.helper)
sub.command()(tools_module.helper)
app.add_typer(sub, name="sub")
app.add_typer(tools.app, name="tools")
app.add_typer(typer_instance=child, name="child")
''',  # noqa: E501
    'shop/extra.py': r'''import typer
import shop.sub.jobs as jobs_module
from .tools import app as tools_app
from . import cli
from shop.front import app as front_app

extra = typer.Typer()


@tools_app.command("relative")
def relative_cmd():
    pass


def register(group):
    from shop.sub.jobs import jobs as local_jobs

    @local_jobs.command("local")
    def local_cmd():
        pass

    @group.command("param")
    def param_cmd():
        pass


@extra.command("same")
def same_cmd():
    pass


@front_app.command("again")
def again_cmd():
    pass


extra.add_typer(jobs_module.jobs)
extra.add_typer(cli.sub)
''',
    'shop/calls.py': r'''"""Calls. These words are not calls: helper() and json.dumps(x)."""
import json
import shop.tools as tools_module
from shop.tools import helper, app as tools_app
from shop.cli import Config
from shop.tools import helper as h


def local():
    pass


def run(x, group):
    # not a call: helper()
    helper(helper())
    print(len(x))
    box = Config()
    box.method()
    group.command()
    local()
    x().helper()
    "helper(x)".join(x)
    (x.join(x)
        .helper())
    {**x}.helper()
    x .helper()
    tools_module.helper()
    h()
    return json.loads(x), json.dumps(box), tools_app
''',
    'missions/alpha/mission.yaml': r'''mission:
  name: Alpha Mission
  steps:
    - name: not this
''',
}
PLANTED.update({
    "shop/sub/__init__.py": "",
    "shop/front/__init__.py": "from .core import app\n",
    "shop/front/core.py": "import typer\n\napp = typer.Typer()\n",
    "missions/beta/mission.yaml": "name: Beta\nsteps:\n  - name: one\n",
    "missions/alpha/templates/plan.md": "# alpha/templates/plan.md\n",
    "missions/alpha/templates/deep/spec.md": "# alpha/templates/deep/spec.md\n",
    "missions/beta/templates/tasks.md": "# beta/templates/tasks.md\n",
})


@dataclass
class Ran:
    project: Path
    outputs: list[tuple[list[str], int, str]]
    report: dict[str, Any]
    document: dict[str, Any]


# The commands docs/rutter-author-guide.md gives for checking a rutter, listed here.
COMMANDS = [
    ["validate", "python_text"],
    ["validate", "typer_text"],
    ["validate", "speckitty"],
    ["status"],
    ["map", "--output", "map.json", "--format", "json"],
]


@pytest.fixture(scope="module")
def ran(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Ran]:
    """Plant the project, copy the rutters in as a third party would, run the guide's commands."""
    project = tmp_path_factory.mktemp("second-stack")
    for name, text in PLANTED.items():
        (project / name).parent.mkdir(parents=True, exist_ok=True)
        (project / name).write_text(text)
    (project / ".periplus").mkdir()
    shutil.copytree(EXAMPLE / "packs", project / ".periplus" / "packs")
    shutil.copy(EXAMPLE / "settings.yml", project / ".periplus" / "settings.yml")

    outputs: list[tuple[list[str], int, str]] = []
    with pytest.MonkeyPatch.context() as patch:
        patch.chdir(project)
        patch.setenv("PERIPLUS_CONFIG_DIR", str(project / "cfg"))
        for argv in COMMANDS:
            buffer = io.StringIO()
            with contextlib.redirect_stdout(buffer):
                code = main(argv)
            outputs.append((argv, code, buffer.getvalue()))
    map_run = next(out for argv, _, out in outputs if argv[0] == "map")
    yield Ran(
        project=project,
        outputs=outputs,
        report=json.loads(map_run),
        document=json.loads((project / "map.json").read_text()),
    )


def test_each_command_for_checking_a_rutter_runs_and_exits_clean(ran: Ran) -> None:
    ran_commands = [argv[0] for argv, _, _ in ran.outputs]
    assert {"validate", "status", "map"} <= set(ran_commands)
    assert [code for _, code, _ in ran.outputs] == [0] * len(ran.outputs), ran.outputs


def test_validate_checks_every_file_of_each_rutter_and_status_matches_it_from_the_project(
    ran: Ran,
) -> None:
    log = "\n".join(out for _, _, out in ran.outputs)
    for pack in sorted((EXAMPLE / "packs").iterdir()):
        for file in sorted(p for p in pack.rglob("*") if p.is_file()):
            assert f"\n  {file.relative_to(pack).as_posix()}\n" in log, (pack.name, file)
        assert re.search(rf"^  {re.escape(pack.name)} +project ", log, re.M), pack.name


def test_the_map_reports_no_rule_unexecuted_no_problem_and_no_planted_file_left_unread(
    ran: Ran,
) -> None:
    report = ran.report
    assert report["not_executed"] == [] and report["problems"] == [], report
    assert [f for f in report["unread"] if not f.startswith(".periplus/")] == [], report["unread"]
    assert report["unlisted"] == [], report["unlisted"]


def test_words_of_a_command_or_a_mount_in_a_docstring_a_literal_or_a_comment_give_nothing(
    ran: Ran,
) -> None:
    quoted = set()
    for f in sorted(ran.project.rglob("*.py")):
        for number, line in enumerate(f.read_text().splitlines(), 1):
            if re.search(r"""["'#].*(\.command\(|add_typer\()""", line):
                quoted.add((f.relative_to(ran.project).as_posix(), number))
    assert len(quoted) >= 5, quoted
    document = ran.document
    placed = {
        (loc["file"], loc["line"]): item.get("id", item.get("kind"))
        for item in document["nodes"] + document["edges"]
        for loc in item["locations"]
        if item.get("type", "").startswith("typer.")
        or item.get("kind") in ("registered_on", "mounted_under")
    }
    assert placed, "no Typer node or edge has a location"
    assert not quoted & set(placed), sorted((k, placed[k]) for k in quoted & set(placed))


def _at(root: Path, file: str, *patterns: str) -> list[tuple[str, int]]:
    lines = (root / file).read_text().splitlines()
    return [(file, n) for n, s in enumerate(lines, 1) if any(re.fullmatch(p, s) for p in patterns)]


def test_every_calls_edge_goes_to_the_name_its_import_binds_at_each_call_line(ran: Ran) -> None:
    root, document = ran.project, ran.document

    def at(file: str, *patterns: str) -> list[tuple[str, int]]:
        return _at(root, file, *patterns)

    expected: dict[tuple[str, str], tuple[bool, list[tuple[str, int]]]] = {
        ("shop.calls", "python.function::shop.tools.helper"): (
            True,
            at("shop/calls.py", r"    helper\(helper\(\)\)", r"    tools_module\.helper\(\)",
               r"    h\(\)"),
        ),
        ("shop.calls", "python.class::shop.cli.Config"): (
            True, at("shop/calls.py", r"    box = Config\(\)")),
        ("shop.calls", "python.function::json.loads"): (
            False, at("shop/calls.py", r"    return json\.loads\(.*")),
        ("shop.calls", "python.function::json.dumps"): (
            False, at("shop/calls.py", r"    return json\.loads\(.*")),
        ("shop.extra", "python.function::shop.tools.app.command"): (
            False, at("shop/extra.py", r'@tools_app\.command\("relative"\)')),
        ("shop.extra", "python.function::shop.sub.jobs.jobs.command"): (
            False, at("shop/extra.py", r'    @local_jobs\.command\("local"\)')),
        ("shop.extra", "python.function::shop.front.app.command"): (
            False, at("shop/extra.py", r'@front_app\.command\("again"\)')),
        ("shop.sub.jobs", "python.function::shop.tools.helper"): (
            True, at("shop/sub/jobs.py", r"helper\(\)", r"parent_tools\.helper\(\)")),
    }
    # A Typer app built through an import of typer: a call to typer.Typer, in each module that does.
    for f in ("shop/cli.py", "shop/extra.py", "shop/front/core.py", "shop/sub/jobs.py",
              "shop/tools.py"):
        expected[(f[:-3].replace("/", "."), "python.function::typer.Typer")] = (
            False, at(f, r"\w+(: typer\.Typer)? = (typer\.)?Typer\(.*\)"))
    assert all(lines for _, lines in expected.values()), expected

    calls = [e for e in document["edges"] if e["kind"] == "calls"]
    found = {
        (e["from"].removeprefix("python.module::"), e["to"]):
        [(loc["file"], loc["line"]) for loc in e["locations"]]
        for e in calls
    }
    assert len(found) == len(calls), calls
    assert found == {k: sorted(v) for k, (_, v) in expected.items()}, (found, expected)
    nodes = {n["id"]: n for n in document["nodes"]}
    for (_, end), (mapped, _) in expected.items():
        node = nodes[end]
        assert node["state"] == ("mapped" if mapped else "unresolved"), node
        if not mapped:
            assert node["unresolved_detail"]["searched_for"] == end.split("::")[1], node
    assert all(
        e["provenance"] == [{"confidence": "inferred", "pack": "python_text", "rule": "call"}]
        for e in calls
    ), calls


def test_a_registration_or_mount_ends_at_the_app_python_binds_at_the_use(ran: Ran) -> None:
    document = ran.document
    text = (ran.project / "shop/extra.py").read_text()
    module, package, lines = "shop.extra", "shop", text.splitlines()

    def at(pattern: str) -> int:
        return next(n for n, s in enumerate(lines, 1) if re.fullmatch(pattern, s))

    def bound(pattern: str) -> str:
        found = re.search(pattern, text, re.M)
        assert found is not None, pattern
        return ".".join(found.groups())

    cases = [  # (kind, line, the end that is the receiver, its id)
        ("mounted_under", at(r"extra\.add_typer\(jobs_module\.jobs\)"), "from",
         bound(r"^import ([\w.]+) as jobs_module$") + ".jobs"),
        ("registered_on", at(r'@tools_app\.command\("relative"\)'), "to",
         package + "." + bound(r"^from \.(\w+) import (\w+) as tools_app$")),
        ("mounted_under", at(r"extra\.add_typer\(cli\.sub\)"), "from",
         package + "." + bound(r"^from \. import (cli)$") + ".sub"),
        ("registered_on", at(r'\s+@local_jobs\.command\("local"\)'), "to",
         bound(r"^\s+from ([\w.]+) import (\w+) as local_jobs$")),
        ("registered_on", at(r'@extra\.command\("same"\)'), "to", module + ".extra"),
        ("registered_on", at(r'\s+@group\.command\("param"\)'), "to", module + ".group"),
        ("registered_on", at(r'@front_app\.command\("again"\)'), "to",
         bound(r"^from ([\w.]+) import (\w+) as front_app$")),
    ]
    nodes = {n["id"]: n for n in document["nodes"]}
    for kind, line, side, name in cases:
        ends = [
            e[side]
            for e in document["edges"]
            if e["kind"] == kind and {"file": "shop/extra.py", "line": line} in e["locations"]
        ]
        assert ends == ["typer.app::" + name], (kind, line, ends, name)
        node = nodes["typer.app::" + name]
        if name.endswith((".group", ".front.app")):
            assert node["state"] == "unresolved", node
            assert node["unresolved_detail"]["searched_for"] == name, node
        else:
            assert node["state"] == "mapped", node
