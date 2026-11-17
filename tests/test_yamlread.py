"""The YAML reader gives what the pure parser gives, whichever parser reads the text."""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any

import pytest
import ruamel.yaml.main
from ruamel.yaml import YAML

from periplus import yamlread
from periplus.engine import source


def _outcome(read: Any) -> tuple[str, ...]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            return ("ok", repr(read()))
        except Exception as error:  # noqa: BLE001 -- the error is the result compared
            return ("error", type(error).__name__, str(error))


def _pure_compose(text: str) -> Any:
    return YAML(typ="safe", pure=True).compose(text)


def _data(path: Path, monkeypatch: pytest.MonkeyPatch | None) -> tuple[str, ...]:
    """What the engine reads from ``path``: its entries and lines, or its message."""
    if monkeypatch is None:
        return _outcome(lambda: source.load_data(path, "f.yml"))
    with monkeypatch.context() as patch:
        patch.setattr(source, "compose", _pure_compose)
        return _outcome(lambda: source.load_data(path, "f.yml"))


def _all_ways(text: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[tuple[Any, Any]]:
    """Each reader's result beside the pure parser's, for one text."""
    path = tmp_path / "f.yml"
    path.write_bytes(text.encode("utf-8"))
    opener = lambda: path.open("r", encoding="utf-8")  # noqa: E731

    def pure_file() -> Any:
        with opener() as stream:
            return YAML(typ="safe", pure=True).load(stream)

    return [
        (
            _outcome(lambda: yamlread.load(text)),
            _outcome(lambda: YAML(typ="safe", pure=True).load(text)),
        ),
        (_outcome(lambda: yamlread.load_file(opener)), _outcome(pure_file)),
        (_data(path, None), _data(path, monkeypatch)),
    ]


def _engine_read(text: str, pure: bool) -> tuple[tuple[str, ...], ...]:
    """The document, and the entries with their lines, one parser gives for ``text``."""
    yaml = lambda: YAML(typ="safe", pure=pure)  # noqa: E731
    return (
        _outcome(lambda: yaml().load(text)),
        _outcome(lambda: source._convert(yaml().compose(text), "f.yml", ())),
    )


#: Text the C parser reads exactly as the pure one does, so the reader takes it.
SAME = {
    "plain data": "langcode: en\nstatus: true\ndependencies:\n  module:\n    - node\n    - user\n",
    "lines": "a:\n  b: 1\n\n  c:\n    - x\n    -\n    - y\nd: 2\n",
    "empty mapping value": "a:\n\nb:\n# c\nc: 1\n",
    "key order": "z: 1\na: 2\nm: 3\n",
    "quoted and plain": "a: '1'\nb: 1\nc: \"yes\"\nd: yes\ne: ''\nf: \"\"\n",
    "yaml 1.2 words": "a: yes\nb: no\nc: on\nd: off\ne: y\nf: True\ng: ~\n",
    "numbers": "a: 017\nb: 0o17\nc: 0x1F\nd: 12:30\ne: 1_000\nf: .inf\ng: 1e3\nh: 2026-08-28\n",
    "quoted empty key": '"": 1\nb: 2\n',
    "key that is not a scalar": "? [a, b]\n: 1\n",
    "duplicate key": "a: 1\nb: 2\na: 3\n",
    "anchors and merge": "x: &x {a: 1}\ny:\n  <<: *x\n  b: 2\nz: [&q 1, *q]\n",
    "crlf": "a: 1\r\nb:\r\n  - x\r\n  - y\r\n",
    "lone cr": "a: 1\rb:\r  - x\r",
    "multi-document": "a: 1\n---\nb: 2\n",
    "document start": "---\na: 1\n",
    "comments": "# head\na: 1  # side\n# between\nb:\n  - x # item\n",
    "json flow": '{"a": 1, "b": [1, 2]}\n',
    "punctuation in quotes": "a: '!empty($x) && $y->z'\nb: \"a: b | c > d\"\n",
}

#: Text the C parser reads alike, which the reader still gives to the pure one.
PURE_ANYWAY = {
    "byte order mark first": "\ufeffa: 1\nb: 2\n",
    "block scalar": "a: |\n  x\n  y\nb: >-\n  z\n",
    "explicit tag": "a: !!str 1\n",
}

#: Text the C parser reads otherwise than the pure one, so the reader must not take its answer.
C_DIFFERS = {
    "tab after a colon": "a:\tb\n",
    "tab before a comment": "a: 1\t# c\n",
    "yaml 1.1 directive": "%YAML 1.1\n---\na: yes\nb: 017\n",
    "paragraph separator": "a: x\u2029\nb: 1\n",
    "byte order mark inside": "settings:\n\ufeff  label: x\n",
    "document end after a block scalar": ">-\n...\n",
    "two document ends": "a: 1\n...\n...\n",
    "anchor ended by a colon": "k:\n  &a: 1\n",
    "anchor in a key": "&bk: v\n",
    "tag the pure parser refuses": "k: !~!v\n",
    "non-specific tag": "k: v\nj: !\n",
    "comment straight after a block header": "text: |#\n  body\nnext: 1\n",
    "blank line deeper than block text": "a: >-\n  \n    \n",
    "colon after a quoted key in flow": 'j: ["b" :+]\n',
    "colon after an anchor in flow": "k: v\nj: [&b :+]\n",
}

#: Broken text: each must give the pure parser's message, marks and all.
BROKEN = {
    "unclosed flow sequence": "a: [1, 2\nb: 3\n",
    "unclosed flow mapping": "a: {b: 1\n",
    "colon in flow sequence": "a: [b: c: d]\n",
    "unclosed double quote": 'a: "x\nb: 1\n',
    "unclosed single quote": "a: 'x\n",
    "bad escape": 'a: "\\q"\n',
    "mapping in a plain scalar": "a: b: c\n",
    "bad indentation": "a:\n  b: 1\n c: 2\n",
    "sequence under a mapping": "a: 1\n- b\n",
    "undefined alias": "a: *nope\n",
    "unknown tag on a value": "a: !!python/object:os.system x\n",
    "duplicate key": "a: 1\na: 2\n",
    "two documents": "a: 1\n---\nb: 2\n",
    "control character": "a: \x07\n",
    "tab indentation": "a:\n\tb: 1\n",
    "block scalar bad indicator": "a: |0\n  x\n",
    "anchor without a name": "a: & x\n",
    "flow mapping missing comma": "a: {b: 1 c: 2}\n",
    "stray closing bracket": "a: [1]]\n",
    "directive after content": "a: 1\n%YAML 1.2\n---\nb: 2\n",
    "key too long": "k" * 1100 + ": 1\n",
}


def test_the_c_parser_is_installed() -> None:
    assert ruamel.yaml.main.CParser is not None


@pytest.mark.parametrize("text", SAME.values(), ids=SAME.keys())
def test_text_the_c_parser_reads_alike_is_read_by_it(text: str) -> None:
    assert yamlread._c_reads_as_pure(text)


@pytest.mark.parametrize("text", PURE_ANYWAY.values(), ids=PURE_ANYWAY.keys())
def test_text_given_to_the_pure_parser_anyway(text: str) -> None:
    assert not yamlread._c_reads_as_pure(text)


@pytest.mark.parametrize(
    "text", [*SAME.values(), *PURE_ANYWAY.values()], ids=[*SAME.keys(), *PURE_ANYWAY.keys()]
)
def test_reader_matches_pure_parser(
    text: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for new, pure in _all_ways(text, tmp_path, monkeypatch):
        assert new == pure


@pytest.mark.parametrize("text", C_DIFFERS.values(), ids=C_DIFFERS.keys())
def test_reader_matches_pure_parser_where_the_c_parser_differs(
    text: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _engine_read(text, pure=False) != _engine_read(text, pure=True)
    for new, pure in _all_ways(text, tmp_path, monkeypatch):
        assert new == pure


@pytest.mark.parametrize("text", BROKEN.values(), ids=BROKEN.keys())
def test_broken_text_gives_the_pure_parser_message(
    text: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for new, pure in _all_ways(text, tmp_path, monkeypatch):
        assert new == pure
    assert _outcome(lambda: yamlread.load(text))[0] == "error"


def test_bytes_that_are_not_utf8_give_the_pure_parser_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "f.yml"
    path.write_bytes(b"a: " + b"x" * 9000 + b"\nb: \xff\n")
    opener = lambda: path.open("r", encoding="utf-8")  # noqa: E731

    def pure_file() -> Any:
        with opener() as stream:
            return YAML(typ="safe", pure=True).load(stream)

    assert _outcome(lambda: yamlread.load_file(opener)) == _outcome(pure_file)
    assert _outcome(pure_file)[1] == "UnicodeDecodeError"
    assert _data(path, None) == _data(path, monkeypatch)
