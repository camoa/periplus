"""The YAML reader takes every scalar key written once, the empty one too, and refuses the rest."""

from __future__ import annotations

from pathlib import Path

import pytest

from periplus.engine.source import SourceUnreadable, load_data, plain


@pytest.mark.parametrize("key", ["''", '""'])
def test_an_empty_quoted_key_written_once_is_read(tmp_path: Path, key: str) -> None:
    path = tmp_path / "a.yml"
    path.write_text(f"a:\n  {key}: x\n  'q k': y\n", encoding="utf-8")
    assert plain(load_data(path, "a.yml")) == {"a": {"": "x", "q k": "y"}}


@pytest.mark.parametrize(
    ("text", "line"),
    [
        ("a: 1\na: 2\n", 2),
        ("'': 1\n\"\": 2\n", 2),
        ("? [1]\n: x\n", 1),
        ("? {b: 1}\n: x\n", 1),
    ],
)
def test_a_key_written_twice_or_not_a_scalar_is_refused(
    tmp_path: Path, text: str, line: int
) -> None:
    path = tmp_path / "a.yml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(SourceUnreadable, match=f"a.yml line {line} "):
        load_data(path, "a.yml")
