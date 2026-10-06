#!/usr/bin/env bash
# A folder nobody can list, in a rutter written in the project's own packs folder for an invented
# format. Below a folder whose rule reads its direct children only, a closed folder leaves the run
# at exit 0 with the map it gives when the folder is open, and its path stands under unlisted in
# JSON and in text. A folder a rule's selection must list, below a two-star folder, ends the run
# with the unreadable-source exit code.
set -euo pipefail
if [ "$(id -u)" -eq 0 ]; then
    echo "unlisted folders skipped: running as root, where folder permissions do not bind"
    exit 0
fi
work="$(mktemp -d)"
closed="$work/site/drawer/closed"
lining="$work/site/chest/top/lining/closed"
trap 'chmod 755 "$closed" "$lining" 2>/dev/null || true; rm -rf "$work"' EXIT
python="$(head -1 "$(command -v "$PERIPLUS")" | sed 's/^#!//')"
site="$work/site"
pack="$site/.periplus/packs/drawer@0.0.1"
mkdir -p "$pack/rules" "$closed/inner" "$lining"
printf 'periplus_version: 0\npacks:\n  - drawer@0.0.1\n' >"$site/.periplus/settings.yml"
plant() {
    cat >"$pack/pack.yaml" <<YAML
pack: drawer
version: 0.0.1
depends: []
folders:
  drawer: $1
files:
  types:
    sock:
      endings: [sock]
      reader: text
YAML
}
cat >"$pack/rules/drawer.yaml" <<'YAML'
node_types:
- name: drawer.sock
  id_namespace: drawer.sock
rules:
- rule: sock
  reads: file
  in: [drawer]
  match: {file: '*', filetype: sock, text: '(?m)^(?<colour>\w+)$'}
  id: {from: {capture: colour}}
  emits: [{node: {type: drawer.sock}}]
  confidence: declared
YAML
printf 'red\n' >"$site/drawer/left.sock"
printf 'blue\n' >"$closed/hidden.sock"
printf 'x\n' >"$closed/inner/note"
printf 'green\n' >"$site/chest/top/one.sock"
printf 'grey\n' >"$lining/two.sock"

# The map with the folder shut matches the map with it open, and the closed folders below the
# folder stand under unlisted in JSON and in text.
check_shut() {
    (cd "$site" && "$PERIPLUS" map --output "$work/shut.json" --format json >"$work/shut.report.json")
    (cd "$site" && "$PERIPLUS" map --output "$work/shut.json" >"$work/shut.report.txt")
    cmp "$work/open.json" "$work/shut.json" || { echo "a closed folder changed the map"; exit 1; }
    expected="$(cd "$site" && find "$1" -mindepth 1 -type d ! -perm -u=rx -print -prune)"
    [ "$expected" = "$2" ] || { echo "planted closed folders: $expected"; exit 1; }
    python3 - "$work/open.report.json" "$work/shut.report.json" "$work/shut.report.txt" "$expected" <<'PY'
import json
import sys

opened, shut = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
text, expected = open(sys.argv[3]).read(), sys.argv[4].split("\n")
assert opened["problems"] == [] and opened["unlisted"] == [], opened
assert shut["problems"] == [], shut["problems"]
assert shut["unlisted"] == expected, (shut["unlisted"], expected)
lines = text.split("\n")
assert f"  unlisted  {len(expected)}" in lines, text
start = lines.index("Folders that could not be listed:")
assert [line.strip() for line in lines[start + 1 : start + 1 + len(expected)]] == expected, text
assert lines[start + 1 + len(expected)] == "", text
PY
}

# One folder level: the rule reads drawer's direct children, so drawer/closed is only walked for
# the unread list. Mode 444 lists the folder but cannot examine its children; mode 000 cannot list.
plant ./drawer
(cd "$site" && "$PERIPLUS" map --output "$work/open.json" --format json >"$work/open.report.json")
for mode in 444 000; do
    chmod "$mode" "$closed"
    check_shut drawer drawer/closed
done

# One star: the rule reads the direct children of chest/top, and the closed folder sits two levels
# below it.
plant './chest/*'
(cd "$site" && "$PERIPLUS" map --output "$work/open.json" --format json >"$work/open.report.json")
chmod 000 "$lining"
check_shut chest chest/top/lining/closed

# Two stars: the rule's selection must list every folder below drawer, the closed one included.
plant './drawer/**'
unreadable="$("$python" -c 'from periplus.errors import ExitCode; print(int(ExitCode.SOURCE_UNREADABLE))')"
status=0
(cd "$site" && "$PERIPLUS" map --output "$work/deep.json" --format json >"$work/deep.report.json") \
    || status=$?
[ "$status" -eq "$unreadable" ] && [ ! -e "$work/deep.json" ] \
    || { echo "a closed folder a rule reads: expected exit $unreadable, got $status"; exit 1; }
python3 - "$work/deep.report.json" "$unreadable" <<'PY'
import json
import sys

report, code = json.load(open(sys.argv[1])), int(sys.argv[2])
assert any(p["code"] == code and "drawer/closed" in p["message"] for p in report["problems"]), report
PY
echo "unlisted folders ok"
