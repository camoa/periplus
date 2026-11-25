"""``periplus upgrade``: ask PyPI for the newest release and upgrade the way Periplus was installed.

No test reaches the network or runs an installer: the fetch, the process runner and the running
install are replaced through ``periplus.upgrade``'s three seams.
"""

from __future__ import annotations

import http.client
import importlib.metadata
import json
import shlex
import subprocess
import sys
from collections.abc import Sequence
from importlib.metadata import PathDistribution
from pathlib import Path
from typing import Any
from urllib.error import URLError

import pytest

import periplus.upgrade as upgrade
from periplus.cli import main
from periplus.errors import ExitCode


def _pypi(*versions: str) -> bytes:
    return json.dumps(
        {"releases": {v: [{"filename": f"periplus_map-{v}.whl"}] for v in versions}}
    ).encode()


def _install(
    tmp_path: Path,
    *,
    version: str = "0.10.2",
    installer: str | None = "pip",
    marker: str | None = None,
    direct_url: dict[str, Any] | None = None,
    from_the_distribution: bool = True,
) -> upgrade.Here:
    prefix = tmp_path / "env"
    site = prefix / "lib" / "site-packages"
    info = site / f"periplus_map-{version}.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: periplus-map\nVersion: {version}\n", encoding="utf-8"
    )
    if installer is not None:
        (info / "INSTALLER").write_text(installer + "\n", encoding="utf-8")
    if direct_url is not None:
        (info / "direct_url.json").write_text(json.dumps(direct_url), encoding="utf-8")
    if marker is not None:
        (prefix / marker).write_text("", encoding="utf-8")
    package = site / "periplus" if from_the_distribution else tmp_path / "checkout/src/periplus"
    package.mkdir(parents=True)
    return upgrade.Here(PathDistribution(info), prefix, package)


class Runner:
    """Records each command and answers with a status, or raises for a program that is absent.

    ``output`` stands in for the new process that reads the installed version after an upgrade.
    """

    def __init__(
        self, codes: Sequence[int | OSError] = (), after: str | Exception = "0.10.3"
    ) -> None:
        self.ran: list[list[str]] = []
        self.read: list[list[str]] = []
        self.codes = list(codes)
        self.after = after

    def output(self, command: list[str]) -> str:
        self.read.append(command)
        if isinstance(self.after, Exception):
            raise self.after
        return self.after + "\n"

    def __call__(self, command: list[str]) -> int:
        self.ran.append(command)
        answer = self.codes.pop(0) if self.codes else 0
        if isinstance(answer, OSError):
            raise answer
        return answer


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    folder = tmp_path / "home"
    folder.mkdir()
    monkeypatch.setenv("HOME", str(folder))
    return folder


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    here: upgrade.Here,
    pypi: bytes | Exception = b"",
    runner: Runner | None = None,
) -> Runner:
    def fetch() -> bytes:
        if isinstance(pypi, Exception):
            raise pypi
        return pypi

    runner = runner or Runner()
    monkeypatch.setattr(upgrade, "_here", lambda: here)
    monkeypatch.setattr(upgrade, "_fetch", fetch)
    monkeypatch.setattr(upgrade, "_run", runner)
    monkeypatch.setattr(upgrade, "_output", runner.output)
    return runner


def test_upgrade_failed_is_exit_35() -> None:
    assert ExitCode.UPGRADE_FAILED == 35


def test_the_newest_installed_says_so_in_one_line_and_runs_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    here = _install(tmp_path, version="0.10.2")
    runner = _wire(monkeypatch, here, _pypi("0.9.0", "0.10.2", "0.11.0rc1", "0.11.0.dev1"))
    assert main(["upgrade"]) == ExitCode.OK
    out = capsys.readouterr().out
    assert out == "periplus-map 0.10.2 is up to date. The newest on PyPI is 0.10.2.\n"
    assert runner.ran == []


