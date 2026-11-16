# Changelog

All notable changes to this project are documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- A pack file may declare node attributes under `attributes`: the types a rule may write each on (`on`), whether a container's value reaches its members (`spreads`), and a short `mark` a reader shows. A map rule may now write a declared attribute, beside its edges, on the node it matched or, with `target: matched_node`, on the node its follow steps reached; a write changes no type or location, and a target no rule found or of a type `on` does not reach is listed under Matches skipped. A spreading attribute is written on each member of a container through the grouping kinds, and through the further kinds its `spreads_along` lists, each toward the end it names, the nearest container winning, with a provenance row `spread.<name>`. The map header `marks` names the mark of each declared attribute a node holds; maps without one are unchanged. The check refuses, with exit 19, an undeclared attribute a map rule writes, a write on a type `on` does not reach, one name declared two ways, a `spreads_along` without `spreads: true` or naming a kind neither the pack nor one it depends on declares, and a declaration of `type_conflict` or `resolution`; a mark that is empty, longer than 40 characters, or holds a bracket or a line break is a schema error. Two rules that give one node's attribute different values at the same file and line now both show under `differs`; before, one value was dropped without a word.
- Every navigation command prints a node's marks in brackets, such as `[not installed]`, on each row that names the node: `find`, `show` (the node's first line and the other end of each edge row), `neighbors`, `affected`, `path` (both ends of a step) and `slice` (the start line and the node's line under its file). The JSON adds `marks` to find, walk and slice rows and to the show report, `other_marks` to show's edge rows, and `from_marks` and `to_marks` to path steps, each a list that is empty when the node has none. `find --mark TEXT`, repeatable, keeps the nodes that carry that mark, and `TEXT` may then be left out; a mark no node carries prints a warning that names the marks the map holds.
- `drupal_basic` declares `installed` on modules and themes, with `spreads: true` and `mark: not installed`. The rules that draw `not_installed_by` also write `installed: no`, so a function, class, route or template of a module `core.extension` does not list prints `[not installed]`. It also spreads along `contains` and `declares_property`, so the methods and properties of such a class print it too. The `not_installed_by` edge stays.
- An edge kind may declare `cause: from | to | none | touch`: which end sets off the other. `from` says the from end sets off or uses the to end, `to` says the to end sets off the from end, `none` says neither, as membership or typing, and `touch` says the from end only points at the to end without running it, as a link to a page. Left out, `groups: true` means `none`, `realizes: true` means `to`, `realizes: to` means `from`, and any other kind is undeclared; nothing implies `touch`. The map header lists each kind it holds edges of under `cause_from_kinds`, `cause_to_kinds`, `cause_none_kinds` or `cause_touch_kinds`, sorted; an undeclared kind is in none of them. Maps of packs with grouping or realizing kinds therefore gain these lists; maps written before still load and match the map schema. `periplus legend` ends a declared kind's line with `cause: <value>`, and its JSON adds `cause` to each kind, null when undeclared. The check refuses, with exit 19, a grouping kind that declares a cause other than `none`, and two declarations of one kind with different causes.
- `periplus depth ID...` says how far the walk by cause goes from some ids, in a line per direction: what they set off and what sets them off, each with the hops to the end, the things reached, the share within 2, 3 and 5 hops, and the hubs it stopped at. A `touching:` line counts what points at the ids or what they point at by `touch` kinds, and a last line names the kinds walked undeclared, or says the map declares no cause directions. It takes `--hub N`, `--through ID` and `--format json`.
- The example rutters `python_text` and `typer_text` declare the cause of their edge kinds.
- Five commands work on a set of ids. `periplus only ID...` lists what the ids set off, by the walk by cause, that nothing else sets off: every chain that sets such a thing off passes through an id. `periplus hubs ID...` lists the hubs that walk stops at, with `--direction off|by`, `--depth N|all` and `--hub N`. `periplus members ID...` counts and lists what each container holds by the map's grouping kinds, with `--type T`. `periplus pieces ID...` splits the ids into the groups that edges among them join. `periplus count ID...` counts the things the ids name by type and by state, and the edges among them by kind, and lists the ids that name no node. Their rows print short names, marks and `[supporting code]`, and each takes `--format json`, described in `navigation.schema.json`.
- `--ids` on `find`, `show`, `neighbors`, `affected`, `only`, `hubs`, `members` and `pieces` prints only the full ids a command lists, one a line, never cut; the count, warnings and problems go to standard error. An id holding a control character prints escaped, and standard error says how many did.
- `-` in place of the ids reads them from standard input, one a line, for `show`, `depth`, `neighbors`, `affected` and the five new commands, so `periplus neighbors ID --depth all --ids | periplus count -` joins two commands.
- `periplus show` takes several ids: one report each, a `---` line between two, and in JSON `{"shown": [...]}`.
- `neighbors` and `affected` take `--full`.
- The first line of `neighbors`, `affected`, `depth`, `only` and `hubs` names at most three starts and counts the rest, `+N more`, so ids read from standard input do not fill it.

### Changed

- The rows of `neighbors` and `affected` print the short name of each thing where one names it alone, and the full id otherwise, and `:line` alone when the row just above is in the same file. `--full` prints full ids and paths as before; the JSON is unchanged. On a real walk of 81 things the text went from 15,839 to 9,951 characters.
- The `periplus-map` skill now says to pipe a periplus command only into another periplus command, instead of never piping.
- `periplus neighbors` lists what the ids set off and `periplus affected` what sets them off, by each kind's cause: a `from` kind is followed forward (`affected`: backward), a `to` kind backward (`affected`: forward), a `none` or `touch` kind never, and an undeclared kind by its raw direction, named on a last line. Both take several ids, `--depth all`, `--hub N` (default 40; a thing with more edges to follow is listed and not walked from, `0` for no limit), `--through ID` to walk one hub, and `--touch` to add what each thing shown points at, one hop out, marked `[touch]`. The text is a tree, each thing under the thing it was reached from, with its kind, `(rev)` when followed backward, `file:line` and marks; source lines and descriptions are left to `show`. Hops not shown print a count line by type, the farthest hops become count lines past a budget of about 20,000 characters (`--limit N` sets it, `0` lifts it), and the first line then gives the command that shows all. The 50-row cut is gone from these walks. The JSON has new rows (`hop`, `id`, `type`, `state`, `via_kind`, `via_direction`, `from`, `file`, `line`, `marks`, `supporting`, `hub`, `touch`), counts per hop and `hubs`. `--raw` keeps the walk as it was, from one id; a map with no cause list gets that walk without `--raw`, with a warning that says so.

### Fixed

- A map rule may write attributes beside its edges, as the rutter guide says; the pack-file schema refused it before.
- The check refuses, with exit 19, a type in an attribute's `on` that neither the pack nor one it depends on declares; before, a misspelt type was never refused.

## [0.8.0] - 2026-11-16

### Added

- A rule may declare the confidence `mentioned`, weaker than `inferred`, for a link drawn only because a name is written as text: a string equal to a known id, a name compared in a condition, a selector in a script, or a name inside another name. The pack, map and navigation schemas accept it, and maps written before still match the map schema. Rules that draw one edge at different confidences each keep their provenance row, in any rule or file order. `show` prints it, and the gaps skill counts `mentioned` edges on their own line.
- The map report lists a map rule under Matches skipped when it would start from, or follow a `node` step to, a node another map rule made with an id no file rule found. The row names the file, the rule, the node and the map rule that made it. Before, such a rule only showed as firing zero times.
- A `name_matches` condition with `child` may take `nth`, a number from 1, and then tests that child among the children of the node type, where a condition without it reads the first. A rule can so tell apart two children that share a type and have no field name.
- `php_basic` maps three more shapes:
  - a `$this->method()` call is a call site joined to its method, with a `calls` edge to the method found on the class, its parents or its traits. A method no mapped class declares stays unresolved under the calling class;
  - `new Foo()`, `new self()` and `new static()` give an `instantiates` edge from the function or method around them. `new $class()` in a method is a call site marked as runtime;
  - `Foo::class`, plain or qualified, gives a `references_class` edge. A class constant such as `Foo::NAME` gives none.
- `drupal_basic` maps:
  - what a module or theme holds: `route_in_module`, `service_in_module`, `class_in_module`, `library_in_module`, `template_in_module`, `library_in_theme` and `template_in_theme`;
  - the rest of what a module or theme holds, each to the extension of the nearest folder above the file that holds an info file, so a submodule or a test module keeps its own: functions of module, install, inc, theme and plain PHP files (`function_in_module`, `function_in_theme`), theme hooks (`theme_hook_in_module`, `theme_hook_in_theme`), templates that open with a comment and macro files, menu links, local tasks, local actions, contextual links and permissions (`<thing>_in_module`), shipped configuration in `config/install` and `config/optional` (`config_in_module`, `config_in_theme`), and components (`component_in_module`, `component_in_theme`); and through the module of a class, plugins, form ids, entity types, plugin types, route alterations, Twig filters and functions, event constants and events, and entity routes (`plugin_in_module`, `form_id_in_module` and the like). A test class `Drupal\Tests\<module>\...` is the module's class, and a class, trait, interface or enum in a theme's folder has `class_in_theme`. A route name may hold a slash. `drupal_js_basic` adds `script_in_module`, `script_in_theme`, `stylesheet_in_module` and `stylesheet_in_theme`, and `js_function_in_module`, `js_function_in_theme`, `behavior_in_module` and `behavior_in_theme` for a script's top-level functions and its behaviors, and `drush_basic` adds `command_in_module` and `command_alias_in_module`;
  - a template path or script path with placeholders, joined to the route whose path has the same shape, as `template_links_route` and the new `script_links_to_route` in `drupal_js_basic`;
  - `getForm(Foo::class)` as a `builds_form` edge from the method or function around it;
  - a `'#theme'` in a function of a module, theme, install, inc or profile file, and a `hook_theme` `template` value that names a folder;
  - an `on403`-style handler of a class that descends from `HttpExceptionSubscriberBase`, as a subscriber of the kernel exception event;
  - `theme_hook/theme_hook_from_module_template.yaml`: a module template `my-card.html.twig` as the template of the hook `my_card` that a loop in `hook_theme` registers, when a class constant or a `'#theme'` names the hook;
  - `theme_hook/theme_hook_constant.yaml`: a method or function that reads a class constant whose text is a theme hook's name, as a `renders_theme_hook` edge at confidence `mentioned`;
  - `theme_hook/theme_hook_render_assigned.yaml`: `$build['#theme'] = 'my_card';` as a `renders_theme_hook` edge, as the array form gives;
  - `field/module_accesses_field.yaml`: the new edge kind `module_accesses_field`, from a module to each field storage its classes' methods or its functions read or write.
- `php_basic` joins a method call on a variable, `$x->m()` or `$x?->m()`, in a method or a plain function, so the map shows what a method calls through its parameters, locals and return values. Each call keeps a call site; its `calls` edge is inferred:
  - through a parameter typed `Foo $x` or `?Foo $x`, in a method or a function;
  - through a local variable assigned `new Foo()`;
  - through a declared return type, as `$this->m()->n()` or `$x = $this->m(); $x->n()`;
  - through a property assigned `new Foo()`;
  - inside a trait, a `$this->m()` also joins the `m()` of each class that uses the trait;
  - the new edge kind `overrides` runs from a method to the inherited method it replaces, so the map shows which child methods replace a parent's.
- `drupal_basic` maps:
  - a method called on a service, as `\Drupal::service('x')->m()`, `$container->get('x')->m()` or a local variable assigned the service, as a `calls` edge to the method on the service's class;
  - each page display of a view as the route `view.<view>.<display>`, with its path, and the new edge kind `route_from_view` to the view.
  - `theme_hook/core_theme_hook.yaml`: a theme template named exactly for a core theme hook, as `user.html.twig` or `node.html.twig`, or a `--` suggestion of one, gives that theme hook; the exact template is that hook's template, and `theme_hook/suggestion_hook.yaml` joins the suggestion as suggesting it. A module's suggestion template gives no `suggests_theme_hook` edge;
  - `theme_hook/preprocess_theme_hook.yaml`: a `preprocess_<hook>` implementation gives the new edge kind `preprocesses_theme_hook` to the theme hook, when the map holds it;
  - `route/entity_canonical_theme_hook.yaml`: the route `entity.<type>.canonical` gives the new edge kind `route_renders_theme_hook` to the theme hook `<type>` when the map holds both;
  - `template/template_path_string.yaml`: a quoted `'@<namespace>/.../<name>.html.twig'` held as a value in a template gives an inferred `template_includes` edge;
  - `url/template_relative_path.yaml`: a relative path in a template's `data-*` attribute, as `data-endpoint="api/item/{{ id }}"`, gives `template_links_route` to the route whose path has its shape;
  - `theme_hook/suggestion_menu.yaml`: `menu--<name>.html.twig` as `suggests_menu` to the menu's configuration;
  - `menu_link/menu_link_in_menu.yaml`: a menu link's `menu_name` as `link_in_menu`;
  - `menu_link/menu_name_compared.yaml`: a `menu_name` key compared to a text, or a `case` of a switch on it, as `checks_menu`, mentioned;
  - `theme/theme_region.yaml`: a theme's regions as `drupal.theme_region` nodes, with `region_of_theme`, `placed_in_region` from block placements and `suggests_region` from `region--<region>` templates;
  - `module/module_installed.yaml`: `installs_module` from `core.extension`, and `not_installed_by` for a mapped module or theme it does not list.
- Map rules take `unless`, chains that stop a rule for the matched node, and `unless_matched`, chains that block one result. A `follow` step may be `incoming_edge`, which walks an edge backwards, and an `id_matches` in a chain may name an earlier capture as `{name}`. The pack check refuses an undeclared edge kind inside a `try` at any depth.
- The map skill has one recipe per kind of question, and tells the reader to use the map together with code search: search the code first, ask the map what touches each thing found with `show`, then run `periplus slice` with the words learned. It says how to read each part of a printed slice, and that a reply cut to fit is not a complete answer.
- An edge kind may declare `groups: true`: its `from` end belongs to the container at its `to` end. The map lists the grouping kinds it holds edges of under `grouping_kinds`, sorted, and leaves the key out when there are none. `periplus validate` refuses a value other than `true` or `false`.
- A node type and an edge kind may carry a `description`, one line of at most 200 characters; `periplus validate` refuses a longer text or one with a line break. Two rutters that declare one kind with different descriptions refuse the map with exit 19; a declaration without one agrees with one that has it. The map carries the descriptions of the types and kinds it holds under `legend`, as `edge_kinds` and `node_types`, keys sorted, and leaves the key out when there are none. Every node type and edge kind of the bundled rutters has one.
- `periplus legend` lists the edge kinds the map holds, most edges first, each with its count, the types at its ends and its description, then the node types the same way. The text aims at 3 KB and counts what it leaves out; `--all` prints every one, `--kind K` and `--type T` print one in full, and `--format json` prints the rows.
- A printed `periplus slice` ends with a `legend:` block: the description of each edge kind its links show, in up to 640 bytes. Over the piece's byte aim the legend is left out first.
- An edge kind may declare `realizes: true`: its `from` end is a concrete form of its `to` end. The map lists such kinds under `realizing_kinds`, sorted, only when it holds an edge of one. A walk in `slice`, printed or written, and `neighbors` adds the mapped nodes that stand for a reached node, and for the start at depth 0, at the same hop; `affected` adds the declarations a node stands for. A node reached along a realizing edge adds no siblings, a node outside the project adds none, and at most 8 join at one node, with a count line past that. `show` lists them under `Realized by`, and a printed slice prints `realized by (kind) -> ...`. `php_basic` declares `implements_method`, `overrides` and `implements` realizing, and `php` declares `implements`. `realizes: to` says the `to` end is the concrete one; the map lists such kinds under `realizing_to_kinds`. `drupal_basic` declares it on `service_class`, `built_by_service`, `built_by_class`, `built_by_method`, `handled_by`, `uses_form`, `entity_class` and `plugin_class`, `drupal` on `plugin_class` and `entity_class`, `drush_basic` on `command_method`, and `laravel_basic` on `handled_by`.
- A rutter names its stack's supporting code, such as tests, in `files.supporting`; the settings add patterns with `supporting` and drop the rutters' with `supporting_from_packs: false`. The map lists the result under `supporting_paths`, only when there is one. A printed `slice` neither prints nor walks supporting code, ends each piece with one count line, and picks a start there only when named or when every match is there; `--support` prints it. `find` marks such rows `[supporting code]` and lists them last; `show`, `neighbors` and `affected` list them last under `in supporting code:`. `php_basic` and `drupal_basic` name `**/tests/**`, and `js_basic` `**/__tests__/**`, `**/*.test.js` and `**/*.spec.js`.
- A node argument of `show`, `neighbors`, `affected`, `path` and `slice` may be a short name, such as `helper`. One name that fits several nodes exits 31 and lists them as a pick-list; in JSON the problem holds `candidates` (`id`, `type`, `location`) and `total`. A name that fits none adds a hint.
- Rows of `find`, `show`, `neighbors`, `affected` and `path` print `file:line`, the source line under it, and the node's description line when the descriptions file has one. A source line is read only from a regular file inside the project, up to 5 MB.
- `find` matches description text and string attribute values too, and marks those rows `[description]` or `[attribute NAME]`. JSON adds `matched`, `matched_attribute`, `by_type` and `description`.
- A declaration rule's attribute template may name its id's sources, such as a docblock group, cut at 300 characters; `php_basic` sets `summary` on classes, interfaces, traits, enums, functions and methods from the docblock's first line, and `js_basic` on function declarations, so `find` reaches a node by a word of its summary.
- `drush_basic` reads a command from the code structure: the command node links to the method and class that `php_basic` found and to the service that registers the class, and each alias is its own node. The text rules it replaces are removed.
- `find --type` and `--path` may repeat. A wrong type name gets suggestions. A cut list prints counts by type and a line on how to narrow.
- `slice` without `--out` prints the piece of the map around some words or ids, in one call. An argument that names a node starts there; other text is searched as `find` searches, as a whole and word by word, and each word, from the rarest down, first gets its best node as a start; the rest are scored by the rarity of the words they match, so a common word never displaces a rare one; among equal scores rarer node types come first, at most two of a type before the rest, each led by the node more other files depend on. A word that names one node is searched too when other words are given. `--starts`, `--type` and `--path` narrow them. The walk follows edges both ways for 2 hops by default. A node whose edges all join it to the node above is folded into it and counted. The 50-row cap gives each start an even share, keeps first the nodes several starts reach, then those the words match, then rarer types and nodes more files depend on, then near hops, and ends with what it left out and the flags that narrow it. `--format json` prints the same piece. The walk follows a grouping edge only from member to container and stops there; a start that is a container lists its members by type, rarest first, with the command that lists one type in full. `slice --out` works as before.
- `php_basic` joins more method calls, each with an inferred `calls` edge:
  - a call on a `catch` variable, to the method on the caught class or its nearest ancestor;
  - a call on a local variable inside a plain function;
  - a call through a chain of returns, such as `$this->a()->b()->c()`, and through a method that returns `static`, with the new edge kind `returns_static`;
  - a call through the method result of a property, such as `$this->p->m()->n()`;
  - a call on a parameter typed by `@param`, or on a local typed by an inline `@var` comment;
  - a call on a local assigned the result of a typed call or a static call;
  - a call on a variable or property whose class an `instanceof` test settles: inside the block of `if ($x instanceof Foo)`, or after `if (!$x instanceof Foo) { return; }` or `assert($x instanceof Foo)`;
  - a call `$this->p->m()` inside a trait, on the type each class that uses the trait declares for `p`.
- `php_basic` adds the edge kind `implements_method`, from a class method to the interface method it implements.
- `drupal_basic` maps entity type manager, container, config factory and queue factory calls on a parameter or property whose declared type is the core, Symfony or PSR interface.
- `drupal_basic` `route/core_user_routes.yaml`: when `core.extension` lists the user module, the core routes `user.login` and `user.register` serve `/user/login` and `/user/register` and use the form ids `user_login_form` and `user_register_form`, with the new edge kind `route_uses_form_id`.
- `drupal_basic` `theme_hook/suggestion_page_path.yaml`: a template `page--a--b.html.twig` gives a `suggests_path` edge to the path `/a/b` when the map holds that path.
- `drupal_basic` `route/route_name_compared.yaml`: a function or method that compares a variable assigned from `getRouteName()` to a quoted route name with `==` or `===` gives a `checks_route` edge to that route, confidence `mentioned`.
- `drupal_basic` `route/route_name_in_list.yaml`: `in_array()` of such a variable against a literal list, inline or assigned to a variable in the same function, gives a `checks_route` edge to each route listed, confidence `mentioned`.
- `drupal_basic` `route/route_custom_access_method.yaml`: a `_custom_access` written `service:method` gives an `access_checked_by` edge to the method on the service's class or its nearest ancestor.
- A tree declaration rule's `where` list takes `within` and `not_within`, each a list of tree node types between the match and its nearest holder. Two rules can so tell a call in a method's own body from one in a closure inside it.
- The node states `boundary` and `unknown_boundary`. A rule end takes `on_miss: unknown_boundary`, or `boundary: {into: {template, type}, kind}` to name the API node it enters, and a node type takes `boundary: true`. When rules mark one end differently, mapped beats boundary, boundary beats unresolved, and unresolved beats unknown boundary. The map report counts boundaries by node and unknown boundaries by pack and reason.
- Rules that type one node as types on different branches of one ancestor no longer stop the map. The node keeps the nearest type they share, and its `type_conflict` attribute names each candidate as `<type> by <pack>/<rule>`. An edge only a candidate type could carry is not written. A boundary classification adds its type to the list and changes no type, and a rule that writes `type_conflict` refuses the map with exit 19. The map report's Type conflicts section, `type_conflicts` in JSON, lists each node with its candidates and counts those edges. Types that share no ancestor still refuse the map with exit 21.
- `drupal_js_basic` `member/script_member_in_block.yaml`: a function declared inside a block, such as the `(function ($) {...})(jQuery)` wrapper, gets `js_function_in_module` or `js_function_in_theme` as a top-level one does.
- `drupal_js_basic` `behavior/behavior_selector.yaml`: a behavior that binds `[data-x="y"]` through `once()` gets a mentioned `behavior_binds_template` edge to each template that writes `data-x="y"`.
- `drupal_js_basic` `behavior/behavior_form_selector.yaml`: a behavior that binds `form.my-form-id` through `once()` gets a mentioned `behavior_binds_form` edge to the form id `my_form_id`.
- `webform_basic` `webform_element/webform_form_selector.yaml`: each webform's submission form id `webform_submission_<id>_add_form`, with `submission_form_of_webform` to its bundle.
- `webform_basic` `bundle/webform_page_path.yaml`: each webform's page path `/webform/<id>`, with `path_shows_webform` to its config object.
- `webform_basic` `bundle/webform_route_parameter.yaml`: a function or method that reads the route parameter `webform` and tests it against `WebformInterface` gets `reads_route_entity` to the entity type webform, and each webform's config object `instance_of_entity_type` to it.
- `salesforce_basic` `event/mapping_id_compared.yaml`: a method that compares `getMapping()->id()` with a quoted id, `self::X` or `static::X` gets a mentioned `acts_on_salesforce_mapping` edge to that mapping.
- `twig_tweak_basic` `rules/entity_form_mode.yaml`: `drupal_entity_form('type', id, 'mode')` gives `renders_form_mode` to the form mode `core.entity_form_mode.<type>.<mode>`.

- `drupal_basic` maps what acts on a page from outside it:
  - `url/template_path_concat.yaml`: a URL a template builds in a `{% set %}` joined with `~`, as `template_links_route` to the route of the same path shape;
  - `hook/hook_on_form.yaml`: the new edge kind `hook_runs_on_form`, from `hook_user_login` to core's `user_login_form`;
  - `form/login_destination_trigger.yaml`: the new edge kind `redirects_after_form`, from a Login Destination rule to the login or registration form its trigger names;
  - `display/form_display_form.yaml`: the new edge kinds `form_uses_display` and `form_of_entity_type`, from an entity form id to its form display and its entity type;
  - `hook/entity_hook_type_test.yaml`: the new edge kind `acts_on_entity_type`, `mentioned`, from a generic entity hook to the entity type its `if` tests.

- `drupal_basic` `mention/php_literal.yaml`: a PHP string literal shaped like a Drupal id is an internal `drupal.literal` node, linked from the method, function or class around it.
- `drupal_basic` `mention/mention_php.yaml`: a method or function holding a literal equal to a route, service, configuration or queue worker id gets a `mentions_route`, `mentions_service`, `mentions_config` or `mentions_queue` edge, confidence `mentioned`.
- `drupal_basic` `mention/twig_literal.yaml`: a template's quoted text shaped like a Drupal id is the same internal node, by `template_names_literal`.
- `drupal_basic` `mention/mention_twig.yaml`: a template holding a route or configuration id as quoted text gets a `mentions_route` or `mentions_config` edge.
- `drupal_js_basic` `mention/mention_library.yaml`: a literal or quoted text equal to a library id gets a `mentions_library` edge.
- `php_basic` `edges/globals.yaml`: `$GLOBALS['name']` written or read gives a `php.global` node with `writes_global` and `reads_global` edges.

### Changed

- `affected` prints its own header when it stops on a problem.
- A slice piece of one thing says `1 thing`.
- A printed `slice` builds its owner and short-name tables, its searches and its satellite checks once a run; on a 43,787-node map it takes about a third of the CPU time it took, with the same output.
- A row's source line is left out when it holds fewer than two letters, digits or underscores, such as `{#`.
- The printed `slice` groups its nodes by file, each file once with the container it belongs to, and gives each node one line with its line, its shortest pasteable name and its type, one source line, its links in the piece by kind and direction, and the count of its edges the piece leaves out. Far ends not mapped and members of one owner fold to counts. An inventory by type ends the piece. Without `--limit` the piece aims at 8 KB. JSON keeps full ids.
- The printed `slice` shows which of the things the words found are linked and which stand alone. It prints them in pieces, the printed nodes that edges other than grouping edges join, each with a header naming its starts. Pieces go by the summed word score of their starts, then by size. After the last of several, a line says no edge of the map joins them as printed and gives the `periplus path` command that tests two. The words pick up to 12 starts: the first 8 walk 2 hops and the rest 1, unless `--depth` says otherwise. Under the 8 KB aim, first-hop rows go from the largest piece first, and every start keeps its line. Paths print below the folder all printed files share, named once. The inventory gives each name its piece number when there are several, and JSON adds `pieces` and a `piece` number to each start and row.
- `drupal_basic` declares its module and theme membership kinds grouping: `class_in_module`, `route_in_module`, `service_in_module`, `library_in_module`, `template_in_module`, `library_in_theme`, `template_in_theme`, `config_provided_by`, `config_provided_by_theme`, `region_of_theme`, `placed_in_region` and `link_in_menu`, and each new membership kind listed under Added, `class_in_theme` among them. So do `drupal_js_basic`'s `script_*`, `stylesheet_*`, `js_function_*` and `behavior_*` kinds and `drush_basic`'s `command_in_module` and `command_alias_in_module`. A Drupal map now lists them under `grouping_kinds`.
- Every PHP function is now a holder in `php_basic`, as a class is: the enclosing type of a call or a parameter in a function's body is the function.
- A theme hook link (`renders_theme_hook`) and a library attachment in PHP (`attaches_library`) start at the method or function around them, no longer at the class. One written outside any named function, such as a property default, gives no edge and one skipped row.
- A runtime `$this->redirect($route)` call site has an id that ends in `(runtime)`, apart from the plain call site at the same line.
- Node and edge ids move and the map grows, so a committed map differs after the upgrade. Map again and review the difference.
- A name a pack's `boundary` block lists reads `boundary`, not `declared`, and two packs listing one name keep a row each instead of refusing the map. A call site marked `resolution: runtime` reads `unknown_boundary`, not `mapped`. Maps built before still validate.
- The known limitations page is removed. A shape no rule maps is listed as not mapped yet in its rutter's `pack.yaml` header.

### Fixed

- `enclosing_method` stops at the nearest holder, so a function declared inside a method no longer takes the method's name. An `enclosing_method` or `enclosing_class` end takes the first node whose type the edge kind allows there.

## [0.7.0] - 2026-11-11

### Added

- A rutter's manifest may hold `add_table_rows: {<pack>: {<table>: {<key>: <value>}}}`, rows for a table that a rutter it depends on owns. The owner's rules find the rows in any run that loads the adding rutter. A run is refused before any file is read when the rows name a rutter it does not depend on, a table that rutter does not declare, or a key another rutter gives a different value.
- An item of a reference rule's `skip_names` may be `{table: <name>}`, so the rule skips that table's keys, the rows other rutters add included.
- Two `where` conditions, `in_table` and `not_in_table`, pass over a match whose name is not, or is, a key of a table, on tree declaration and reference rules, map rules and file rules. The form `{table, capture}` tests a named capture of the where's pattern instead, and `{table, fill: enclosing_type}` tests the name of the type that holds the match, or with `pattern` and `capture` a capture of a pattern searched in it, so two small rules can split one shape.
- An edge end with `fallback` and `on_miss` may take `on_miss_name: fallback`, which puts the unresolved mark under the fallback name. The order of the names tried does not change.
- A declaration rule's `name_child` is a path of one step or more; `[name]` reaches a name that has no field, and a rule on each element of a statement that declares several names fires once per element.
- A call whose arguments sit in a child with no field name has its arguments read from its first named child of the node type `identity.call_arguments` names.
- A tree declaration rule may name, under `match.encloses_for`, rutters it depends on; their reference rules then start their edges at its node, so a dependent rutter's node can start another rutter's calls without copying its rules.
- `php_basic` maps `self::`, `static::` and `parent::` calls through the class and its ancestors. A function call tries the namespaced name, then the global name, as PHP does, and an unmapped one stays unresolved under its global name. A `@var` class name written `Lib\Mailer` is read as written.
- `drupal_basic` maps much more of a Drupal site:
  - route and path links from the method or function around the call, in classes, traits and enums;
  - static `load`, `loadMultiple` and `create` on an entity class, through a table keyed by the full class name that other rutters extend;
  - the plugins a view uses, `\Drupal::cache()` bins, access checks joined to the services that apply to a route's requirements, and simple configuration owned by a theme;
  - service arguments that list services, service factories, route subscribers and HTTP exception subscribers by their base class, constraint validators, entity handlers, plugin types and their managers;
  - events keyed by the text their constant holds, with subscribers and dispatches; Twig extension filters and functions and the templates that use them;
  - field reads and writes in code and templates, with a field name that storages on several entity types share kept as its own node; template suggestions;
  - role checks and changes, configuration reads and edits, queue use, form alters, local tasks, local actions and contextual links, the entity and confirm form bases, Twig macro imports, and names given by a class constant, for each constant of a statement.
- `js_basic` skips calls to the built-in globals it lists, and keeps one unresolved node per library function or shared-object call. It maps functions assigned to a dotted name or written in an object literal as member functions, and calls to them. Its tables `globals`, `shared_objects`, `library_globals` and `excluded_objects` take rows from other rutters through `add_table_rows`. `drupal_js_basic` maps script URLs, classes inside a behavior, and calls inside a behavior starting at the behavior, `Drupal.behaviors.x.attach()` included.
- `webform_basic` maps the handlers a webform uses and each of its elements. `salesforce_basic` maps the field and webform element a mapping's tokens and WebformElements rows name. `profile_basic`, `eck_basic`, `paragraphs_basic`, `salesforce_basic` and `webform_basic` add their entity classes to `drupal_basic`'s table.
- Two bundled rutters: `eca_basic@0.0.1` maps ECA models, their event, condition and action plugins, their entries and successors, and the fields, roles, bundles and events they name; `salesforce_eca_basic@0.0.1` adds the Salesforce ECA event names to it.
- The gaps skill reads gaps from the map's marks and the code at each mark, groups them by the rule that would close them, and prints a Plain classes section and three more kinds of site fault: an undefined theme library, menu link parent or theme hook. The rutter skill lists the keys added in this release and shows how to close a gap through an internal node and a map rule. The map skill reads `periplus types` before it picks a command.

### Changed

- A reference rule checks `skip_names` before it checks that the name is written as a name, so a listed keyword, such as `self`, leaves no skipped row.
- The contributed Drupal rutters no longer carry a copy of the entity call rule; they add rows to `drupal_basic`'s table. `salesforce_basic` depends on `webform_basic`. `drupal_next`'s YAML text type is now `drupal_basic`'s `drupal_yml_text`, so `drupal_next` and `webform_basic` map in one project.
- Node and edge ids move, so a committed map differs after the upgrade. Entity edges come from one rule at the call's line; events are keyed by their name text; route and path links start at methods; calls in a Drupal behavior start at the behavior; fewer calls leave skipped rows. Map again and review the difference.

### Fixed

- A map, data or text rule's end with one type mints its id in that type's namespace, not the edge kind's.
- An empty `name_child` step is refused; it loaded and fired nothing, or was dropped.
- `periplus validate` inside a project reports rows that two pinned rutters add with different values to one table, with the message and exit code `periplus map` gives.

## [0.6.0] - 2026-11-11

### Added

- `js_basic` maps a call written `f(x)` as a `js_calls` edge, from the function that holds it, or from the script at its top level, to the function it names; a name the script does not declare is an unresolved end.
- A node type marked `internal: true` serves the map rules and stays out of the written map, with every edge that has an end on one; the map report counts what it left out.
- `periplus show` prints the entry `.periplus/descriptions.yaml` holds for the node and for each edge, in text and JSON, and `description: none` for a node without one.
- `periplus slice --path` may repeat, and a prefix that matches no node is refused.
- The `periplus-map` skill answers a question about a feature in steps: find the candidates, show each, and cut one slice from every confirmed start. It writes a missing description entry for a node or edge whose code it read.
- A span's `balance` entry longer than one character is a pattern, so a span can balance tags such as `<fn ...>` and `</fn>`; an entry of one character still matches that character. An entry that matches the empty text on its own, such as `/*`, is refused; one that matches zero characters only in context, such as `(?=a)`, loads and counts where it matches.
- A text rule's templates may name `{file_stem}`, in its id, values, attributes, bindings and edge ends, as other file rules' ids do; it was refused with exit 26. A capture named `file_stem` keeps its own text, and a value named `file_stem` is refused, since the engine gives that name.
- A file rule without `match.text` may hold `values`, each a template over path values, settings values, `file_stem`, the values before it and, under `match.each`, `key`, with `normalize` and `case`; its id may name them. Such a rule with `values` was refused with exit 26. A value from a capture or an enclosing span is refused, since the rule has neither, and so is a value named `file_stem` or `key`, which the engine gives.
- A rutter's manifest declares, under `values`, the settings values its rules read.

### Changed

- A text rule's template fills a capture of an optional group that took no part in the match as empty text, when another capture the template names took part, in an id, a value, an attribute, a binding or an edge end; it made nothing before. One rule with `(?<pkg>\w+)(?:\.(?<sub>\w+))?` and the template `x:{pkg}{sub}` reads both `create("alpha")` and `create("alpha.beta")`. A template where no capture it names took part, as `x:{sub}` or `{dir}.{sub}` over a path value, still makes nothing and leaves no skipped row; a capture that took part and matched empty text still makes nothing in an id, attribute or edge template. Only a capture counts as taking part: `{v}{sub}`, with the value `v` set and `sub` untaken, makes nothing.
- `periplus validate` runs the checks `periplus map` runs on the rutter and its dependencies once its files pass the schemas, so a rule the engine cannot execute is reported before a map. It also gives map's folder refusals; inside a project that pins the rutter, or a rutter that depends on it, and whose pinned rutters' dependencies all resolve, it resolves folders against every pinned rutter, as map does, and otherwise against the rutter and its dependencies.
- A rule, and a path value's template and normalize, may rely only on a settings value the settings give, the user settings in `<config dir>/settings.yml` among them, or one its rutter or a rutter it depends on declares in its manifest's `values`. `periplus map`, and `periplus validate` in a project that pins the rutter or a rutter that depends on it, refuse a project whose settings do not give a declared value.
- A `{name}` in a normalize step's `replace` pattern is a path value or a settings value, filled in as literal text, escaped, as an id pattern's is; it was matched as the literal text `{name}`. A `{name}` in the step's `with` text is filled in too. A name that is neither is refused when the pack loads; in an import's `bind.normalize`, only the tree rules that resolve a name with `bound_first_segment` are refused, and the message names the imports file. A quantifier such as `{2}` stays a quantifier, and a brace after an odd number of backslashes, as `\{node}`, stays literal, in an id pattern too; in `with` text a backslash is literal and stays. A normalize or id pattern that does not compile once its values are filled in, as an empty value inside `[...]`, loads, does not run where it would have, and lists a skipped row there; an import's step lists one only for the rules that read the imports.

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
