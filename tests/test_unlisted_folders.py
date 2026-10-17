"""A folder whose children cannot be examined is recorded under unlisted by ``files_in``."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from periplus.engine.select import Selection, files_in


@pytest.fixture
def shut_folder(tmp_path: Path) -> Iterator[Path]:
    closed = tmp_path / "drawer" / "closed"
    (closed / "inner").mkdir(parents=True)
    (closed / "sock.sock").write_text("left\n")
    (tmp_path / "drawer" / "open.sock").write_text("right\n")
    closed.chmod(0o444)
    yield tmp_path
    closed.chmod(0o755)


@pytest.mark.skipif(os.geteuid() == 0, reason="folder permissions do not bind for root")
def test_a_mode_444_folder_is_unlisted_and_none_of_its_files_are_listed(
    shut_folder: Path,
) -> None:
    selection = Selection.build([], {}, [], [], [], [])

    listed, unlisted = files_in(shut_folder, ["drawer"], selection)

    assert (listed, unlisted) == (["drawer/open.sock"], ["drawer/closed"])