def test_versions_compare_as_numbers_not_as_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    here = _install(tmp_path, version="0.9.0", marker="uv-receipt.toml", installer="uv")
    _wire(monkeypatch, here, _pypi("0.9.0", "0.10.0"))
    assert main(["upgrade", "--check"]) == ExitCode.OK
    assert "newest: 0.10.0" in capsys.readouterr().out


def test_check_prints_both_versions_and_the_command_and_runs_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    here = _install(tmp_path, installer="uv", marker="uv-receipt.toml")
    runner = _wire(monkeypatch, here, _pypi("0.10.2", "0.10.3"))
    assert main(["upgrade", "--check"]) == ExitCode.OK
    assert capsys.readouterr().out == (
        "installed: 0.10.2\nnewest: 0.10.3\ncommand: uv tool upgrade periplus-map\n"
    )
    assert runner.ran == []


@pytest.mark.parametrize(
    ("installer", "marker", "command"),
    [
        ("uv", "uv-receipt.toml", ["uv", "tool", "upgrade", "periplus-map"]),
        ("pip", "pipx_metadata.json", ["pipx", "upgrade", "periplus-map"]),
        (
            "uv",
            None,
            ["uv", "pip", "install", "--upgrade", "periplus-map", "--python", sys.executable],
        ),
        ("pip", None, [sys.executable, "-m", "pip", "install", "--upgrade", "periplus-map"]),
    ],
    ids=["uv-tool", "pipx", "uv-pip", "pip"],
)
def test_each_install_kind_runs_its_own_upgrade_command(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    home: Path,
    capsys: pytest.CaptureFixture[str],
    installer: str,
    marker: str | None,
    command: list[str],
) -> None:
    here = _install(tmp_path, installer=installer, marker=marker)
    runner = _wire(monkeypatch, here, _pypi("0.10.2", "0.10.3"))
    assert main(["upgrade"]) == ExitCode.OK
    assert runner.ran == [command]
    assert f"running: {shlex.join(command)}\n" in capsys.readouterr().out


def test_an_upgrade_refreshes_installed_skills_with_the_new_program_and_names_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (home / ".claude/skills/periplus-map").mkdir(parents=True)
    here = _install(tmp_path, installer="uv", marker="uv-receipt.toml")
    runner = _wire(monkeypatch, here, _pypi("0.10.3"))
    assert main(["upgrade"]) == ExitCode.OK
    assert len(runner.ran) == 2
    child = runner.ran[1]
    assert child[:2] == [sys.executable, "-I"]
    assert "main(['skills', 'install'])" in child[-1]
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "periplus-map 0.10.2 is installed. The newest is 0.10.3."
    assert out.rstrip("\n").splitlines()[-1] == (
        "Run periplus update in each project to move its rutter pins."
    )


