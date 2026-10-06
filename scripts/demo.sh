#!/usr/bin/env bash
# Run every executable file in scripts/demo.d in name order; stop with its status on the first
# failure. A later task adds a check by adding one file there. PERIPLUS names the command to run
# (default: periplus on the path).
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export ROOT="$root" PERIPLUS="${PERIPLUS:-periplus}"
for check in "$root"/scripts/demo.d/*; do
    [ -x "$check" ] || continue
    echo "== $(basename "$check")"
    "$check"
done
