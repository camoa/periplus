"""The error vocabulary: the exit-code table, the record a failure renders into, and the base
class every failing module raises.

Every module in the package imports this one, and ``cli`` imports it at module level — before the
dependency check has run. That places one constraint on this file, and the constraint is its whole
shape:

    ``errors`` and ``preflight`` import only the standard library, and nothing on ``cli``'s
    module-level import path imports ``ruamel.yaml``, ``platformdirs`` or ``jsonschema``.

Two clauses, because they are two different properties. The first is about this file and can be
read off the header below. The second is about a graph, and it is the one a missing dependency
reported by name actually needs: a first-party ``from periplus.settings import ...``
here would satisfy "standard library only" while pulling ``ruamel.yaml`` onto the very path the
dependency check exists to keep clear. ``jsonschema`` is the third name in that clause since
``periplus validate`` grew a reference validator, and it is why ``cli`` imports that module inside
``main()`` rather than at module level. The file would look clean and the startup check would be
broken. Declaring ``Problem`` in ``resolution.py`` would have exactly that defect.

An earlier wording of this constraint said this module "imports nothing". That is literally false
and cannot be satisfied — ``ExitCode`` needs ``enum``, ``Problem`` needs ``dataclasses``,
``ClassVar`` needs ``typing`` and ``Mapping`` needs ``collections.abc``. The two-clause form above
replaced it.

``tests/test_console_script.py`` asserts the graph property directly: it imports ``periplus.cli`` in
a subprocess with every runtime distribution blocked at ``sys.meta_path``, having first confirmed in
that same subprocess that the block works.

What this module costs, recorded because it is paid on every invocation and the trade is
deliberate rather than overlooked. ``dataclasses`` is about 8.6 ms of import subtree on this
project's interpreter, against ``argparse`` at about 1.6 ms, because it pulls ``inspect``, ``ast``,
``dis`` and ``tokenize``. ``Problem`` is a frozen dataclass anyway: nothing in this package crosses
a boundary as a dictionary with implied keys, which is what lets a JSON renderer be a mechanical
walk rather than a place where the record's shape is re-decided. Startup time is not a
measured requirement.

The distribution name is not here. It is in ``__init__.py``, which needs it to resolve
``__version__`` and which imports nothing at all; taking it from here would pull ``enum`` and
``dataclasses`` into every ``import periplus``, and the reverse edge would be a cycle. It was never
error vocabulary — it sat in the design here only because this was to be the module importing
nothing, and ``__init__.py`` is now that module.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import IntEnum
from types import MappingProxyType
from typing import ClassVar

__all__ = ["ExitCode", "HarnessError", "Problem"]


class ExitCode(IntEnum):
    """Every status the process can return, one per class of failure.

    One code per class, and each is a different thing for a person to do about it: install
    something, fix a pin, delete a copy, fix a name, break a cycle. There is no code for a pin
    disagreeing with a manifest, because that check belongs to the validator: ``packs.py`` assigns
    it there by name, and ``manifest.py`` — which does open a ``pack.yaml`` — deliberately declines
    it, carrying the directory's name and the manifest's own ``pack`` side by side rather than
    choosing between them. Pin matching itself opens nothing inside a pack directory and could not
    make the check; the reader that could is not its owner.

    All of them are declared here although nothing in this package raises ``INTERNAL`` and nothing
    returns ``USAGE`` as a value — both are statuses the process produces anyway, an uncaught
    exception through the interpreter and a usage error through ``parser.error``. A code table
    costs nothing to declare and withholding members would mean editing this enum in five later
    components — which is the edit the open-closed principle says should never be needed. What
    each member traces to is written beside it.

    7 and 8 are absent rather than free. They were declared for a folder component, forecasting
    ``FOLDER_UNKNOWN`` and ``FOLDER_CYCLE``, and were deleted because nothing
    folder-shaped was ever built and this file's own rule is that a failure class arrives with the
    module that raises it. Neither number is reused: renumbering would change a status a person
    may already have scripted against.
    """

    #: Resolved. Implied by every command that produces a report.
    OK = 0

    #: An exception that is not a ``HarnessError``. Nothing raises it:
    #: an uncaught Python exception already exits 1, so a top-level handler here would only
    #: swallow the traceback that makes an internal error diagnosable. The member documents what
    #: the status means. Adding the handler is a separate decision.
    INTERNAL = 1

    #: A usage error — argparse's own status, and the one ``cli`` already returned as a literal
    #: before this enum existed.
    USAGE = 2

    #: A settings file that was **asked for** is not there. Raised by
    #: ``resolution._refuse_a_named_file_that_is_not_there``, and by nothing else.
    #:
    #: It used to mean "no settings file at either level", which ``_merge`` raised on every
    #: unconfigured run — so a fresh install exited 3 and printed a ``Problems`` section, reporting
    #: its own normal starting condition as a fault. That is gone: for a command whose job is to
    #: describe a state, an empty one is the state. What is left is the narrower case with the
    #: opposite remedy — a path a person typed that does not exist, where exit 0 would tell them a
    #: file was read that never was.
    #:
    #: The number is unchanged through both, which is the point of declaring the table up front.
    NO_SETTINGS = 3

    #: A settings file could not be read or parsed. It follows
    #: from the decision to parse with ``ruamel.yaml`` at ``typ='safe'``, which raises on a
    #: duplicate key where PyYAML silently keeps the last value. That refusal has to surface.
    UNREADABLE_SETTINGS = 4

    #: A pin matched no directory name. The *report* is required — "a named pin with no
    #: matching directory is reported missing"; that the status is non-zero, and that it is 5, is a
    #: design decision.
    PIN_UNMATCHED = 5

    #: One pin matched a directory name under two roots. Same split as above: "reported twice
    #: rather than resolved" is the requirement, the status is the decision.
    PIN_DUPLICATED = 6

    #: A required distribution is absent. A non-zero status naming which one is required; the
    #: number 9 is design.
    MISSING_DEPENDENCY = 9

    #: A path a command had to create is already there, and nothing was overwritten. Raised by
    #: ``init.TargetExists``, which enumerates its causes: a settings file that already exists, a
    #: regular file where either directory belongs, or a symlink where either belongs, refused
    #: rather than followed. All are one thing to do about it: look at the named path. The number
    #: 10 is design; it is the first member added after the original table.
    TARGET_EXISTS = 10

    #: A pack manifest exists as a path and could not be turned into a mapping. Raised by
    #: ``manifest.ManifestUnreadable``, whose ``detail`` names which of the five causes it was.
    #: The same shape as ``UNREADABLE_SETTINGS`` and a separate number, because the two name
    #: different files with different owners: a person edits their own settings file, and a pack
    #: manifest is shipped by whoever wrote the pack.
    UNREADABLE_MANIFEST = 11

    #: A ``depends`` entry names a pack no directory on the search path carries. One thing to do
    #: about it: install that pack, or fix the name. The number 12 is design.
    #:
    #: ``DEPENDS_`` and not ``DEPENDENCY_``, throughout: ``MISSING_DEPENDENCY`` above already
    #: means a runtime *distribution*, and so does ``preflight.DependencyStatus``. The three
    #: members below are named for the manifest key they read, which is the one word that cannot
    #: be confused with the other meaning.
    DEPENDS_UNMATCHED = 12

    #: A ``depends`` entry names a pack two directories on the search path both carry — ``php``
    #: with a ``php@0.1.0`` and a ``php@0.2.0`` beside it. The same split as ``PIN_DUPLICATED``:
    #: it is reported rather than resolved, because a ``depends`` entry carries no version and
    #: nothing in the manifest says which of the two the author meant.
    DEPENDS_DUPLICATED = 13

    #: A pack's ``depends`` chain reaches back to a pack already on the path being walked, itself
    #: included. One thing to do about it: break the cycle. The manifest schema does not forbid
    #: it — ``depends`` items are matched against a name pattern and nothing compares them to the
    #: declaring pack — so it is detected here rather than assumed away.
    DEPENDS_CYCLE = 14

    #: A pack named on the command line is not on the pack search path. Returned by
    #: ``spec._unknown_pack``, and reachable the first time somebody types ``periplus spec`` and
    #: misspells a pack.
    #:
    #: Its own number, and not ``DEPENDS_UNMATCHED``, although the remedy is the same sentence —
    #: install that pack, or fix the name. That member says a *manifest* names a pack nothing
    #: carries, which is a fault in a file somebody wrote and shipped; this one says an *argument*
    #: does, which is a typo at a prompt. Different file, different owner, and a report printing
    #: one number for both would tell a reader less than it knows.
    #:
    #: **It is a code in the report first, and on the process status it is often not there at
    #: all.** Two facts about where it can appear, both read off the code rather than argued:
    #:
    #: * It never co-occurs with a ``DEPENDS_*`` code. ``spec._describe_pack`` appends this
    #:   problem and returns *before* ``resolve_pack_order`` is called, so a run that produced 15
    #:   walked no dependency graph, and a run that walked one found the pack. The two are
    #:   mutually exclusive by construction, and an earlier version of this docblock justified the
    #:   member with a run — a misspelled ``drupal`` whose ``yaml`` dependency is also missing —
    #:   that cannot happen.
    #: * It does co-occur with a settings or pin fault, because ``spec`` resolves the search path
    #:   exactly as ``status`` does and inherits every problem resolution found. A report's status
    #:   is the *lowest* code among its problems and 15 is the highest number any report reaches
    #:   this way, so any such fault takes the status and this one is masked: ``periplus spec
    #:   twigg`` exits 5 in a project pinning a pack that is not installed, and 15 in a directory
    #:   that is not a project. Measured, both. (16 below is higher still and is never reached by
    #:   ``min()`` at all; that is the whole of its own note.)
    #:
    #: So the process status of a project that has any other fault does not tell a broken pack
    #: name from a broken invocation, and a script that needs to must read the report rather than
    #: ``$?``. That is where the two stay distinguishable: the problem is carried in
    #: ``SpecReport.problems`` under this code with a ``detail`` naming the pack asked for and
    #: every pack that is there, printed beside its number in the text form and under ``problems``
    #: in ``--format json``. The status says a run had a fault; the report says which faults.
    PACK_UNKNOWN = 15

    #: A file inside a pack disagrees with the schema that pack file is written against. Returned
    #: by ``validate.ValidationReport.exit_code``, and by nothing else.
    #:
    #: Its own number, and not one of the ``UNREADABLE_`` codes: those say a file could not be
    #: turned into a mapping at all, and this one says the mapping is there and says the wrong
    #: thing. One remedy either way — open the named file — but a different fault, and the report
    #: names a key and a pointer inside the document for this one and cannot for those.
    #:
    #: **It is the one code with its own aggregation rule, and it needs one.** Every other report
    #: takes ``min()`` over its problems, for the reason ``ResolutionReport.exit_code`` gives: the
    #: status must not depend on the order the stages appended in. 16 is the highest number in this
    #: table, so under ``min()`` it would be masked by every existing code — a ``validate`` run in a
    #: project that also pins a pack nobody installed would exit 5, answering a question about a
    #: pack with a fault in a settings file. So ``validate`` departs: **any schema error yields 16,
    #: and with none the resolution problems aggregate by ``min()`` exactly as they do elsewhere.**
    #: That departure is a property of one report and not of this table, which is why it is stated
    #: here beside the member and asserted by a pair of tests — one run with both faults at once,
    #: one with only the resolution fault — because either alone is satisfied by the wrong rule.
    #:
    #: A schema error is never dropped from the report to make the status say something. Both
    #: kinds are carried side by side: ``ValidationReport.errors`` and ``ValidationReport.problems``
    #: are separate fields because they are faults in different files with different owners.
    SCHEMA_INVALID = 16

    #: ``periplus map`` built a document its own schema refuses: an engine defect, nothing written.
    MAP_INVALID = 17

    #: A folder name is unknown, cyclic, in conflict between packs, or leaves the project root.
    FOLDER_UNRESOLVED = 18

    #: A pack's rule file cannot be read, or its types or rules disagree.
    PACK_RULES_UNREADABLE = 19

    #: A source file cannot be read as data: a parse error, bytes that are not UTF-8, a root that
    #: is not a mapping, a tag outside the core set, or a key written twice in one mapping.
    SOURCE_UNREADABLE = 20

    #: Rules found types for one id that do not lie on one ancestor chain.
    TYPE_COLLISION = 21

    #: An edge's end has a type the edge kind does not allow there.
    EDGE_ILLEGAL = 22

    #: A pack names a type that neither it nor a pack it depends on declares.
    UNDECLARED_TYPE = 23

    #: An edge rule names a kind that neither its pack nor a pack it depends on declares.
    UNDECLARED_EDGE_KIND = 24

    #: Two rules of one pack carry one name.
    RULE_DUPLICATED = 25

    #: A rule has a shape the engine cannot execute, so the run is refused rather than partial.
    RULE_NOT_EXECUTABLE = 26

    #: The map could not be written to the path asked for.
    OUTPUT_UNWRITABLE = 27

    #: A pack's grammar pins a parser runtime or a grammar version other than the one installed,
    #: or one that is not installed at all. Found before any source file is opened.
    GRAMMAR_MISMATCH = 28


@dataclass(frozen=True, slots=True)
class Problem:
    """One failure, as a record rather than as a formatted string.

    ``message`` is the one line a person reads. ``detail`` is the same failure as named facts, so a
    consumer of ``--format json`` reads keys rather than parsing prose. Both are populated at the
    point the failure is found, where the facts are still in scope.

    Frozen and slotted so that a report is assembled from records that cannot be edited after the
    stage that produced them has returned, and so that a renderer walking a report cannot silently
    depend on a key nobody declared.
    """

    code: ExitCode
    message: str
    detail: Mapping[str, str]


class HarnessError(Exception):
    """The base of every failure the harness raises, carrying its own exit code.

    ``code`` is declared and deliberately not assigned. A subclass sets it, so the exit-code table
    is a property of the class hierarchy rather than a branch inside ``main`` — adding a failure
    class is a new exception class and a new enum member, never an edit to the console script.

    Nothing enforces that a subclass remembered. A subclass that forgets raises ``AttributeError``
    from ``problem()`` rather than reporting some default code, which is the better of the two
    failure modes: a missing code is loud, and a wrong code is a report that lies.

    No subclass ships in this file. Each one arrives with the module that raises it —
    ``SettingsUnreadable`` with ``settings.py``. A subclass
    with no raiser and no test exercising it is work pulled forward, and shipping them here would
    let the claim above be asserted once instead of exercised five times. The test for
    ``problem()`` defines its own subclass, which tests the mechanism rather than one instance of
    it.

    ``packs.py`` ships no subclass at all. It returns ``Problem`` records directly, because one
    call has to report every unmatched pin and an exception carries one.
    """

    code: ClassVar[ExitCode]

    def __init__(self, message: str, detail: Mapping[str, str] | None = None) -> None:
        """Take the one-line message and the named facts that go with it.

        ``detail`` is accepted here, rather than left for a subclass to add later, because without
        it ``problem()`` could only ever return an empty mapping and ``Problem.detail`` would be a
        dead field until some component reopened this file to fix that. Reopening this file is the
        thing the class is arranged to avoid.

        The mapping is copied and wrapped, so the record ``problem()`` returns cannot be edited
        through the exception that produced it. A frozen dataclass stops the field being rebound;
        it does not stop the mapping inside it being mutated, and this is where that is closed.
        ``types`` is already resident before user code runs, so the wrap costs nothing measurable.
        """
        super().__init__(message)
        self.detail: Mapping[str, str] = MappingProxyType(dict(detail or {}))

    def problem(self) -> Problem:
        """This failure as a ``Problem``, carrying the raising subclass's own code.

        ``type(self).code`` rather than a literal, which is the whole arrangement: the code
        travels with the class, so this method never learns about a new failure class.
        """
        return Problem(code=type(self).code, message=str(self), detail=self.detail)
