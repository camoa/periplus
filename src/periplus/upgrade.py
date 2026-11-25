"""``periplus upgrade``: ask PyPI for the newest release and upgrade the way Periplus was installed.

The only command that reaches the network, and only when a person runs it. How Periplus was
installed is read from what Python records: the distribution's ``INSTALLER`` and
``direct_url.json``, and the marker file each tool leaves in the environment it made. ``uv tool``
writes ``uv-receipt.toml`` and ``pipx`` writes ``pipx_metadata.json`` at the environment's root.

``_fetch``, ``_run``, ``_output`` and ``_here`` are the seams the tests replace. Each new process
starts its interpreter with ``-I``, so it loads the installed package and not one in the working
directory.
"""

from __future__ import annotations

import http.client
import importlib.metadata
import importlib.resources
import json
import re
import shlex
import subprocess
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from periplus import DISTRIBUTION
from periplus.errors import ExitCode
from periplus.skills_install import SKILLS_DIRECTORY

__all__ = ["Here", "upgrade"]

PYPI_URL = f"https://pypi.org/pypi/{DISTRIBUTION}/json"
TIMEOUT_SECONDS = 10
#: A final release, such as ``0.10.3``. A pre-release or a development release does not match.
_FINAL = re.compile(r"\d+(?:\.\d+)*")
_REFRESH_SKILLS = "from periplus.cli import main; raise SystemExit(main(['skills', 'install']))"
_READ_VERSION = f"import importlib.metadata as m; print(m.version('{DISTRIBUTION}'))"


@dataclass(frozen=True, slots=True)
class Here:
    """The installed distribution, the environment it sits in, and the package that is running."""

    distribution: importlib.metadata.Distribution
    prefix: Path
    package: Path


def _here() -> Here:
    return Here(
        importlib.metadata.distribution(DISTRIBUTION),
        Path(sys.prefix),
        Path(__file__).parent,
    )


