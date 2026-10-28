# Bundled rutters

A rutter is a folder of YAML files that tells Periplus how to find one stack's things in real files. To pin one, name it as `<name>@<version>` under `packs:` in `.periplus/settings.yml`; the README's [Pin a rutter](../README.md#2-pin-a-rutter) section shows how.

Each entry below gives the rutter, its version, what it maps and the rutters it depends on. A pinned rutter loads its dependencies too, so you pin only the one you want.

## Base languages and file types

| Rutter | What it maps | Depends on |
|---|---|---|
| `php_basic@0.2.0` | PHP classes, interfaces, traits, enums, functions and methods. Inheritance, interface use, trait use, containment, properties and parameters with their types, and call sites. Plain and static calls, and method calls through a typed or assigned property. A call to a PHP builtin makes nothing. | none |
| `js_basic@0.0.1` | JavaScript scripts, and the functions that have a name of their own, each under its script's path. It reads `.js` files only and maps no calls. Needs the `js` extra. | none |
| `go_basic@0.0.3` | Go functions, methods, structs and interfaces, each under its package's import path. Calls inside one package, and calls through an import. It skips test files and `vendor`, and needs the module path in the settings as `values.module`. Needs the `go` extra. | none |
| `yaml_basic@0.1.0` | Claims `.yml` and `.yaml` files for the rutters that depend on it. It has no rules of its own. | none |
| `twig_basic@0.1.0` | Claims `.twig` files for the rutters that depend on it. It has no rules of its own. | none |

## Drupal core

| Rutter | What it maps | Depends on |
|---|---|---|
| `drupal_basic@0.3.0` | Configuration, modules, themes, services, routes, permissions, libraries, templates, hooks, entity types, fields, displays, forms, roles, block placements and plugins such as blocks, actions, field widgets and formatters, queue workers and REST resources. The services and entity types that PHP code names in calls such as `\Drupal::service('x')`. | `php_basic`, `yaml_basic`, `twig_basic` |
| `drupal_js_basic@0.0.1` | Drupal JavaScript behaviors and the behaviors they attach, the `drupalSettings` keys that PHP attaches and behaviors read, the libraries that PHP, templates and components attach, the library scripts and stylesheets, and the paths that script strings write. Needs the `js` extra. | `js_basic`, `drupal_basic` |

## Drupal contributed modules

Pin one of these beside `drupal_basic` when the site uses the module.

| Rutter | What it maps | Depends on |
|---|---|---|
| `ai_basic@0.0.1` | The AI module's agent plugins and function call plugins, declared by attribute, each joined to its class. | `drupal_basic`, `php_basic` |
| `advancedqueue_basic@0.0.1` | The Advanced Queue module's job type plugins, each joined to its class. | `drupal_basic`, `php_basic` |
| `config_pages_basic@0.0.1` | Each Config Pages type, as a bundle of the entity type `config_pages`. | `drupal_basic` |
| `crop_basic@0.0.1` | Each Crop API crop type, as a bundle of the entity type `crop`. | `drupal_basic` |
| `drush_basic@0.0.1` | Drush commands in the custom modules, from the `Command` attribute or the `@command` tag, each joined to its method and class. | `drupal_basic`, `php_basic` |
| `eck_basic@0.0.1` | Each Entity Construction Kit entity type and each of its bundles. | `drupal_basic` |
| `paragraphs_basic@0.0.1` | Each paragraph type, as a bundle of the entity type `paragraph`. | `drupal_basic` |
| `profile_basic@0.0.1` | Each Profile type, as a bundle of the entity type `profile`. | `drupal_basic` |
| `salesforce_basic@0.0.1` | Salesforce mapping field plugins, each mapping with its Salesforce object and the bundle, entity type and fields it maps, and the Salesforce events that subscribers name. | `drupal_basic`, `php_basic` |
| `twig_tweak_basic@0.0.1` | The block plugins, menus, entity types, entity forms and field storages that Twig Tweak functions such as `drupal_block('x')` name in templates. | `drupal_basic` |
| `webform_basic@0.0.1` | Webform handler plugins declared by annotation, each joined to its class, and each webform as a bundle of `webform_submission`. | `drupal_basic`, `php_basic` |

## Laravel

| Rutter | What it maps | Depends on |
|---|---|---|
| `laravel_basic@0.0.5` | Routes with their prefixes and names, each joined to its controller method, its resource controller or the view it renders. Controllers, models, migrations, Blade views with their includes, extends and component tags, and configuration files with their keys. The views and configuration keys that PHP code names in `view()` and `config()` calls, and that views name in `config()`. It reads the standard Laravel folders. | `php_basic` |

## Reference rutters

These older rutters pass `periplus validate`. They hold vocabulary only and cannot make a map. Use the `_basic` rutters above instead.

| Rutter | For | Depends on |
|---|---|---|
| `php@0.1.0` | PHP | none |
| `yaml@0.0.1` | YAML | none |
| `twig@0.0.1` | Twig | none |
| `drupal@0.1.0` | Drupal | `php`, `yaml` |
| `go@0.0.2` | Go | none |

## Write a new rutter

[Writing a rutter](rutter-author-guide.md) explains the files of a rutter and how to check one.
