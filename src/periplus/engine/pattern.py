"""Compile a pack's regular expression with Python's ``re``, and apply normalize steps."""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from functools import cache, lru_cache

__all__ = [
    "compile_pattern",
    "compile_unfilled",
    "fill_values",
    "filled_pattern",
    "reshape",
    "value_names",
]

#: An escaped character, or a ``{name}`` in an id pattern or a normalize step's pattern or
#: replacement: a path or settings value. An escaped character is matched first, so a brace after
#: an odd number of backslashes stays literal. A name starts with a letter, so a quantifier such as
#: ``{2}`` stays one.
_VALUE = re.compile(r"\\.|\{([A-Za-z]\w*)\}", re.DOTALL)


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


def compile_unfilled(expression: str) -> re.Pattern[str]:
    """The expression compiled before its values are known, to check it and read its captures:
    each value it names filled in as one letter, or, when that does not compile, as empty text, so
    a value at either end of a range such as ``[z-{p}]`` is left to the run. Raises ``re.error``
    when it compiles neither way."""
    try:
        return compile_pattern(fill_values(expression, lambda _: "x"))
    except re.error:
        return compile_pattern(fill_values(expression, lambda _: ""))


@cache
def value_names(text: str) -> tuple[str, ...]:
    """Each name the text names as ``{name}``, in order."""
    return tuple(found.group(1) for found in _VALUE.finditer(text) if found.group(1))


def fill_values(text: str, fill: Callable[[str], str]) -> str:
    """The text with each ``{name}`` it names replaced with ``fill(name)``."""
    if not value_names(text):
        return text
    return _VALUE.sub(lambda found: fill(found[1]) if found[1] else found[0], text)


def filled_pattern(expression: str, values: Mapping[str, str]) -> re.Pattern[str] | None:
    """The expression compiled with each value it names filled in as literal text, escaped;
    ``None`` when a value it names is absent or the filled expression does not compile."""
    names = value_names(expression)
    if any(name not in values for name in names):
        return None
    return _compiled(expression, tuple((name, values[name]) for name in names))


@lru_cache(maxsize=4096)
def _compiled(expression: str, values: tuple[tuple[str, str], ...]) -> re.Pattern[str] | None:
    """The expression with the values filled in, compiled; ``None`` when it does not compile, as
    an empty value inside a character class makes ``[]``. Cached by the values it names, so a
    path value does not recompile the pattern on every call."""
    given = dict(values)
    try:
        return compile_pattern(fill_values(expression, lambda name: re.escape(given[name])))
    except re.error:
        return None


def reshape(
    value: str,
    normalize: Sequence[tuple[re.Pattern[str], str]],
    case: str = "",
    values: Mapping[str, str] | None = None,
) -> str:
    """The value with each normalize step applied in order, then set to ``lower`` or ``upper``
    case. Each ``{name}`` in a step's pattern is filled with that one of ``values`` as literal
    text, and in its replacement as text. A step naming a value ``values`` lacks, or whose pattern
    does not compile once filled, does not run."""
    known = values or {}
    for step, replacement in normalize:
        named = value_names(replacement)
        if any(name not in known for name in named):
            continue
        if value_names(step.pattern):
            filled = filled_pattern(step.pattern, known)
            if filled is None:
                continue
            step = filled
        if named:
            replacement = fill_values(replacement, known.__getitem__)
        value = step.sub(replacement.replace("\\", "\\\\"), value)
    return value.lower() if case == "lower" else value.upper() if case == "upper" else value
