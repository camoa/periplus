"""Plant a rutter in a project's own packs folder and map the project in-process.

Shared by the ``test_demo_a_*`` files, which carry the checks that used to be demo scripts. It
holds no test.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from periplus.map import MapReport, run
from periplus.preflight import check_runtime_dependencies


def plant(root: Path, files: dict[str, str | bytes]) -> None:
    """Write each file under ``root``, making the folders it needs."""
    for name, body in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(body, bytes):
            path.write_bytes(body)
        else:
            path.write_text(body)


def rutter(root: Path, name: str, manifest: str, rules: dict[str, str] | None = None) -> None:
    """Write ``name@0.0.1`` under the project's packs folder: its manifest and its rule files."""
    folder = f".periplus/packs/{name}@0.0.1"
    plant(root, {f"{folder}/pack.yaml": manifest})
    plant(root, {f"{folder}/rules/{file}": body for file, body in (rules or {}).items()})


def pin(root: Path, *pins: str) -> None:
    """Write the project's settings file pinning the packs."""
    plant(root, {".periplus/settings.yml": "periplus_version: 0\npacks:\n" + "".join(
        f"  - {each}\n" for each in pins
    )})


def map_project(root: Path) -> tuple[MapReport, dict[str, Any]]:
    """Map the project; the document is empty when nothing was written."""
    report = run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "_config")},
        dependencies=check_runtime_dependencies(),
        output=Path("map.json"),
    )
    document = json.loads((root / "map.json").read_text()) if report.map_path else {}
    return report, document


def mapped(root: Path) -> dict[str, Any]:
    """Map the project, which must run without a problem or a rule left unexecuted."""
    report, document = map_project(root)
    assert report.problems == () and report.not_executed == (), report
    return document


def nodes(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {node["id"]: node for node in document["nodes"]}


def edges(document: dict[str, Any], kind: str | None = None) -> set[tuple[str, str, str]]:
    return {
        (edge["kind"], edge["from"], edge["to"])
        for edge in document["edges"]
        if kind is None or edge["kind"] == kind
    }