def _fetch() -> bytes:
    with urllib.request.urlopen(PYPI_URL, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
        body: bytes = response.read()
    return body


def _run(command: list[str]) -> int:
    return subprocess.run(command, check=False).returncode  # noqa: S603


def _output(command: list[str]) -> str:
    return subprocess.run(command, check=True, capture_output=True, text=True).stdout  # noqa: S603


def _release(version: str) -> tuple[int, ...]:
    """The release numbers without trailing zeros, so ``1.0`` and ``1.0.0`` compare equal."""
    match = _FINAL.match(version)
    parts = [int(part) for part in match.group().split(".")] if match else []
    while parts and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def _newest(body: bytes) -> str:
    releases = json.loads(body)["releases"]
    final = [version for version in releases if _FINAL.fullmatch(version)]
    if not final:
        raise ValueError("PyPI lists no final release")
    return str(max(final, key=_release))


def _direct(here: Here) -> dict[str, object] | None:
    """The distribution's ``direct_url.json``. ``ValueError`` when it is not a JSON object."""
    direct = json.loads(here.distribution.read_text("direct_url.json") or "null")
    if direct is not None and not isinstance(direct, dict):
        raise ValueError("direct_url.json is not an object")
    return direct


def _found(here: Here) -> str:
    installer = (here.distribution.read_text("INSTALLER") or "").strip()
    return f"installer {installer or 'unknown'}, environment {here.prefix}"


def _local(here: Here, direct: dict[str, object] | None) -> str | None:
    """The line for an install from a folder, which this command does not upgrade, or None."""
    url = str(direct.get("url", "")) if direct is not None else ""
    folder = urllib.request.url2pathname(urllib.parse.urlparse(url).path) if url else ""
    info = direct.get("dir_info") if direct is not None else None
    if isinstance(info, dict) and not info.get("editable"):
        return (
            f"Periplus was installed from the local folder {folder}. "
            "Install it again from that folder."
        )
    installed_at = Path(str(here.distribution.locate_file("periplus"))).resolve()
    if isinstance(info, dict) or installed_at != here.package.resolve():
        return (
            f"Periplus runs from a source checkout: {folder or here.package}. Update it with git."
        )
    return None


def _command(here: Here, direct: dict[str, object] | None) -> list[str] | str:
    """The upgrade command, or what was found when no command fits."""
    installer = (here.distribution.read_text("INSTALLER") or "").strip()
    if direct is None and (here.prefix / "uv-receipt.toml").is_file():
        return ["uv", "tool", "upgrade", DISTRIBUTION]
    if direct is None and (here.prefix / "pipx_metadata.json").is_file():
        return ["pipx", "upgrade", DISTRIBUTION]
    if direct is None and installer == "uv":
        return ["uv", "pip", "install", "--upgrade", DISTRIBUTION, "--python", sys.executable]
    if direct is None and installer == "pip":
        return [sys.executable, "-m", "pip", "install", "--upgrade", DISTRIBUTION]
    return _found(here) + (f", installed from {direct.get('url')}" if direct is not None else "")


def _unknown(found: str) -> int:
    generic = shlex.join([sys.executable, "-m", "pip", "install", "--upgrade", DISTRIBUTION])
    print(f"periplus: cannot tell how {DISTRIBUTION} was installed: {found}.", file=sys.stderr)
    print(
        f"periplus: upgrade it with the tool that installed it, such as: {generic}", file=sys.stderr
    )
    return ExitCode.UPGRADE_FAILED


def _skills_installed(home: Path) -> bool:
    shipped = importlib.resources.files("periplus") / SKILLS_DIRECTORY
    skills = home / ".claude" / "skills"
    return any(entry.is_dir() and (skills / entry.name).is_dir() for entry in shipped.iterdir())


def upgrade(*, check: bool, home: Path) -> int:
    """Upgrade Periplus when PyPI holds a newer release, or with ``check`` say what would run."""
    try:
        here = _here()
    except importlib.metadata.PackageNotFoundError:
        return _unknown(f"no {DISTRIBUTION} metadata in {sys.prefix}")
    installed = here.distribution.version
    try:
        newest = _newest(_fetch())
    except (OSError, http.client.HTTPException, ValueError, KeyError, TypeError) as error:
        print(f"periplus: cannot read the newest version from PyPI: {error}", file=sys.stderr)
        return ExitCode.UPGRADE_FAILED
    if _release(installed) >= _release(newest):
        print(f"{DISTRIBUTION} {installed} is up to date. The newest on PyPI is {newest}.")
        return ExitCode.OK

    try:
        direct = _direct(here)
    except ValueError:
        return _unknown(_found(here) + ", direct_url.json cannot be read")
    local = _local(here, direct)
    if local is not None:
        print(local)
        return ExitCode.OK
    command = _command(here, direct)
    if isinstance(command, str):
        return _unknown(command)
    if check:
        print(f"installed: {installed}\nnewest: {newest}\ncommand: {shlex.join(command)}")
        return ExitCode.OK

    print(f"{DISTRIBUTION} {installed} is installed. The newest is {newest}.")
    print(f"running: {shlex.join(command)}", flush=True)
    try:
        status = _run(command)
    except OSError as error:
        status, reason = -1, str(error)
    else:
        reason = f"exit {status}"
    if status != 0:
        print(f"periplus: the upgrade failed: {shlex.join(command)}: {reason}", file=sys.stderr)
        return ExitCode.UPGRADE_FAILED

    try:
        now = _output([sys.executable, "-I", "-c", _READ_VERSION]).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        print(
            f"periplus: the installer ran, but the version cannot be read: {error}", file=sys.stderr
        )
        return ExitCode.UPGRADE_FAILED
    if now == installed:
        print(
            f"periplus: the installer ran, but {DISTRIBUTION} is still {installed}, "
            "as when the install is pinned to one version.",
            file=sys.stderr,
        )
        return ExitCode.UPGRADE_FAILED

    if _skills_installed(home):
        print("refreshing the skills in ~/.claude/skills", flush=True)
        try:
            status = _run([sys.executable, "-I", "-c", _REFRESH_SKILLS])
        except OSError:
            status = -1
        if status != 0:
            print(
                "periplus: the skills were not refreshed. Run periplus skills install.",
                file=sys.stderr,
            )
            return ExitCode.UPGRADE_FAILED
    else:
        print("No Periplus skills are installed. Run periplus skills install to add them.")
    print("Run periplus update in each project to move its rutter pins.")
    return ExitCode.OK
