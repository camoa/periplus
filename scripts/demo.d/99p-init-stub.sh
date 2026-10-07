#!/usr/bin/env bash
# `periplus init` on a Drupal checkout writes a settings file whose pin `periplus status` matches,
# and every pin and folder key the stub names as a commented example resolves against the bundled
# packs, so a renamed rutter or folder key fails here instead of misleading a reader.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
site="$work/site"
mkdir -p "$site"
printf '{"require": {"drupal/core": "^11"}}\n' >"$site/composer.json"
python="$(head -1 "$(command -v "$PERIPLUS")" | sed 's/^#!//')"

(cd "$site" && "$PERIPLUS" init >"$work/init.txt")
(cd "$site" && "$PERIPLUS" status >"$work/status.txt")
grep -q '^Problems:$' "$work/status.txt" && sed -n '/^Problems:/,$p' "$work/status.txt" | grep -qx '  none' \
    || { echo "status reports problems after init"; cat "$work/status.txt"; exit 1; }

"$python" - "$site/.periplus/settings.yml" "$ROOT/src/periplus/settings.stub.yml" \
    "$ROOT/src/periplus/packs" <<'PY'
import re, sys
from pathlib import Path
from ruamel.yaml import YAML

settings, stub, packs = (Path(a) for a in sys.argv[1:4])
yaml = YAML(typ="safe")
written = yaml.load(settings)["packs"]
lines = stub.read_text().splitlines()
example_pins = [m[1] for line in lines if (m := re.match(r"#   - (\S+@\S+)$", line))]
in_folders = False
example_keys = []
for line in lines:
    if line.startswith("# folders:"):
        in_folders = True
    elif in_folders and (m := re.match(r"#   (\w+): ", line)):
        example_keys.append(m[1])
    elif in_folders:
        in_folders = False
assert written and example_pins and example_keys, (written, example_pins, example_keys)
for pin in written + example_pins:
    assert (packs / pin / "pack.yaml").is_file(), f"no bundled pack for {pin}"
declared = yaml.load(packs / "drupal_basic@0.3.0" / "pack.yaml")["folders"]
for key in example_keys:
    assert key in declared, f"drupal_basic declares no folder key {key}: {sorted(declared)}"
assert "drupal_basic@0.3.0" in written and "drupal_basic@0.3.0" in example_pins, (written, example_pins)
PY
echo "init stub ok"
