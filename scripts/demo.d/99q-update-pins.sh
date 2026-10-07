#!/usr/bin/env bash
# `periplus update` moves a pin to the installed version and leaves the rest of the settings file,
# comments included, byte-identical. A pin to a rutter that only the project's own packs hold is
# kept. The JSON form carries the same entries. Outside a project the exit is 3.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
python="$(head -1 "$(command -v "$PERIPLUS")" | sed 's/^#!//')"
site="$work/site"
mkdir -p "$site/.periplus/packs/mine@1.0.0"
cat >"$site/.periplus/settings.yml" <<'YML'
# Kept comment, top.
periplus_version: 0

# Kept comment, above packs.
packs:
  # Kept comment, above the first pin.
  - drupal_basic@0.1.0   # kept trailing comment
  - mine@1.0.0

# Kept comment, bottom.
YML
cp "$site/.periplus/settings.yml" "$work/before.yml"

(cd "$site" && "$PERIPLUS" update --format json >"$work/report.json")
out="$(cd "$site" && "$PERIPLUS" update)" || true
[ "$out" = "kept drupal_basic@0.2.0: already current
kept mine@1.0.0: shipped from the project's own packs" ] \
    || { echo "second run printed: $out"; exit 1; }
sed 's/drupal_basic@0.2.0/drupal_basic@0.1.0/' "$site/.periplus/settings.yml" | cmp - "$work/before.yml" \
    || { echo "the settings file changed beyond the pin"; exit 1; }
"$python" - "$work/report.json" <<'PY'
import json, sys
report = json.load(open(sys.argv[1]))
assert [(c["name"], c["old"], c["new"]) for c in report["changed"]] == [("drupal_basic", "0.1.0", "0.2.0")], report
assert report["kept"] == [{"pin": "mine@1.0.0", "reason": "shipped from the project's own packs"}], report
PY
cp "$work/before.yml" "$site/.periplus/settings.yml"
text="$(cd "$site" && "$PERIPLUS" update)"
printf '%s\n' "$text" | grep -qxF "drupal_basic: 0.1.0 -> 0.2.0" || { echo "text: $text"; exit 1; }

mkdir "$work/bare"
status=0
(cd "$work/bare" && "$PERIPLUS" update >"$work/bare.txt") || status=$?
[ "$status" -eq 3 ] && grep -qF "no .periplus/settings.yml found for this project" "$work/bare.txt" \
    || { echo "outside a project: $status"; cat "$work/bare.txt"; exit 1; }
echo "update pins ok"
