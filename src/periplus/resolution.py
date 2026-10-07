"""The order the stages run in, and the one record they fill. No stage logic lives here.

``resolve()`` is the single programmatic entry point the console script calls and the one a second
consumer imports. It takes the working directory and the environment as arguments rather than
reading them, so a test resolves against a temporary tree with no monkeypatching anywhere, and so
that nothing in the run depends on global mutable state.

``dependencies`` is passed in and never gathered. The check runs exactly once, in ``main``, before
this module is imported at all — that ordering is the whole of "a missing dependency fails at
startup, named", and a second ``check_runtime_dependencies()`` call from inside ``resolve`` would
run the check after the failure it exists to prevent.

Every stage runs whenever its inputs are available, not when everything upstream succeeded. With no
settings file the run has no pins, so matching is skipped — but the bundled root, the user root and
their candidate directories are knowable with no settings at all, so they are still listed. A stage
that did not run says so in ``ResolutionReport.skipped`` rather than leaving a section that a reader
cannot tell from an empty one.

This module imports ``settings`` and ``packs``, so it imports ``ruamel.yaml`` and ``platformdirs``
transitively. ``cli`` therefore imports it inside ``main()`` and never at module level.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

import periplus
from periplus.errors import ExitCode, Problem
from periplus.packs import (
    MatchedPack,
    PackCandidate,
    PackRoot,
    bundled_digest,
    discover_candidates,
    match_pins,
    resolve_pack_roots,
)
from periplus.preflight import DependencyStatus
from periplus.settings import (
    CONFIG_DIR_VARIABLE,
    ResolvedSettings,
    SettingsSource,
    SettingsUnreadable,
    find_project_root,
    load_settings_document,
    locate_settings,
    resolve_settings,
    user_config_dir,
)

__all__ = ["ResolutionReport", "resolve"]


@dataclass(frozen=True, slots=True)
class ResolutionReport:
    """Everything one run resolved, as records rather than as formatted text.

    There is no ``folders`` field. ``settings`` already carries ``ResolvedSettings.folders`` — the
    merged templates, sorted by name, each naming the file that won it — and with no folder
    interpolation built there is no interpolated value for a second field to hold. ``extensions``
    and every other settings key are reached the same way, so the record has one path to each fact.

    ``user_config_from`` names which of two branches decided the user configuration directory, and
    never names ``XDG_CONFIG_HOME``. ``PERIPLUS_CONFIG_DIR`` is read out of the environment mapping
    this module is handed; everything else is ``platformdirs``, which reads the process environment
    itself and never sees that mapping. A report naming a variable nothing in this package read
    would be false under any test that passes a constructed environment. The directory itself is
    not a field: it is already in the record twice, as the user settings source's ``root`` and as
    the user pack root's ``display``, and a third path to one fact is where two renderers drift.

    ``skipped`` maps the name of a stage that did not run to the reason its inputs were
    unavailable. Each key is the name of the field that stage fills, so ``skipped["packs"]``
    explains an empty ``packs``. That is the difference between "no pins were matched" and
    "matching never ran", which no other field can carry: three unmatched pins also produce an
    empty ``packs``.

    ``tool_version`` is kept because the report is meant to be readable
    without infrastructure and comparable across runs, and a report that does not name the version
    that produced it turns an upgrade into an unexplained diff.
    """

    tool_version: str
    rutters_digest: str
    project_root: Path | None
    user_config_from: Literal["PERIPLUS_CONFIG_DIR", "platformdirs"]
    settings_sources: tuple[SettingsSource, ...]
    settings: ResolvedSettings | None
    pack_roots: tuple[PackRoot, ...]
    candidates: tuple[PackCandidate, ...]
    packs: tuple[MatchedPack, ...]
    dependencies: tuple[DependencyStatus, ...]
    skipped: Mapping[str, str]
    problems: tuple[Problem, ...]

    @property
    def exit_code(self) -> ExitCode:
        """The lowest code among every problem found, or ``OK`` when there were none.

        Lowest rather than first or last, so the status does not depend on the order the stages
        happened to append in.

        This used to explain why exit 3 was never emitted beside exit 4 — 3 would win the
        comparison and report "no settings file found" about a file the run had just named. The
        old hazard is gone with the problem that caused it: no settings file anywhere is no longer
        a problem, so the two can no longer describe the same file.

        **They can still co-occur, about different files, and the old wording claimed otherwise.**
        A user settings file that will not parse plus a ``--settings`` naming a path that is not
        there gives ``[3, 4]`` and exits 3 — measured. That is correct rather than a defect: two
        layers, two independent faults, and the lowest code wins because the caller has to fix the
        thing they asked for before the other one matters. What is no longer possible is the case
        the old sentence was about, where 3 and 4 spoke about one file and 3 lied about it.
        """
        return min((problem.code for problem in self.problems), default=ExitCode.OK)


def resolve(
    start: Path,
    env: Mapping[str, str],
    dependencies: tuple[DependencyStatus, ...],
    settings_path: Path | None = None,
    project_root: Path | None = None,
    pack_checks: bool = False,
) -> ResolutionReport:
    """Run every stage whose inputs are available, and return what they found.

    There is no ``use_user_settings`` parameter. Its only caller was ``--no-user-settings``, which
    was dropped because ``PERIPLUS_CONFIG_DIR`` in ``env`` covers the same need better — it can
    point the user layer at an empty directory, which produces a named ``absent`` source instead of
    no source at all, and that is more of the report rather than less. The flag was also asymmetric
    in a way nothing ever exercised: it would have suppressed the user settings *file* while the
    user *pack root* stayed on the search path, and every root has to be reported.

    ``project_root`` stays although no flag sets it. ``--project-root`` was dropped on the grounds
    that ``resolve()`` already takes it, so tests lose nothing; removing it too would retroactively
    invalidate the reason that flag was dropped.

    With ``pack_checks``, a resolution with no problem also carries what ``periplus map`` refuses
    the matched packs for before it reads a source file.

    Never raises for anything a person's input can cause. Every such failure is a ``Problem`` in
    the record, because the record is the report and a traceback is not.
    """
    config_dir = user_config_dir(env)
    user_config_from: Literal["PERIPLUS_CONFIG_DIR", "platformdirs"] = (
        "PERIPLUS_CONFIG_DIR" if env.get(CONFIG_DIR_VARIABLE) else "platformdirs"
    )

    # The root hint locates the project settings file; the root the report carries is read back
    # off the source that locating produced. Three things can decide a project root — this
    # argument, the `--settings` anchor rule, and the walk up from `start` — and `locate_settings`
    # already implements all three. The anchor rule lives in a private function in `settings.py`,
    # and a rule written in two places is a rule that drifts.
    #
    # The hint is `None` when `settings_path` was given and no root was, because `locate_settings`
    # takes a given root over the anchor: passing the walk's answer there would let a run made
    # from inside some other project silently anchor an explicitly named settings file to that
    # project's root. The precedence is an explicit root, then the `--settings` anchor,
    # then the walk, and this is the line that holds it.
    root_hint = _root_hint(start, settings_path, project_root)
    located = locate_settings(root_hint, config_dir, settings_path)
    sources, documents, problems = _read(located)
    effective_root = next((source.root for source in sources if source.kind == "project"), None)

    skipped: dict[str, str] = {}
    settings = _merge(sources, documents, skipped)
    _refuse_a_named_file_that_is_not_there(settings_path, sources, problems)

    pack_roots = resolve_pack_roots(
        effective_root, config_dir, settings.pack_paths if settings is not None else None
    )
    candidates = discover_candidates(pack_roots)
    packs = _match(settings, candidates, skipped, problems)
    if pack_checks and packs and not problems:
        given = settings.values if settings else {}
        values = {name: s.value for name, s in given.items()}
        origins = {name: s.sources[-1].name for name, s in given.items()}
        problems.extend(_pack_problems(packs, candidates, values, origins))

    return ResolutionReport(
        tool_version=periplus.__version__,
        rutters_digest=bundled_digest(),
        project_root=effective_root,
        user_config_from=user_config_from,
        settings_sources=sources,
        settings=settings,
        pack_roots=pack_roots,
        candidates=candidates,
        packs=packs,
        dependencies=dependencies,
        # Sorted by code then message, once, at the end. `match_pins` returns its problems in pin
        # order and the stages above append theirs, so without this the record's order would be
        # the order the stages happen to run in.
        problems=tuple(sorted(problems, key=lambda problem: (int(problem.code), problem.message))),
        # Sorted by name. Every mapping that reaches a renderer is emitted in name order, and a
        # mapping that arrives already sorted is not a reason for the renderer to assume it.
        skipped=dict(sorted(skipped.items())),
    )


def _refuse_a_named_file_that_is_not_there(
    settings_path: Path | None, sources: tuple[SettingsSource, ...], problems: list[Problem]
) -> None:
    """A settings file the caller named and that is not there is a mistake, not a state.

    This is the one distinction ``_merge`` structurally cannot make. It is handed documents and
    sources, and by the time it sees them "the project layer is absent" looks identical whether a
    ``--settings`` flag named the file or the walk up simply found no project. Only this function's
    caller holds the flag.

    The distinction matters because the two have opposite remedies. Nothing configured is the
    ordinary starting state and is not reported as a failure. A path a
    person typed that does not exist is a typo or a stale script, and answering it with exit 0 and
    an empty ``Problems`` section tells them their file was read when it was not — the same class
    of lie as reporting a stale location. A run against an unexpected settings file has to be
    visible rather than silent, because that is a security concern.

    ``NO_SETTINGS`` keeps the meaning it always had and becomes reachable again through a narrower
    door: not "no settings anywhere", which is fine, but "the settings file you asked for is not
    there", which is not.
    """
    if settings_path is None:
        return
    named = next((source for source in sources if source.kind == "project"), None)
    if named is None or named.status != "absent":
        return
    problems.append(
        Problem(
            code=ExitCode.NO_SETTINGS,
            message=f"the settings file named on the command line is not there: {named.path}",
            detail={"path": str(named.path)},
        )
    )


def _root_hint(start: Path, settings_path: Path | None, project_root: Path | None) -> Path | None:
    """Which root, if any, to hand ``locate_settings`` — never the anchor rule itself.

    ``None`` is not "no root": it is "let the file decide", and ``locate_settings`` answers it with
    the ``--settings`` anchor when there is a settings path and with no project source at all when
    there is not.
    """
    if project_root is not None:
        return project_root
    if settings_path is not None:
        return None
    return find_project_root(start)


def _read(
    located: tuple[SettingsSource, ...],
) -> tuple[tuple[SettingsSource, ...], dict[str, Mapping[str, object]], list[Problem]]:
    """Read every located file that is there, and mark the ones that would not parse.

    A source whose file will not parse is *replaced* with one reading ``skipped``, and kept. It is
    replaced rather than edited because ``SettingsSource`` is frozen, and kept rather than dropped
    because the report has to name the file it refused.
    """
    sources: list[SettingsSource] = []
    documents: dict[str, Mapping[str, object]] = {}
    problems: list[Problem] = []
    for source in located:
        if source.status != "used":
            sources.append(source)
            continue
        try:
            documents[source.kind] = load_settings_document(source.path)
        except SettingsUnreadable as error:
            problem = error.problem()
            problems.append(problem)
            sources.append(replace(source, status="skipped", reason=problem.message))
        else:
            sources.append(source)
    return tuple(sources), documents, problems


def _merge(
    sources: tuple[SettingsSource, ...],
    documents: Mapping[str, Mapping[str, object]],
    skipped: dict[str, str],
) -> ResolvedSettings | None:
    """Merge whatever was read, or record why there was nothing to merge.

    **No settings file at either level is a state, not a problem.** Nothing is wrong with a machine
    nobody has configured yet: every stage whose inputs were available still ran, and the bundled
    root was still found and its packs still discovered. Every path that *was* looked for is
    already printed under ``Settings sources`` with its own ``absent`` — one line in the ordinary
    unconfigured case, because with no project root there is no project source at all, and two
    once a ``.periplus/`` exists. The ``skipped`` entry set below is what the
    ``Effective settings`` block renders, and it says why the merge produced nothing without
    claiming anybody did something wrong.

    This function is deliberately **not** where a settings file the caller *named* is checked. It
    cannot see the flag; ``resolve`` can, and does. See
    ``_refuse_a_named_file_that_is_not_there``.

    This function appends no ``Problem`` at ``ExitCode.NO_SETTINGS`` here. If it did, a fresh
    install would exit 3 and print a ``Problems`` section, which is a command reporting its own
    normal starting condition as a failure. ``exit_code`` is ``min()`` over the problems with ``OK``
    as its default, so an empty list is 0.

    The other branch exits 4. "Every settings file that was found could not
    be read" appends no problem of its own either — the exit-4 problem comes from ``_read``
    catching ``SettingsUnreadable`` — so the two branches are independent.
    """
    if documents:
        return resolve_settings(documents.get("user"), documents.get("project"), sources)

    if any(source.status == "skipped" for source in sources):
        skipped["settings"] = "every settings file that was found could not be read"
        return None

    skipped["settings"] = "no settings file was found at either level"
    return None


def _pack_problems(
    packs: tuple[MatchedPack, ...],
    candidates: tuple[PackCandidate, ...],
    values: Mapping[str, str] | None = None,
    origins: Mapping[str, str] | None = None,
) -> list[Problem]:
    """The problems ``periplus map`` finds in the matched packs before it reads a source file,
    given the project's settings values and the settings file of each."""
    # Imported here: `periplus.validate`, which the pack checks read, imports this module.
    from periplus.engine.check import checked
    from periplus.manifest import resolve_pack_order

    loaded, problems = resolve_pack_order(packs, candidates)
    return list(problems) if problems else checked(loaded, values, origins)[1]


def _match(
    settings: ResolvedSettings | None,
    candidates: tuple[PackCandidate, ...],
    skipped: dict[str, str],
    problems: list[Problem],
) -> tuple[MatchedPack, ...]:
    """Match the pins the settings declared, or record that there were none to match.

    Both matches of a name found under two roots are kept. The name is
    reported twice rather than resolved, so dropping either would resolve it by omission.
    """
    if settings is None:
        skipped["packs"] = "no settings resolved, so no pins were declared"
        return ()
    if settings.packs is None:
        skipped["packs"] = "no settings file declared a packs list"
        return ()
    matches, pin_problems = match_pins(settings.packs.value, candidates)
    problems.extend(pin_problems)
    return matches
