"""A single-block map-report guide check maps the example tree once (c2)."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CHECK = ROOT / "scripts" / "demo.d" / "99zd-map-report-guide.sh"
REAL_PERIPLUS = Path(sys.executable).parent / "periplus"

# Block 1 of the guide is a `periplus show ...` run in the example project, so it is a block
# other than 0 whose own command is not a map.
SINGLE_BLOCK = "1"

STAND_IN = """#!/bin/bash
printf '%s\\t%s\\n' "$PWD" "$*" >> "$STAND_IN_LOG"
exec "$STAND_IN_REAL" "$@"
"""


@pytest.mark.criterion(id="c2")
def test_single_block_check_maps_the_example_tree_once_c2(tmp_path: Path) -> None:
    stand_in = tmp_path / "periplus"
    stand_in.write_text(STAND_IN)
    stand_in.chmod(0o755)
    log = tmp_path / "calls.log"
    log.write_text("")

    env = dict(os.environ)
    env.pop("GUIDE_DOC", None)
    env["ROOT"] = str(ROOT)
    env["PERIPLUS"] = str(stand_in)
    env["GUIDE_BLOCKS"] = SINGLE_BLOCK
    env["STAND_IN_LOG"] = str(log)
    env["STAND_IN_REAL"] = str(REAL_PERIPLUS)
    done = subprocess.run(  # noqa: S603 - fixed argv, repository-owned script
        [shutil.which("bash") or "/bin/bash", str(CHECK)],
        env=env,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert done.returncode == 0, done.stdout + done.stderr

    calls = [line.split("\t", 1) for line in log.read_text().splitlines()]
    maps_of_example = [
        (cwd, args)
        for cwd, args in calls
        if cwd.endswith("/project") and args.split()[:1] == ["map"]
    ]
    assert len(maps_of_example) == 1, maps_of_example
    assert "--format json" in maps_of_example[0][1], maps_of_example


@pytest.mark.criterion(id="c2")
def test_unselected_check_over_the_real_page_still_passes_c2(
    guide_real_page_check: subprocess.CompletedProcess[str],
) -> None:
    assert guide_real_page_check.returncode == 0, (
        guide_real_page_check.stdout + guide_real_page_check.stderr
    )
    assert guide_real_page_check.stdout.startswith("map report guide ok: ")
    assert guide_real_page_check.stdout.rstrip().endswith(" examples")
