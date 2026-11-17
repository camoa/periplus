"""A rule or span that runs long on one file is named on standard error while it runs, and the
map and the report stay the same bytes."""

from __future__ import annotations

import signal
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from test_demo_a_support import pin, plant, rutter

from periplus.cli import main
from periplus.map import MapReport, render_json, render_text, run
from periplus.preflight import check_runtime_dependencies

# A run of letters that ends in no letter makes the second branch backtrack 2**n times, and
# never match; the first branch matches a word after the run, so a rule stopped early loses it.
RUNAWAY = "z(?<name>\\w+)|(?:a+)+$"

MANIFEST = """\
pack: slowpack
version: 0.0.1
depends: []
folders:
  src: ./src/**
files:
  types:
    txt:
      endings: [txt]
      reader: text
{spans}"""

SPANS = """\
      spans:
      - {name: runaway, open: '(?:a+)+$', balance: ['{', '}']}
"""

RULES = """\
node_types:
- {name: slowpack.word, id_namespace: slowpack.word}
rules:
- rule: word
  reads: file
  in: [src]
  match: {file: '*', filetype: txt, text: 'word (?<name>\\w+)'}
  id: {from: {capture: name}}
  emits: [{node: {type: slowpack.word}}]
  confidence: declared
"""

SLOW_RULE = f"""\
- rule: slow
  reads: file
  in: [src]
  match: {{file: '*', filetype: txt, text: '{RUNAWAY}'}}
  id: {{from: {{capture: name}}}}
  emits: [{{node: {{type: slowpack.word}}}}]
  confidence: declared
"""


class _Clocked:
    """Standard error that keeps each write with the time it was made."""

    def __init__(self) -> None:
        self.writes: list[tuple[float, str]] = []

    def write(self, text: str) -> int:
        self.writes.append((time.monotonic(), text))
        return len(text)

    def flush(self) -> None:
        pass

    @property
    def text(self) -> str:
        return "".join(text for _, text in self.writes)


def _project(root: Path, letters: int, *, span: bool = False) -> None:
    rutter(
        root,
        "slowpack",
        MANIFEST.format(spans=SPANS if span else ""),
        {"words.yaml": RULES + ("" if span else SLOW_RULE)},
    )
    pin(root, "slowpack@0.0.1")
    plant(root, {"src/one.txt": "word hello\n" + "a" * letters + "!\nzed\n"})


def _map(root: Path, slow_after: float, output: str = "map.json") -> MapReport:
    return run(
        start=root,
        env={"PERIPLUS_CONFIG_DIR": str(root / "_config")},
        dependencies=check_runtime_dependencies(),
        output=Path(output),
        slow_after=slow_after,
    )


@contextmanager
def _listening() -> Iterator[_Clocked]:
    """Standard error caught with its times, set inside the test: pytest sets its own at the
    start of the call, over one a fixture set."""
    clocked = _Clocked()
    with patch.object(sys, "stderr", clocked):
        yield clocked


def test_the_warning_names_the_rutter_rule_and_file_while_the_match_still_runs(
    tmp_path: Path,
) -> None:
    with _listening() as stderr:
        _project(tmp_path, 24)
        started = time.monotonic()
        report = _map(tmp_path, 0.05)
        finished = time.monotonic()
        assert report.exit_code == 0
        lines = [(at, text) for at, text in stderr.writes if text.strip()]
        assert len(lines) == 2, stderr.text
        (warned_at, warning), (_, took) = lines
        assert warning.startswith(
            "periplus map: slow: rule slow of rutter slowpack on src/one.txt: "
        )
        assert warning.rstrip().endswith("s so far, still running")
        assert took.startswith(
            "periplus map: slow: rule slow of rutter slowpack on src/one.txt: took "
        )
        # The line comes near the threshold, well before the match ends.
        assert warned_at - started < 1.0
        assert finished - warned_at > 0.15, (warned_at - started, finished - started)


def test_a_span_that_runs_long_is_named_by_its_rutter_and_name(tmp_path: Path) -> None:
    with _listening() as stderr:
        _project(tmp_path, 20, span=True)
        _map(tmp_path, 0.005)
        assert "periplus map: slow: span runaway of rutter slowpack on src/one.txt: " in stderr.text
        assert "rule word" not in stderr.text


def test_nothing_is_written_under_the_threshold(tmp_path: Path) -> None:
    with _listening() as stderr:
        _project(tmp_path, 18, span=True)
        _map(tmp_path, 5.0)
        assert stderr.text == ""


def test_the_map_and_the_report_are_the_same_bytes_whether_the_warning_fires_or_not(
    tmp_path: Path,
) -> None:
    with _listening() as stderr:
        _project(tmp_path, 20)
        quiet = _map(tmp_path, 60.0, "quiet.json")
        assert stderr.text == ""
        loud = _map(tmp_path, 0.005, "loud.json")
        assert "rule slow" in stderr.text
        assert (tmp_path / "quiet.json").read_bytes() == (tmp_path / "loud.json").read_bytes()
        # The word after the slow run is found though the warning fired before the rule reached it.
        assert '"slowpack.word::ed"' in (tmp_path / "loud.json").read_text()
        assert loud.exit_code == quiet.exit_code == 0
        assert render_text(loud).replace("loud.json", "x") == render_text(quiet).replace(
            "quiet.json", "x"
        )
        assert render_json(loud).replace("loud.json", "x") == render_json(quiet).replace(
            "quiet.json", "x"
        )


def test_no_timer_handler_or_thread_is_left_after_the_map(tmp_path: Path) -> None:
    with _listening() as stderr:
        _project(tmp_path, 20)
        handler, threads = signal.getsignal(signal.SIGALRM), threading.active_count()
        _map(tmp_path, 0.005)
        assert "rule slow" in stderr.text
        assert signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0)
        assert signal.getsignal(signal.SIGALRM) is handler
        assert threading.active_count() == threads


def test_the_slow_after_option_sets_the_threshold(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with _listening() as stderr:
        _project(tmp_path, 20)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("PERIPLUS_CONFIG_DIR", str(tmp_path / "_config"))
        assert main(["map", "--output", "a.json"]) == 0
        assert stderr.text == ""
        assert main(["map", "--output", "b.json", "--slow-after", "0.005"]) == 0
        assert "rule slow of rutter slowpack" in stderr.text
        with pytest.raises(SystemExit) as refused:
            main(["map", "--slow-after", "0"])
        assert refused.value.code == 2
