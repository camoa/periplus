"""Shared helpers for the skill tests: the gap-read headings and a reader for one section."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADINGS = ("Resolution gaps", "Detail gaps", "Site faults", "Unknown boundaries", "Plain classes")


def _section(out: str, heading: str) -> list[str]:
    """The lines printed under `heading`, up to the next report heading."""
    inside: list[str] = []
    active = False
    for line in out.splitlines():
        bare = line.strip().lstrip("#").strip().rstrip(":")
        if bare in HEADINGS:
            active = bare == heading
            continue
        if active and line.strip():
            inside.append(line)
    return inside
