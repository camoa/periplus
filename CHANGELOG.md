# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.1] - 2026-11-04

### Changed

- In the GraphML export each node's `label` is now the short form of its map id, the id without its type prefix and without namespaces, and the full map id is in the node's `id` data; each edge carries a `label` equal to its kind, beside `kind`. A reader that took the map id from `label` reads `id` instead.
- The navigation guide's slice section says what an edge kind is, that an either-way slice widens through a hub such as a shared service or permission, and that `--kind` keeps a feature slice to the feature.

## [0.4.0] - 2026-11-04

### Added

- `periplus slice` writes the items around some ids, or under a path prefix, and what they reach along edges to a depth, into a map file of their own. `--direction out` and `in` follow edges one way; `both` follows an edge either way at every hop. It refuses a slice over `--limit` and an `--out` that is the map it reads, writing nothing.
- `periplus export --format graphml|dot|mermaid` prints a map or a slice for Gephi, yEd, Graphviz or Mermaid. GraphML names each node by a generated token and carries the map id as the node's `label`; DOT quotes every id; Mermaid uses generated node tokens and escapes angle brackets in labels.
- The Drupal rutter maps a route name written in a PHP call, `Url::fromRoute`, `Link::createFromRoute` or `$this->redirect`, to the route it names, with a `links_to_route` edge from the class or function around the call.
- A README section on upgrading an install from PyPI.

### Changed

- Every damaged-map error names `periplus check-map`, exit 29 names a map that cannot be read and exit 30 a damaged one, and `periplus affected` reads "via <kind> to <item>".
- `periplus show` formats an edge's locations as it formats a node's.
- `periplus update` refuses one rutter pinned at one version in two roots, and prints each root whole.
- Contributors: the bundled rutters write a repeated rule pattern once, with a YAML anchor, and rule files reuse it. The map output does not change.

## [0.3.0] - 2026-10-28

### Added

- Three Claude skills ship with the package: `periplus-rutter` for writing a rutter, `periplus-map` for reading a map, and `periplus-gaps` for working through the gaps in a map report.
- `periplus skills install` copies the skills into `~/.claude/skills`, and replaces older copies when you run it again after an update.
- A README section on using the skills with Codex CLI, Gemini CLI, GitHub Copilot in VS Code and Cursor.
- A page, `docs/rutters.md`, that lists every bundled rutter with its version, what it maps and the rutters it depends on. The README and the rutter author guide link to it.
- A reviewer checklist in `CONTRIBUTING.md` for the items that no test covers.

### Changed

- Contributors: the test suite runs in parallel and in the test process, the end-to-end checks in `scripts/demo.d` are a short set of acceptance scripts, and `CONTRIBUTING.md` describes the new layout and release steps.

## [0.2.1] - 2026-10-26

### Added

- A workflow that publishes `periplus-map` to PyPI when a version tag is pushed.
- The README's install step installs from PyPI by name first, then from the repository at a tag, then from a local checkout.
- The package page on PyPI links to the repository, the changelog and the issue tracker.

## [0.2.0] - 2026-10-23

The first tagged release.

### Added

- The mapper engine and the command line tool, with `periplus init`, `periplus status`, `periplus spec`, `periplus validate` and `periplus map`.
- Twenty-four bundled rutters: five reference packs (php, drupal, twig, yaml, go), the language and framework rutters (php_basic, drupal_basic, drupal_js_basic, js_basic, twig_basic, yaml_basic, go_basic, laravel_basic), and eleven rutters for contributed Drupal modules (advancedqueue, ai, config_pages, crop, drush, eck, paragraphs, profile, salesforce, twig_tweak, webform). The Drupal, PHP, Twig, YAML and Drupal JS rutters were rebuilt on a large Drupal site.
- `periplus update`, which moves a project's pins to the installed rutters.
- Install carries the tree's rutters and prints their digest.
- Engine rule abilities: pack tables as a rule step, class constants as call arguments, `match.ending` and boundary lists.
- File-level node links for scripts, styles, templates, config, hooks, forms, service calls and URLs.
- Map navigation commands: `periplus types`, `periplus find`, `periplus show`, `periplus neighbors`, `periplus affected` and `periplus path`, with text or JSON output.
- `periplus check-map`, which runs the full schema check on a written map.
- Map rules that run in passes, so rutter rules join property calls on their own.
- Drupal, PHP and Drupal JS rutter rules for attachments, settings, behaviors, paths and libraries.
- Documentation: the rutter author guide, the navigation guide, the map report guide, the known limitations page and the contributor page.
- `periplus validate` takes `name@version` and says which copy of the rutter it checks.
- The licence is Apache 2.0.
