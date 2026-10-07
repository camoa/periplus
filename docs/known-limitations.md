# Known limitations

The README's Known limitations section lists the limits a new user meets first. This page lists
the rest. The `pack.yaml` of every bundled rutter except `yaml_basic` and `twig_basic` opens with
a list of its known gaps.

## The engine

- **The `out_of_reach` state** is in the map schema. The engine does not write it yet.

## The rutters

- **PHP:** a method call on an object, `$x->m()`, is not stated. `use function` aliases do not
  bind. A call to a PHP built-in function makes nothing, but the names are compared as written:
  `\strlen()` and `StrLen()` still give an unresolved function. A built-in of an extension that
  was not loaded when the list was taken is not listed. A project's own function named like a
  built-in, `function strlen()` in its namespace, gets no edge from an unqualified call. Drupal's
  global functions, such as `t()`, are not built-ins and give an unresolved function.
  `skip_names` matches the exact case, so `ISSET(` still gives an unresolved function.
- **Drupal:** template `embed` and `include` give no edge. A contributed module's plugins and
  bundle config files are mapped only by that module's rutter, listed below. Without one, its
  bundle config file stays a plain config object and its bundle is `referenced`, with no label.
  Things generated at run time, such as a route from a view, appear as `referenced`. A service or entity type that no mapped file declares, such as `config.factory`
  or `node`, appears as `referenced`, and so does a misspelled name. A service that `get('x')`
  names on an object written `$container`, `$this->container` or `\Drupal::getContainer()` gives
  an edge with confidence `inferred`, so a `$container` or `$this->container` that is not Drupal's
  service container gives a false service.
- **Drupal, hooks:** a function in a module, install, include, theme, profile, `post_update.php` or
  `deploy.php` file is a hook
  when its name starts with the first part of the file name and an underscore. So any function
  that starts with the first part of the file name reads as a hook, such as the form callback
  `mymod_settings_submit`, the helper `mymod_build_list` or `mymod_update_NEXT`. The prefix is
  the file name, not an installed module, so Drupal core inside the mapped folders would give false
  hooks from files such as `form.inc`. A procedural shim kept beside a `Hook` attribute method for
  the same hook, a `LegacyHook` shim, reads as a second implementation. A function below one that
  carries `ProceduralHookScanStop`, and every function of a module that sets
  `skip_procedural_hook_scan`, still reads as a hook, though Drupal does not scan them. A file
  named other than its module or theme gives no hook. Nor does a function named with another module's name, such
  as `othermod_cron` in `mymod.module`. A hook with a variable part keeps it:
  `mymod_form_user_login_form_alter` implements `form_user_login_form_alter`. A function in a plain
  `.php` file other than `post_update.php` or `deploy.php` gives no hook. Each such file leaves two
  skipped rows in the report. A theme's include file gives hooks only
  when the theme's folder sits directly below `custom_theme` and is named by its machine name.
- **Drupal, missing results:** a class that extends `ContentEntityBase` with no entity type
  attribute or annotation, such as an abstract base or a bundle class, is not marked as an entity
  class. A service or entity type named by a variable or a concatenation gives no edge and goes
  under skipped, and so does a class constant that no mapped file declares as text. So does
  `parent::X`, even when a mapped file declares it: Drupal reads only `self` and `static` as the
  enclosing class.
  `getStorage('x')` on an object not named `entityTypeManager` or `$entity_type_manager`,
  `get('x')` on a container with another name, and other entity type manager methods such as
  `getHandler('x')` give no edge. `$etm->getStorage('x')` gives no entity type edge. An entity
  class is known by its short name, so `User::load(1)` on a module's own `User` class gives a false
  entity type. The container rule reads
  only `$container`, `$this->container` and `\Drupal::getContainer()` as written:
  `$this->getContainer()->get('x')`, `static::getContainer()->get('x')`, a receiver split over
  lines, `$container?->get('x')` and another letter case, such as `->GET('x')`, give no edge and no
  skipped row. Core plugins whose folders the rutter does not name give nothing, such as a views
  argument, sort or display plugin, and so do a views field, filter or style plugin and a mail
  plugin declared by an annotation. A plugin type, its attribute class and its plugin manager get
  no node. A display in the mode `default` has no `in_mode` edge, and an entity reference field's
  target bundles give no edge.
- **Drupal, routes and roles:** route requirements and options other than those the manifest
  lists give nothing, such as `_entity_create_access` or `_auth`. A `_custom_access` written
  `service:method` gives an edge to the service only. A parameter converted to an entity by its
  name alone, or typed other than `entity:<type>`, gives no `loads_entity_type` edge. An attribute
  keeps its value as written, so `no_cache: 'TRUE'` and `no_cache: true` differ. The `applies_to`
  key of an `access_check` tag is kept on the service, not on its `tagged_as` edge, because the
  engine accepts an attribute on an edge and does not execute it; a custom requirement that such a
  tag binds gives no edge.
