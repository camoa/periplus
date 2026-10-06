#!/usr/bin/env bash
# A project that pins the old drupal_basic@0.1.0 stops with exit 5 and the problem that no pack
# directory of that name is on the pack search path. The JSON detail names drupal_basic@0.2.0 as
# the near miss, so the version to pin is given. No map file is written.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
site="$work/site"
mkdir -p "$site/.periplus"
printf 'periplus_version: 0\npacks:\n  - drupal_basic@0.1.0\n' >"$site/.periplus/settings.yml"
python="$(head -1 "$(command -v "$PERIPLUS")" | sed 's/^#!//')"
code="$("$python" -c 'from periplus.errors import ExitCode; print(int(ExitCode.PIN_UNMATCHED))')"
[ "$code" -eq 5 ] || { echo "the unmatched pin exit code is $code, not 5"; exit 1; }
words="no pack directory is named 'drupal_basic@0.1.0' on the pack search path"

status=0
(cd "$site" && "$PERIPLUS" map --output "$work/map.json" >"$work/report.txt") || status=$?
[ "$status" -eq 5 ] && grep -qF "$words" "$work/report.txt" && [ ! -e "$work/map.json" ] \
    || { echo "text: the old pin was not refused: $status"; cat "$work/report.txt"; exit 1; }

status=0
(cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json") \
    || status=$?
[ "$status" -eq 5 ] && [ ! -e "$work/map.json" ] \
    || { echo "json: the old pin was not refused: $status"; exit 1; }
"$python" - "$work/report.json" "$words" <<'PY'
import json, sys
problems = json.load(open(sys.argv[1]))["problems"]
assert len(problems) == 1, problems
assert problems[0]["code"] == 5, problems
assert problems[0]["message"] == sys.argv[2], problems
assert problems[0]["detail"]["pin"] == "drupal_basic@0.1.0", problems
assert "drupal_basic@0.2.0" in problems[0]["detail"]["near_misses"], problems
PY
echo "old pin ok"
