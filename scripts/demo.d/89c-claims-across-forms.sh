#!/usr/bin/env bash
# Claims across the two forms, in two rutters written in the project's own packs folder for an
# invented format. A short-form list claims each ending for the type named by that ending. So a
# declared type of another name read the same way with a listed ending is a reported conflict
# naming both rutters, a declared type named by the ending is not, and two short-form lists
# sharing an ending load, with or without a leading dot.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
python="$(head -1 "$(command -v "$PERIPLUS")" | sed 's/^#!//')"
unreadable="$("$python" -c 'from periplus.errors import ExitCode; print(int(ExitCode.PACK_RULES_UNREADABLE))')"
site="$work/site"
packs="$site/.periplus/packs"
mkdir -p "$packs/tannery@0.0.1" "$packs/furrier@0.0.1" "$site/hides"
printf 'periplus_version: 0\npacks:\n  - tannery@0.0.1\n  - furrier@0.0.1\n' \
    >"$site/.periplus/settings.yml"
printf 'pack: tannery\nversion: 0.0.1\ndepends: []\nfiles:\n  extensions: [hide, fur]\n' \
    >"$packs/tannery@0.0.1/pack.yaml"
printf 'x\n' >"$site/hides/one.hide"
furrier() {
    printf 'pack: furrier\nversion: 0.0.1\ndepends: []\nfiles:\n%s\n' "$1" \
        >"$packs/furrier@0.0.1/pack.yaml"
}
run() {
    status=0
    (cd "$site" && "$PERIPLUS" map --output "$work/$1.json" --format json >"$work/$1.report.json") \
        || status=$?
}

# A declared type of another name, pelt, claiming the listed ending hide.
furrier $'  types:\n    pelt:\n      endings: [hide]\n      reader: data\n      format: yaml'
run pelt
[ "$status" -eq "$unreadable" ] && [ ! -e "$work/pelt.json" ] \
    || { echo "pelt: expected exit $unreadable, got $status"; exit 1; }
python3 - "$work/pelt.report.json" "$unreadable" <<'PY'
import json
import sys

report, code = json.load(open(sys.argv[1])), int(sys.argv[2])
conflicts = [p for p in report["problems"] if p["code"] == code and "ending hide" in p["message"]]
assert len(conflicts) == 1, report["problems"]
message = conflicts[0]["message"]
assert "tannery/" in message and "furrier/" in message and "pelt" in message, message
PY

# A declared type named hide, claiming hide: the type the short list names.
furrier $'  types:\n    hide:\n      endings: [hide]\n      reader: data\n      format: yaml'
run same
[ "$status" -eq 0 ] || { echo "same name: expected exit 0, got $status"; cat "$work/same.report.json"; exit 1; }

# Two short-form lists sharing hide.
furrier '  extensions: [hide]'
run short
[ "$status" -eq 0 ] || { echo "two short lists: expected exit 0, got $status"; cat "$work/short.report.json"; exit 1; }

# The key is the ending without a leading dot: a short .hide beside the short hide, and beside a
# declared type named hide.
furrier '  extensions: [.hide]'
run dotted
[ "$status" -eq 0 ] || { echo "dotted short list: expected exit 0, got $status"; cat "$work/dotted.report.json"; exit 1; }
printf 'pack: tannery\nversion: 0.0.1\ndepends: []\nfiles:\n  extensions: [.hide, fur]\n' \
    >"$packs/tannery@0.0.1/pack.yaml"
furrier $'  types:\n    hide:\n      endings: [hide]\n      reader: data\n      format: yaml'
run dotted_same
[ "$status" -eq 0 ] \
    || { echo "dotted beside declared hide: expected exit 0, got $status"; cat "$work/dotted_same.report.json"; exit 1; }
echo "claims across forms ok"