- **Drupal, settings to know:** only the custom modules and themes are read as PHP. A folder
  setting may not leave the project root, so a site is mapped from inside its own tree.
  `drupal_basic` repeats `php_basic`'s grammar pin, so a grammar update must change both.
- **Drupal contributed modules, bundles:** `config_pages_basic`, `crop_basic`, `eck_basic`,
  `paragraphs_basic`, `profile_basic` and `webform_basic` map each type's label and nothing else of
  its settings, such as a paragraph type's behaviors, a crop type's aspect ratio, a profile type's
  roles or a webform's elements and handlers. Their entity types, other than an ECK one, are
  declared by the module's PHP, which is not mapped, so they stay `referenced`. An image style's
  crop effect and a field's allowed paragraph types give no edge. An ECK bundle's entity type is
  read from its file name, so a file renamed by hand gives a wrong edge. `eck_basic` declares its
  path value on `yaml_basic`'s type `yml`, so a type of another name that claims the ending `yml`
  is refused beside it.
- **Drupal contributed modules, plugins:** in `ai_basic`, `advancedqueue_basic`,
  `salesforce_basic` and `webform_basic`, a plugin id that is not a text literal, or in an
  annotation not text in double quotes, makes no plugin and is listed under skipped. `webform_basic` reads handlers declared by annotation only, and no other
  Webform plugin type. `salesforce_basic` reads any class with a generic `Plugin` annotation in the
  mapping field folder as a mapping field. It does not read a mapping's `field_mappings`, so a field
  mapped by a property path, a Salesforce field and a direction give no edge. Sync triggers, pull
  settings and other Salesforce plugin types give nothing. An event used through an alias, or
  written as its own text, makes no event, and no edge joins a subscriber to its event.
- **Drush:** the `@command` tag is read as text, because the engine reads a docblock annotation
  only in the form `@Name(...)` and allows one text file type per ending. Its class is named from
  the file's path, so its edges are inferred, and a class named otherwise gives unresolved ends.
  An attribute without the named argument `name:`, aliases, options, arguments, hooks and
  validators give nothing. Nothing joins a command class's service to its command.
- **Twig Tweak:** only `drupal_block`, `drupal_menu`, `drupal_entity`, `drupal_entity_form` and
  `drupal_field` give edges, each from a quoted first argument; a name in a variable gives no edge
  and no skipped row. `drupal_entity` ends at the entity type, not the entity, and `drupal_field`
  at the field storage. A Twig file not named `.html.twig` gives no edge. A call inside a quoted
  text or a verbatim block still gives one. Two templates of one name in two modules are one node.
- **JavaScript:** `js_basic` maps named functions only. A call, an import, an export, a
  generator, a class, a class method and a function that is an object member or an argument give
  nothing. Two functions of one name in one script are one node. A `.mjs`, `.cjs`, `.jsx` or `.ts`
  file is not read. A script's id is its path from the project folder.
- **Drupal JavaScript:** `drupal_js_basic` reads a behavior only as `Drupal.behaviors.name = {...}`,
  and any object so assigned is one, with or without `attach`. A behavior call or a settings read
  outside a behavior object makes no edge and goes under skipped. `detach`, `once()`, `Drupal.t()`,
  `drupalSettings['key']` and a read through `attach`'s settings parameter give no edge. Only the
  first key after `drupalSettings` is read. The array form of a PHP library attachment is read as
  text and named by PSR-4 path, so it is inferred and a file outside a `src` folder gives no edge.
  A library named by a constant or a variable, and the scripts a `.libraries.yml` file lists, give
  no edge.
- **Python:** text rules see no scopes. Every call starts at the module, and a local name that
  shadows an import gives a false edge. Method calls on objects and imports re-exported through
  another file are not followed. More forms are listed in the author guide.
- **Go:** a method call on a value, `s.Serve()`, makes no edge, and neither does the outer call of
  a chained call; its inner call is mapped on its own. An import binds its alias, else its path's
  last segment less a `/vN` suffix with N 2 or more, or a `.vN` suffix, so a
  package whose name differs from that needs an alias, or its calls make no edge. A dot import's
  names land in the caller's package. A local variable named like an imported package gives a
  false edge to that package. A method call on a package variable, `os.Stdout.Write()`, gives a
  false edge to an unresolved function named `os.Stdout.Write`. A generic call, `pkg.F[T](x)`,
  makes no edge and is not listed as skipped. A local function variable called as `fn()` shows as an
  unresolved package function, or as a false edge when the package declares `fn`. A project
  function named like a builtin, such as `min`, gets no edge. A type declared inside a function gets
  a package-level id. Build constraints are not read, so every platform file is mapped. Test files
  and folders named `testdata` or `vendor` are not read. A nested module is mapped under the outer
  module's path. A folder whose name starts with `_` or a dot is not read, though Go builds such a
  package when another package imports it by path. A call into it through an alias ends at an
  unresolved function.
