"""The CI tests job installs every extra the tests need, and the README says which."""

import os
import re
import shlex
import subprocess
from pathlib import Path

import pytest
from ruamel.yaml import YAML
from test_packaging import PROJECT_ROOT, UV, _run_or_fail, _scripts_dir

WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "checks.yml"
README = PROJECT_ROOT / "README.md"
JS_TEST_FILES = [
    "tests/test_library_scripts.py",
    "tests/test_library_styles.py",
    "tests/test_list_key_filter.py",
    "tests/test_enclosing_file_edges.py",
]


EIGHT_JS_TESTS = [
    "tests/test_enclosing_file_edges.py::test_a_script_links_to_every_function_and_behavior_it_declares",
    "tests/test_library_scripts.py::test_a_library_links_to_its_scripts_and_each_script_to_its_behavior",
    "tests/test_library_scripts.py::test_the_library_nodes_and_edges_the_map_had_before_are_kept",
    "tests/test_library_scripts.py::test_a_script_key_read_from_the_drupal_root_ends_at_a_referenced_node",
    "tests/test_library_scripts.py::test_a_pack_that_declares_the_type_yml_again_in_full_keeps_the_library_edges",
    "tests/test_library_styles.py::test_a_library_links_to_its_local_stylesheets_and_not_to_an_address",
    "tests/test_list_key_filter.py::test_a_library_address_makes_no_node_and_no_edge",
    "tests/test_list_key_filter.py::test_a_matches_glob_keeps_exactly_the_keys_it_selects",
]


def _tests_job_install_steps() -> list[dict]:
    """The steps of the tests job whose run text holds a pip install line."""
    workflow = YAML(typ="safe").load(WORKFLOW.read_text(encoding="utf-8"))
    return [
        step
        for step in workflow["jobs"]["tests"]["steps"]
        if "pip install" in str(step.get("run", ""))
    ]


def _tests_job_install_lines() -> list[str]:
    return [
        line.strip()
        for step in _tests_job_install_steps()
        for line in str(step.get("run", "")).splitlines()
        if "pip install" in line
    ]


def _tests_job_install_extras() -> list[str]:
    """The extras named by the pip install line of the tests job."""
    extras: list[str] = []
    for line in _tests_job_install_lines():
        for group in re.findall(r"\[([^\]]*)\]", line):
            extras.extend(part.strip() for part in group.split(",") if part.strip())
    return extras


def _install_args_as_the_workflow_builds_it() -> list[str]:
    """The tokens after `pip install` on the workflow line, with the project path made absolute."""
    lines = [
        line
        for line in _tests_job_install_lines()
        if any(a.startswith(".") or "[" in a for a in shlex.split(line))
    ]
    assert len(lines) == 1, f"expected one pip install line naming the project: {lines}"
    tokens = shlex.split(lines[0])
    args = tokens[tokens.index("install") + 1 :]
    return [f"{PROJECT_ROOT}{a[1:]}" if a == "." or a.startswith(".[") else a for a in args]


def _readme_text() -> str:
    return " ".join(README.read_text(encoding="utf-8").replace("`", "").split())


def _readme_ci_paragraph() -> str:
    """The README paragraph that names the workflow file, the one describing its install."""
    paragraphs = re.split(r"\n\s*\n", README.read_text(encoding="utf-8"))
    hits = [p for p in paragraphs if "checks.yml" in p]
    return " ".join(hits[0].replace("`", "").split()) if hits else ""


@pytest.mark.slow
@pytest.mark.criterion(id="c1")
def test_install_line_extras_run_the_javascript_tests_green_c1(tmp_path: Path) -> None:
    extras = _tests_job_install_extras()
    assert set(extras) == {"dev", "js"}, f"workflow extras: {extras}"
    assert all("if" not in s for s in _tests_job_install_steps()), "install step is conditional"
    args = _install_args_as_the_workflow_builds_it()
    if UV is None:
        pytest.fail("uv is not on PATH")
    venv = tmp_path / "venv"
    _run_or_fail([UV, "venv", str(venv)], "uv venv", timeout=120)
    python = _scripts_dir(venv) / ("python.exe" if os.name == "nt" else "python")
    _run_or_fail(
        [UV, "pip", "install", "--python", str(python), *args], "uv pip install", timeout=120
    )
    run = subprocess.run(  # noqa: S603 - fixed argv built here
        [
            str(python),
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-rA",
            *EIGHT_JS_TESTS,
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert run.returncode == 0, run.stdout[-3000:] + run.stderr[-1000:]
    for node in EIGHT_JS_TESTS:
        assert f"PASSED {node}" in run.stdout, f"{node} did not pass"
    grammar = subprocess.run(  # noqa: S603 - fixed argv built here
        [str(python), "-c", "import tree_sitter_javascript"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert grammar.returncode == 0, grammar.stdout + grammar.stderr


@pytest.mark.criterion(id="c2")
def test_readme_names_every_installed_extra_and_drops_old_wording_c2() -> None:
    extras = _tests_job_install_extras()
    assert {"dev", "js"} <= set(extras), f"workflow extras: {extras}"
    paragraph = _readme_ci_paragraph()
    assert paragraph, "no README paragraph naming checks.yml found"
    for extra in extras:
        assert re.search(rf"\b{re.escape(extra)}\b", paragraph), f"{extra} missing: {paragraph}"
    text = _readme_text()
    assert "installs the package with its dev extra only" not in text, "old sentence still present"
    flat = re.sub(r"[\[\]\-]", " ", text)
    flat = re.sub(r"\.(?=\S)", "", flat)
    flat = re.sub(r"\bextras\b", "extra", flat).lower()
    flat = " ".join(flat.split())
    assert not re.search(r"\bdev\s+(extra\s+)?only\b", flat), "README still says dev only"
    assert not re.search(r"\bonly\s+(the\s+)?dev\b", flat), "README still says only dev"
    # part of the old wording the clause rejects
    assert "has not run yet" not in flat


@pytest.mark.criterion(id="wo1")
def test_readme_keeps_the_go_sentence_wo1() -> None:
    assert "never maps a Go project" in _readme_ci_paragraph()
