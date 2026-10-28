"""The map is the same bytes whatever the hash seed and the locale of the process that writes it.

This runs three operating-system processes. A hash seed and a locale differ only between
processes, so two in-process maps cannot show a set iterated into the document: both share one
seed and one dict ordering by construction.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from test_demo_b_support import plant, settings

SRC = Path(__file__).resolve().parent.parent / "src"

_CHILD = """
import locale, os, sys
from pathlib import Path

locale.setlocale(locale.LC_ALL, "")  # raises locale.Error when LC_ALL names a locale not installed

from periplus.map import run
from periplus.preflight import check_runtime_dependencies

root = Path(sys.argv[1])
report = run(
    start=root,
    env={"PERIPLUS_CONFIG_DIR": str(root / "config")},
    dependencies=check_runtime_dependencies(),
    output=Path("map.json"),
)
assert report.problems == (), report.problems
sys.stdout.buffer.write((root / "map.json").read_bytes())
"""

SERVICE = "<?php\n\nnamespace App\\Service;\n\nclass {0}\n{{\n    public function {1}() {{}}\n}}\n"

PAGE = """\
<?php

namespace App\\Web;

use App\\Service\\Alpha;
use App\\Service\\Beta;
use App\\Service\\Gamma;
use App\\Service\\Delta;

class Base
{
    public function boot() {}
}

class Page extends Base
{
    private Alpha $alpha;

    private Beta $beta;

    private Gamma $gamma;

    public function __construct(private Delta $delta)
    {
    }

    public function run(): void
    {
        $this->alpha->one();
        $this->beta->two();
        $this->gamma->three();
        $this->delta->four();
        $this->boot();
    }
}
"""


def _map_in_a_child(root: Path, **overrides: str) -> bytes:
    """Map ``root`` in a fresh interpreter, so hash seed and locale are this call's to choose."""
    env = {
        "PYTHONPATH": str(SRC),
        "PATH": os.environ.get("PATH", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        **overrides,
    }
    result = subprocess.run(  # noqa: S603 - list argv, shell unset, nothing interpolated
        [sys.executable, "-c", _CHILD, str(root)],
        capture_output=True,
        env=env,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode()
    return result.stdout


def test_three_processes_with_two_hash_seeds_and_two_locales_write_the_same_map(
    tmp_path: Path,
) -> None:
    """Many nodes and edges of one kind (classes, methods, call sites, calls), so a set iterated
    in place of a sorted list orders them one way under one seed and another under the next. The
    third run keeps seed 0 and changes the locale; a locale missing on the machine fails the run."""
    plant(
        tmp_path,
        {
            **settings("php_basic@0.2.0"),
            "src/Service/Alpha.php": SERVICE.format("Alpha", "one"),
            "src/Service/Beta.php": SERVICE.format("Beta", "two"),
            "src/Service/Gamma.php": SERVICE.format("Gamma", "three"),
            "src/Service/Delta.php": SERVICE.format("Delta", "four"),
            "src/Web/Page.php": PAGE,
        },
    )
    first = _map_in_a_child(tmp_path, PYTHONHASHSEED="0", LC_ALL="C")
    second = _map_in_a_child(tmp_path, PYTHONHASHSEED="2", LC_ALL="C")
    third = _map_in_a_child(tmp_path, PYTHONHASHSEED="0", LC_ALL="es_ES.utf8")
    assert first.count(b"php.method::") >= 6, first[:300]
    assert second == first
    assert third == first
