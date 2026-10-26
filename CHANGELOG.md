# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
