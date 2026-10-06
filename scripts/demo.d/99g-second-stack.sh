#!/usr/bin/env bash
# The second stack: three rutters under examples/second-stack (python_text, typer_text on it, and
# speckitty), loaded the way a third party's rutter arrives, by copying them into a planted
# project's own packs folder. Each command docs/rutter-author-guide.md names runs here, in the
# project folder: validate accepts every rutter file, status loads the three, and map lists no rule
# as not executed. An end that an alias, a relative or a function-local import settles reaches the
# bound app. Words of a command or a mount in a docstring, a text literal or a comment give
# nothing.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
p="$work/project"

# The planted project. The counts below are read from these files.
mkdir -p "$p/shop/sub" "$p/shop/front" "$p/missions/alpha/templates/deep" "$p/missions/beta/templates"
cat >"$p/shop/__init__.py" <<'EOF'
"""The shop package. These words are not a call: app.add_typer(sub)."""
from .tools import helper
from . import cli
EOF
cat >"$p/shop/tools.py" <<'EOF'
import typer

app = typer.Typer()


def helper():
    return app


@app.command()
def run_all():
    pass
EOF
: >"$p/shop/sub/__init__.py"
printf 'from .core import app\n' >"$p/shop/front/__init__.py"
printf 'import typer\n\napp = typer.Typer()\n' >"$p/shop/front/core.py"
cat >"$p/shop/sub/jobs.py" <<'EOF'
from typer import Typer
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
EOF
cat >"$p/shop/cli.py" <<'EOF'
"""Commands. The words @app.command("ghost") and app.add_typer(phantom) are not calls."""
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
EOF
# Ends an import settles, a re-export that is not an app, a same-module name and a parameter
# receiver.
cat >"$p/shop/extra.py" <<'EOF'
import typer
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
EOF
# The call forms: an imported function called twice on one line and again below, an imported
# class, a module alias with a dotted name, an outside library, an alias of a function; and a
# builtin, a method on an object, a call on a parameter, a call on a call's result, a same-module
# function and words in a docstring, a text literal and a comment, which give nothing. A method
# named as an import gives nothing too: on a continuation line, after a brace or after a space.
cat >"$p/shop/calls.py" <<'EOF'
"""Calls. These words are not calls: helper() and json.dumps(x)."""
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
EOF
cat >"$p/missions/alpha/mission.yaml" <<'EOF'
mission:
  name: Alpha Mission
  steps:
    - name: not this
EOF
printf 'name: Beta\nsteps:\n  - name: one\n' >"$p/missions/beta/mission.yaml"
for t in alpha/templates/plan.md alpha/templates/deep/spec.md beta/templates/tasks.md; do
    echo "# $t" >"$p/missions/$t"
done

# The commands of the guide, verbatim, in the project folder, with periplus on the path as the
# command under test and REPO naming this repository.
guide="$ROOT/docs/rutter-author-guide.md"
[ "$(wc -l <"$guide")" -le 231 ] || { echo "the guide is longer than 231 lines"; exit 1; }
mkdir -p "$work/bin"
ln -s "$(command -v "$PERIPLUS")" "$work/bin/periplus"
grep '^\$ ' "$guide" | sed 's/^\$ //' >"$work/commands.sh"
[ "$(wc -l <"$work/commands.sh")" -ge 8 ] || { echo "the guide names too few commands"; exit 1; }
(cd "$p" && REPO="$ROOT" PATH="$work/bin:$PATH" bash -euo pipefail "$work/commands.sh" \
    >"$work/commands.log" 2>&1) || {
    cat "$work/commands.log" 2>/dev/null
    echo "a command of the guide failed"
    exit 1
}
for name in validate status map; do
    grep -q "$name" "$work/commands.sh" || { echo "the guide does not name $name"; exit 1; }
done

# Each YAML block of the guide is copied from the rutter file its fence names: under one indent,
# its lines are a run of that file's lines, byte for byte.
python3 - "$guide" "$ROOT/examples/second-stack/packs" "$ROOT/examples/guide/packs" <<'PY'
import re
import sys
from pathlib import Path

guide = Path(sys.argv[1]).read_text()
blocks = re.findall(r"^```yaml (\S+)\n(.*?)^```$", guide, re.M | re.S)
assert blocks and len(blocks) == guide.count("```yaml"), "a YAML block of the guide names no file"
for name, block in blocks:
    source = next(r / name for r in map(Path, sys.argv[2:]) if (r / name).is_file())
    quoted, lines = block.splitlines(), source.read_text().splitlines()
    indents = [s[: len(s) - len(quoted[0])] for s in lines]
    assert any(
        lines[i].endswith(quoted[0]) and not indents[i].strip(" ")
        and lines[i:i + len(quoted)] == [indents[i] + q for q in quoted]
        for i in range(len(lines))
    ), f"the guide's block from {name} is not copied from it:\n{block}"
PY

