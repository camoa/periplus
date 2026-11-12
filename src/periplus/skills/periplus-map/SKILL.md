---
name: periplus-map
description: Answers code questions from a Periplus map by following its edges, and records what a node or edge does in the descriptions file beside the map. Use when a project has a .periplus/map.json and the user asks what calls or uses this, who uses this service, what breaks if this changes, where something is defined, how A reaches B, which subscribers listen to an event, what makes up a feature, or which files take part in a feature. Use it before grep.
---

# Navigate a Periplus map

## Standing rules

1. Rules are small and add to each other: one rule solves one case, and several cases are several rules. Split by rule file inside one rutter, never by adding rutters; a new rutter repeats the file types and folders the covering one already holds, and a small rule can be read, tested and removed alone.
2. A rutter reads its stack in passes by depth: structure first, then one layer inside each class, then joins in the map. Each pass reads what the one before it found, so no rule has to look a thing up itself.
3. There is no stack knowledge in the engine; a stack's shape is a rule in a rutter. The engine then stays the same for every stack, and a third-party rutter can do all a built-in one does.
4. Write the rule and run it: probe before saying a rutter cannot, and quote the engine's message. A guess about the format's limits has been wrong before; the message is the evidence.
5. A rutter meant for others never names the project it was built on, in its code, rules, examples or prose. The name leaks the project and ties the rule to one site.

## The map is a guide, not the answer

Use the map to learn what a thing is, where it is and what it links to. Then check the code. Every
answer takes two passes:

1. Map pass. Follow the edges and collect the items, each with its file and line.
2. Code pass. Search the files for the names the map gave you, and for the question's own words.
   Add what the search finds and the map did not. Remove nothing the map gave unless the code at
   its line shows it is wrong.

An item belongs in the answer when either pass finds it. Never skip the code pass because the map
pass looked complete. When the two disagree, the code wins.

## Before the first command

- The map is already built. Do not run `periplus map` to answer a question. Rebuild only when the
  user asks for it. `periplus status` does not say whether the map is stale.
- Never pipe map output into `head` or `tail`. Pass `--limit 0` to `find`, `show`, `neighbors`,
  `affected` and `path`. A cut list ends with `showing N of TOTAL`.
- `periplus find` only gets you a starting id. Its rows are name matches, not the answer. The
  answer comes from following edges with `show`, `neighbors`, `affected`, `path` and `slice`.
- Your first three calls: `periplus types` once, in full, to learn the edge kinds; `periplus find`
  with `--type` and `--limit 0` for a start id; `periplus show` on that id with `--limit 0`.

Ids and filters:

- Quote an id in single quotes. Single and doubled backslashes both work. An unknown id exits 31
  and lists close ids.
- `find` matches text in the id, never the file path. `--type T` keeps T and its subtypes. It
  takes one type: a repeated `--type` keeps only the last, so run `find` once per type.
- `find ""` lists every node. With `--map` on a slice file, it lists every node of the slice.
- `neighbors` follows edges out of a node, `affected` follows edges into it. Both take `--depth N`
  and repeated `--kind K`. `path` follows edges forward only.
- Write slices to a scratch folder, never into the project. A slice stops at 500 items unless you
  pass `--limit 0`.

The kinds below come from the bundled Drupal, PHP, JavaScript and Twig rutters. For another stack,
pick the matching kinds from `periplus types`.

## Recipes by question

**What uses this service or class?**

```console
$ periplus show drupal.service::my_module.mailer --limit 0
$ periplus neighbors 'php.type::Drupal\my_module\Service\Mailer' --kind contains --kind implements --limit 0
$ periplus affected 'php.method::Drupal\my_module\Service\Mailer::send' --kind calls --limit 0
$ periplus affected 'php.type::Drupal\my_module\Service\Mailer' --kind instantiates --kind references_class --kind builds_form --limit 0
```

`show` lists who fetches the service (`uses_service`), who injects it (`injects_service`) and its
class (`service_class`). Calls land on methods, not on the service, so run `affected` on each
public method. Run it on the same method of each interface too: callers often type the interface.
The last command lists the methods that create the class with `new`, name it as `\A\B\Foo::class`,
or build it as a form. A `calls` edge also covers `$this->method()` inside the class and its
subclasses.

**Where is this defined?** `periplus find mailer --type drupal.service --limit 0`, then
`periplus show ID`. The `location` line is the file and line of the definition.

**What breaks if this class or its constructor changes?**

```console
$ periplus show 'php.type::Drupal\my_module\Service\Mailer' --limit 0
$ periplus affected 'php.type::Drupal\my_module\Service\Mailer' --depth 3 --kind inherits --kind service_class --kind plugin_class --limit 0
$ periplus affected 'php.method::Drupal\my_module\Service\Mailer::__construct' --kind calls --limit 0
$ periplus affected 'php.type::Drupal\my_module\Service\Mailer' --kind instantiates --limit 0
$ periplus neighbors drupal.service::my_module.mailer --kind injects_service --limit 0
```

This gives subclasses at every depth, the service and plugin definitions that name each class,
the subclass constructors that call `parent::__construct`, the methods that call `new` on the
class, and the arguments the service file passes. Run the `instantiates` command on each subclass
too. For any other change, run `periplus affected ID --depth 2 --limit 0` and narrow it with
`--kind`.

**How does A reach B?**

```console
$ periplus path drupal.route::my_module.report 'php.method::Drupal\my_module\Service\Mailer::send' --limit 0
$ periplus affected 'php.method::Drupal\my_module\Controller\ReportController::view' --kind contains
$ periplus neighbors 'php.method::Drupal\my_module\Controller\ReportController::view' --kind calls --kind instantiates --kind builds_form --kind renders_theme_hook --kind attaches_library --limit 0
```

