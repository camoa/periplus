"""Tests of the suite-fast task: a block selector for the guide check, one shared real-page run,
the eight JavaScript tests inside the CI venv, and no test lost."""

import ast
import importlib
import inspect
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "docs" / "map-report-guide.md"
CHECK = ROOT / "scripts" / "demo.d" / "99zd-map-report-guide.sh"
PERIPLUS = Path(sys.executable).parent / "periplus"
MARKER_RE = re.compile(r"^<!-- nav-run(?:: \S+)? -->$", re.M)
BLOCK_RE = re.compile(
    r"^<!-- nav-run(?:: \S+)? -->\n```[^\n]*\n(?P<body>.*?)^```$", re.M | re.S
)
FENCE_RE = re.compile(r"^```[^\n]*\n.*?^```$", re.M | re.S)
# One check call is long under load before the selector exists; the cap only stops a hang.
CALL_TIMEOUT = 600


def _check(
    blocks: str | None,
    doc: Path | None = None,
    root: Path = ROOT,
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "ROOT": str(root), "PERIPLUS": str(PERIPLUS)}
    env.pop("GUIDE_DOC", None)
    env.pop("GUIDE_BLOCKS", None)
    if doc is not None:
        env["GUIDE_DOC"] = str(doc)
    if blocks is not None:
        env["GUIDE_BLOCKS"] = blocks
    bash = shutil.which("bash") or "/bin/bash"
    return subprocess.run(  # noqa: S603 - fixed argv, repository-owned script
        [bash, str(root / "scripts" / "demo.d" / CHECK.name)],
        env=env,
        cwd=root,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=CALL_TIMEOUT,
    )


def _last(run: subprocess.CompletedProcess[str]) -> str:
    lines = (run.stdout or "").strip().splitlines()
    return lines[-1] if lines else ""


def _out(run: subprocess.CompletedProcess[str]) -> str:
    return f"exit {run.returncode}\n{run.stdout}\n{run.stderr}"


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def _marker_count(text: str) -> int:
    return len(MARKER_RE.findall(text))


@pytest.mark.criterion(id="c2")
@pytest.mark.parametrize("k", range(_marker_count(_page())))
def test_selector_runs_each_block_alone_and_none_runs_only_the_checks_c2(k: int) -> None:
    n = _marker_count(_page())
    assert n >= 2, "the page holds too few nav-run markers"
    run = _check(str(k))
    assert run.returncode == 0, f"GUIDE_BLOCKS={k}: " + _out(run)
    assert _last(run) == f"map report guide ok: block {k} of {n}", (
        f"GUIDE_BLOCKS={k}: " + _out(run)
    )
    # The checks below do not depend on the block, so one case runs them.
    if k != 0:
        return
    none = _check("none")
    assert none.returncode == 0, "GUIDE_BLOCKS=none: " + _out(none)
    assert _last(none) == f"map report guide ok: checks of {n}", _out(none)
    out_of_range = _check(str(n))
    assert out_of_range.returncode == 1, f"GUIDE_BLOCKS={n}: " + _out(out_of_range)
    assert (out_of_range.stdout + out_of_range.stderr).strip(), (
        "no message for an out-of-range block"
    )
    assert not _last(out_of_range).startswith("map report guide ok"), _out(out_of_range)
    unset = _check(None)
    assert unset.returncode == 0, "GUIDE_BLOCKS unset: " + _out(unset)
    assert _last(unset) == f"map report guide ok: {n} examples", _out(unset)


