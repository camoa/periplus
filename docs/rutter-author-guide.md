# Writing a rutter

A rutter is a pack of data that tells Periplus how to find one stack's things in real files. The
engine decides what must be done: which files are read, how a match becomes a node, and when an
edge end is unresolved. The rutter decides how: which folders, which file types, which patterns
and which names. A new stack is a new rutter, never engine code.

The three rutters in `examples/second-stack/packs` are the worked example. `python_text` maps
Python modules, top-level classes and functions, and imports. `typer_text` depends on it and maps
Typer apps, commands and mounts. `speckitty` maps spec-kitty's missions and their templates.
The PHP and Drupal rutters read a parse tree; [Reading the Drupal rutters](rutter-author-guide-drupal.md)
walks through them. [Text spans](rutter-author-guide-text.md) covers nested regions of a text file.
[Second children and id patterns](rutter-author-guide-abilities.md) tests a call's class and its
method in one rule, and keeps an id only when its source fits a pattern.

## The files of a rutter, and how a project loads one

A rutter is one folder named `<pack>@<version>`. It holds:

- `pack.yaml`, the manifest: the pack's name, version and dependencies, as `depends: [python_text]`
  with no version, its named folders, and its file types: endings, reader, path values, sections.
- pack files, each other `.yaml` or `.yml` file in any subfolder: node types, edge kinds, rules.

A rutter may name only the types it declares, or the types of a pack it depends on. A project
reads rutters from its own `.periplus/packs` folder and names them in `.periplus/settings.yml`. The
project folder is the import root. In the settings, `pack_paths` adds rutter folders, relative to
the project folder, and `re_include` takes back by glob what a rutter's `files.exclude` leaves out.
`values` names strings, as `values: {module: example.com/app}`, that any template may name, a
path value's too. A setting that a path value, a capture or the engine also gives, and a path value
template naming what neither its pattern nor a setting gives, refuse the map with exit 19.
Run these in the project folder, with `REPO` naming the repository:

```
$ mkdir -p .periplus/packs
$ cp -r "$REPO"/examples/second-stack/packs/. .periplus/packs/
$ cp "$REPO"/examples/second-stack/settings.yml .periplus/settings.yml
```

## One rule of each shape

A whole-file rule makes one node per file, at line 1. The id comes from a path value, which the
manifest computes from the file's path. The pattern is searched, its captures fill the template,
and then each normalize step and the case reshape the result:

```yaml python_text@0.1.0/pack.yaml
module:
  pattern: '^(?<path>.+)\.py$'
  template: '{path}'
  normalize:
  - {replace: '/__init__$', with: ''}
  - {replace: '/', with: '.'}
```

```yaml python_text@0.1.0/rules/python.yaml
- rule: module
  reads: file
  in: [python]
  match: {file: '**', filetype: python}
  id: {template: '{module}'}
  emits: [{node: {type: python.module}}]
  confidence: declared
```

`match.file` globs the file's stem, its name less its type's ending: `file: mission` reads
`mission.yaml`. A rule reads the files directly in each folder `in` names; a folder value needs
`/**` to reach those below. A text rule fires once per match of `match.text`, an RE2 pattern, on a
file type read as text. One rule reads one way: to read a tree type's files as text too, declare a
second type on that ending under `files.types`, as `php_notes: {endings: [php], reader: text}`; each
rule takes its own type's path values and sections, and two types read alike are refused. A text
rule's node sits at the match's line, its id a template over captures and path values:

```yaml python_text@0.1.0/rules/python.yaml
- rule: class
  reads: file
  in: [python]
  match: {file: '**', filetype: python, text: '(?m)^class[ \t]+(?<name>\w+)'}
  id: {template: '{module}.{name}'}
  emits: [{node: {type: python.class}}]
  confidence: declared
```

Values reshape a capture before an id or an attribute uses it. In Typer, a command with no
written name takes its function's name, lowercased, with dashes for underscores:

```yaml typer_text@0.1.0/rules/commands.yaml
values:
  command:
    from: {capture: fn}
    normalize:
    - {replace: '^.*\.', with: ''}
    - {replace: '_', with: '-'}
    case: lower
```

A binding rule names what a file's imports bind. It emits only bindings, has no id, writes nothing
to the map, and serves no tree rule. Its values pick the bound name and target from one capture:

```yaml python_text@0.1.0/rules/python.yaml
values:
  bound: {from: {capture: spec}, normalize: [{replace: '^\w+[ \t]+as[ \t]+', with: ''}]}
  orig: {from: {capture: spec}, normalize: [{replace: '[ \t]+as[ \t]+\w+$', with: ''}]}
emits: [{binding: {name: '{bound}', target: '{source}.{orig}'}}]
```

An end or an id with `resolve` runs its steps in order on the written name; the first that holds
gives it. `bound_first_segment` holds when the file binds the first segment; `prefix_with: module`
always holds. An edge end with `on_miss: unresolved` that no rule maps becomes an unresolved node,
which records the rule and the name searched for. Without `on_miss`, the end is a referenced node:

```yaml typer_text@0.1.0/rules/apps.yaml
emits:
- edge:
    kind: mounted_under
    from: this_node
    to: {from: {capture: parent}, resolve: [bound_first_segment, {prefix_with: module}], separator: '.', on_miss: unresolved}
```

Sections are spans of a file type's text that a text rule does not read. A match that starts
inside one gives nothing. Python's sections are its strings and its comments, the first being:

```yaml python_text@0.1.0/pack.yaml
sections:
- name: long_string
  open: '(?<mark>"""|'''''')'
  close: '{mark}'
```

Confidence is declared per rule: `declared` where the file states it, `inferred` for a convention.

