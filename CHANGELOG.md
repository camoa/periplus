# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `js_basic` maps a call written `f(x)` as a `js_calls` edge, from the function that holds it, or from the script at its top level, to the function it names; a name the script does not declare is an unresolved end.
- A node type marked `internal: true` serves the map rules and stays out of the written map, with every edge that has an end on one; the map report counts what it left out.
- `periplus show` prints the entry `.periplus/descriptions.yaml` holds for the node and for each edge, in text and JSON, and `description: none` for a node without one.
- `periplus slice --path` may repeat, and a prefix that matches no node is refused.
- The `periplus-map` skill answers a question about a feature in steps: find the candidates, show each, and cut one slice from every confirmed start. It writes a missing description entry for a node or edge whose code it read.
- A span's `balance` entry longer than one character is a pattern, so a span can balance tags such as `<fn ...>` and `</fn>`; an entry of one character still matches that character.

### Changed

- `periplus validate` runs the checks `periplus map` runs on the rutter and its dependencies once its files pass the schemas, so a rule the engine cannot execute is reported before a map. It also gives map's folder refusals; inside a project that pins the rutter, or a rutter that depends on it, and whose pinned rutters' dependencies all resolve, it resolves folders against every pinned rutter, as map does, and otherwise against the rutter and its dependencies. A rutter declares the settings values its rules read in its manifest's `values`; a rule may rely only on a value the settings give, the user settings in `<config dir>/settings.yml` among them, or one its rutter or a rutter it depends on declares. `periplus map`, and `periplus validate` in a project that pins the rutter or a rutter that depends on it, refuse a project whose settings do not give a declared value.
- A `{name}` in a normalize step's `replace` pattern is a path value or a settings value, filled in as literal text, escaped, as an id pattern's is; it was matched as the literal text `{name}`. A `{name}` in the step's `with` text is filled in too. A name that is neither is refused when the pack loads; in an import's `bind.normalize`, only the tree rules that resolve a name with `bound_first_segment` are refused, and the message names the imports file. A quantifier such as `{2}` stays a quantifier, and a brace after an odd number of backslashes, as `\{node}`, stays literal, in an id pattern too. A pattern that does not compile once its values are filled in, as an empty value inside `[...]`, does not run on that file and lists a skipped row. A path value's template and normalize may rely only on a settings value the settings give, or one its rutter or a rutter it depends on declares.

## [0.5.2] - 2026-11-09

### Changed

- The Go and JavaScript grammars, `tree-sitter-go` and `tree-sitter-javascript`, are dependencies of the package. One `pip install periplus-map` serves every bundled rutter, so `go_basic`, `js_basic` and `drupal_js_basic` map without a second install. The `go` and `js` extras are gone: `periplus-map[go,js]` still installs, and pip warns that the extras do not exist.

## [0.5.1] - 2026-11-07

### Added

- A TypeScript const whose value is a `useCallback` or `useMemo` call is a function: it gets a `typescript.function` node, a `declares_callable` edge and a binding, and the calls inside it start at it.
- The Drupal rutter gives a component's path attribute its own edge kind, `component_links_path`, from the component node, so the rule fires once per component file; `links_to_path` keeps classes, functions and templates.
- The Drupal entity handler rule reads every handler key: storage, storage schema, access, list builder, view builder, views data, translation, the four form operations and the route provider's html handler.

### Changed

- A function, component or hook declared inside another function takes the enclosing names in its id, `module:Outer:name`, so two nested declarations with one name in one file stay apart and a call inside one starts at the right node. The TypeScript, React, Next.js and Drupal-next rules that name the enclosing function join the whole path with `:`.
- A value read from the enclosing spans takes `excluding_own: true` to leave out the span that opens where the match starts, the one the match itself opens: a declaration that opens a `function_body` span then reads only the functions around it, and the key word that opens an OAuth scope string is no longer read as a scope.
- The loader checks the names a `try` block's steps use the same way as the steps outside it, and refuses a rule whose step names a capture nothing before it made.
- The Drupal rutter's `psr4_class` reads `<module>/tests/src/A.php` as `Drupal\Tests\<module>\A`, so the second path value that worked around it goes, and the permission-check edge no longer starts at interfaces, which have no body.
- Twin rules that share one match live in one file with a YAML anchor: the TypeScript function rules, the React component and hook rules and the Drupal-next endpoint method rules.

## [0.5.0] - 2026-11-07

### Added

