"""``periplus update`` and a pack pinned at one version under two roots."""

from __future__ import annotations

from pathlib import Path

import pytest

from periplus.cli import main
from periplus.errors import ExitCode


def _site(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, pins: list[str]) -> Path:
    """A project pinning ``pins``, one extra root named in ``pack_paths``, and a user config dir."""
    root = tmp_path / "project"
    (root / ".periplus" / "packs").mkdir(parents=True)
    listing = "".join(f"  - {pin}\n" for pin in pins)
    (root / ".periplus" / "settings.yml").write_text(
        f"packs:\n{listing}pack_paths:\n  - ../extra\n", encoding="utf-8"
    )
    (tmp_path / "extra").mkdir()
    config = tmp_path / "userconf"
    config.mkdir()
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(config))
    monkeypatch.chdir(root)
    return root


def test_distinct_pins_in_two_roots_print_what_they_printed_before(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _site(tmp_path, monkeypatch, ["alpha@1.0.0", "beta@1.0.0"])
    (root / ".periplus" / "packs" / "alpha@1.0.0").mkdir()
    (tmp_path / "extra" / "beta@1.0.0").mkdir()

    code = main(["update"])

    assert code == 0
    assert capsys.readouterr().out == (
        "kept alpha@1.0.0: shipped from the project's own packs\n"
        "kept beta@1.0.0: shipped from a pack_paths root\n"
    )


def test_one_pin_in_two_roots_exits_with_the_duplicate_code_and_names_both_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _site(tmp_path, monkeypatch, ["dup@1.0.0"])
    (root / ".periplus" / "packs" / "dup@1.0.0").mkdir()
    (tmp_path / "extra" / "dup@1.0.0").mkdir()

    code = main(["update"])

    assert code == ExitCode.PIN_DUPLICATED
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "the pack directory 'dup@1.0.0' was found under more than one root"
    assert [line.strip() for line in lines[1:]] == [
        str(root / ".periplus" / "packs"),
        str(tmp_path / "extra"),
    ]


def test_roots_whose_names_hold_a_comma_and_space_print_whole_one_per_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "project, one"
    (root / ".periplus" / "packs" / "dup@1.0.0").mkdir(parents=True)
    (tmp_path / "extra, two" / "dup@1.0.0").mkdir(parents=True)
    (root / ".periplus" / "settings.yml").write_text(
        "packs:\n  - dup@1.0.0\npack_paths:\n  - ../extra, two\n", encoding="utf-8"
    )
    config = tmp_path / "userconf"
    config.mkdir()
    monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(config))
    monkeypatch.chdir(root)

    code = main(["update"])

    assert code == ExitCode.PIN_DUPLICATED
    lines = capsys.readouterr().out.splitlines()
    assert [line.strip() for line in lines[1:]] == [
        str(root / ".periplus" / "packs"),
        str(tmp_path / "extra, two"),
    ]