## How to check a rutter

```
$ periplus validate python_text
$ periplus validate typer_text
$ periplus validate speckitty
$ periplus status
$ periplus map --output map.json --format json >report.json
```

`validate` checks each file of a rutter against the two schemas; `status` shows which rutters the
project matched, and from where; `periplus spec <pack>` prints the schemas and what the rutter's
manifest declares and inherits. In the map report, `not_executed` lists the rules the engine cannot
run and why, `problems` what the run could not do, `unlisted` the folders it could not list: each
should be empty. `unread` lists the files in the rules' folders that no rule read; it holds `.git`,
the settings and the rutters when a folder is the whole project, so it is never empty there. A
rule holding a key the schemas accept and the engine does not run is not executed;
[Tree references](rutter-author-guide-references.md) lists the keys. An unresolved end is a node in
state `unresolved`, counted in `counts.nodes_by_state`.

## Adding a reference type

A reference is a use of a thing, such as a call. `python_text` states calls with one edge kind and
one rule; a tree rutter, with a [reference rule](rutter-author-guide-references.md). A kind name
takes no dot, so the kind is `calls`, not `python.calls`. Its end lists the types a call can reach:

```yaml python_text@0.1.0/rules/python.yaml
- kind: calls
  from: python.module
  to: [python.function, python.class, python.module]
```

The rule fires once per `name(` or `a.b(` outside a string or a comment, which the sections give.
Its id is the module, so each call is an edge from the module:

```yaml python_text@0.1.0/rules/python.yaml
- rule: call
  reads: file
  in: [python]
  match:
    file: '**'
    filetype: python
    text: '\.[ \t]*\w+(?:\.\w+)*\(|\b(?<callee>\w+(?:\.\w+)*)\('
  id: {template: '{module}'}
  emits:
  - edge:
      kind: calls
      from: this_node
      to: {from: {capture: callee}, types: [python.function, python.class, python.module], resolve: [bound_first_segment], separator: '.', on_miss: unresolved}
  confidence: inferred
```

The end resolves through the file's bindings only. A name whose first segment no import binds
resolves to nothing, and an end that resolves to nothing makes no edge. So a builtin such as
`print(`, a local or a parameter whose name no import binds, a method on an object such as
`self.save(`, a function of the same module, a `def` or `class` header, and a keyword against its
parenthesis, such as `if(`, `return(`, `raise(` or `import(`, give nothing. The format has no
lookbehind, so the first branch consumes any name after a dot, as in `f().name(`, `x .name(` or a
`.name(` that starts a line, and captures nothing. An end whose capture is empty makes nothing.

`types` lists the candidate types in order. The end lands on the first that a rule maps under the
resolved name; when none does, it is an unresolved node of the first type, searched for under that
name. After `from shop.cli import Config`, `Config()` lands on the class. After `import json`,
`json.loads(` is unresolved: a library outside the project. A call on an imported Typer app,
`@app.command()` after `from .cli import app`, is a calls edge to the unresolved
`<package>.cli.app.command` name beside the command's `registered_on` edge.

An edge kind is one name in every rutter a project loads. Two rutters giving one kind different ends
refuse the map with exit 19, naming the kind and both files: `python_text` and `php_basic` each
declare `calls` and `contains`, so one project cannot load both. Give the types at each end of a
kind one id namespace, or a rule building that end from the kind's types is not executed. An end
filled only by whole ids, such as `{declared: <type>}`, may list types of different id namespaces.

## What the format cannot say today

- Python's scopes, in bindings. A binding holds for the whole file and the later one wins, so a
  name imported twice with a use between, a name rebound after its use, and a function-local
  import unlike the module's binding of that name all take the file's last binding. A name that
  shadows an import is not seen, so a parameter, an assignment, a for target, a with or except
  name, or a comprehension variable gives a false edge: after `from os import path`,
  `for path in paths: path.exists()` gives one to os.path.exists. An import of three dots or more
  binds nothing. An aliased `Typer` is missed, and any `x.Typer(` makes an app, whatever module
  `x` is. Python reads scopes, so Python and the rutter differ on a name a `def` rebinds, an
  import inside an `except` handler, and two calls on one line whose names end in the same segment.
- One registration per id. Two that build one id give one node or edge with two locations, and an
  attribute whose values differ holds both. In spec-kitty, `cli/commands/__init__.py` registers
  `next` twice and mounts `doctor` twice, and `mission_type.py` registers `list` on two functions.
- A form the patterns do not read gives nothing: a keyword value with nested braces or brackets,
  a call nested two deep, or a quote escaped in a text literal; a mount whose first argument is a
  call, `add_typer(typer.Typer(), ...)`; an import continued with `\` or followed by `;`, losing
  the names after it; more than three names in an import list; a call with a space before its
  parenthesis, `helper (x)`, or in an f-string, `f"{helper(x)}"`, which the string section hides.
- A command decorator the patterns miss: more than two decorators before its `def`, a blank line or
  comment between them, one continued with `\`, or an apostrophe in a comment in its arguments.
- A method, a nested function or a base class. A text rule sees text, not scopes, so every call
  is from the module, and a method call on an object gives nothing.
- A pattern that looks ahead or back, or that repeats a capture: RE2 has none. The engine runs
  Python's `re`, which loads a lookahead and refuses a lookbehind of varying width; neither is
  portable. Stacked decorators therefore take one rule per depth, an import list one per position.
- An edge from a text rule whose two ends are both templates. One end must be `this_node`, which
  takes no `on_miss`, so a mount is stated by two rules, one for each end.
- An edge from a whole-file rule on a text file. A template's edge is a text rule on `\A`.