- Three bundled rutters read TypeScript as text: `typescript@0.1.0` maps modules, imports, packages, functions and their calls; `react@0.1.0` maps components, hooks, renders and hook uses; `nextjs@0.2.0` maps App Router pages, layouts, route handlers, middleware, fetches of a route and links to a page. Two bundled Drupal rutters join them: `drupal_more@0.1.0` maps base fields, field use by name, entity handlers, job creation and permission checks; `drupal_next@0.1.0` maps the next module's sites and settings, Drupal endpoints and the TypeScript calls to them, JSON:API resources and OAuth scopes. A function, component or hook declared inside another function gets its own node, and a call or render inside it starts there.
- A describe skill, `periplus-describe`, takes a slice file as its working set and writes one entry per located item to the descriptions file: text, file and line, read from the code. It keeps every existing entry and reports a stale one, and it reports an item with no location instead of writing an entry for it.
- Two keys for a rutter's map rules. An edge end takes `fallback: [<resolve steps>]`, a second name tried under each candidate type after the first, resolved from the name as written. A follow takes `try: [<steps>]`, a sub-walk that may reach nothing, after which the walk goes on from the current node with the captures it had, so an end with `on_miss` still marks the call. A bad value of either key is refused at load with a message naming the rule.
- A declaration rule may set a constant attribute on the node it emits, and a match may name the grammar node type its nearest holder must be, with `holder`. A call whose method name, callee or literal argument is built at run time is kept at its line as a call-site node marked `resolution: runtime`, with no invented target; the PHP and Drupal rutters place that mark, and the gaps skill reports those sites under an Unknown boundaries heading.
- `periplus slice --format json` prints its report as one JSON document, and `periplus export` streams a JSON report, with the same exit codes as the text forms.
- A single-directory component's own template, `<name>.twig` beside `<name>.component.yml`, gives the edges an `.html.twig` template gives, from the component node.

### Changed

- The PHP rutter resolves a call through a typed property to the nearest class that declares the method, through `try`, and keeps its unresolved mark when the class or the method is outside the map. An unqualified function call inside a namespace resolves to the namespaced function first and the global one second; a qualified call never falls back. A `@var` doc-comment of a scalar word or a two-class union makes no type node and no method node on a fake class.
- The Drupal JavaScript rutter declares its own text spans, with a class-body span and a class guard, so an attachment or settings array returned by a class method is read where it sits. The Drupal rutter marks a route, service or entity-type argument built at run time in plain functions and hooks as it does in class methods.
- The rutter skill and the rutter author guides carry the lessons of five rutters written outside the project: how a type is named, when a whole-file rule needs `\A` and which sections it reads, the shapes of twin rules, declared versus inferred marks, and where a second path value belongs. The gaps skill ships its read program as a script, and each skill says when to load it and why each standing rule stands.
- `periplus validate` in CI runs over every bundled rutter, the five new ones included.

### Fixed

- A rule pattern's named groups are rewritten by a scanner that copies escaped pairs and character classes as they are, so `[(?<]` stays a class of three characters.
- Seven navigation commands share one JSON writer; the loader names the follow steps once and builds the `fallback` paths from its resolve lists; the map report demo honours a guide line of `...`.

## [0.4.2] - 2026-11-05

### Changed

- The gaps skill reports in two halves. Resolution gaps: referenced and unresolved items, the skipped rows of the map report, and inferred edges. Detail gaps: items a catch-all rule made, grouped by what would tell them apart, groups under a generic parent type that has children for other groups and none for this one, and referenced classes and modules ranked by how much first-party code leans on each. Each half says which rows are first-party, and a thing the map is right about but the site has wrong, such as a method called that no class defines, is listed under its own heading, never as a missing rule.
- The rutter skill measures what a rule added by mapping before and after, offers the next gap its rule uncovered until the person stops or records an accepted unknown in the settings file, and drafts an upstream issue, with a minimal example and the engine's message, when a gap is a bundled rule's defect or a shape the engine refuses.
- Every step of the three skills works from the installed tool: a step that reads a bundled rule or the rule format names `periplus status` or `periplus spec`, never a repository path.

### Fixed

- A rule pattern may hold an escaped backslash right before a named group, such as `Drupal\\(?<ns>\w+)`. The named-group rewrite counts the backslashes before the group: an even run keeps the group under its name, an odd run keeps the paren literal, and lookbehinds are left as they were. Such a pattern was refused before.

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
