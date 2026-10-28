"""Plant a site under a folder and map it in-process, for the tests that replaced demo scripts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from periplus.map import MapReport, run
from periplus.preflight import check_runtime_dependencies


def plant(root: Path, files: Mapping[str, str]) -> None:
    """Write each file at its path below ``root``, making the folders."""
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def settings(*packs: str, values: str = "") -> dict[str, str]:
    """The project settings file, pinning ``packs``."""
    pins = "".join(f"  - {pack}\n" for pack in packs)
    return {".periplus/settings.yml": f"periplus_version: 0\npacks:\n{pins}{values}"}


def map_site(root: Path) -> tuple[MapReport, Any]:
    """Map ``root``; the document is ``None`` when the run wrote none."""
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    written = root / "map.json"
    return report, json.loads(written.read_text()) if written.exists() else None


def clean_map(root: Path) -> tuple[MapReport, Any]:
    """Map ``root`` and require a run with no problem, nothing unexecuted and a document."""
    report, document = map_site(root)
    assert report.problems == () and report.not_executed == (), report
    assert document is not None
    return report, document


def line_of(path: Path, text: str) -> int:
    """The one-based number of the first line of ``path`` that is ``text`` once stripped."""
    lines = path.read_text(encoding="utf-8").splitlines()
    return next(n for n, written in enumerate(lines, 1) if written.strip() == text)


def fires(report: MapReport) -> dict[tuple[str, str], int]:
    return {(pack, rule): count for pack, rule, count in report.executed}


def edge_set(document: Any, kind: str | None = None) -> set[tuple[str, str, str]]:
    return {(e["kind"], e["from"], e["to"]) for e in document["edges"] if kind in (None, e["kind"])}
