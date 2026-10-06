"""The order the stages run in, what a skipped stage says, and which failures reach the record.

Every test here calls ``resolve()`` against a temporary tree with a constructed environment
mapping. Nothing monkeypatches a module, because ``resolve`` takes the directory and the
environment as arguments precisely so that nothing has to.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from periplus.errors import ExitCode
from periplus.preflight import DependencyStatus
from periplus.resolution import resolve

# A fixed, complete dependency tuple. `resolve` is handed this rather than calling the check
# itself — the check runs once, in `main`, before `resolution` is imported at all — so the tests
# supply it the same way `main` does and no test here depends on what is installed.
DEPENDENCIES = (
    DependencyStatus(distribution="platformdirs", installed="4.11.5", present=True),
    DependencyStatus(distribution="ruamel.yaml", installed="0.19.1", present=True),
)


def _project(tmp_path: Path, settings: str | None = None) -> Path:
    """A project root: a directory holding ``.periplus/``, and optionally a settings file in it."""
    root = tmp_path / "project"
    (root / ".periplus").mkdir(parents=True)
    if settings is not None:
        (root / ".periplus" / "settings.yml").write_text(settings, encoding="utf-8")
    return root


def _user_config(tmp_path: Path, settings: str | None = None) -> Path:
    """A user configuration directory, with or without a settings file of its own."""
    config = tmp_path / "userconf"
    config.mkdir(parents=True, exist_ok=True)
    if settings is not None:
        (config / "settings.yml").write_text(settings, encoding="utf-8")
    return config


def test_a_stage_whose_inputs_are_unavailable_is_skipped_and_says_so(tmp_path: Path) -> None:
    """With no settings file anywhere, matching is skipped and every knowable root is still listed.

    The rule is "inputs available", not "everything upstream succeeded", and this fixture is what
    separates the two: there is a real project root, so all three roots are knowable and their
    candidates are still discovered, while there are no pins at all, so matching never runs. A
    fixture with no project root produces two roots and hides the distinction.

    ``packs == ()`` alone cannot carry that difference — it is what a run with three unmatched pins
    also produces — so the record has to say the stage did not run.
    """
    root = _project(tmp_path)
    config = _user_config(tmp_path)
    (root / ".periplus" / "packs").mkdir()

    report = resolve(root, {"PERIPLUS_CONFIG_DIR": str(config)}, DEPENDENCIES)

    assert [pack_root.kind for pack_root in report.pack_roots] == ["project", "user", "bundled"]
    assert report.packs == ()
    assert report.settings is None
    assert set(report.skipped) == {"settings", "packs"}
    # Nothing is wrong with this machine, so nothing is reported as wrong with it. An
    # unconfigured run is a state `status` describes, not a failure it reports: every settings path
    # it looked for is printed under `Settings sources` with its own `absent` -- one here, the user
    # layer, because with no project root there is no project source to report -- and the `skipped`
    # entry below says why the merge produced nothing.
    assert report.problems == ()
    assert report.exit_code is ExitCode.OK
    # The stage that could run did: the bundled root holds the shipped packs, and they are
    # discovered with no settings file in play at all. Which packs those are is `test_packs.py`'s
    # discovery question, not this one.
    assert [c.entry for c in report.candidates if c.root.kind == "bundled"] != []


def test_a_settings_file_that_was_asked_for_and_is_not_there_is_a_problem(tmp_path: Path) -> None:
    """Not configuring anything is a state. Naming a file that is not there is a mistake.

    `_merge` cannot tell those apart: it is handed documents and sources, and by then "the project
    layer is absent" looks the same whether a `--settings` flag named it or a walk failed to find
    one. So when the exit-3 problem was removed from `_merge` -- correctly, for the unconfigured
    case -- it went from both, and `status --settings /nope.yml` began reporting exit 0 with an
    empty `problems` list and JSON indistinguishable from an ordinary fresh machine.

    `resolve()` is the one place that knows, because it holds the flag. The distinction is drawn
    there, and `ExitCode.NO_SETTINGS` is what it raises: the code kept its meaning through the
    removal and this is the caller that gives it back a reachable one.
    """
    config = _user_config(tmp_path)
    named = tmp_path / "nowhere" / "settings.yml"

    report = resolve(
        tmp_path,
        {"PERIPLUS_CONFIG_DIR": str(config)},
        DEPENDENCIES,
        settings_path=named,
    )

    assert report.exit_code is ExitCode.NO_SETTINGS
    assert [problem.code for problem in report.problems] == [ExitCode.NO_SETTINGS]
    assert str(named) in report.problems[0].detail["path"]


def test_finding_no_settings_file_without_being_asked_is_not_a_problem(tmp_path: Path) -> None:
    """The other side of the same line, so neither can be satisfied by collapsing both.

    A test for the mistake alone would pass for an implementation that called every absent
    settings file a mistake, which is the behaviour this test rules out.
    """
    config = _user_config(tmp_path)

    report = resolve(tmp_path, {"PERIPLUS_CONFIG_DIR": str(config)}, DEPENDENCIES)

    assert report.problems == ()
    assert report.exit_code is ExitCode.OK


def test_two_layers_can_fail_independently_and_the_lowest_code_wins(tmp_path: Path) -> None:
    """Exit 3 and exit 4 can co-occur, about different files, and a docstring said they could not.

    A user settings file that will not parse is exit 4; a `--settings` naming a path that is not
    there is exit 3. Both at once is two layers with two independent faults, and `min()` reports 3
    because the caller has to fix the file they asked for before the other one matters.

    Written because the claim was made in prose and nothing checked it. What the removal of the
    old exit-3 problem did close is the case where 3 and 4 described *one* file and 3 lied about
    it; the general co-occurrence was never impossible.
    """
    config = _user_config(tmp_path)
    (config / "settings.yml").write_text("- not a mapping\n", encoding="utf-8")
    named = tmp_path / "nowhere" / "settings.yml"

    report = resolve(
        tmp_path,
        {"PERIPLUS_CONFIG_DIR": str(config)},
        DEPENDENCIES,
        settings_path=named,
    )

    assert sorted(int(problem.code) for problem in report.problems) == [3, 4]
    assert report.exit_code is ExitCode.NO_SETTINGS


def test_the_unconfigured_state_is_named_once_and_not_twice(tmp_path: Path) -> None:
    """One fact, in the section whose job is to carry it.

    The settings paths that were looked for are in `settings_sources`, one per layer, each with its
    own `absent` status. A problem repeating them in a `searched`
    detail under a heading that says something is wrong would be the same fact twice, with the
    second copy in the wrong place.

    Asserted on the rendered text rather than on the record, because "reported once" is a claim
    about what a person reads. Asserting `report.problems == ()` would pass for a run that printed
    the paths under `Problems` some other way.
    """
    from periplus.report import render_text

    config = _user_config(tmp_path)
    rendered = render_text(resolve(tmp_path, {"PERIPLUS_CONFIG_DIR": str(config)}, DEPENDENCIES))

    sources, _, problems = rendered.partition("Problems:")
    settings_path = str(config / "settings.yml")

    assert settings_path in sources, rendered
    assert settings_path not in problems, rendered
    assert problems.strip() == "none", rendered
    assert "no settings file was found at either level" in sources, rendered


@pytest.mark.parametrize("layer", ["project", "user"])
def test_a_settings_file_that_will_not_parse_is_exit_4_and_stays_marked_skipped(
    tmp_path: Path, layer: str
) -> None:
    """One problem, naming the file, at the code that says what to do about it — at either layer.

    The exit-4 half was named ``test_exit_3_is_not_emitted_beside_the_file_it_would_contradict``
    and guarded a hazard that no longer exists: ``_merge`` used to append an exit-3 problem for "no
    settings file at either level", and because ``exit_code`` is the lowest code among the
    problems, a run emitting both would have reported "no settings file was found" about a file it
    had just found, named and refused. That problem is gone — an unconfigured run is not a failure
    — so there is no 3 anywhere for this to be emitted beside.

    The refused file stays in ``settings_sources``, reading ``skipped`` and carrying a reason.
    ``SettingsSource`` is frozen, so it is replaced rather than edited. Dropping it instead would
    pass any assertion that only looks at ``problems`` while the report stopped naming the file it
    refused.

    Both layers, because the rule is "no source is ``used`` **and** none is ``skipped``" and the
    predicate names no ``kind``, so the user row holds by construction. That is exactly the
    reasoning this project has been caught by seven times. An implementation that tested only the
    project layer — ``next((s for s in sources if s.kind == "project"), None)`` in place of the
    ``any()`` — passes the project row and fails the user one.

    The project row has no user file on purpose: with one that parses there is a ``used`` source,
    and that suppresses the 3 for a reason this test is not about. The user row starts in a
    directory with no ``.periplus`` anywhere above it, so there is no project source at all rather
    than an absent one.
    """
    if layer == "project":
        start = _project(tmp_path, "- not a mapping\n")
        config = _user_config(tmp_path)
        refused = start / ".periplus" / "settings.yml"
        expected_sources = [("user", "absent"), ("project", "skipped")]
    else:
        config = _user_config(tmp_path, "- not a mapping\n")
        start = tmp_path / "outside"
        start.mkdir()
        refused = config / "settings.yml"
        expected_sources = [("user", "skipped")]

    report = resolve(start, {"PERIPLUS_CONFIG_DIR": str(config)}, DEPENDENCIES)

    assert [problem.code for problem in report.problems] == [ExitCode.UNREADABLE_SETTINGS]
    assert report.exit_code is ExitCode.UNREADABLE_SETTINGS
    assert report.settings is None

    assert [(s.kind, s.status) for s in report.settings_sources] == expected_sources
    skipped = [s for s in report.settings_sources if s.status == "skipped"]
    assert skipped[0].reason is not None
    assert skipped[0].path == refused


def test_the_project_root_is_read_back_off_the_located_source(tmp_path: Path) -> None:
    """All three ways a project root is decided, each against a tree where the others would differ.

    The precedence: an explicit root wins, then the
    ``--settings`` anchor, then the walk up from ``start``. Every case starts the walk inside a real
    project tree whose root is *not* the expected answer, so a rule that let the walk win would fail
    each of the last two rather than agreeing with them by coincidence.

    The anchor rule itself is never re-derived here. ``locate_settings`` owns it, the report reads
    the root back off the source it produced, and a rule written in two places is a rule that
    drifts.
    """
    walked = _project(tmp_path)
    config = {"PERIPLUS_CONFIG_DIR": str(_user_config(tmp_path))}

    explicit = tmp_path / "explicit"
    explicit.mkdir()
    assert resolve(walked, config, DEPENDENCIES, project_root=explicit).project_root == explicit

    anchored = tmp_path / "anchored"
    (anchored / ".periplus").mkdir(parents=True)
    (anchored / ".periplus" / "settings.yml").write_text("packs: []\n", encoding="utf-8")
    report = resolve(
        walked, config, DEPENDENCIES, settings_path=anchored / ".periplus/settings.yml"
    )
    assert report.project_root == anchored

    loose = tmp_path / "loose"
    loose.mkdir()
    (loose / "elsewhere.yml").write_text("packs: []\n", encoding="utf-8")
    report = resolve(walked, config, DEPENDENCIES, settings_path=loose / "elsewhere.yml")
    assert report.project_root == loose

    # The three answers are three different directories, and none of them is the one the walk
    # would have found. Without this the first case could pass while the other two agreed with
    # each other for the wrong reason.
    assert len({explicit, anchored, loose, walked}) == 4


def test_problems_reach_the_record_ordered_by_code_and_not_by_the_stage_that_found_them(
    tmp_path: Path,
) -> None:
    """A duplicate pin written before a missing one still reports 5 before 6.

    ``match_pins`` returns its problems in pin order, so the natural append order here is 6 then 5.
    Pins already written in outcome order cannot test the sort.

    The same fixture covers two properties the worked example cannot: a directory added through
    ``pack_paths`` appears among the roots, naming the settings file that added it, and one name
    under two roots is reported twice rather than resolved.
    """
    root = _project(
        tmp_path,
        "packs:\n  - dup@1.0.0\n  - missing@1.0.0\npack_paths:\n  - ../extra\n",
    )
    config = _user_config(tmp_path)
    (root / ".periplus" / "packs" / "dup@1.0.0").mkdir(parents=True)
    (tmp_path / "extra" / "dup@1.0.0").mkdir(parents=True)

    report = resolve(root, {"PERIPLUS_CONFIG_DIR": str(config)}, DEPENDENCIES)

    assert [problem.code for problem in report.problems] == [
        ExitCode.PIN_UNMATCHED,
        ExitCode.PIN_DUPLICATED,
    ]
    assert report.exit_code is ExitCode.PIN_UNMATCHED

    configured = [pack_root for pack_root in report.pack_roots if pack_root.kind == "configured"]
    assert [pack_root.display for pack_root in configured] == [str(tmp_path / "extra")]
    assert configured[0].source is not None
    assert configured[0].source.name == str(root / ".periplus" / "settings.yml")

    # Both matches survive. Reporting the name once would resolve the duplicate by omission.
    assert [(m.pin, m.root.kind) for m in report.packs] == [
        ("dup@1.0.0", "project"),
        ("dup@1.0.0", "configured"),
    ]


def test_the_report_names_the_branch_that_decided_the_user_configuration_directory(
    tmp_path: Path,
) -> None:
    """``PERIPLUS_CONFIG_DIR`` or ``platformdirs``, and never ``XDG_CONFIG_HOME``.

    ``platformdirs.user_config_dir`` takes no environment argument and reads ``os.environ``
    directly, so it never sees the mapping ``resolve`` is handed. In production that mapping is
    ``os.environ`` and the two agree, which is exactly what would make the defect invisible: under
    a test passing a constructed environment, a report naming ``XDG_CONFIG_HOME`` would be naming a
    variable nothing in this package read.

    The second case proves it by passing an ``XDG_CONFIG_HOME`` that ``platformdirs`` is reading
    from the real process environment rather than from here — the report must still say
    ``platformdirs``, and the located user file must not sit under the directory this mapping names.
    """
    config = _user_config(tmp_path)
    report = resolve(tmp_path, {"PERIPLUS_CONFIG_DIR": str(config)}, DEPENDENCIES)
    assert report.user_config_from == "PERIPLUS_CONFIG_DIR"
    assert [s.root for s in report.settings_sources if s.kind == "user"] == [config]

    decoy = tmp_path / "xdg"
    report = resolve(tmp_path, {"XDG_CONFIG_HOME": str(decoy)}, DEPENDENCIES)
    assert report.user_config_from == "platformdirs"
    assert [s.root for s in report.settings_sources if s.kind == "user"] != [decoy / "periplus"]

    # An empty value is not an override. `user_config_dir` treats it as absent, so the branch the
    # report names has to agree with the branch the directory came from.
    report = resolve(tmp_path, {"PERIPLUS_CONFIG_DIR": ""}, DEPENDENCIES)
    assert report.user_config_from == "platformdirs"
