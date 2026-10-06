# Contributing to Periplus

Periplus maps a code base with rutters, which are folders of YAML files. Most contributions are a
new rutter, a change to a rutter, or a report of a wrong map. This page says how to make each one
and how to run the tests and the checks.

## Propose a rutter

A bundled rutter lives in `src/periplus/packs/<pack>@<version>/`. The folder name gives the
rutter's name and its exact version. The `pack` and `version` keys in its `pack.yaml` give the
same two values. The bundled rutters that make a map are named `<stack>_basic`, as `php_basic`,
`go_basic` and `laravel_basic`.

To learn how to write a rutter, read [`docs/rutter-author-guide.md`](docs/rutter-author-guide.md)
and the pages it links. Write the rutter in your own project first, in `.periplus/packs/`, and map
that project until the map holds what the code holds.

A pull request for a rutter contains:

- The rutter folder, with `pack.yaml` and its pack files.
- A list of known gaps at the top of `pack.yaml`, as comments. `laravel_basic@0.0.5/pack.yaml`
  and `go_basic@0.0.3/pack.yaml` show the form.
- An end-to-end check in `scripts/demo.d` that maps a small project and compares the result with
  what it expects. `98c-go-pack.sh` and `98d-laravel-pack.sh` are examples.
- A row in the README table of rutters, with what the rutter finds and how it was checked.

Run `periplus validate <pack>` before you open the pull request. A rutter that does not validate
stops the map.

## Run the tests and the checks

Install `uv`. Then, in the repository:

```
uv sync --frozen --all-extras
```

This installs Periplus, the development tools and the Go grammar into `.venv`, at the versions
in `uv.lock`.

Run the pytest suite:

```
.venv/bin/python -m pytest -o addopts="" -q
```

Some tests build a virtual environment or a wheel with `uv`. They fail when `uv` is not on the
path. To run the suite as the CI workflow runs it, omit `-o addopts=""`. The options in
`pyproject.toml` then add `--strict-markers --strict-config`.

Run the static checks that the CI workflow runs:

```
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy
```

Run the end-to-end checks:

```
ROOT=$PWD PERIPLUS=$PWD/.venv/bin/periplus bash scripts/demo.sh
```

`scripts/demo.sh` runs each executable file in `scripts/demo.d` in name order. It stops at the
first check that fails. `PERIPLUS` names the command the checks run. A new check must be
executable, or `demo.sh` does not run it. The checks need `python3` on the path.

Several checks find Python by reading the first line of the `PERIPLUS` script. When the path to
`.venv` is longer than 127 bytes, uv writes a `/bin/sh` launcher there, and those checks fail.
Clone the repository into a short path.

The CI workflow, `.github/workflows/checks.yml`, does not run the end-to-end checks. Run them
yourself before you open a pull request.

## The rules a rutter holds

**No false node.** A false node or edge is a defect. A node or edge that the rutter does not make
is a limit, and the rutter states it. Until a known false result is fixed, the gap list names it
under its own heading, as `laravel_basic` does under "False results".

**A stated confidence.** Each rule declares `confidence`, as `declared` or `inferred`. Use
`declared` when the file states the thing, such as a class declaration. Use `inferred` when the
rule depends on a convention, such as a folder name or a naming pattern. A rule on an explicit
declaration and a rule on a naming convention never state the same confidence.

**State every limit as observed.** A shape that the rutter does not map goes in the gap list at
the top of `pack.yaml`. Write what you saw on real code: the input, and what the map holds for
it. Do not write a guess about code you did not run.

**A gap is a rutter issue first.** Fix a gap in the rutter. Change the engine only when a rutter
cannot say what the code holds. In that case, say in the pull request what the rutter format
cannot say.

**A new version replaces the old one.** A bundled rutter at a new version replaces the folder of
the old version. Maps made with the old version must be made again.

**A check or a test makes its own input.** Each test and each check writes the small project it
maps, in a temporary folder. The repository holds no site to map. Map your own projects to find
gaps, then write each gap as a small input that a check can hold.

## Report a wrong map

Open an issue at <https://github.com/camoa/periplus/issues>. The maintainers cannot see your code,
so give a case that anybody can run:

1. The output of `periplus --version`.
2. Your `.periplus/settings.yml`, and each rutter it pins, with its version.
3. The smallest set of files that shows the problem. Write new files that have the same shape as
   your code. Do not attach private code.
4. The command you ran, such as `periplus map --output map.json --format json`.
5. The wrong node or edge, from the map: its `id` or its ends, its `locations` and its
   `provenance`, which names the rutter and the rule.
6. What the code holds, and whether the map holds a false result or misses a result.

If the rutter's gap list already states the case, say so. The issue then asks for the gap to be
closed, and it is not a new defect.

## License

Periplus is licensed under the Apache License 2.0. See `LICENSE` and `NOTICE`. A contribution
that you submit to this repository is licensed under the same terms, as section 5 of `LICENSE`
states.
