#!/usr/bin/env bash
# docs/map-report-guide.md, run from its own text, by the markers of docs/navigation.md. Every
# fenced block after `<!-- nav-file: PATH -->` is written to PATH in a new project, which pins the
# bundled Drupal rutters; every fenced block after `<!-- nav-run -->` is run in it, in order, and
# must print the rest of its block byte for byte, the project's own path as /path/to/project, with
# a last line `(exit N)` for a nonzero exit code. The first block is the map run. A path whose first
# segment F has its own F/.periplus/settings.yml block is written to a sibling project F instead,
# and a block after `<!-- nav-run: F -->` runs there, once F has been mapped. Every key of the map
# command's JSON report must then appear in the page as a heading word or a code term, the three
# decision sections must name what they are for, and the README must link the page. GUIDE_DOC
# names the file read, the repository's by default.
set -euo pipefail
doc="${GUIDE_DOC:-$ROOT/docs/map-report-guide.md}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
export PERIPLUS_CONFIG_DIR="$work/userconf"
mkdir "$PERIPLUS_CONFIG_DIR"
site="$work/project"
mkdir -p "$site"

python3 - "$doc" "$site" "$work/runs" <<'PY'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
site, runs = Path(sys.argv[2]), Path(sys.argv[3])
fence = r"```[^\n]*\n(?P<body>.*?)^```$"
files = list(re.finditer(r"^<!-- nav-file: (?P<path>\S+) -->\n" + fence, text, re.M | re.S))
blocks = list(re.finditer(r"^<!-- nav-run(?:: (?P<dir>\S+))? -->\n" + fence, text, re.M | re.S))
assert len(files) == len(re.findall(r"<!-- nav-file:", text)) >= 5, "a nav-file marker has no block"
assert len(blocks) == len(re.findall(r"<!-- nav-run(?::[^>]*)? -->", text)) >= 2, "a nav-run marker has no block"
settings = "/.periplus/settings.yml"
siblings = {m["path"][: -len(settings)] for m in files if m["path"].endswith(settings)}
siblings = {name for name in siblings if "/" not in name}
assert not siblings & {site.name, runs.name, "userconf"}, siblings
for m in files:
    parts = Path(m["path"]).parts
    root = site.parent / parts[0] if parts[0] in siblings else site
    target = root / Path(*parts[1:]) if root != site else site / m["path"]
    assert root in target.parents and ".." not in parts, m["path"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(m["body"], encoding="utf-8")
runs.mkdir()
for number, m in enumerate(blocks):
    first, _, rest = m["body"].partition("\n")
    assert first.startswith("$ periplus "), first
    code = 0
    exit_line = re.search(r"^\(exit (\d+)\)\n\Z", rest, re.M)
    if exit_line:
        code, rest = int(exit_line[1]), rest[: exit_line.start()]
    (runs / f"{number}.cmd").write_text(first[len("$ periplus "):] + "\n", encoding="utf-8")
    (runs / f"{number}.out").write_text(rest, encoding="utf-8")
    (runs / f"{number}.code").write_text(f"{code}\n", encoding="utf-8")
    assert not m["dir"] or m["dir"] in siblings, f"nav-run: {m['dir']} names no sibling project"
    (runs / f"{number}.dir").write_text(f"{m['dir'] or ''}\n", encoding="utf-8")
(runs / "count").write_text(f"{len(blocks)}\n", encoding="utf-8")
PY

[ "$(cat "$work/runs/0.cmd")" = "map" ] || { echo "the guide's first command is not periplus map"; exit 1; }
count="$(cat "$work/runs/count")"
declare -A mapped=()
for ((i = 0; i < count; i++)); do
    cmd="$(cat "$work/runs/$i.cmd")"
    dir="$(cat "$work/runs/$i.dir")"
    here="$site"
    if [ -n "$dir" ]; then
        here="$work/$dir"
        # A first block that is a map run maps the sibling itself. A sibling's map may be refused;
        # the block that runs it shows the refusal.
        [ -n "${mapped[$dir]:-}" ] || [ "${cmd%% *}" = map ] \
            || (cd "$here" && "$PERIPLUS" map >/dev/null 2>&1) || true
        mapped[$dir]=1
    fi
    set +e
    # The command line is split on spaces; no documented argument holds one.
    # shellcheck disable=SC2086
    (cd "$here" && "$PERIPLUS" $cmd >"$work/got.txt" 2>&1)
    code=$?
    set -e
    sed -i "s#$here#/path/to/project#g" "$work/got.txt"
    [ "$code" = "$(cat "$work/runs/$i.code")" ] \
        || { cat "$work/got.txt"; echo "periplus $cmd exited $code, the guide says $(cat "$work/runs/$i.code")"; exit 1; }
    cmp -s "$work/got.txt" "$work/runs/$i.out" \
        || { diff "$work/runs/$i.out" "$work/got.txt" || true; echo "periplus $cmd printed what the guide does not show"; exit 1; }
done

# Every key of the JSON report is a heading word or a code term outside the fenced blocks.
(cd "$site" && "$PERIPLUS" map --format json >"$work/report.json")
python3 - "$doc" "$work/report.json" <<'PY'
import json
import re
import sys
from pathlib import Path

prose = re.sub(r"^```[^\n]*\n.*?^```$", "", Path(sys.argv[1]).read_text(encoding="utf-8"), flags=re.M | re.S)
headings = [line for line in prose.splitlines() if line.startswith("#")]
missing = [
    key for key in sorted(json.loads(Path(sys.argv[2]).read_text(encoding="utf-8")))
    if not any(re.search(r"(?<![\w.])" + re.escape(key) + r"(?![\w.])", h) for h in headings)
    and f"`{key}`" not in prose
]
assert not missing, f"the guide does not name the report keys {missing}"

# Each decision section names what its reader needs, in its prose, not in a marker.
text = re.sub(r"(?m)^\s*<!--.*\n", "", prose)
sections = {part.split("\n", 1)[0]: part for part in re.split(r"(?m)^(?=## )", text)}
needs = {
    "## A shape the map lacks": [
        "](known-limitations.md)", "Known gaps", "skipped", "zero_fires", "path_in_script_string",
        "library_script", "setting_attached_in_array",
    ],
    "## Where a rule belongs": [
        ".periplus/packs", ".periplus/settings.yml", "periplus status", "drupal_js_basic",
        "path_in_script_string", "event_from_data_track",
    ],
    "## When a gap is the engine's": ["match.body_child", "exit 26"],
}
for heading, terms in needs.items():
    absent = [term for term in terms if term not in sections.get(heading, "")]
    assert not absent, f"the section {heading!r} does not name {absent}"
PY

grep -Eq '^\|.*\]\((\./)?docs/map-report-guide\.md(#[^)]*)?\)' "$ROOT/README.md" \
    || { echo "the README does not link the guide"; exit 1; }
echo "map report guide ok: $count examples"