@pytest.mark.criterion(id="c2")
def test_selector_selects_the_altered_block_and_only_that_one_c2(tmp_path: Path) -> None:
    text = _page()
    blocks = list(BLOCK_RE.finditer(text))
    k, j = 1, 2
    assert len(blocks) > j and len(blocks) == _marker_count(text)
    body = blocks[k].group("body")
    lines = body.split("\n")
    assert lines[0].startswith("$ periplus "), lines[0]
    assert not lines[0].startswith("$ periplus map"), lines[0]
    last = max(i for i, line in enumerate(lines) if line)
    lines[last] += " CHANGED"
    altered = text[: blocks[k].start("body")] + "\n".join(lines) + text[blocks[k].end("body"):]
    doc = tmp_path / "altered.md"
    doc.write_text(altered, encoding="utf-8")

    under_k = _check(str(k), doc)
    assert under_k.returncode not in (0, 127), f"GUIDE_BLOCKS={k} passed an altered block {k}"
    assert not _last(under_k).startswith("map report guide ok"), _out(under_k)
    under_none = _check("none", doc)
    assert under_none.returncode == 0, (
        "GUIDE_BLOCKS=none failed on an altered block: " + _out(under_none)
    )
    assert _last(under_none).startswith("map report guide ok: checks of"), _out(under_none)
    under_j = _check(str(j), doc)
    assert under_j.returncode == 0, (
        f"GUIDE_BLOCKS={j} failed on block {k}'s alteration: " + _out(under_j)
    )
    assert _last(under_j).startswith(f"map report guide ok: block {j} of"), _out(under_j)


@pytest.mark.criterion(id="c2")
def test_none_still_fails_a_report_key_missing_from_headings_and_code_terms_c2(
    tmp_path: Path,
) -> None:
    control = _check("none")
    assert control.returncode == 0, "unchanged page under none: " + _out(control)
    assert _last(control).startswith("map report guide ok: checks of"), _out(control)

    key = "unread"
    text = _page()
    parts = FENCE_RE.split(text)
    fences = FENCE_RE.findall(text)
    word = re.escape(key)
    changed = []
    for part in parts:
        part = "\n".join(
            re.sub(r"(?<![\w.])" + word + r"(?![\w.])", "ZZ", ln) if ln.startswith("#") else ln
            for ln in part.split("\n")
        )
        changed.append(re.sub(r"`" + word + r"`", "`periplus " + key + "`", part))
    mutated = changed[0]
    for fence, part in zip(fences, changed[1:], strict=True):
        mutated += fence + part
    assert mutated != text
    doc = tmp_path / "no_key.md"
    doc.write_text(mutated, encoding="utf-8")
    run = _check("none", doc)
    assert run.returncode not in (0, 127), (
        "GUIDE_BLOCKS=none passed without a report key: " + _out(run)
    )
    assert not _last(run).startswith("map report guide ok"), _out(run)


@pytest.mark.criterion(id="c2")
def test_none_still_fails_a_copied_tree_whose_readme_has_no_link_row_c2(tmp_path: Path) -> None:
    copy_root = tmp_path / "tree"
    shutil.copytree(
        ROOT,
        copy_root,
        ignore=shutil.ignore_patterns(".venv", ".git", "node_modules", "__pycache__", ".*_cache"),
    )
    control = _check("none", root=copy_root)
    assert control.returncode == 0, "unchanged copy under none: " + _out(control)
    assert _last(control).startswith("map report guide ok: checks of"), _out(control)

    link = re.compile(r"\]\((?:\./)?docs/map-report-guide\.md(?:#[^)]*)?\)")
    readme = copy_root / "README.md"
    lines = readme.read_text(encoding="utf-8").splitlines(keepends=True)
    kept = [ln for ln in lines if not link.search(ln)]
    readme.write_text("".join(kept), encoding="utf-8")
    run = _check("none", root=copy_root)
    assert run.returncode not in (0, 127), (
        "GUIDE_BLOCKS=none passed with no README link row: " + _out(run)
    )
    assert not _last(run).startswith("map report guide ok"), _out(run)


def _guide_modules() -> tuple[object, object]:
    tests_dir = str(Path(__file__).resolve().parent)
    if tests_dir not in sys.path:
        sys.path.insert(0, tests_dir)
    return (
        importlib.import_module("test_map_report_guide"),
        importlib.import_module("test_map_report_guide_decisions"),
    )


def _recording_subprocess(calls: list[dict]) -> SimpleNamespace:
    def run(argv, **kwargs):  # noqa: ANN001, ANN003
        calls.append({"argv": [str(a) for a in argv], "kwargs": kwargs})
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    return SimpleNamespace(
        run=run,
        CompletedProcess=subprocess.CompletedProcess,
        DEVNULL=subprocess.DEVNULL,
        PIPE=subprocess.PIPE,
        TimeoutExpired=subprocess.TimeoutExpired,
    )


