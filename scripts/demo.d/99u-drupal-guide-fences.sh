#!/usr/bin/env bash
# The Drupal pack's blocks in three author guides: each YAML block whose fence names a
# drupal_basic@0.3.0 file is copied from it, as 99g-second-stack checks the main guide. Under one
# indent, the block's lines are a run of that file's lines, byte for byte. The references guide
# quotes the table and the table step, the abilities guide the constant keys, and the Drupal guide
# a rule narrowed by ending.
set -euo pipefail
python3 - "$ROOT/src/periplus/packs" "$ROOT"/docs/rutter-author-guide-{references,abilities,drupal}.md <<'PY'
import re
import sys
from pathlib import Path

packs = Path(sys.argv[1])
for guide in map(Path, sys.argv[2:]):
    text = guide.read_text()
    blocks = [
        (name, block)
        for name, block in re.findall(r"^```yaml (\S+)\n(.*?)^```$", text, re.M | re.S)
        if name.startswith("drupal_basic@0.3.0/")
    ]
    assert blocks, f"{guide.name} quotes no drupal_basic@0.3.0 file"
    for name, block in blocks:
        source = packs / name
        assert source.is_file(), f"{guide.name} names {name}, which is not a file"
        quoted, lines = block.splitlines(), source.read_text().splitlines()
        indents = [s[: len(s) - len(quoted[0])] for s in lines]
        assert any(
            lines[i].endswith(quoted[0]) and not indents[i].strip(" ")
            and lines[i:i + len(quoted)] == [indents[i] + q for q in quoted]
            for i in range(len(lines))
        ), f"the block of {guide.name} from {name} is not copied from it:\n{block}"
    print(f"{guide.name}: {len(blocks)} drupal_basic blocks")
PY
echo "drupal guide fences ok"
