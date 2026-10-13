#!/usr/bin/env bash
# docs/navigation.md, run from its own text. The two source files of its worked example are written
# to a new project beside the shipped examples/second-stack rutters and settings; the project is
# mapped; and every fenced block after `<!-- nav-run -->` is run in it: the first line is the
# command, the rest is the output it must print, byte for byte, and a last line `(exit N)` names a
# nonzero exit code. The project's own path is printed as /path/to/project. NAV_DOC names the file
# read, the repository's by default, so a broken copy can be run.
set -euo pipefail
doc="${NAV_DOC:-$ROOT/docs/navigation.md}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
export PERIPLUS_CONFIG_DIR="$work/userconf"
mkdir "$PERIPLUS_CONFIG_DIR"
site="$work/project"
mkdir -p "$site/.periplus"
cp -r "$ROOT/examples/second-stack/packs" "$ROOT/examples/second-stack/settings.yml" "$site/.periplus/"

python3 - "$doc" "$site" "$work/runs" <<'PY'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
site, runs = Path(sys.argv[2]), Path(sys.argv[3])
fence = r"```[^\n]*\n(?P<body>.*?)^```$"
files = list(re.finditer(r"^<!-- nav-file: (?P<path>\S+) -->\n" + fence, text, re.M | re.S))
blocks = list(re.finditer(r"^<!-- nav-run -->\n" + fence, text, re.M | re.S))
assert len(files) == len(re.findall(r"<!-- nav-file:", text)) >= 2, "a nav-file marker has no block"
assert len(blocks) == len(re.findall(r"<!-- nav-run -->", text)) >= 8, "a nav-run marker has no block"
for m in files:
    target = site / m["path"]
    assert site in target.parents and ".." not in Path(m["path"]).parts, m["path"]
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
(runs / "count").write_text(f"{len(blocks)}\n", encoding="utf-8")
PY

(cd "$site" && "$PERIPLUS" map >"$work/map.log") || { cat "$work/map.log"; echo "the guide's example does not map"; exit 1; }

count="$(cat "$work/runs/count")"
for ((i = 0; i < count; i++)); do
    cmd="$(cat "$work/runs/$i.cmd")"
    set +e
    # The command line is split on spaces; no documented argument holds one.
    # shellcheck disable=SC2086
    (cd "$site" && "$PERIPLUS" $cmd >"$work/got.txt" 2>&1)
    code=$?
    set -e
    sed -i "s#$site#/path/to/project#g" "$work/got.txt"
    [ "$code" = "$(cat "$work/runs/$i.code")" ] \
        || { cat "$work/got.txt"; echo "periplus $cmd exited $code, the guide says $(cat "$work/runs/$i.code")"; exit 1; }
    cmp -s "$work/got.txt" "$work/runs/$i.out" \
        || { diff "$work/runs/$i.out" "$work/got.txt" || true; echo "periplus $cmd printed what the guide does not show"; exit 1; }
done

# Every command the guide documents has a block, and the guide names the full check and the exit codes.
for name in types find show neighbors affected path check-map; do
    grep -q "^\\\$ periplus $name" "$doc" || { echo "the guide has no example of $name"; exit 1; }
done
for code in 29 30 31; do
    grep -q "^| $code |" "$doc" || { echo "the guide does not list exit code $code"; exit 1; }
done
# The guide's setup block names the checkout by path, so it runs from an empty folder.
grep -q '^mkdir -p .periplus shop$' "$doc" && grep -q '^cp -r /path/to/periplus/examples/second-stack/packs /path/to/periplus/examples/second-stack/settings.yml .periplus/$' "$doc" \
    || { echo "the guide's setup block has drifted"; exit 1; }
echo "navigation guide ok: $count examples"
