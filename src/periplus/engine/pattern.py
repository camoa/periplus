"""Compile a pack's regular expression with Python's ``re``, and apply normalize steps."""

from __future__ import annotations

import re
from collections.abc import Sequence

__all__ = ["compile_pattern", "reshape"]

#: A named group written ``(?<name>``, which ``re`` spells ``(?P<name>``; lookbehind stays alone.
_NAMED_GROUP = re.compile(r"(?<!\\)\(\?<(?![=!])")


def compile_pattern(expression: str) -> re.Pattern[str]:
    """The expression as a compiled pattern. Raises ``re.error`` when it does not compile.

    The pack format names RE2; this uses Python's ``re`` engine instead.
    """
    return re.compile(_NAMED_GROUP.sub("(?P<", expression))


def reshape(value: str, normalize: Sequence[tuple[re.Pattern[str], str]], case: str = "") -> str:
    """The value with each normalize step applied in order, then set to ``lower`` or ``upper``
    case."""
    for step, replacement in normalize:
        value = step.sub(replacement.replace("\\", "\\\\"), value)
    return value.lower() if case == "lower" else value.upper() if case == "upper" else value
