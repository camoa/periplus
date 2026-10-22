"""Tests for docs/map-report-guide.md and its demo check."""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "docs" / "map-report-guide.md"
README = ROOT / "README.md"
CHECK = ROOT / "scripts" / "demo.d" / "99zd-map-report-guide.sh"
PERIPLUS = ROOT / ".venv" / "bin" / "periplus"

FENCE = r"```[^\n]*\n(?P<body>.*?)^```$"
FENCE_RE = re.compile(r"^```[^\n]*\n.*?^```$", re.M | re.S)
RUN_RE = re.compile(r"^<!-- nav-run -->\n" + FENCE, re.M | re.S)
FILE_RE = re.compile(r"^<!-- nav-file: (?P<path>\S+) -->\n" + FENCE, re.M | re.S)
EXIT_RE = re.compile(r"^\(exit \d+\)$")


def _page_text() -> str:
    return PAGE.read_text(encoding="utf-8") if PAGE.is_file() else ""


def _run_check(
    doc: Path | None, root: Path = ROOT, periplus: Path = PERIPLUS
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["ROOT"] = str(root)
    env["PERIPLUS"] = str(periplus)
    env.pop("GUIDE_DOC", None)
    if doc is not None:
        env["GUIDE_DOC"] = str(doc)
    bash = shutil.which("bash") or "/bin/bash"
    return subprocess.run(  # noqa: S603 - fixed argv, repository-owned script
        [bash, str(root / "scripts" / "demo.d" / CHECK.name)],
        env=env, cwd=root, capture_output=True, text=True, timeout=900
    )


def _report_keys(tmp_path: Path) -> list[str]:
    """Top-level keys of a real `map --format json` run over a small planted project."""
    site = tmp_path / "keysite"
    (site / ".periplus").mkdir(parents=True)
    src = ROOT / "examples" / "second-stack"
    shutil.copytree(src / "packs", site / ".periplus" / "packs")
    shutil.copy(src / "settings.yml", site / ".periplus" / "settings.yml")
    (site / "app.py").write_text("def run():\n    return 1\n", encoding="utf-8")
    env = dict(os.environ)
    env["PERIPLUS_CONFIG_DIR"] = str(tmp_path / "userconf")
    (tmp_path / "userconf").mkdir()
    proc = subprocess.run(  # noqa: S603 - fixed argv
        [str(PERIPLUS), "map", "--format", "json"],
        cwd=site, env=env, capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    keys = sorted(json.loads(proc.stdout))
    assert len(keys) >= 17, keys
    return keys


def _outside_fences(text: str) -> str:
    return FENCE_RE.sub("", text)


def _names_key(text: str, key: str) -> bool:
    """Key is a heading word or a code span equal to the key, outside fenced blocks."""
    prose = _outside_fences(text)
    for line in prose.splitlines():
        if line.startswith("#") and re.search(r"(?<![\w.])" + re.escape(key) + r"(?![\w.])", line):
            return True
    return re.search(r"`" + re.escape(key) + r"`", prose) is not None


def _runs(text: str) -> list[re.Match[str]]:
    return list(RUN_RE.finditer(text))


def _splice(text: str, match: re.Match[str], body: str) -> str:
    return text[: match.start("body")] + body + text[match.end("body"):]


def _output_line_index(body: str) -> int | None:
    lines = body.split("\n")  # last element is "" after the final newline
    for i in range(len(lines) - 2, 0, -1):
        if lines[i] and not EXIT_RE.match(lines[i]):
            return i
    return None


@pytest.mark.criterion(id="c1")
def test_readme_links_page_and_page_names_every_report_key_c1(tmp_path: Path) -> None:
    readme = README.read_text(encoding="utf-8")
    rows = [
        line for line in readme.splitlines()
        if line.lstrip().startswith("|")
        and re.search(r"\]\((?:\./)?docs/map-report-guide\.md(?:#[^)]*)?\)", line)
    ]
    assert len(rows) == 1, "README table must hold exactly one row with a link to the page"

    text = _page_text()
    missing = [k for k in _report_keys(tmp_path) if not _names_key(text, k)]
    assert missing == [], f"keys absent from the page as heading or code term: {missing}"

    control = _run_check(None)
    assert control.returncode == 0, "real tree must pass: " + control.stdout + control.stderr
    copy_root = tmp_path / "tree"
    shutil.copytree(
        ROOT, copy_root,
        ignore=shutil.ignore_patterns(
            ".venv", ".git", "node_modules", "__pycache__", ".*_cache"
        ),
    )
    copy_control = _run_check(None, root=copy_root)
    assert copy_control.returncode == 0, (
        "unchanged copy must pass: " + copy_control.stdout + copy_control.stderr
    )
    link = re.compile(r"\]\((?:\./)?docs/map-report-guide\.md(?:#[^)]*)?\)")
    copy_readme = copy_root / "README.md"
    lines = copy_readme.read_text(encoding="utf-8").splitlines(keepends=True)
    kept = [ln for ln in lines if not link.search(ln)]
    copy_readme.write_text("".join(kept), encoding="utf-8")
    result = _run_check(None, root=copy_root)
    assert result.returncode not in (0, 127), (
        "check passed with the README link row removed: " + result.stdout + result.stderr
    )


@pytest.mark.criterion(id="c1")
def test_check_fails_when_a_report_key_is_not_a_heading_or_code_term_c1(tmp_path: Path) -> None:
    control = _run_check(None)
    assert control.returncode == 0, "unchanged page must pass: " + control.stdout + control.stderr

    text = _page_text()
    parts = FENCE_RE.split(text)
    fences = FENCE_RE.findall(text)
    for key in _report_keys(tmp_path):
        word = re.escape(key)
        changed_parts = []
        for part in parts:
            lines = [
                re.sub(r"(?<![\w.])" + word + r"(?![\w.])", "ZZ", ln) if ln.startswith("#") else ln
                for ln in part.split("\n")
            ]
            part = "\n".join(lines)
            changed_parts.append(re.sub(r"`" + word + r"`", "`periplus " + key + "`", part))
        mutated = changed_parts[0]
        for fence, part in zip(fences, changed_parts[1:], strict=True):
            mutated += fence + part
        assert not _names_key(mutated, key), f"mutation left {key} named"
        copy = tmp_path / f"no_{key}.md"
        copy.write_text(mutated, encoding="utf-8")
        result = _run_check(copy)
        assert result.returncode not in (0, 127), f"check passed without key {key}"

    missing_doc = _run_check(tmp_path / "no_such_page.md")
    assert missing_doc.returncode not in (0, 127), "check passed with no page at GUIDE_DOC"

    wrapper = tmp_path / "periplus-extra-key"
    wrapper.write_text(
        "#!/usr/bin/env bash\n"
        'if [ "$*" = "map --format json" ]; then\n'
        f'  "{PERIPLUS}" "$@" | python3 -c \'import json,sys; d=json.load(sys.stdin); '
        "d[\"zz_extra_key\"]=1; print(json.dumps(d))\'\n"
        "else\n"
        f'  exec "{PERIPLUS}" "$@"\n'
        "fi\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    extra = _run_check(None, periplus=wrapper)
    assert extra.returncode not in (0, 127), (
        "check passed though the report holds a key the page does not name: "
        + extra.stdout + extra.stderr
    )


@pytest.mark.criterion(id="c5")
def test_every_nav_run_block_prints_its_fenced_output_c5() -> None:
    text = _page_text()
    runs = _runs(text)
    assert len(runs) >= 2
    assert any("/path/to/project" in m.group("body") for m in runs), (
        "no fenced output holds the substituted project path"
    )
    result = _run_check(None)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.criterion(id="c5")
def test_changed_fenced_output_fails_the_check_c5(tmp_path: Path) -> None:
    control = _run_check(None)
    assert control.returncode == 0, (
        "unchanged page must pass first: " + control.stdout + control.stderr
    )

    text = _page_text()
    runs = _runs(text)
    assert len(runs) >= 2, "page has too few nav-run blocks"
    tried = 0
    for n, match in enumerate(runs):
        body = match.group("body")
        idx = _output_line_index(body)
        if idx is None:
            continue
        lines = body.split("\n")
        variants = {}
        edited = list(lines)
        edited[idx] = lines[idx] + " CHANGED"
        variants["word"] = "\n".join(edited)
        edited = list(lines)
        edited[idx] = lines[idx] + " "
        variants["trailing-space"] = "\n".join(edited)
        edited = list(lines)
        edited.insert(idx + 1, "")
        variants["blank-line"] = "\n".join(edited)
        for name, new_body in variants.items():
            assert new_body != body
            copy = tmp_path / f"run{n}_{name}.md"
            copy.write_text(_splice(text, match, new_body), encoding="utf-8")
            result = _run_check(copy)
            assert result.returncode not in (0, 127), (
                f"check passed with nav-run block {n} changed ({name})"
            )
            tried += 1
    assert tried >= 6, "too few output lines changed"

    first = runs[0]
    cmd_lines = first.group("body").split("\n")
    cmd_lines[0] = "$ periplus nosuchsubcommand"
    copy = tmp_path / "command_changed.md"
    copy.write_text(_splice(text, first, "\n".join(cmd_lines)), encoding="utf-8")
    result = _run_check(copy)
    assert result.returncode not in (0, 127), "check passed with a command line changed"

    for n, match in enumerate(runs):
        body = match.group("body")
        idx = _output_line_index(body)
        if idx is None:
            continue
        lines = body.split("\n")
        del lines[idx]
        shorter = "\n".join(lines)
        assert shorter != body
        copy = tmp_path / f"run{n}_shorter.md"
        copy.write_text(_splice(text, match, shorter), encoding="utf-8")
        result = _run_check(copy)
        assert result.returncode not in (0, 127), (
            f"check passed with the last output line of block {n} removed"
        )

    last = runs[-1]
    block = last.group(0)
    body = last.group("body")
    idx = _output_line_index(body)
    assert idx is not None
    lines = body.split("\n")
    lines[idx] += " CHANGED"
    extra_block = block.replace(body, "\n".join(lines))
    assert extra_block != block
    copy = tmp_path / "extra_block.md"
    joined = text[: last.end()] + "\n\n" + extra_block + text[last.end():]
    copy.write_text(joined, encoding="utf-8")
    result = _run_check(copy)
    assert result.returncode not in (0, 127), "check passed with one more altered block added"

    appender = tmp_path / "periplus-append-line"
    appender.write_text(
        "#!/usr/bin/env bash\n"
        f'"{PERIPLUS}" "$@"\n'
        "rc=$?\n"
        'if [ "$*" != "map --format json" ]; then echo "APPENDED LINE"; fi\n'
        "exit $rc\n",
        encoding="utf-8",
    )
    appender.chmod(0o755)
    result = _run_check(None, periplus=appender)
    assert result.returncode not in (0, 127), "check passed with one more line on every command"

    rewriter = tmp_path / "periplus-rewrite-path"
    rewriter.write_text(
        "#!/usr/bin/env bash\n"
        f'"{PERIPLUS}" "$@" 2>&1 | sed "s#$PWD#/somewhere/else#g"\n'
        'exit "${PIPESTATUS[0]}"\n',
        encoding="utf-8",
    )
    rewriter.chmod(0o755)
    result = _run_check(None, periplus=rewriter)
    assert result.returncode not in (0, 127), "check passed though the project path was rewritten"