`no path` means no forward chain. Try `path TO FROM` too. A chain often breaks where two edges
point at the same node: a route and a class both point at a method. Step across by hand: from the
method, `affected --kind contains` gives its class; from the class, `neighbors` goes on. A method
points at the methods it calls (`calls`, `$this->helper()` included), the classes it creates, the
forms it builds, the theme hooks it renders and the libraries it attaches, so walk method by
method with the last command. A theme hook reaches its template through `theme_hook_template`.

**Everything that takes part in a feature**

```console
$ periplus find report --type drupal.route --limit 0
$ periplus affected drupal.module::my_module --depth 1 --kind route_in_module --kind service_in_module --kind class_in_module --kind library_in_module --kind template_in_module --limit 0
$ periplus slice --path web/modules/custom/my_module/ --direction out --depth 3 --kind handled_by --kind uses_form --kind contains --kind renders_theme_hook --kind theme_hook_template --kind template_includes --kind attaches_library --kind template_attaches_library --kind library_includes_script --kind library_includes_stylesheet --kind script_declares_behavior --kind builds_form --kind plugin_class --kind service_class --kind route_serves_path --kind subscribed_by --kind uses_queue --limit 0 --out /tmp/feature-out.map.json
$ periplus slice --path web/modules/custom/my_module/ --direction in --depth 2 --kind route_serves_path --kind links_to_path --kind script_links_to_path --kind template_links_route --kind script_links_to_route --kind links_to_route --kind places_plugin --kind uses_service --kind injects_service --kind calls --kind suggests_theme_hook --limit 0 --out /tmp/feature-in.map.json
$ periplus types --map /tmp/feature-out.map.json
$ periplus find "" --map /tmp/feature-out.map.json --type drupal.template --limit 0
$ periplus affected drupal.module::my_module --kind depends_on_module --limit 0
```

The `affected` command lists what the module holds: its routes, services, classes, libraries and
templates. A theme holds its own through `library_in_theme` and `template_in_theme`. JavaScript
and config files have no such edge, so also start from the folder with `--path`. The out slice reaches templates, libraries and scripts in other folders, such as a theme. The in
slice finds what points into the module: links, block placements, callers. Run `find` once per
type for the feature's words (route, template, library, service): things in other modules are
joined to the feature by name only. List each slice by type with `find ""`. The last command
lists config that declares the module.

**Which subscribers listen to this event?**

```console
$ periplus find order --type drupal.event --limit 0
$ periplus neighbors drupal.event::my_module.order_placed --kind subscribed_by --kind dispatched_by --kind dispatched_by_function --limit 0
$ periplus find "" --type drupal.event_subscriber_class --limit 0
```

The reverse question, which events a method listens to, is
`periplus affected 'php.method::Drupal\my_module\EventSubscriber\OrderSubscriber::onPlaced' --kind subscribed_by`.
A subscriber class that inherits its event list from a base class outside the map has no
`subscribed_by` edge. Compare the subscriber list with the listeners and read the ones left over.

## When to read source

Read the code after the map names its file and line: to confirm the edge, and for details the map
does not hold. Each row carries a state:

- `mapped`: found in the project's files, with a location.
- `referenced` or `declared`: named by an edge, defined outside the mapped files.
- `unresolved`: a rule looked for the target by name and found none. The edge and its source
  line are real; the target is not in the map.

A call site with `attribute resolution: "runtime"` picks its target at run time. The map does not
guess it. Say so in the answer, then grep for that gap only.

An empty result is not proof. Edges exist only where a rutter has a rule. The bundled rutters do
not map these yet: PHP calls written `$this->method()`; `new Foo(...)` and `new static(...)`; a
form class passed to a form builder by class name; a URL written as a plain string in code or in a
template attribute. The code pass is where you find these. To record a gap, use the periplus-gaps
skill.

## Worked example

Each command's options, output and exit codes are in [Navigation](https://github.com/camoa/periplus/blob/v0.7.0/docs/navigation.md). On the
project in the Navigation guide's worked example, these run as shown:

<!-- nav-run -->
```console
$ periplus types
$ periplus find helper
$ periplus show python.function::shop.tools.helper
$ periplus neighbors python.module::shop.cli --kind imports
$ periplus affected python.function::shop.tools.helper
$ periplus path python.module::shop.cli python.function::shop.tools.helper
```

## Read and write the descriptions file

The map holds ids, types and locations, not what a thing does. That text lives in
`.periplus/descriptions.yaml`, beside the map and never inside it. The engine neither reads nor
writes the file, so the map stays byte-identical from run to run. Commit it with the map.

`periplus show` prints a node's entry, or `description: none` when it has none, and an edge's
entry under its row. `neighbors` and `affected` print no entries, so run `show` on each id they
reach that the answer rests on.

When you read the code of a node or an edge that has no entry, write its entry before you answer.
A reading that leaves no entry leaves no record, so the next question reads the code again.

The file has two top-level keys:

- `nodes` maps a node id to an entry.
- `edges` is a list of entries. An edge has no id in the map, so each entry carries `from`,
  `kind` and `to` exactly as the map writes them.

Every entry carries `text`, one or more sentences on what the thing actually does, and `file` and
`line`, where you read it. When the code at that file and line no longer matches the text, read
the code again and rewrite the entry. The shape is in references/descriptions.schema.json.

<!-- example descriptions: .periplus/descriptions.yaml -->
```yaml
nodes:
  python.function::shop.tools.helper:
    text: Returns the constant 1. It reads nothing and changes nothing.
    file: shop/tools.py
    line: 1
edges:
  - from: python.module::shop.cli
    kind: calls
    to: python.function::shop.tools.helper
    text: The hello command's greet function calls helper and discards the result.
    file: shop/cli.py
    line: 9
```
