"""Compile a pack's regular expression with Python's ``re``, and apply normalize steps."""

from __future__ import annotations

import re
from collections.abc import Sequence

__all__ = ["compile_pattern", "reshape"]


def _named_groups(expression: str) -> str:
    """The expression with each named group ``(?<name>`` spelt ``(?P<name>`` the way ``re`` wants.

    A lookbehind, ``(?<=`` or ``(?<!``, stays as it is. An escaped character is copied as a pair, so
    a backslash before the paren leaves it literal. Text inside a character class is copied as it
    is, so ``[(?<]`` stays a class of three characters.
    """
    out: list[str] = []
    i = 0
    in_class = False
    while i < len(expression):
        ch = expression[i]
        if ch == "\\":
            out.append(expression[i : i + 2])
            i += 2
        elif in_class:
            in_class = ch != "]"
            out.append(ch)
            i += 1
        elif ch == "[":
            in_class = True
            # A ] right after [ or [^ is a literal member of the class, not its end.
            end = i + 1
            if expression[end : end + 1] == "^":
                end += 1
            if expression[end : end + 1] == "]":
                end += 1
            out.append(expression[i:end])
            i = end
        elif expression.startswith("(?<", i) and not expression.startswith(("(?<=", "(?<!"), i):
            out.append("(?P<")
            i += 3
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def compile_pattern(expression: str) -> re.Pattern[str]:
    """The expression as a compiled pattern. Raises ``re.error`` when it does not compile.

    The pack format names RE2; this uses Python's ``re`` engine instead.
    """
    return re.compile(_named_groups(expression))


def reshape(value: str, normalize: Sequence[tuple[re.Pattern[str], str]], case: str = "") -> str:
    """The value with each normalize step applied in order, then set to ``lower`` or ``upper``
    case."""
    for step, replacement in normalize:
        value = step.sub(replacement.replace("\\", "\\\\"), value)
    return value.lower() if case == "lower" else value.upper() if case == "upper" else value