def test_an_upgrade_without_installed_skills_writes_none_and_says_how(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (home / ".claude/skills/some-other-skill").mkdir(parents=True)
    here = _install(tmp_path)
    runner = _wire(monkeypatch, here, _pypi("0.10.3"))
    assert main(["upgrade"]) == ExitCode.OK
    assert len(runner.ran) == 1
    out = capsys.readouterr().out
    assert "No Periplus skills are installed. Run periplus skills install to add them.\n" in out
    assert "Run periplus update in each project to move its rutter pins.\n" in out


def test_a_failed_skills_refresh_exits_35(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (home / ".claude/skills/periplus-map").mkdir(parents=True)
    here = _install(tmp_path)
    _wire(monkeypatch, here, _pypi("0.10.3"), Runner([0, 27]))
    assert main(["upgrade"]) == ExitCode.UPGRADE_FAILED
    assert "periplus skills install" in capsys.readouterr().err


def test_a_skills_refresh_that_cannot_start_exits_35_with_one_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (home / ".claude/skills/periplus-map").mkdir(parents=True)
    _wire(monkeypatch, _install(tmp_path), _pypi("0.10.3"), Runner([0, OSError(8, "Exec format")]))
    assert main(["upgrade"]) == ExitCode.UPGRADE_FAILED
    err = capsys.readouterr().err
    assert err.count("\n") == 1
    assert err.startswith("periplus: the skills were not refreshed")


def test_after_the_installer_the_version_is_read_by_a_new_isolated_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path
) -> None:
    runner = _wire(monkeypatch, _install(tmp_path), _pypi("0.10.3"))
    assert main(["upgrade"]) == ExitCode.OK
    assert len(runner.read) == 1
    assert runner.read[0][:2] == [sys.executable, "-I"]
    assert "periplus-map" in runner.read[0][-1]


@pytest.mark.parametrize(
    "after",
    ["0.10.2", OSError(2, "No such file"), subprocess.CalledProcessError(1, "python")],
    ids=["unchanged", "cannot-start", "cannot-read"],
)
def test_an_installer_that_changed_nothing_is_not_a_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    home: Path,
    capsys: pytest.CaptureFixture[str],
    after: str | Exception,
) -> None:
    (home / ".claude/skills/periplus-map").mkdir(parents=True)
    here = _install(tmp_path, installer="uv", marker="uv-receipt.toml")
    runner = _wire(monkeypatch, here, _pypi("0.10.3"), Runner(after=after))
    assert main(["upgrade"]) == ExitCode.UPGRADE_FAILED
    assert len(runner.ran) == 1
    captured = capsys.readouterr()
    assert "periplus update" not in captured.out
    assert captured.err.count("\n") == 1
    assert captured.err.startswith("periplus: the installer ran")
    if after == "0.10.2":
        assert "is still 0.10.2" in captured.err


@pytest.mark.parametrize(
    "answer", [1, FileNotFoundError(2, "No such file or directory")], ids=["exit-1", "absent"]
)
def test_a_failed_upgrade_prints_the_error_exits_35_and_refreshes_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    home: Path,
    capsys: pytest.CaptureFixture[str],
    answer: int | OSError,
) -> None:
    (home / ".claude/skills/periplus-map").mkdir(parents=True)
    here = _install(tmp_path, installer="uv", marker="uv-receipt.toml")
    runner = _wire(monkeypatch, here, _pypi("0.10.3"), Runner([answer]))
    assert main(["upgrade"]) == ExitCode.UPGRADE_FAILED
    assert len(runner.ran) == 1
    err = capsys.readouterr().err
    assert err.startswith("periplus: the upgrade failed: uv tool upgrade periplus-map")


@pytest.mark.parametrize(
    "pypi", [URLError("timed out"), TimeoutError("timed out"), http.client.IncompleteRead(b"{")]
)
def test_pypi_out_of_reach_exits_35_and_runs_nothing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    home: Path,
    capsys: pytest.CaptureFixture[str],
    pypi: Exception,
) -> None:
    runner = _wire(monkeypatch, _install(tmp_path), pypi)
    assert main(["upgrade"]) == ExitCode.UPGRADE_FAILED
    assert capsys.readouterr().err.startswith("periplus: cannot read the newest version from PyPI:")
    assert runner.ran == []


def test_an_answer_that_is_not_json_exits_35(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    runner = _wire(monkeypatch, _install(tmp_path), b"<html>")
    assert main(["upgrade"]) == ExitCode.UPGRADE_FAILED
    assert "cannot read the newest version from PyPI" in capsys.readouterr().err
    assert runner.ran == []


@pytest.mark.parametrize(
    ("direct_url", "from_the_distribution", "line"),
    [
        (
            {"url": "file:///work/periplus", "dir_info": {"editable": True}},
            False,
            "Periplus runs from a source checkout: /work/periplus. Update it with git.",
        ),
        (
            {"url": "file:///work/periplus", "dir_info": {}},
            True,
            "Periplus was installed from the local folder /work/periplus. "
            "Install it again from that folder.",
        ),
        (None, False, "Periplus runs from a source checkout: {package}. Update it with git."),
    ],
    ids=["editable", "local-folder", "running-elsewhere"],
)
@pytest.mark.parametrize("check", [[], ["--check"]], ids=["run", "check"])
def test_a_source_checkout_is_not_upgraded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    home: Path,
    capsys: pytest.CaptureFixture[str],
    direct_url: dict[str, Any] | None,
    from_the_distribution: bool,
    line: str,
    check: list[str],
) -> None:
    here = _install(
        tmp_path, installer="uv", direct_url=direct_url, from_the_distribution=from_the_distribution
    )
    runner = _wire(monkeypatch, here, _pypi("0.10.3"))
    assert main(["upgrade", *check]) == ExitCode.OK
    assert capsys.readouterr().out == line.format(package=here.package) + "\n"
    assert runner.ran == []


