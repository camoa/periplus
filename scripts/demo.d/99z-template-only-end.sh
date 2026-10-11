#!/usr/bin/env bash
# The references guide's example of an edge end from the file's path alone (from: [] with a
# template): its two YAML blocks are planted as written in the guide, as a project-local pack, and
# mapped. Each configuration file whose name has an owner gets one provided_by edge to that
# module; a file whose name has none gets no edge.
set -euo pipefail

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

python3 - "$ROOT/docs/rutter-author-guide-references.md" "$work" <<'PY'
import re
import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text()
blocks = re.findall(r"^```yaml (\.periplus/packs/owner@0\.0\.1/\S+)\n(.*?)^```$", text, re.M | re.S)
assert [name for name, _ in blocks] == [
    ".periplus/packs/owner@0.0.1/pack.yaml",
    ".periplus/packs/owner@0.0.1/rules/config.yaml",
], blocks
for name, block in blocks:
    target = Path(sys.argv[2]) / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(block)
PY
mkdir -p "$work/config"
printf 'periplus_version: 0\npacks: [owner@0.0.1]\n' >"$work/.periplus/settings.yml"
printf 'name: x\n' >"$work/config/mymod.settings.yml"
printf 'id: a\n' >"$work/config/othermod.mail.yml"
printf 'id: b\n' >"$work/config/plain.yml"
(cd "$work" && PERIPLUS_CONFIG_DIR="$work/cfg" "$PERIPLUS" map --output map.json --format json >report.json)

python3 - "$work" <<'PY'
import json
import sys
from pathlib import Path

work = Path(sys.argv[1])
report = json.loads((work / "report.json").read_text())
assert report["problems"] == [] and report["not_executed"] == [], report
document = json.loads((work / "map.json").read_text())
edges = sorted((e["from"], e["kind"], e["to"]) for e in document["edges"])
assert edges == [
    ("app.config::mymod.settings", "provided_by", "app.module::mymod"),
    ("app.config::othermod.mail", "provided_by", "app.module::othermod"),
], edges
states = {n["id"]: n["state"] for n in document["nodes"]}
assert states["app.config::plain"] == "mapped" and states["app.module::mymod"] == "referenced", states
PY
echo "template-only end ok"