def _stand_in_factory(tmp_path: Path) -> SimpleNamespace:
    """A tmp_path_factory stand-in whose shared folder (the parent of the base) is fresh."""
    base = tmp_path / "base"
    base.mkdir(exist_ok=True)
    return SimpleNamespace(getbasetemp=lambda: base)


@pytest.mark.criterion(id="c2")
def test_guide_fixture_is_session_scoped_and_guide_controls_read_it_c2(
    request: pytest.FixtureRequest,
) -> None:
    defs = request._fixturemanager.getfixturedefs("guide_real_page_check", request.node)  # type: ignore[attr-defined]
    assert defs, "no fixture named guide_real_page_check is visible to the tests"
    assert defs[-1].scope == "session", f"guide_real_page_check scope is {defs[-1].scope}"

    guide, decisions = _guide_modules()
    controls = [
        (guide, "test_readme_links_page_and_page_names_every_report_key_c1"),
        (guide, "test_check_fails_when_a_report_key_is_not_a_heading_or_code_term_c1"),
        (guide, "test_every_nav_run_block_prints_its_fenced_output_c5"),
        (guide, "test_changed_fenced_output_fails_the_check_c5"),
        (decisions, "test_check_fails_when_a_limits_item_is_missing_from_the_section_c2"),
        (decisions, "test_check_fails_when_a_placement_item_is_missing_from_the_section_c3"),
    ]
    for module, name in controls:
        params = inspect.signature(getattr(module, name)).parameters
        assert "guide_real_page_check" in params, f"{name} does not read guide_real_page_check"


