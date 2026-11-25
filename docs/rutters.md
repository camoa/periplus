# Bundled rutters

A rutter is a folder of YAML files that tells Periplus how to find one stack's things in real files. To pin one, name it as `<name>@<version>` under `packs:` in `.periplus/settings.yml`; the README's [Pin a rutter](../README.md#2-pin-a-rutter) section shows how.

Each entry below gives the rutter, its version, what it maps and the rutters it depends on. A pinned rutter loads its dependencies too, so you pin only the one you want.

The bundled rutters are in `src/periplus/packs`. The manifest of each, except `yaml_basic`,
`twig_basic`, `typescript`, `react`, `nextjs`, `drupal_more` and `drupal_next`, opens with a list of
what it does not map yet.

## Base languages and file types

| Rutter | What it maps | Depends on |
|---|---|---|
| `php_basic@0.2.0` | PHP classes, interfaces, traits, enums, functions and methods. Inheritance, interface use, trait use, containment, properties and parameters with their types, and call sites. Plain and static calls, calls on `self`, `static`, `parent` and `$this`, and method calls through a typed or assigned property. Method calls on a variable, in a method or a function, joined through a typed parameter, a local assigned `new Foo()` or `$this->m()`, or a property assigned `new Foo()`, and calls on what `$this->m()` returns. A trait's `$this->m()` joined in each class that uses it, and `overrides` from a method to the inherited one it replaces. The classes a `new` creates, as `instantiates`, and a `Foo::class` or `\A\B\Foo::class`, as `references_class`. A call to a PHP builtin makes nothing. Reads a parse tree. | none |
| `js_basic@0.0.1` | JavaScript scripts, and the functions that have a name of their own, each under its script's path. Functions assigned to a dotted name, `A.b.c = function () {}`, under the dotted name when `A` is a global object such as `window`, else under its script's path, and functions written in an object literal assigned to one, the same way. Calls written `f(x)`, and member calls such as `A.b.c()` to a mapped member function, from the function or the script that holds them, as `js_calls`; a member call on a shared object that is not a browser one, which no script assigns, ends at one unresolved member function. A call to a JavaScript or browser global, such as `parseInt` or `fetch`, makes nothing. It reads `.js` files only. Reads a parse tree. | none |
| `go_basic@0.0.3` | Go functions, methods, structs and interfaces, each under its package's import path. Calls written `f(x)` inside one package, and `pkg.F(x)` through an import, to another package of the module or to an unresolved function outside it. It skips test files and `vendor`, and needs the module path in the settings as `values.module`. Reads a parse tree. | none |
| `yaml_basic@0.1.0` | Claims `.yml` and `.yaml` files for the rutters that depend on it. It has no rules of its own. | none |
| `twig_basic@0.1.0` | Claims `.twig` files for the rutters that depend on it. It has no rules of its own. | none |
| `typescript@0.1.0` | TypeScript modules, imports, packages and functions in `.ts` and `.tsx` files, and calls from one function to a function the file binds by name. It reads the files as text; the project sets the folder the `@/` alias points at as `typescript_alias_root`. | none |
| `react@0.1.0` | React components and hooks, named by convention, the components a function renders, the hooks it uses, and the `use client` or `use server` directive. It reads the files as text. | `typescript` |
| `nextjs@0.2.0` | Next.js App Router pages, layouts, route handlers with their HTTP methods, middleware and special files under `app`. A `fetch` of a route, a link to a page, and a name or prop that holds a route URL. It reads the files as text. | `react` |

To map a Go module, run Periplus at the module's root. Give the module path in the settings,
because Periplus does not read `go.mod`:

```yaml
periplus_version: 0
packs:
  - go_basic@0.0.3
values:
  module: example.com/app
```

## Drupal core

| Rutter | What it maps | Depends on |
|---|---|---|
| `drupal_basic@0.3.0` | Configuration, modules, themes, services, routes, permissions, libraries, templates, hooks, entity types, fields, displays, forms, roles, block placements and plugins such as blocks, actions, field widgets and formatters, queue workers and REST resources. The services and entity types that PHP code names in calls such as `\Drupal::service('x')`, `$container->get('x')`, `\Drupal::entityQuery('x')`, an entity type manager's `getStorage('x')` or a static `load()` on a module's own entity class, the routes and paths a method or function links to, the method a call on a service reaches, the route each page display of a view serves, as `route_from_view`, and the views plugins a view uses. Plugin types with their plugins and managers, an entity type's handler classes, a constraint's validator, and the service that answers a custom route requirement. Events with their subscribers and dispatchers, the Twig filters and functions a module's extension provides and the templates that call them, the field storages that code and templates name, and the block, theme hook or field a suggestion template's name points to. Hooks from `Hook` attribute methods, and from procedural functions named by their file's name, such as `mymod_cron` in `mymod.module`. The roles that code checks, changes or names as text, through `hasRole`, `addRole`, `removeRole` or `in_array` on `getRoles()`, with the role as text or a class constant, the configuration objects that `\Drupal::config('x')` and a config factory name, the queue workers whose queues it gets, and the forms a `form_<id>_alter` hook alters. The factory that builds a service, local tasks, local actions and contextual links with their routes and classes, entity and confirm forms as forms, and the macro files templates import. The variables a theme hook declares, also in a loop over a constant list of names, the templates that read them and the code that passes them, also through a method that takes the hook as a parameter, the variables an include hands a template with its hash, a template's `{% set %}` names, the names a template reads from one that includes it with no hash, and the theme template that overrides a module's template of the same name. Each PHP attribute with the class, method, function, property or parameter it sits on, each route subscriber as a route alter marked `resolution: runtime`, and the themes `core.extension` installs. The module or theme that holds each route, service, library, class and template, the form class a `getForm(X::class)` builds, and the route a template's path reaches by its shape. | `php_basic`, `yaml_basic`, `twig_basic` |
| `drupal_js_basic@0.0.1` | Drupal JavaScript behaviors, the behaviors they attach and the calls written in them, the `drupalSettings` keys that PHP attaches and behaviors read, the libraries that PHP, templates and components attach, the library scripts and stylesheets, and the paths that script strings, template literals and `Drupal.url()` write, with the route a template literal's path reaches by its shape. A request whose URL is built at run time is a node marked `resolution: runtime`. | `js_basic`, `drupal_basic` |
| `drupal_more@0.1.0` | Base fields an entity class defines and the entity type a reference field targets, the PHP class or trait that reads or writes a field by name, a `has_handler` edge from an entity class to each handler class its annotation names, the storage schema, views data and translation handlers among them, which `drupal_basic` does not read, `Job::create('type')` calls, and `->hasPermission('literal')` checks. | `drupal_basic`, `advancedqueue_basic` |

## Drupal contributed modules

Pin one of these beside `drupal_basic` when the site uses the module.

| Rutter | What it maps | Depends on |
|---|---|---|
| `ai_basic@0.0.1` | The AI module's agent plugins and function call plugins, declared by attribute, each joined to its class. | `drupal_basic`, `php_basic` |
| `advancedqueue_basic@0.0.1` | The Advanced Queue module's job type plugins, by attribute or annotation, each joined to its class. | `drupal_basic`, `php_basic` |
| `config_pages_basic@0.0.1` | Each Config Pages type, from its config file, as a bundle of the entity type `config_pages`. | `drupal_basic` |
| `crop_basic@0.0.1` | Each Crop API crop type, from its config file, as a bundle of the entity type `crop`. | `drupal_basic` |
| `drupal_next@0.1.0` | The next module's sites, per-bundle settings and four plugin kinds, the site's preview and revalidate handlers in the Next.js app, Drupal endpoints with their HTTP methods from routing files and REST resources, the TypeScript calls to an endpoint, JSON:API resources and OAuth scopes. | `drupal_basic`, `php_basic`, `typescript`, `react`, `nextjs` |
| `drush_basic@0.0.1` | Drush commands in the custom modules, from the `Command` attribute or the `@command` tag, each joined to its method, its class and the service that registers that class, and each alias in the `@aliases` tag joined to its command. | `drupal_basic`, `php_basic` |
| `eca_basic@0.0.1` | Each ECA model, from its config file, with the event, condition and action plugins it names, a custom module's ECA event and condition plugins joined to their classes, the events its event plugins react to, its entries and their successors, and the field storages, roles, bundles and entity types its configuration names. | `drupal_basic`, `php_basic` |
| `eck_basic@0.0.1` | Each Entity Construction Kit entity type and each of its bundles, from their config files, and the entity type a static `EckEntityType::load()` names. | `drupal_basic` |
| `paragraphs_basic@0.0.1` | Each paragraph type, as a bundle of the entity type `paragraph`, the entity type a static `load()` on `Paragraph` or `ParagraphsType` names, and the paragraph field storage a template reads as `paragraph.field_x`, or as `content.field_x` in a `paragraph--` template. | `drupal_basic` |
| `profile_basic@0.0.1` | Each Profile type, as a bundle of the entity type `profile`, and the entity type a static `load()` on `Profile` or `ProfileType` names. | `drupal_basic` |
| `salesforce_basic@0.0.1` | Salesforce mapping field plugins, each mapping with its Salesforce object and the bundle, entity type and fields it maps, the field storages its tokens name and the webform elements its webform submission tokens and `WebformElements` rows name, the Salesforce events that subscribers name, and the entity type a static `load()` on `MappedObject` or `SalesforceMapping` names. | `drupal_basic`, `php_basic`, `webform_basic` |
| `salesforce_eca_basic@0.0.1` | The ECA event plugins of the Salesforce ECA module, added to `eca_basic`'s table of event plugins, so a model that reacts to one links to the Salesforce event a subscriber subscribes to. No rules of its own. | `eca_basic`, `salesforce_basic` |
| `twig_tweak_basic@0.0.1` | The block plugins, menus, entity types, entity forms and field storages that Twig Tweak functions such as `drupal_block('x')` name in templates. | `drupal_basic` |
| `webform_basic@0.0.1` | Webform handler plugins declared by annotation, each joined to its class, each webform, from its config file, as a bundle of `webform_submission` with the handlers it runs and its elements, and the entity type a static `load()` on `Webform` or `WebformSubmission` names. | `drupal_basic`, `php_basic` |

## Laravel

| Rutter | What it maps | Depends on |
|---|---|---|
| `laravel_basic@0.0.5` | Routes with the prefixes and names of `Route::prefix()->name()->group()` groups, each joined to its controller method, its resource controller or the view it renders. Controllers, models, migrations, Blade views with their includes, extends and component tags, and configuration files with the text keys of the array each returns. The views and configuration keys that PHP code names in `view()` and `config()` calls, and that views name in `config()`. It reads the standard Laravel folders. Reads text, and a parse tree for the calls. | `php_basic` |

To map a Laravel application, pin `php_basic@0.2.0` and `laravel_basic@0.0.5` and run Periplus
at the application's root. The default Laravel folders need no settings. To move the templates,
set `views_root` under `folders`; a template is named by its path below `views_root`.

## Example rutters

These rutters are in `examples/second-stack/packs`, not in the package. Copy them into a
project's `.periplus/packs` to use them; [Writing a rutter](rutter-author-guide.md) shows how.

| Rutter | What it maps | Depends on |
|---|---|---|
| `python_text@0.1.0` | Python modules, top-level classes and functions, imports and calls. Reads text. | none |
| `typer_text@0.1.0` | Typer apps, commands and mounts. | `python_text` |
| `speckitty@0.1.0` | spec-kitty missions and their templates. | none |

## Write a new rutter

[Writing a rutter](rutter-author-guide.md) explains the files of a rutter and how to check one.
