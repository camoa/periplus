"""Setup shared across the test files."""

import subprocess

import pytest


@pytest.fixture(scope="session")
def guide_real_page_check() -> subprocess.CompletedProcess[str]:
    """One run of the map report guide check over the real page, every block, for the session."""
    from test_map_report_guide import _run_check

    return _run_check(None)
