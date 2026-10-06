"""Framework detection: which packs a repository looks like it needs, read off the packs themselves.

The signatures and the records here were written before the bodies were, as the specification the
tests in ``tests/test_detect.py`` were written against. Eleven of those tests expect ``()`` and so
passed against the skeleton's unconditional empty answer; their sensitivity is not something being
green demonstrates, and it was checked by planting a spurious detection and watching each one fire.

The one rule this module exists to keep, and the reason it is not a table of frameworks:

    A detector is declared in a pack manifest, never in engine code. Recognising a new stack is a
    ``detect:`` block in somebody's ``pack.yaml`` and no edit here. A third-party pack is detected
    exactly as a bundled one is, because this module cannot tell them apart — it reads manifests
    off the pack search path and evaluates what they declare.

That property fails silently, so ``tests/test_detect.py`` asserts it
with a fixture pack this package has never heard of rather than with a bundled one.

**Where it sits.** It reads ``pack.yaml``, so it is on ``manifest.py``'s side of the line
``packs.py`` draws: ``packs.py`` opens no file inside a pack directory and this module opens one per
candidate. It is a peer of ``manifest.py`` rather than part of it because it also probes the
*repository* being initialised, which is a second tree and a second question, and ``manifest.py``
is about pack files only.

**It never raises for anything a person's input can cause, and it returns no ``Problem``.** A pack
whose manifest cannot be read contributes no detection and no report — the same posture
``manifest.py`` takes towards a mistyped ``depends``, and for the same reason: the validator
reports what a pack file gets wrong, and ``periplus status`` reports what the pack search path gets
wrong. A detector is a suggestion written into a file a person then edits, so the cost of a missed
detection is a line they type and the cost of a spurious one is a wrong pin in a committed
artifact. Every ambiguity therefore resolves towards detecting nothing.

**Determinism**, which is a stated property of this tool and not a nicety. Detections come back
sorted by pin, never in the order the filesystem listed the pack directories, and a signal is
evaluated against a path joined under the repository root rather than against whatever the pack
asked for.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from periplus.manifest import ManifestUnreadable, load_manifest
from periplus.packs import PackCandidate
from periplus.preflight import DependencyStatus
from periplus.resolution import resolve

__all__ = ["DETECT_KEY", "Detection", "detect", "detect_packs"]

#: The manifest key a pack declares its detector under. Named here rather than spelled at each use,
#: and read out of ``PackManifest.document`` rather than off a field: ``manifest.py`` carries the
#: whole parsed mapping precisely so a consumer like this one can read a block it does not model,
#: and its docstring names framework detection as one of the two consumers that exist for.
DETECT_KEY = "detect"

#: The key a detector names its alternatives under, and the two a single alternative may carry.
#: They are the same names ``pack-manifest.schema.json`` declares, and the sets exist so that this
#: evaluator closes both levels the way the schema closes them: a block or a signal carrying a key
#: neither set holds is read as no detector at all. The schema is what tells an author they wrote
#: ``contain:``; this is what stops that manifest detecting on existence alone in the meantime,
#: because the validator that enforces the schema is a later task and ``init`` does not run it.
ANY_OF_KEY = "any_of"
PATH_KEY = "path"
CONTAINS_KEY = "contains"
_DETECT_KEYS = frozenset({ANY_OF_KEY})
_SIGNAL_KEYS = frozenset({PATH_KEY, CONTAINS_KEY})


@dataclass(frozen=True, slots=True)
class Detection:
    """One pack whose detector fired, and the evidence that fired it.

    ``pack`` is the pack half of the directory name and ``pin`` is the whole ``<pack>@<version>``,
    which is what a ``packs:`` list holds. Both, because they answer two questions: which pack this
    is, and what to write into a settings file. Deriving one from the other at a call site is how
    two callers come to disagree about where the version came from.

    ``path`` is the repository-relative path of the signal that matched, carried so a person can be
    told *why* a pack was suggested. A detection with no evidence behind it is a guess presented as
    a finding.
    """

    pack: str
    pin: str
    path: str


def detect_packs(root: Path, candidates: Sequence[PackCandidate]) -> tuple[Detection, ...]:
    """Every pack on the search path whose declared detector matches the repository at ``root``.

    ``root`` is the repository being examined and ``candidates`` are the pack directories to read,
    both arguments rather than discovered here, for the reason ``describe_contract`` takes its
    candidates: a test drives this against a temporary tree with nothing monkeypatched, and the
    question of where packs live stays in ``packs.py``.

    Only ``named`` candidates are considered — an entry that is not a ``<pack>@<version>``
    directory is not a pack, whatever is inside it.

    Sorted by pin. Never raises.

    One detection per pin, and the first candidate carrying that pin is the one that answers. Two
    roots holding the same ``<pack>@<version>`` directory are the state ``match_pins`` reports as
    ``PIN_DUPLICATED``, and this is not the place it is reported: what a settings file needs is the
    pin written once, and writing it twice would hand a person a duplicate to delete on top of the
    problem the resolver will name for them anyway.
    """
    found: dict[str, Detection] = {}
    for candidate in candidates:
        if candidate.status != "named" or candidate.name is None or candidate.entry in found:
            continue
        try:
            manifest = load_manifest(candidate.root.traversable / candidate.entry)
        except ManifestUnreadable:
            # One unreadable `pack.yaml` on the search path contributes nothing and stops nothing.
            # See the module docstring: reporting on the search path is `periplus status`'s, and a
            # third-party pack with a truncated manifest must not turn creating a project into a
            # traceback.
            continue
        evidence = _first_match(root, manifest.document.get(DETECT_KEY))
        if evidence is not None:
            found[candidate.entry] = Detection(
                pack=candidate.name.pack, pin=candidate.entry, path=evidence
            )
    return tuple(found[pin] for pin in sorted(found))


def _first_match(root: Path, block: object) -> str | None:
    """The path of the first signal in ``block`` that matches ``root``, or nothing.

    ``block`` is whatever the manifest had under ``detect:`` — a mapping if the author wrote one,
    and any YAML value at all otherwise. Every shape that is not a detector answers ``None``, which
    is the same answer a pack with no ``detect:`` key gives: an unreadable detector recognises
    nothing, never everything.

    The alternatives are tried in the order they were written, so the evidence a person is shown is
    the first thing the author said would count rather than whichever probe happened to run first.
    """
    if not isinstance(block, Mapping) or not set(block) <= _DETECT_KEYS:
        return None
    alternatives = block.get(ANY_OF_KEY)
    if not isinstance(alternatives, list | tuple) or not alternatives:
        return None
    for signal in alternatives:
        matched = _match(root, signal)
        if matched is not None:
            return matched
    return None


def _match(root: Path, signal: object) -> str | None:
    """One alternative against the repository: its declared path if it matches, else nothing.

    A signal with no ``path`` matches nothing. That is the case the direction of every decision
    here exists for: read as "no constraint", a pathless signal fires on every repository there is,
    and the pin it writes lands in a committed file with nothing in the tree to explain it.

    ``contains`` is a **literal substring** of the file's text, never a pattern. A pack is
    third-party data read with no time limit around it, and a backtracking regular expression over
    an attacker-chosen subject is a cost this has no way to bound. A file that will not decode as
    UTF-8 or will not open matches nothing, rather than matching on its bytes.

    What comes back is the path **as the pack declared it**, not the absolute path that was
    probed: it is evidence a person reads beside a repository-relative settings file, and the
    machine's own directory layout is not part of why a pack was suggested.
    """
    if not isinstance(signal, Mapping) or not set(signal) <= _SIGNAL_KEYS:
        return None
    declared = signal.get(PATH_KEY)
    if not isinstance(declared, str):
        return None
    target = _under(root, declared)
    if target is None or not target.is_file():
        return None
    if CONTAINS_KEY not in signal:
        return declared
    wanted = signal[CONTAINS_KEY]
    if not isinstance(wanted, str):
        return None
    try:
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    return declared if wanted in text else None


def _under(root: Path, declared: str) -> Path | None:
    """``declared`` joined under ``root``, or ``None`` if it does not stay there.

    A signal path is third-party data and ``pathlib`` obliges whatever it is handed: ``root /
    "../outside.txt"`` reaches upwards and joining an absolute path discards the root entirely. So
    the join is checked rather than trusted, and both sides are resolved before the check, which is
    also what stops a symlink inside the repository from pointing the probe out of it.

    What that closes is a probe. A detector alternative per candidate path turns a committed
    settings file into a readout of which files exist on the machine that ran ``init``, and the
    person reviewing that diff has no way to see where the answer came from.

    The root itself is not a match. A path that resolves to the repository is not a file inside it,
    and an empty ``path:`` is the way to write one by accident.
    """
    try:
        base = root.resolve()
        full = (base / declared).resolve()
    except (OSError, ValueError):
        return None
    if full == base or not full.is_relative_to(base):
        return None
    return full


def detect(
    start: Path,
    env: Mapping[str, str],
    dependencies: tuple[DependencyStatus, ...],
) -> tuple[Detection, ...]:
    """The command's entry point: resolve the pack search path, then detect against ``start``.

    The search path is resolved **exactly as ``status`` resolves it**, by calling ``resolve()`` —
    the same choice ``spec()`` makes and for the same reason. A second definition of where packs
    live would drift, and would miss a ``pack_paths`` root a user-level settings file added.

    Problems ``resolve()` found are deliberately dropped rather than returned. This runs as part of
    ``periplus init``, where a directory matching no pack still exits 0, and a
    settings fault surfacing through the create-a-project command would report on a state that
    command is not about. ``periplus status`` is where the search path is reported on.
    """
    return detect_packs(start, resolve(start=start, env=env, dependencies=dependencies).candidates)
