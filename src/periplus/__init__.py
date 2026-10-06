"""Periplus — a schema-first, deterministic codebase mapper, configurable to any stack.

The package holds every unit of logic. ``periplus.cli`` parses arguments and wires; it decides
nothing. Import what you need from the module that owns it rather than from here: this module
exposes only the version, and resolves even that lazily, so importing the package does almost no
work.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

# Declares what ``__getattr__`` resolves, so a consumer reading ``periplus.__version__`` gets
# ``str`` and not ``Any``.
#
# This is a declaration in the module and not a ``__init__.pyi`` stub beside it, because a stub
# *shadows* the module under PEP 561: mypy opens the stub and never reads this file. Measured
# before the stub was deleted — a planted ``broken: int = "not an int"`` at module level left
# ``mypy`` reporting success; with this declaration instead, the same plant is reported.
#
# The trade: a module-level ``__getattr__`` makes *every* attribute of this package valid to
# mypy, so a consumer writing ``periplus.anything_at_all`` type-checks clean where the stub
# rejected it.
if TYPE_CHECKING:
    __version__: str

__all__ = ["DISTRIBUTION", "__version__"]

#: The distribution name on PyPI. The import name is ``periplus`` and the console script is
#: ``periplus``; only the distribution carries the ``-map`` suffix, because ``periplus`` on PyPI
#: is taken by an unrelated project.
DISTRIBUTION = "periplus-map"


def __getattr__(name: str) -> str:
    """Resolve ``__version__`` on first access rather than at import.

    ``importlib.metadata.version`` reads the installed distribution's metadata off disk,
    which is work, and work at import time is paid by every consumer including one that never
    asks for the version. PEP 562 lets that cost fall on the caller who wants it.

    The number itself lives in ``pyproject.toml`` and nowhere else, so what this returns is
    what the project declared, by construction rather than by two files agreeing.

    The result is cached into the module dict, so the metadata read happens at most once per
    process and every later access is an ordinary attribute lookup.
    """
    if name == "__version__":
        from importlib.metadata import version

        resolved = version(DISTRIBUTION)
        globals()["__version__"] = resolved
        return resolved
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    """List ``__version__`` alongside the real module contents.

    PEP 562 pairs ``__getattr__`` with ``__dir__`` for exactly this reason: without it a name
    promised in ``__all__`` is importable but absent from ``dir()``, so anything that
    introspects the module — a REPL completion, a doc generator, a plugin loader reading
    exports — sees a namespace that contradicts the module's own declaration.

    Returns ``__all__`` exactly. Unioning it with ``globals()`` was tried and leaked
    ``annotations`` — the ``__future__`` import's own binding — into the module's advertised
    surface, along with every module dunder. This module's public surface *is* ``__all__``, so
    saying so is both simpler and true.
    """
    return sorted(__all__)
