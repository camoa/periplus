#!/usr/bin/env bash
# The rutters digest `periplus status` prints is the sha256 of the packs in the tree: every file
# under src/periplus/packs, in sorted path order, each as its relative path, a NUL, its bytes, a NUL.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
python="$(head -1 "$(command -v "$PERIPLUS")" | sed 's/^#!//')"
expected="$("$python" -I - "$ROOT/src/periplus/packs" <<'PY'
import hashlib, pathlib, sys
root = pathlib.Path(sys.argv[1])
digest = hashlib.sha256()
for path in sorted(p for p in root.rglob("*") if p.is_file()):
    name = path.relative_to(root).as_posix()
    digest.update(name.encode() + b"\0" + path.read_bytes() + b"\0")
print(digest.hexdigest())
PY
)"
(cd "$work" && "$PERIPLUS" status --format json >"$work/status.json") || true
actual="$("$python" -I -c 'import json, sys; print(json.load(open(sys.argv[1]))["rutters_digest"])' "$work/status.json")"
[ "$actual" = "$expected" ] || { echo "status prints $actual, the tree gives $expected"; exit 1; }
(cd "$work" && "$PERIPLUS" status) | grep -qx "rutters: $expected" \
    || { echo "the text status has no 'rutters: $expected' line"; exit 1; }
echo "rutter digest ok"
