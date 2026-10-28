#!/usr/bin/env bash
# `periplus spec` prints the pack contract: every document it names is shipped, and the JSON form
# carries each one's text.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
python="$(head -1 "$(command -v "$PERIPLUS")" | sed 's/^#!//')"

(cd "$work" && "$PERIPLUS" spec --format json >"$work/spec.json")
"$python" - "$work/spec.json" <<'PY'
import json, sys

documents = json.load(open(sys.argv[1], encoding="utf-8"))["documents"]
paths = [d["path"] for d in documents]
assert "schema/map.schema.json" in paths and "spec/rules.md" in paths, paths
assert all(d["text"].strip() for d in documents), "a contract document is empty"
PY
echo "spec ok"