# validate checked every file of each rutter; status matched the three from the project.
packs="$ROOT/examples/second-stack/packs"
for pack in "$packs"/*; do
    (cd "$pack" && find . -type f | sed 's#^\./##') | while read -r file; do
        grep -q "^  $file\$" "$work/commands.log" || { echo "validate did not check $pack/$file"; exit 1; }
    done
    grep -q "^  $(basename "$pack") *project " "$work/commands.log" \
        || { echo "status did not match $(basename "$pack") from the project"; exit 1; }
done

# The map report: no rule not executed, no problem, no file of a declared type left unread.
python3 - "$p/report.json" "$p/map.json" "$p" <<'PY'
import json
import re
import sys
from pathlib import Path

report, document, root = json.load(open(sys.argv[1])), json.load(open(sys.argv[2])), Path(sys.argv[3])
assert report["not_executed"] == [] and report["problems"] == [], report
# Unread: the copied rutters and the report this run writes, and no planted file.
assert not [f for f in report["unread"] if not f.startswith(".periplus/") and f != "report.json"], report["unread"]
assert report["unlisted"] == [], report["unlisted"]

# Words of a command or a mount after a quote or a hash on their line: inside a docstring, a text
# literal or a comment. None of those lines carries a Typer node or edge.
quoted = set()
for f in sorted(root.rglob("*.py")):
    for number, line in enumerate(f.read_text().splitlines(), 1):
        if re.search(r"""["'#].*(\.command\(|add_typer\()""", line):
            quoted.add((f.relative_to(root).as_posix(), number))
assert len(quoted) >= 5, quoted
placed = {
    (loc["file"], loc["line"]): item.get("id", item.get("kind"))
    for item in document["nodes"] + document["edges"]
    for loc in item["locations"]
    if item.get("type", "").startswith("typer.") or item.get("kind") in ("registered_on", "mounted_under")
}
assert placed, "no Typer node or edge has a location"
assert not quoted & set(placed), sorted((k, placed[k]) for k in quoted & set(placed))
PY

# Every calls edge by exact value: from the module, to the name the import of the callee's first
# segment binds, at each call line; mapped when the project holds that function or class. Nothing
# else is a calls edge.
python3 - "$p/map.json" "$p" <<'PY'
import json
import re
import sys
from pathlib import Path

document, root = json.load(open(sys.argv[1])), Path(sys.argv[2])


def at(file, *patterns):
    lines = (root / file).read_text().splitlines()
    return [(file, n) for n, s in enumerate(lines, 1) if any(re.fullmatch(p, s) for p in patterns)]


expected = {  # (from module, to id): (mapped, [(file, line), ...])
    ("shop.calls", "python.function::shop.tools.helper"): (True, at(
        "shop/calls.py", r"    helper\(helper\(\)\)", r"    tools_module\.helper\(\)", r"    h\(\)")),
    ("shop.calls", "python.class::shop.cli.Config"): (True, at("shop/calls.py", r"    box = Config\(\)")),
    ("shop.calls", "python.function::json.loads"): (False, at("shop/calls.py", r"    return json\.loads\(.*")),
    ("shop.calls", "python.function::json.dumps"): (False, at("shop/calls.py", r"    return json\.loads\(.*")),
    ("shop.extra", "python.function::shop.tools.app.command"): (
        False, at("shop/extra.py", r'@tools_app\.command\("relative"\)')),
    ("shop.extra", "python.function::shop.sub.jobs.jobs.command"): (
        False, at("shop/extra.py", r'    @local_jobs\.command\("local"\)')),
    ("shop.extra", "python.function::shop.front.app.command"): (
        False, at("shop/extra.py", r'@front_app\.command\("again"\)')),
    ("shop.sub.jobs", "python.function::shop.tools.helper"): (True, at(
        "shop/sub/jobs.py", r"helper\(\)", r"parent_tools\.helper\(\)")),
}
# A Typer app built through an import of typer: a call to typer.Typer, in each module that does.
for f in ("shop/cli.py", "shop/extra.py", "shop/front/core.py", "shop/sub/jobs.py", "shop/tools.py"):
    expected[(f[:-3].replace("/", "."), "python.function::typer.Typer")] = (
        False, at(f, r"\w+(: typer\.Typer)? = (typer\.)?Typer\(.*\)"))
assert all(lines for _, lines in expected.values()), expected

calls = [e for e in document["edges"] if e["kind"] == "calls"]
found = {(e["from"].removeprefix("python.module::"), e["to"]):
         [(loc["file"], loc["line"]) for loc in e["locations"]] for e in calls}
assert len(found) == len(calls), calls
assert found == {k: sorted(v) for k, (_, v) in expected.items()}, (found, expected)
nodes = {n["id"]: n for n in document["nodes"]}
for (_, end), (mapped, _) in expected.items():
    node = nodes[end]
    assert node["state"] == ("mapped" if mapped else "unresolved"), node
    if not mapped:
        assert node["unresolved_detail"]["searched_for"] == end.split("::")[1], node
assert all(e["provenance"] == [{"confidence": "inferred", "pack": "python_text", "rule": "call"}]
           for e in calls), calls
unresolved = sum(not mapped for mapped, _ in expected.values())
nodes = len({end for (_, end), (mapped, _) in expected.items() if not mapped})
print("calls:", len(expected), "edges,", unresolved, "unresolved ends,", nodes, "unresolved nodes")
PY

# Each planted case in shop/extra.py ends where Python's binding at the use puts it, read from the
# import that binds it; the parameter receiver is marked not resolved under the module's name, and
# the re-exported name under the bound name, not the written one and not the app it re-exports.
python3 - "$p/map.json" "$p/shop/extra.py" <<'PY'
import json
import re
import sys

document, text = json.load(open(sys.argv[1])), open(sys.argv[2]).read()
module, package, lines = "shop.extra", "shop", text.splitlines()


def at(pattern):
    return next(n for n, s in enumerate(lines, 1) if re.fullmatch(pattern, s))


def bound(pattern):
    return ".".join(re.search(pattern, text, re.M).groups())


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
    ends = [e[side] for e in document["edges"]
            if e["kind"] == kind and {"file": "shop/extra.py", "line": line} in e["locations"]]
    assert ends == ["typer.app::" + name], (kind, line, ends, name)
    node = nodes["typer.app::" + name]
    if name.endswith((".group", ".front.app")):
        assert node["state"] == "unresolved", node
        assert node["unresolved_detail"]["searched_for"] == name, node
    else:
        assert node["state"] == "mapped", node
print("binding cases:", [name for *_, name in cases])
PY

echo "second stack ok"