- **Laravel, false results:** a route inside the array form `Route::group(['prefix' => ...])`,
  or a group chained with a call other than `prefix`, `name` and `middleware`, gets an id and a
  name without that group's prefix, and two such routes with one verb and URI merge into one
  node. Inside a prefix group, a URI keeps a final slash that Laravel drops. Below a
  routes folder not named `routes`, a subfolder's `web.php` shares the `web:` names of the top
  `web.php`. A grouped `use` binds nothing, so a route's edge ends at an unresolved method that
  exists. Controllers and models are typed by folder, not by base class. A component tag ends at
  `components.<name>`, so these tags end at a view that does not exist: `<x-dynamic-component>`,
  an anonymous component in `card/index.blade.php` or `card/card.blade.php`, a class component
  whose `render()` returns another view, an inline class component, a class registered under an
  alias, and a component under `Blade::anonymousComponentPath()`. A tag or a directive inside an
  HTML comment still gives an edge. `view()` and `config()` are matched by their written name, so a
  project's own function named `view` or `config` gives an edge as if it were Laravel's helper.
  `view('books/show')` ends at an unresolved view, not at the existing `books.show`.
- **Laravel, configuration keys:** each configuration file also gets a key named by the file
  alone, `app` for `config/app.php`. It stands for the whole array and is not a key the file
  declares. A key gets no node, nor does any key below it, in an array outside the returned one,
  in a call's argument, a closure, an arrow function, a `match`, a list entry, old `array( )`
  syntax, the second array of a `+`, or an array indexed at once. Nor does it when it or a key
  above it holds a dot, is not a text literal, or starts a line after a line that ends in a
  comment. An array indexed at once that holds arrays three deep or a `]` in a string, and an array
  returned on one branch, `if ($x) return [...];`, still give false key nodes.
- **Laravel, configuration reads:** a read of a key that no configuration file declares, such as a
  key set at run time, ends at an `unresolved` key when a PHP function or method reads it. Read
  only from a template, it ends at a `referenced` key. A missing configuration file is marked
  `unresolved` only from a template. Two identical calls on one line count once.
- **Laravel, missing results:** an invokable controller, `'Controller@method'` and
  `Route::controller` give no edge to a method. A route chained after another method, such as
  `Route::middleware('auth')->get(...)`, gives no node, and neither does `Route::match`.
  `Route::resource` is one node, not seven. A model outside `app/Models` is not typed as a model.
  A quote that PHP rejects as unpaired hides every later route in its file.
  `view('mail::html.button')` ends at an unresolved view, not at the package's view.
  `view(view: 'a.b')`, `view()->make('x')`, `response()->view('x')` and `Route::view('/', 'x')`
  in a method give no edge.
- **Laravel, routes read as text:** a `view('x')` or `config('x.y')` call in a PHP function or
  method is read from the parse tree. The routes are still read as text. Reading them from the
  tree needs three things the engine lacks: an id that joins the URI argument with a path value,
  the upper-cased verb and each enclosing group's prefix; a route name read from a chained
  `->name()` call on a parent node; and an edge end from an array argument such as
  `[BookController::class, 'index']` whose class the imports resolve.
- **Laravel, settings to know:** route and config files in a subfolder get no node; with the
  routes folder set to `./routes/**`, `routes/admin/web.php` routes are named `admin/web:`.
  Templates outside `views_root` are read and get no node and no `reads_config` edge, and the
  report lists them nowhere. A `config('x.y')` call in one still gives the key `x`, named by the
  file, a `key_of` edge to its file, and counts a fire of `config_read_in_view` and
  `config_key_in_file`. A views folder set
  without a final `/**` reads only the files directly in it.

## Not yet built

- Go method calls on a value. A call written `v.M()` is not mapped, because the rutter cannot know the
  type of `v`. Calls of an imported package's function, `pkg.F()`, are mapped.
- Boundaries declared by a rutter. The `boundary` key is accepted and not executed.
- An order among rutters that state the same thing.
- A choice between one map file and a map split by pack or by folder. This is an open design
  question.
- Descriptions written by an AI reader. That is a later stage, and the map holds none.
