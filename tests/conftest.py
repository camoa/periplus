"""Setup shared across the test files."""

import os


def pytest_report_header() -> str:
    """The machine's load when the run starts, so a timing on the record carries its load."""
    return "load average at start: " + " ".join(f"{x:.2f}" for x in os.getloadavg())
