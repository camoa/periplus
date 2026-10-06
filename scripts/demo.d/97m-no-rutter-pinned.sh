#!/usr/bin/env bash
# A project that pins no rutter: settings with no packs key, and settings with packs: []. Both stop
# with exit 17 and one problem that says no rutter is pinned, names packs in .periplus/settings.yml
# and names periplus status, in text and in JSON format. No map file is written.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
site="$work/site"
mkdir -p "$site/.periplus"
python="$(head -1 "$(command -v "$PERIPLUS")" | sed 's/^#!//')"
code="$("$python" -c 'from periplus.errors import ExitCode; print(int(ExitCode.MAP_INVALID))')"
words='no rutter is pinned: list one under packs in .periplus/settings.yml; periplus status shows the bundled rutters'

for settings in 'periplus_version: 0\n' 'periplus_version: 0\npacks: []\n'; do
    printf "$settings" >"$site/.periplus/settings.yml"
    status=0
    (cd "$site" && "$PERIPLUS" map --output "$work/map.json" >"$work/report.txt") || status=$?
    [ "$status" -eq "$code" ] && grep -qF "$words" "$work/report.txt" && [ ! -e "$work/map.json" ] \
        || { echo "text: no rutter pinned was not refused: $status"; cat "$work/report.txt"; exit 1; }
    status=0
    (cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json") \
        || status=$?
    "$python" - "$work/report.json" "$code" "$words" <<'PY' || { echo "json: $status"; exit 1; }
import json, sys
problems = json.load(open(sys.argv[1]))["problems"]
assert len(problems) == 1, problems
assert problems[0]["code"] == int(sys.argv[2]), problems
assert problems[0]["message"] == sys.argv[3], problems
assert problems[0]["detail"] == {"setting": "packs"}, problems
PY
    [ "$status" -eq "$code" ] && [ ! -e "$work/map.json" ] && [ ! -e "$site/.periplus/map.json" ] \
        || { echo "json: no rutter pinned was not refused: $status"; exit 1; }
done
echo "no rutter pinned ok"