@pytest.mark.criterion(id="c2")
def test_guide_fixture_runs_the_check_once_over_the_real_page_c2(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    defs = request._fixturemanager.getfixturedefs("guide_real_page_check", request.node)  # type: ignore[attr-defined]
    assert defs, "no fixture named guide_real_page_check to read the behaviour of"
    func = defs[-1].func
    kwargs = {name: _stand_in_factory(tmp_path) for name in inspect.signature(func).parameters}
    assert set(kwargs) <= {"tmp_path_factory"}, f"the fixture asks for {sorted(kwargs)}"
    monkeypatch.delenv("GUIDE_DOC", raising=False)
    monkeypatch.delenv("GUIDE_BLOCKS", raising=False)
    calls: list[dict] = []
    sentinel = subprocess.CompletedProcess(["recorded"], 0, stdout="", stderr="")

    def record(argv, **kw):  # noqa: ANN001, ANN003
        calls.append({"argv": [str(a) for a in argv], "kwargs": kw})
        return sentinel

    with monkeypatch.context() as m:
        m.setattr(subprocess, "run", record)
        result = func(**kwargs)
        if inspect.isgenerator(result):
            result = next(result)
    assert len(calls) == 1, f"the fixture made {len(calls)} subprocess calls"
    call = calls[0]
    assert call["argv"][-1].endswith("scripts/demo.d/99zd-map-report-guide.sh"), (
        f"argv ends with {call['argv'][-1]}"
    )
    env = call["kwargs"].get("env")
    env = os.environ if env is None else env
    assert "GUIDE_DOC" not in env and "GUIDE_BLOCKS" not in env
    assert call["kwargs"].get("timeout") == 120, call["kwargs"].get("timeout")
    assert result is sentinel, "the fixture did not return the CompletedProcess of its run"


def test_guide_fixture_shares_one_check_run_across_workers_wo4(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    defs = request._fixturemanager.getfixturedefs("guide_real_page_check", request.node)  # type: ignore[attr-defined]
    assert defs, "no fixture named guide_real_page_check to read the behaviour of"
    func = defs[-1].func
    shared = tmp_path / "popen-shared"
    factories = []
    for worker in ("gw0", "gw1"):
        base = shared / worker
        base.mkdir(parents=True)
        factories.append(SimpleNamespace(getbasetemp=lambda base=base: base))
    params = list(inspect.signature(func).parameters)
    assert set(params) <= {"tmp_path_factory"}, f"the fixture asks for {sorted(params)}"
    calls: list[list[str]] = []

    def record(argv, **kw):  # noqa: ANN001, ANN003
        calls.append([str(a) for a in argv])
        return subprocess.CompletedProcess(argv, 3, stdout="the stdout", stderr="the stderr")

    def once(factory: SimpleNamespace) -> subprocess.CompletedProcess:
        result = func(**{name: factory for name in params})
        if inspect.isgenerator(result):
            result = next(result)
        return result

    with monkeypatch.context() as m:
        m.setattr(subprocess, "run", record)
        first = once(factories[0])
        second = once(factories[1])
    script_calls = [c for c in calls if c and c[-1].endswith("99zd-map-report-guide.sh")]
    assert len(script_calls) == 1, f"the check script ran {len(script_calls)} times in total"
    assert (first.returncode, first.stdout, first.stderr) == (3, "the stdout", "the stderr")
    assert (second.returncode, second.stdout, second.stderr) == (
        first.returncode,
        first.stdout,
        first.stderr,
    )


@pytest.mark.criterion(id="c2")
def test_every_altered_page_run_in_the_guide_tests_passes_the_blocks_keyword_c2() -> None:
    tests_dir = Path(__file__).resolve().parent
    seen = 0
    for name in ("test_map_report_guide.py", "test_map_report_guide_decisions.py"):
        tree = ast.parse((tests_dir / name).read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not (isinstance(fn, ast.FunctionDef) and fn.name.startswith("test_")):
                continue
            for node in ast.walk(fn):
                if not (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in ("_run_check", "_check_rc")
                ):
                    continue
                seen += 1
                given = [k.value for k in node.keywords if k.arg == "blocks"]
                assert given, (
                    f"{name}:{node.lineno} {fn.name} calls {node.func.id} without blocks="
                )
                # A bare None is the full run in disguise: the keyword must select something.
                assert not (isinstance(given[0], ast.Constant) and given[0].value is None), (
                    f"{name}:{node.lineno} {fn.name} passes blocks=None, which selects nothing"
                )
    assert seen >= 10, f"only {seen} calls of the check helpers found in the guide tests"


@pytest.mark.criterion(id="c2")
def test_every_call_of_the_check_script_carries_timeout_120_c2(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    guide, decisions = _guide_modules()
    calls: list[dict] = []
    fake = _recording_subprocess(calls)
    monkeypatch.setattr(guide, "subprocess", fake)
    monkeypatch.setattr(decisions, "subprocess", fake)

    guide._run_check(None)  # type: ignore[attr-defined]
    decisions._check_rc("# page\n")  # type: ignore[attr-defined]
    script_calls = [c for c in calls if any("99zd-map-report-guide.sh" in a for a in c["argv"])]
    assert len(script_calls) == 2, f"expected two script calls, saw {len(script_calls)}"
    for c in script_calls:
        assert c["kwargs"].get("timeout") == 120, f"timeout is {c['kwargs'].get('timeout')}"

    defs = request._fixturemanager.getfixturedefs("guide_real_page_check", request.node)  # type: ignore[attr-defined]
    assert defs, "no fixture named guide_real_page_check to drive for its timeout"
    func = defs[-1].func
    kwargs = {name: _stand_in_factory(tmp_path) for name in inspect.signature(func).parameters}
    assert set(kwargs) <= {"tmp_path_factory"}, f"the fixture asks for {sorted(kwargs)}"
    calls.clear()
    with monkeypatch.context() as m:
        m.setattr(subprocess, "run", fake.run)
        func(**kwargs)
    fixture_calls = [c for c in calls if any("99zd-map-report-guide.sh" in a for a in c["argv"])]
    assert len(fixture_calls) == 1, f"the fixture made {len(fixture_calls)} script calls"
    fixture_timeout = fixture_calls[0]["kwargs"].get("timeout")
    assert fixture_timeout == 120, fixture_timeout

    tests_dir = Path(__file__).resolve().parent
    scanned = 0
    for name in ("test_map_report_guide.py", "test_map_report_guide_decisions.py", "conftest.py"):
        path = tests_dir / name
        assert path.exists(), f"{name} does not exist"
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and ast.unparse(node.func) == "subprocess.run"):
                continue
            scanned += 1
            timeouts = [k.value for k in node.keywords if k.arg == "timeout"]
            assert len(timeouts) == 1, f"{name}:{node.lineno} subprocess.run has no timeout keyword"
            value = timeouts[0]
            assert isinstance(value, ast.Constant) and value.value == 120, (
                f"{name}:{node.lineno} timeout is {ast.unparse(value)}, not the literal 120"
            )
    assert scanned >= 3, f"only {scanned} subprocess.run calls found in the three files"


@pytest.mark.criterion(id="c2")
def test_guide_helpers_pass_the_block_selector_through_the_environment_c2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guide, decisions = _guide_modules()
    assert "blocks" in inspect.signature(guide._run_check).parameters  # type: ignore[attr-defined]
    assert "blocks" in inspect.signature(decisions._check_rc).parameters  # type: ignore[attr-defined]
    assert "_block_index" in vars(guide), "_block_index helper is missing"

    calls: list[dict] = []
    fake = _recording_subprocess(calls)
    monkeypatch.setattr(guide, "subprocess", fake)
    monkeypatch.setattr(decisions, "subprocess", fake)
    guide._run_check(None, blocks=3)  # type: ignore[attr-defined]
    decisions._check_rc("# page\n", blocks="none")  # type: ignore[attr-defined]
    guide._run_check(None)  # type: ignore[attr-defined]
    envs = [c["kwargs"]["env"] for c in calls]
    assert envs[0].get("GUIDE_BLOCKS") == "3"
    assert envs[1].get("GUIDE_BLOCKS") == "none"
    inherited = os.environ.get("GUIDE_BLOCKS")
    assert "GUIDE_BLOCKS" not in envs[2] or envs[2]["GUIDE_BLOCKS"] == inherited


@pytest.mark.criterion(id="c2")
def test_guide_test_ids_of_the_earlier_build_are_all_still_defined_and_block_index_exists_c2(
) -> None:
    guide, decisions = _guide_modules()
    held = {
        guide: [
            "test_readme_links_page_and_page_names_every_report_key_c1",
            "test_check_fails_when_a_report_key_is_not_a_heading_or_code_term_c1",
            "test_every_nav_run_block_prints_its_fenced_output_c5",
            "test_changed_fenced_output_fails_the_check_c5",
        ],
        decisions: [
            "test_check_fails_when_a_limits_item_is_missing_from_the_section_c2",
            "test_check_fails_when_a_placement_item_is_missing_from_the_section_c3",
            "test_check_fails_when_the_quoted_refusal_or_exit_code_differs_c4",
            "test_main_project_pins_myproject_and_shows_its_node_wo2",
            "test_check_runs_folder_blocks_and_fails_on_altered_output_wo2",
        ],
    }
    # Nine ids existed at 6a191e7 (the work order says ten); collection reports 4 + 5.
    for module, names in held.items():
        missing = [n for n in names if not callable(getattr(module, n, None))]
        assert missing == [], f"test ids lost from {module.__name__}: {missing}"
    assert hasattr(guide, "_block_index"), "tests do not map a nav-run match to its block index"


def _ci_extras_with_fakes(
    monkeypatch: pytest.MonkeyPatch,
    calls: list[dict],
    import_rc: int,
    omit: str | None,
    ran: list[list[str]] | None = None,
) -> object:
    ci = importlib.import_module("test_ci_extras") if "test_ci_extras" in sys.modules else None
    if ci is None:
        _guide_modules()  # puts the tests directory on sys.path
        ci = importlib.import_module("test_ci_extras")

    def run_or_fail(argv, label, *a, **k):  # noqa: ANN001, ANN002, ANN003
        if ran is not None:
            ran.append([str(x) for x in argv])
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    def run(argv, **kwargs):  # noqa: ANN001, ANN003
        argv = [str(x) for x in argv]
        calls.append({"argv": argv, "kwargs": kwargs})
        if "-c" in argv:
            err = "ImportError" if import_rc else ""
            return subprocess.CompletedProcess(argv, import_rc, stdout="", stderr=err)
        passed = "\n".join(f"PASSED {i}" for i in ci.EIGHT_JS_TESTS if i != omit)  # type: ignore[attr-defined]
        return subprocess.CompletedProcess(argv, 0, stdout=passed + "\n", stderr="")

    monkeypatch.setattr(ci, "_run_or_fail", run_or_fail)
    fake = SimpleNamespace(run=run, CompletedProcess=subprocess.CompletedProcess)
    monkeypatch.setattr(ci, "subprocess", fake)
    if getattr(ci, "UV", None) is None:
        monkeypatch.setattr(ci, "UV", "uv")
    return ci


@pytest.mark.criterion(id="c1")
def test_ci_extras_runs_exactly_the_eight_ids_and_imports_the_grammar_c1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[dict] = []
    ran: list[list[str]] = []
    ci = _ci_extras_with_fakes(monkeypatch, calls, import_rc=0, omit=None, ran=ran)
    ci.test_install_line_extras_run_the_javascript_tests_green_c1(tmp_path)  # type: ignore[attr-defined]
    eight = list(ci.EIGHT_JS_TESTS)  # type: ignore[attr-defined]
    pytest_calls = [c for c in calls if "pytest" in c["argv"]]
    assert len(pytest_calls) == 1, f"pytest ran {len(pytest_calls)} times"
    argv = pytest_calls[0]["argv"]
    assert argv[1:6] == ["-m", "pytest", "-p", "no:cacheprovider", "-rA"], argv
    assert argv[6:] == eight, "nested pytest was not given exactly the eight ids"
    assert not any(a.startswith("--ignore") for a in argv)
    assert pytest_calls[0]["kwargs"].get("timeout") == 120
    imports = [c for c in calls if "-c" in c["argv"]]
    assert len(imports) == 1, "the grammar import was not run in the venv"
    assert imports[0]["argv"][-2:] == ["-c", "import tree_sitter_javascript"]
    assert imports[0]["argv"][0] == pytest_calls[0]["argv"][0], "import used another interpreter"
    assert imports[0]["kwargs"].get("timeout") == 120

    venvs = [a for a in ran if a[1:2] == ["venv"]]
    assert len(venvs) == 1, f"the venv was built {len(venvs)} times: {ran}"
    venv = Path(venvs[0][2])
    scripts = ci._scripts_dir(venv)  # type: ignore[attr-defined]
    venv_python = str(scripts / ("python.exe" if os.name == "nt" else "python"))
    assert venv_python != sys.executable
    assert argv[0] == venv_python, f"nested pytest ran {argv[0]}, not the venv's {venv_python}"
    assert imports[0]["argv"][0] == venv_python, (
        f"import ran {imports[0]['argv'][0]}, not {venv_python}"
    )
    installs = [a for a in ran if a[1:3] == ["pip", "install"]]
    assert len(installs) == 1, f"expected one uv pip install call: {ran}"
    assert installs[0][3:5] == ["--python", venv_python], installs[0]
    named = [a for a in installs[0][5:] if "[" in a and "js" in a]
    assert named, f"the install carries no argument naming the js extra: {installs[0]}"
    assert str(ci.PROJECT_ROOT) in named[0], named  # type: ignore[attr-defined]


@pytest.mark.criterion(id="c1")
def test_ci_extras_fails_when_the_grammar_import_fails_c1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[dict] = []
    ci = _ci_extras_with_fakes(monkeypatch, calls, import_rc=1, omit=None)
    with pytest.raises(AssertionError):
        ci.test_install_line_extras_run_the_javascript_tests_green_c1(tmp_path)  # type: ignore[attr-defined]
    assert any("-c" in c["argv"] for c in calls), "the import was never attempted"


@pytest.mark.criterion(id="c1")
def test_ci_extras_fails_when_one_passed_line_is_missing_c1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[dict] = []
    probe = _ci_extras_with_fakes(monkeypatch, calls, import_rc=0, omit=None)
    omitted = list(probe.EIGHT_JS_TESTS)[3]  # type: ignore[attr-defined]
    calls.clear()
    ci = _ci_extras_with_fakes(monkeypatch, calls, import_rc=0, omit=omitted)
    with pytest.raises(AssertionError) as caught:
        ci.test_install_line_extras_run_the_javascript_tests_green_c1(tmp_path)  # type: ignore[attr-defined]
    assert omitted in str(caught.value), str(caught.value)[:300]
    nested = [c for c in calls if "pytest" in c["argv"]]
    assert nested and nested[0]["argv"][6:] == list(ci.EIGHT_JS_TESTS)  # type: ignore[attr-defined]
    assert nested[0]["kwargs"].get("timeout") == 120


@pytest.mark.criterion(id="c1")
def test_ci_extras_fails_when_the_workflow_install_line_lacks_the_js_extra_c1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    calls: list[dict] = []
    ran: list[list[str]] = []
    ci = _ci_extras_with_fakes(monkeypatch, calls, import_rc=0, omit=None, ran=ran)
    text = ci.WORKFLOW.read_text(encoding="utf-8")  # type: ignore[attr-defined]
    assert "'.[dev,js]'" in text
    planted = tmp_path / "checks.yml"
    planted.write_text(text.replace("'.[dev,js]'", "'.[dev]'"), encoding="utf-8")
    monkeypatch.setattr(ci, "WORKFLOW", planted)
    with pytest.raises(AssertionError):
        ci.test_install_line_extras_run_the_javascript_tests_green_c1(tmp_path)  # type: ignore[attr-defined]
    assert not any("js" in a for argv in ran for a in argv[5:]), ran


# Per-file collected counts of tests/ at 6a191e7 (pytest --collect-only -q, 59 files, 569 ids).
COLLECTED_AT_6A191E7 = {
    "test_argument_ends.py": 13, "test_boundary.py": 14, "test_boundary_classify.py": 5,
    "test_boundary_shape_hint.py": 3, "test_check_map.py": 55, "test_ci_extras.py": 3,
    "test_config_owner.py": 2, "test_console_script.py": 16, "test_constant_argument.py": 8,
    "test_contract.py": 4, "test_declared_end.py": 13, "test_detect.py": 16,
    "test_detection_guards.py": 10, "test_enclosing_file_edges.py": 4,
    "test_enclosing_method_end.py": 3, "test_entity_hooks.py": 1, "test_form_ids.py": 3,
    "test_id_pattern.py": 11, "test_init.py": 15, "test_library_scripts.py": 4,
    "test_library_styles.py": 1, "test_list_key_filter.py": 10, "test_manifest.py": 26,
    "test_map_no_rutter.py": 2, "test_map_report_guide.py": 4,
    "test_map_report_guide_decisions.py": 5, "test_match_ending.py": 5,
    "test_navigate_find.py": 11, "test_navigate_mapfile.py": 22, "test_navigate_output.py": 24,
    "test_navigate_path.py": 13, "test_navigate_show.py": 10, "test_navigate_types.py": 8,
    "test_navigate_walk.py": 12, "test_node_id.py": 7, "test_packaging.py": 10,
    "test_packs.py": 12, "test_path_urls.py": 1, "test_property_calls.py": 4,
    "test_property_type_sources.py": 5, "test_qualified_source.py": 1, "test_readme_hero.py": 6,
    "test_reference_template_end.py": 3, "test_refusal_messages.py": 6,
    "test_refusal_messages_boundary.py": 7, "test_release_0_2_0.py": 4, "test_report.py": 8,
    "test_resolution.py": 10, "test_rutter_keys.py": 2, "test_settings.py": 30,
    "test_spans.py": 8, "test_spec.py": 23, "test_table_step.py": 4, "test_theme_hooks.py": 6,
    "test_twig_relations.py": 1, "test_unexecuted_keys.py": 6, "test_unlisted_folders.py": 1,
    "test_validate.py": 42, "test_where_child.py": 6,
}


@pytest.mark.criterion(id="c4")
def test_no_collected_test_is_lost_and_the_readme_counts_the_collected_total_c4() -> None:
    run = subprocess.run(  # noqa: S603 - fixed argv
        [sys.executable, "-m", "pytest", "--collect-only", "-qq", "-p", "no:cacheprovider"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=600,
    )
    assert run.returncode == 0, run.stdout[-2000:] + run.stderr[-1000:]
    counts = {
        m.group(1): int(m.group(2))
        for m in re.finditer(r"^tests/(test_\w+\.py): (\d+)$", run.stdout, re.M)
    }
    total = sum(counts.values())
    assert sum(COLLECTED_AT_6A191E7.values()) == 569
    assert total >= 569, f"collected {total}"
    short = {
        f: (counts.get(f, 0), was)
        for f, was in COLLECTED_AT_6A191E7.items()
        if counts.get(f, 0) < was
    }
    assert short == {}, f"files collecting fewer tests than at 6a191e7: {short}"

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    stated = [int(n) for n in re.findall(r"\b(\d{3,}) tests\b", readme)]
    assert len(stated) >= 2, f"README holds {len(stated)} test-count statements"
    assert stated == [total] * len(stated), f"README states {stated}, collected {total}"
