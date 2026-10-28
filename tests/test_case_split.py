"""Tests of the case split: one test case per report key, altered guide block and selector value."""

import ast
import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"
GUIDE_FILE = "tests/test_map_report_guide.py"
FAST_FILE = "tests/test_suite_fast.py"
KEY_TEST = "test_check_fails_when_a_report_key_is_not_a_heading_or_code_term_c1"
BLOCK_TEST = "test_changed_fenced_output_fails_the_check_c5"
SELECTOR_TEST = "test_selector_runs_each_block_alone_and_none_runs_only_the_checks_c2"
VARIANTS = ("word", "trailing-space", "blank-line")
# Assert statements the two files held before the loops were split (28 and 88).
ASSERTS_BEFORE_SPLIT = 116


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"_split_{name}", TESTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _collected_ids() -> list[str]:
    run = subprocess.run(  # noqa: S603 - fixed argv
        [
            sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider",
            GUIDE_FILE, FAST_FILE,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=300,
    )
    assert run.returncode == 0, run.stdout[-2000:] + run.stderr[-1000:]
    return [line for line in run.stdout.splitlines() if "::" in line]


def _cases(ids: list[str], file: str, test: str) -> set[str]:
    prefix = f"{file}::{test}["
    return {i[len(prefix) : -1] for i in ids if i.startswith(prefix) and i.endswith("]")}


@pytest.mark.criterion(id="c3")
def test_collect_only_lists_one_case_per_key_block_and_selector_value_c3(tmp_path: Path) -> None:
    guide = _load("test_map_report_guide")
    fast = _load("test_suite_fast")
    ids = _collected_ids()

    live = guide._report_keys(tmp_path)
    assert len(live) >= 17, f"the live map report holds {len(live)} keys"
    assert sorted(getattr(guide, "REPORT_KEYS", [])) == live
    assert _cases(ids, GUIDE_FILE, KEY_TEST) == set(live)

    runs = guide._runs(guide._page_text())
    assert len(runs) >= 2
    wanted = {
        f"run{n}-{variant}"
        for n, match in enumerate(runs)
        if guide._output_line_index(match.group("body")) is not None
        for variant in VARIANTS
    }
    assert len(wanted) >= 6
    assert _cases(ids, GUIDE_FILE, BLOCK_TEST) >= wanted
    deleted = {
        f"run{n}-deleted"
        for n, match in enumerate(runs)
        if guide._output_line_index(match.group("body")) is not None
    }
    assert _cases(ids, GUIDE_FILE, BLOCK_TEST) == wanted | deleted

    blocks = fast._marker_count(fast._page())
    assert blocks >= 2
    assert _cases(ids, FAST_FILE, SELECTOR_TEST) == {str(k) for k in range(blocks)}


@pytest.mark.criterion(id="c3")
def test_the_two_guide_files_keep_every_assert_the_old_loops_held_c3() -> None:
    counts = {
        name: sum(
            isinstance(node, ast.Assert)
            for node in ast.walk(ast.parse((ROOT / name).read_text(encoding="utf-8")))
        )
        for name in (GUIDE_FILE, FAST_FILE)
    }
    assert sum(counts.values()) >= ASSERTS_BEFORE_SPLIT, counts
