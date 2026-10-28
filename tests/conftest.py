"""Setup shared across the test files."""

import fcntl
import json
import os
import subprocess

import pytest


def pytest_report_header() -> str:
    """The machine's load when the run starts, so a timing on the record carries its load."""
    return "load average at start: " + " ".join(f"{x:.2f}" for x in os.getloadavg())


@pytest.fixture(scope="session")
def guide_real_page_check(
    tmp_path_factory: pytest.TempPathFactory,
) -> subprocess.CompletedProcess[str]:
    """One run of the map report guide check over the real page, every block, for the session.

    xdist runs a session fixture once per worker, so the first worker runs the check under a lock
    in the folder the workers share and the others read its result back.
    """
    from test_map_report_guide import _run_check

    run_id = os.environ.get("PYTEST_XDIST_TESTRUNUID")
    if not run_id:
        return _run_check(None)
    shared = tmp_path_factory.getbasetemp().parent / f"guide-real-page-check-{run_id}"
    with shared.with_suffix(".lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        result_file = shared.with_suffix(".json")
        if result_file.is_file():
            saved = json.loads(result_file.read_text(encoding="utf-8"))
            return subprocess.CompletedProcess(
                saved["args"], saved["returncode"], saved["stdout"], saved["stderr"]
            )
        run = _run_check(None)
        saved = {"args": [str(a) for a in run.args], "returncode": run.returncode,
                 "stdout": run.stdout, "stderr": run.stderr}
        result_file.write_text(json.dumps(saved), encoding="utf-8")
        return run
