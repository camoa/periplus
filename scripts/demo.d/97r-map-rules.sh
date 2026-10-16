#!/usr/bin/env bash
# Map rules run in passes. The map-rule guide page's example, each fenced block after a marker
# `<!-- map-example: <path> -->` written to that path, is validated and mapped twice; the maps are
# byte-identical. inherited_holds gives Car the part its ancestor Base holds in pass 1;
# ask_through_part reads that edge in pass 2 and composes the chained edge calls from
# fleet.ask::Car.start to fleet.method::Engine.start; pass 3 adds nothing. No rule is not executed.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
export PERIPLUS_CONFIG_DIR="$work/userconf"
mkdir "$PERIPLUS_CONFIG_DIR"
site="$work/site"
mkdir -p "$site/.periplus"
printf 'periplus_version: 0\npacks:\n  - fleet@0.0.1\n' >"$site/.periplus/settings.yml"

python3 - "$ROOT/docs/rutter-author-guide-map-rules.md" "$site" <<'PY'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
site = Path(sys.argv[2])
found = re.findall(r"^<!-- map-example: (\S+) -->\n```[^\n]*\n(.*?)^```$", text, re.M | re.S)
assert len(found) == 3, [path for path, _ in found]
for path, body in found:
    target = site / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
PY

(cd "$site" && "$PERIPLUS" validate fleet >/dev/null)
(cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json")
(cd "$site" && "$PERIPLUS" map --output "$work/again.json" --format json >/dev/null)
cmp "$work/map.json" "$work/again.json"

python3 - "$work" <<'PY'
import json
import os
import sys

work = sys.argv[1]
document = json.load(open(os.path.join(work, "map.json")))
report = json.load(open(os.path.join(work, "report.json")))
for key in ("problems", "not_executed", "skipped"):
    assert report[key] == [], (key, report[key])
edges = {(e["kind"], e["from"], e["to"]): e for e in document["edges"]}
held = edges[("holds", "fleet.class::Car", "fleet.class::Engine")]
assert [p["rule"] for p in held["provenance"]] == ["inherited_holds"], held
chained = edges[("calls", "fleet.ask::Car.start", "fleet.method::Engine.start")]
assert [p["rule"] for p in chained["provenance"]] == ["ask_through_part"], chained
assert chained["locations"] == [{"file": "yard/cars.fleet", "line": 5}], chained
states = {n["id"]: n["state"] for n in document["nodes"]}
assert states["fleet.method::Engine.start"] == "mapped", states
passes = [(p["pass"], [(f["rule"], f["fires"]) for f in p["fired"]]) for p in report["map_passes"]]
assert passes == [
    (1, [("inherited_holds", 1)]),
    (2, [("ask_through_part", 1)]),
    (3, []),
], passes
fires = {row["rule"]: row["fires"] for row in report["executed"]}
assert fires["inherited_holds"] == 1 and fires["ask_through_part"] == 1, fires
PY
echo "map rules ok"
