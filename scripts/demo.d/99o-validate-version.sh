#!/usr/bin/env bash
# `validate` takes name@version and says which copy it checked. With the bundled drupal_basic@0.2.0
# and copies drupal_basic@0.3.0 (project) and drupal_basic@0.4.0 (user): the bare name inside a project pinning 0.3.0 checks 0.3.0;
# the bare name outside a project is PACK_AMBIGUOUS (exit 15) and lists both; name@version checks
# the named copy; a version nobody carries is PACK_UNKNOWN (exit 15) naming the versions there are.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
export PERIPLUS_CONFIG_DIR="$work/userconf"
site="$work/site"
other="$work/other"
mkdir -p "$PERIPLUS_CONFIG_DIR" "$site/.periplus/packs" "$other"
python="$(head -1 "$(command -v "$PERIPLUS")" | sed 's/^#!//')"
bundled="$("$python" -c 'import importlib.resources as r; print(r.files("periplus") / "packs")')"
cp -R "$bundled/drupal_basic@0.2.0" "$site/.periplus/packs/drupal_basic@0.3.0"
printf 'periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n' >"$site/.periplus/settings.yml"
mkdir "$PERIPLUS_CONFIG_DIR/packs"
cp -R "$bundled/drupal_basic@0.2.0" "$PERIPLUS_CONFIG_DIR/packs/drupal_basic@0.4.0"

# Outside a project the bare name has two copies of different versions and nothing to choose by.
status=0
(cd "$other" && "$PERIPLUS" validate drupal_basic >"$work/ambiguous.txt") || status=$?
[ "$status" -eq 15 ] && grep -q "PACK_AMBIGUOUS" "$work/ambiguous.txt" \
    && grep -q "drupal_basic@0.2.0" "$work/ambiguous.txt" \
    && grep -q "drupal_basic@0.4.0" "$work/ambiguous.txt" \
    && grep -q "drupal_basic@<version>" "$work/ambiguous.txt" \
    || { echo "ambiguous: $status"; cat "$work/ambiguous.txt"; exit 1; }

# name@version checks that bundled copy and prints the three lines.
(cd "$other" && "$PERIPLUS" validate drupal_basic@0.2.0 >"$work/named.txt") \
    || { echo "named copy did not validate"; cat "$work/named.txt"; exit 1; }
grep -q "^  pack:  *drupal_basic@0.2.0" "$work/named.txt" \
    && grep -q "^  version:  *0.2.0" "$work/named.txt" \
    && grep -q "^  directory:  *.*drupal_basic@0.2.0" "$work/named.txt" \
    || { echo "named copy lines missing"; cat "$work/named.txt"; exit 1; }

# Inside a project the pinned 0.3.0 is the copy checked, and it is the project-local directory.
(cd "$site" && "$PERIPLUS" validate drupal_basic >"$work/pinned.txt") \
    || { echo "pinned copy did not validate"; cat "$work/pinned.txt"; exit 1; }
grep -q "^  version:  *0.3.0" "$work/pinned.txt" \
    && grep -q "^  directory:  *$site/.periplus/packs/drupal_basic@0.3.0" "$work/pinned.txt" \
    || { echo "pinned copy not named"; cat "$work/pinned.txt"; exit 1; }

# A version on no root is unknown and names the versions that are there.
status=0
(cd "$other" && "$PERIPLUS" validate drupal_basic@9.9.9 >"$work/unknown.txt") || status=$?
[ "$status" -eq 15 ] && grep -q "0.2.0, 0.4.0" "$work/unknown.txt" \
    || { echo "unknown version: $status"; cat "$work/unknown.txt"; exit 1; }
echo "validate version ok"
