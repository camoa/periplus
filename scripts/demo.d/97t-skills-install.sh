#!/usr/bin/env bash
# `periplus skills install` copies every shipped skill folder under HOME/.claude/skills. HOME names
# a new folder, so the real home directory is never written.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
mkdir "$work/home"

HOME="$work/home" "$PERIPLUS" skills install >"$work/out.txt"
for source in "$ROOT"/src/periplus/skills/*/; do
    name="$(basename "$source")"
    [ -f "$work/home/.claude/skills/$name/SKILL.md" ] \
        || { echo "skill $name was not installed"; cat "$work/out.txt"; exit 1; }
    grep -qx "$work/home/.claude/skills/$name" "$work/out.txt" \
        || { echo "skill $name is not in the printed list"; cat "$work/out.txt"; exit 1; }
done
echo "skills install ok"
