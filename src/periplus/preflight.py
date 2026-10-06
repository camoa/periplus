"""The runtime dependency check: what the package declares it needs, and what is actually there.

This module exists because of one requirement — "the command exits non-zero naming
which one, **rather than failing later inside a subcommand**". Answering the first half needs
nothing; a missing import raises on its own and the status is non-zero. The second half is the
whole design: the failure has to be found before anything that would trip over it is imported. So
``cli`` imports this module and ``errors`` at module level and imports ``periplus.resolution``
inside ``main()``, and this file is what runs in the gap.

That is also why the check reads installed metadata instead of importing the packages. Importing
``ruamel.yaml`` to find out whether ``ruamel.yaml`` is importable would raise the exact
``ImportError`` that must not be what the user sees.

Standard library only, and nothing here or on ``cli``'s module-level import path may import
``ruamel.yaml``, ``platformdirs`` or ``jsonschema``. See ``errors`` for the two-clause form of that
property and the test that holds it.

This module reports and does not decide. It returns statuses; ``main`` turns an absence into a
process status. ``resolution.resolve()`` will later be handed the same tuple as a parameter rather
than calling this function again, because a second call from inside ``resolve`` would run the check
after the failure it exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["REQUIRED", "DependencyStatus", "check_runtime_dependencies"]

#: The distributions the package cannot run without, hardcoded here and compared against
#: ``pyproject.toml`` by a test rather than read back at runtime. Reading them at runtime would
#: mean parsing PEP 508 requirement strings with their markers and extras evaluated, which is a
#: fourth dependency for three packages that would then need it.
#:
#: ``jsonschema`` is the third, and it is the name this list most needed. ``periplus validate``
#: checks a pack against the shipped schemas with the reference implementation, so an install
#: without it dies of an ``ImportError`` inside a subcommand — the one failure this module exists
#: to prevent — unless the name is here.
#:
#: A language grammar is not here: only a loaded rutter that pins one needs it, and the pack
#: check reports a pinned grammar that is absent or cannot be imported.
#:
#: Written in the manifest's own order rather than sorted, on purpose.
#: ``check_runtime_dependencies`` sorts, and a sorted constant would make that sort a no-op that
#: could be deleted with every test
#: still green — the determinism the report needs would then rest on the order somebody happened to
#: type here.
REQUIRED: tuple[str, ...] = (
    "ruamel.yaml",
    "platformdirs",
    "jsonschema",
    "tree-sitter",
)


@dataclass(frozen=True, slots=True)
class DependencyStatus:
    """What was found for one distribution.

    ``installed`` and ``present`` are both carried because they answer different questions. The
    report names the version when there is one, and a consumer branching on availability should
    read a boolean rather than infer one from ``None``.
    """

    distribution: str
    installed: str | None
    present: bool


def check_runtime_dependencies() -> tuple[DependencyStatus, ...]:
    """One status per required distribution, sorted by distribution name.

    Sorted by code point through Python's own string ordering, which is not locale-aware — the
    report has to be byte-identical across two runs on the same input, and these statuses reach it.

    ``importlib.metadata`` is imported here rather than at module level, and that is a decision
    with a measurement behind it rather than a style preference. It costs about 29 ms of import
    subtree — roughly 36 ms of wall clock on a whole interpreter run, measured 2026-08-30 on
    Python 3.14.7 — which is over three times what ``dataclasses`` costs and most of the 44 ms the
    packaging component fought to remove by resolving ``__version__`` lazily. At module level it
    would sit on ``cli``'s module-level import path and be paid by ``periplus --help``, by every
    consumer that imports ``periplus.cli`` as a library, and by the blocked-import test. Here it is
    paid by the caller that asks, which is the same arrangement and the same reason as
    ``__init__.__getattr__``. Re-measure with
    ``python -X importtime`` rather than trusting the number.
    """
    from importlib.metadata import PackageNotFoundError, version

    statuses = []
    for distribution in sorted(REQUIRED):
        try:
            installed: str | None = version(distribution)
        except PackageNotFoundError:
            installed = None
        statuses.append(
            DependencyStatus(
                distribution=distribution,
                installed=installed,
                present=installed is not None,
            )
        )
    return tuple(statuses)