@pytest.mark.parametrize("check", [[], ["--check"]], ids=["run", "check"])
def test_an_unknown_install_prints_what_was_found_and_the_pip_command_and_exits_35(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    home: Path,
    capsys: pytest.CaptureFixture[str],
    check: list[str],
) -> None:
    here = _install(tmp_path, installer="conda")
    runner = _wire(monkeypatch, here, _pypi("0.10.3"))
    assert main(["upgrade", *check]) == ExitCode.UPGRADE_FAILED
    err = capsys.readouterr().err
    assert "installer conda" in err
    assert str(here.prefix) in err
    assert f"{sys.executable} -m pip install --upgrade periplus-map" in err
    assert runner.ran == []


def test_no_installed_distribution_is_an_unknown_install(
    monkeypatch: pytest.MonkeyPatch, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def absent() -> upgrade.Here:
        raise importlib.metadata.PackageNotFoundError("periplus-map")

    runner = _wire(monkeypatch, upgrade.Here(PathDistribution(Path()), Path(), Path()), b"")
    monkeypatch.setattr(upgrade, "_here", absent)
    assert main(["upgrade"]) == ExitCode.UPGRADE_FAILED
    assert "cannot tell how periplus-map was installed" in capsys.readouterr().err
    assert runner.ran == []


def test_a_damaged_direct_url_is_an_unknown_install(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    here = _install(tmp_path, installer="uv", marker="uv-receipt.toml")
    (tmp_path / "env/lib/site-packages/periplus_map-0.10.2.dist-info/direct_url.json").write_text(
        '{"url": ', encoding="utf-8"
    )
    runner = _wire(monkeypatch, here, _pypi("0.10.3"))
    assert main(["upgrade"]) == ExitCode.UPGRADE_FAILED
    assert "cannot tell how periplus-map was installed" in capsys.readouterr().err
    assert runner.ran == []


@pytest.mark.parametrize(("installed", "newest"), [("1.0", "1.0.0"), ("1.0.0", "1.0")])
def test_trailing_zeros_do_not_make_a_version_newer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    home: Path,
    capsys: pytest.CaptureFixture[str],
    installed: str,
    newest: str,
) -> None:
    runner = _wire(monkeypatch, _install(tmp_path, version=installed), _pypi(newest))
    assert main(["upgrade"]) == ExitCode.OK
    assert "is up to date" in capsys.readouterr().out
    assert runner.ran == []


def test_this_checkout_reads_as_a_source_checkout_named_by_its_folder(
    monkeypatch: pytest.MonkeyPatch, home: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The real ``_here`` on the environment the tests run in, an editable install of a checkout."""
    runner = Runner()
    monkeypatch.setattr(upgrade, "_fetch", lambda: _pypi("999.0.0"))
    monkeypatch.setattr(upgrade, "_run", runner)
    assert main(["upgrade"]) == ExitCode.OK
    out = capsys.readouterr().out
    prefix, suffix = "Periplus runs from a source checkout: ", ". Update it with git.\n"
    assert out.startswith(prefix)
    assert out.endswith(suffix)
    assert (Path(out[len(prefix) : -len(suffix)]) / "pyproject.toml").is_file()
    assert runner.ran == []
