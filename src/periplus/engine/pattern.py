"""Compile a pack's regular expression with Python's ``re``, and apply normalize steps."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

__all__ = ["PATTERN_VALUE", "compile_pattern", "reshape"]

#: A ``{name}`` in an id pattern or a normalize step's pattern: a path or settings value, filled
#: as literal text. A name starts with a letter, so a quantifier such as ``{2}`` stays one.
PATTERN_VALUE = re.compile(r"\{([A-Za-z]\w*)\}")


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


def reshape(
    value: str,
    normalize: Sequence[tuple[re.Pattern[str], str]],
    case: str = "",
    values: Mapping[str, str] | None = None,
) -> str:
    """The value with each normalize step applied in order, then set to ``lower`` or ``upper``
    case. Each ``{name}`` in a step's pattern is filled with that one of ``values`` as literal
    text; a step naming a value ``values`` lacks matches nothing."""
    known = values or {}
    for step, replacement in normalize:
        names = PATTERN_VALUE.findall(step.pattern)
        if not all(name in known for name in names):
            continue
        if names:
            filled = PATTERN_VALUE.sub(lambda found: re.escape(known[found.group(1)]), step.pattern)
            step = re.compile(filled)
        value = step.sub(replacement.replace("\\", "\\\\"), value)
    return value.lower() if case == "lower" else value.upper() if case == "upper" else value
