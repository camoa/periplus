# Known limitations

The README's Known limitations section lists the limits a new user meets first. This page lists
the rest. `php_basic@0.2.0/pack.yaml`, `drupal_basic@0.2.0/pack.yaml`, `go_basic@0.0.3/pack.yaml`
and `laravel_basic@0.0.5/pack.yaml` each open with a list of their known gaps.

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
- **Drupal:** template `embed` and `include` give no edge. Plugin types that contributed modules
  define need their own rutter. Things generated at run time, such as a route from a view, appear
  as `referenced`. A service or entity type that no mapped file declares, such as `config.factory`
  or `node`, appears as `referenced`, and so does a misspelled name. A service that `get('x')`
  names on an object written `$container`, `$this->container` or `\Drupal::getContainer()` gives
  an edge with confidence `inferred`, so a `$container` or `$this->container` that is not Drupal's
  service container gives a false service.
- **Drupal, hooks:** a function in a module, install, include, theme or profile file is a hook
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
  `.php` file gives no hook, so a post-update function in `mymod.post_update.php` gives no hook. It
  leaves two skipped rows in the report.
- **Drupal, missing results:** a class that extends `ContentEntityBase` with no entity type
  attribute or annotation, such as an abstract base or a bundle class, is not marked as an entity
  class. A service or entity type named by a variable gives no edge and goes under skipped.
  `getStorage('x')` on an object not named `entityTypeManager`, `get('x')` on a container with
  another name, other entity type manager methods such as `getViewBuilder('x')`, and static
  shortcuts such as `\Drupal::config('x')` give no edge. `$etm->getStorage('x')`,
  `\Drupal::service('entity_type.manager')->getStorage('x')` and
  `$container->get('entity_type.manager')->getStorage('x')` give no entity type edge. The last two
  give a service edge to `entity_type.manager`. The container rule reads only `$container`,
  `$this->container` and `\Drupal::getContainer()` as written: `$this->getContainer()->get('x')`,
  `static::getContainer()->get('x')`, a receiver split over lines, `$container?->get('x')` and
  another letter case, such as `->GET('x')`, give no edge and no skipped row.
- **Drupal, settings to know:** only the custom modules and themes are read as PHP. A folder
  setting may not leave the project root, so a site is mapped from inside its own tree.
  `drupal_basic` repeats `php_basic`'s grammar pin, so a grammar update must change both.
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

## Not yet verified

The independent checkers and hand audits named below were runs on private code. They are not part
of this repository.

- The Laravel map, against an independent checker or a hand audit. Only its configuration keys
  were compared with PHP's own reading.
- Go declarations and same-package calls, against an independent checker. Only the pack's
  author's script has checked them, on 0.0.1, and it treats each function as one scope. Go calls
  into imported packages are checked by an independent checker on two projects only. No hand
  audit has read a Go map.
- Drupal call edges, beyond the 43-edge hand audit. The Drupal checker does not read calls yet.
- Whether an AI that reads a map explains the code better than one that searches the files.
- The audits are samples, read by models, not a running Drupal site.

## Not yet built

- Go method calls on a value. A call written `v.M()` is not mapped, because the rutter cannot know the
  type of `v`. Calls of an imported package's function, `pkg.F()`, are mapped.
- Boundaries declared by a rutter. The `boundary` key is accepted and not executed.
- An order among rutters that state the same thing.
- A choice between one map file and a map split by pack or by folder. This is an open design
  question.
- Descriptions written by an AI reader. That is a later stage, and the map holds none.
