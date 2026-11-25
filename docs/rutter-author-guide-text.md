# Text spans, enclosing values and two skipped rows

Read [Writing a rutter](rutter-author-guide.md) first. This page covers the keys a text rutter uses
for nested regions of a file, for a node's line, and for a path below a folder; and the two rows
a map report adds when a rule fires and makes less than it names.

## Spans

A span is a region of a text file that holds other matches, such as a Laravel route group. A file
type declares its spans beside its sections, each with a `name`, an `open` pattern and a
`balance` pair of an opening and a closing token:

```yaml laravel_basic@0.0.5/pack.yaml
spans:
- name: group
  open: 'Route::(?:(?:prefix\(\s*[''"](?<prefix>[^''"]*)[''"]\s*\)|name\(\s*[''"](?<name>[^''"]*)[''"]\s*\)|middleware\((?:[^()''"]|''[^'']*''|"[^"]*")*\))\s*->\s*)+group(?=\s*\()'
  balance: ['(', ')']
```

A span starts at each match of `open` outside the type's sections. From the end of that match,
each opening token outside the sections counts one up and each closing token one down. The span
ends after the closing token that brings the count to zero or below, or at the end of the file
when none does. So the open must stop before its first opening token, as above.
An open that takes it starts the count one short, and the span ends at the first inner pair.

Sections matter here: a closing token inside a string or a comment does not count. Spans of
one name nest, since each match of `open` starts its own span. In this route file:

```php
Route::prefix('admin')->name('admin.')->group(function () {
    Route::get('/stats', [BookController::class, 'index'])->name('stats');
    Route::get('x', function () {
        return view('welcome');
    });
    if (true) {
        Route::get('/inside-if', [BookController::class, 'index']);
    }
    $s = '})}';
    Route::middleware(['auth'])->prefix('/v1/')->name('v1.')->group(function () {
        Route::get('/', [BookController::class, 'index'])->name('root');
    });
});
Route::get('/outside', [BookController::class, 'index']);
```

the outer span runs from its first line to the `)` of the `});` before the last route, and the
inner span holds only the `/` route. A closure route and the if block each balance their own parentheses,
and `'})}'` is a string section, so neither ends the group. A same-kind counter of `});` would
end the group at the closure route.

A match outside every span still fires. To drop it, name the span's value in the id, then strip
it with `normalize`, as `{scope}|{name}` with `^.*\|`.

A `balance` entry of one character matches that character; a longer entry is a pattern, so a
tag language balances its tags:

```yaml
sections:
- name: comment
  open: '<!--'
  close: '-->'
spans:
- name: function
  open: '(?=<fn\b[^>]*\bname="(?<name>\w+)")'
  balance: ['<fn\b', '</fn>']
```

The open is a lookahead, so it stops before its own `<fn`, which counts one up. An inner `<fn`
counts one more and its `</fn>` one down, so the function's own `</fn>` ends the span. The body is
no section, so a comment inside it stays a section a rule does not read.

A longer entry is a regular expression, never literal text, so escape its metacharacters:
`<\?php`, `/\*`, `\{\{`. Unescaped, `<?php` means "an optional `<`, then `php`", and it still
loads. An entry that matches the empty text on its own, such as `/*` ("zero or more slashes"), is
refused. An entry that matches zero characters only in context, such as `(?=a)`, `\b` or `(?<=x)`,
loads; where it matches, it counts, and the search goes on one character later.

A `{name}` in a `balance` entry is not filled in: it matches the literal text `{name}`.

A token counts where it starts. One that starts outside the sections counts even when its match
runs into a section; one that starts inside a section is skipped, and the search goes on after
that section. Tokens never overlap: the search goes on after each token counted. Where an opening
and a closing token start together, the opening counts. So a pair whose closing token matches
only where the opening token matches never closes, and that span runs to the end of the file.

## A value from the enclosing spans

A text rule's value may read a capture of every span that holds the match:

```yaml laravel_basic@0.0.5/rules/routes.yaml
  values:
    method: {from: {capture: verb}, case: upper}
    prefix: {from: {enclosing: group, capture: prefix}, join: '/', normalize: [{replace: '/+', with: '/'}, {replace: '^/|/$', with: ''}]}
    path: {template: '{prefix} {uri}', normalize: [{replace: '^ ', with: ''}, {replace: ' /*$', with: ''}, {replace: ' /*', with: '/'}]}
  id: {template: '{route_file}:{method} {path}'}
```

`from: {enclosing: group, capture: prefix}` takes the `prefix` capture of each `group` span whose
region holds the start of the match, outermost first, and joins them with `join`, empty by
default, so nested `function_body` spans give `outerinner`. A span that opens at that very start
is held too, which is how a key that opens an array reads itself as the last segment of its path;
`excluding_own: true` beside `capture` leaves it out, so a declaration that opens a
`function_body` span reads only the functions around it. To take the innermost name, use `join: '|'` with `normalize: [{replace: '^.*\|', with: ''}]`, which gives `inner`. A span whose capture took no part, or is empty, adds nothing. No such span gives the
empty value. Then `normalize` and `case` run, as for any value. Each step runs once, so climbing two `../` levels takes the step twice. The `/` route above gets the
prefix `admin/v1`: `admin` and `/v1/` joined, then each run of slashes made one and the outer
slashes trimmed.

A value's template reads an empty value; an id, attribute or edge template does not, and makes
nothing when it names one. So `path` joins the prefix and the URI, a space between, and its steps
tell the two cases apart: with no prefix the leading space goes and the URI stays as written,
`/outside`; with one the space becomes a slash, `admin/stats`, and a URI of `/` alone leaves
`admin/v1`. A name prefix works the same way, `join` left empty:

```yaml laravel_basic@0.0.5/rules/routes.yaml
    name_prefix: {from: {enclosing: group, capture: name}}
    full_name: {template: '{name_prefix}{name}'}
```

and the attribute reads `from: {value: full_name}`, so the `/` route is named `admin.v1.root`.
A rule names only a span its file type declares and a capture its `open` holds, or it is not
executed, and the report says which. A value reads only its own file: a variable set in another
file is not followed.

## The line of a node

A text rule's node sits at the line its match starts on. When the match reaches back before the
thing it names, `line` names the capture whose line the node takes:

```yaml
- rule: item
  reads: file
  in: [src]
  match: {file: '*', filetype: blk, text: 'item\s+(?<name>\w+)'}
  id: {from: {capture: name}}
  line: {capture: name}
  emits: [{node: {type: blocks.item}}]
  confidence: declared
```

On `item` at line 11 and `five` at line 12, the node `blocks.item::five` sits at line 12. Its
values and anything a template makes sit there too; an attribute or edge end from a capture keeps
that capture's own line. A capture that took no part leaves the match's line.

## A path value relative to a folder

A path value searches its `pattern` in the file's path from the project folder. With
`relative_to`, it searches the path below a named folder:

```yaml laravel_basic@0.0.5/pack.yaml
view:
  pattern: '^(?<name>.+)\.blade\.php$'
  template: '{name}'
  relative_to: views_root
  normalize:
  - {replace: '/', with: '.'}
```

The folder resolves as a rule's folders do, settings first. The deepest of its directories that
holds the file is cut from the front of the path, with the slash after it, before the pattern
runs. With `views_root: ./resources/views`, `resources/views/books/index.blade.php` searches
`books/index.blade.php` and gives `books.index`. A project that sets `views_root: ./templates`
gets the same id from `templates/books/index.blade.php`. A file no directory of the folder holds
has no such value.

The folder's value must hold no `**` segment, since the deepest directory below it would always
win. A pack whose `relative_to` names such a folder, or a folder no loaded pack declares, is
refused when the rules load, at exit 19. A settings value that gives the folder `**` is refused
before any file is read, at exit 18:

```
the folder views_root, which a path value is relative_to, holds ** in its value
```

## A project that is one unit at its root

A pattern that reads a name from a folder, such as the unit in `units/inv/src/one.sx`, finds no
such folder when the project folder is that unit: the path is `src/one.sx`. `root_name` names a
settings value that stands for the project folder's name:

```yaml
values:
  unit_name: The unit's name, when the project folder is one unit.
files:
  types:
    code:
      endings: [sx]
      reader: text
      path_values:
        unit:
          pattern: '^(?:.*?/)??(?<unit>[^/]+)/src/[^/]+\.sx$'
          template: '{unit}'
          root_name: unit_name
```

When the settings give `values: {unit_name: inv}`, the pattern searches `inv/src/one.sx` and the
value is `inv`, as it is for `units/inv/src/one.sx` in a larger project. A folder inside the unit
keeps its own name: `sub/src/two.sx` searches `inv/sub/src/two.sx` and gives `sub`. The name
comes from the settings, never from the folder on disk, so the map is the same wherever the
checkout sits. The name goes before every path that starts at the project folder: a path value
with no `relative_to`, or one `relative_to` a folder that the settings set to `.`. A path value
relative to a folder below the project folder, and a path value with no `root_name`, search the
path as it is. Without the value the path is searched as it is too, so `periplus map` does not
ask for a value that a `root_name` names and no `{name}` in a loaded rutter's files reads.
`periplus init` prints a line for each value a `root_name` names, with the sentence its rutter
declares.

A `root_name` naming a value that the rutter, or a rutter it depends on, does not declare, and
the settings do not give, is refused when the rules load, at exit 19, as a template naming one
is. So is a given value that is empty, `.` or `..`, or holds `/`, `\`, a space or a control
character:

```
the settings value unit_name of <project>/.periplus/settings.yml, which acme/pack.yaml reads as the name of the project folder, is 'inv/sub', which is no folder name
```

A capture that is also a settings value stays refused, as for any template.

## The keys of a list as paths

A data rule can turn each key under a list into the path of another file. A path value on the
file's type gives the folder the file sits in, and the edge's `to` joins it with each key:

```yaml drupal_js_basic@0.1.0/pack.yaml
    yml:
      endings: [yml]
      reader: data
      format: yaml
      path_values:
        libraries_dir:
          pattern: '^(?<dir>.+)/[^/]+$'
          template: '{dir}'
```

With `to: {from: [{each: js.*}], template: '{libraries_dir}/{key}', where: [{not_matches: 'http:*'}]}`,
a libraries file `web/modules/custom/m/m.libraries.yml` that lists `js/form.js` under `js:` gives
an edge to `web/modules/custom/m/js/form.js`, and a key starting `http:` gives none. `matches` and
`not_matches` are globs on the key and are described in
[Tree references](rutter-author-guide-references.md#filtering-the-keys-of-a-list-form-edge-end).
The end reaches a script's `js.file` node through `from: enclosing_file`, described there too.

## Two skipped rows

The map report's `skipped` list holds a row, with its `file`, `line`, `rule` and `reason`, for a
match that made less than its rule names. Two reasons say a rule fired and made less than that.

A fire that makes no node and no edge leaves `fired and emitted nothing`, unless it left an edge's
row or every source it names is absent, as below. An edge whose end
cannot be made while its rule fires leaves a row naming the edge's kind and what it lacks, and the
rule's other edges still emit. In this planted rutter, beside `laravel_basic`:

```yaml
- rule: probe_nothing
  reads: file
  in: [routes]
  match: {file: '*', filetype: route_file, text: 'probe (?<a>nothing) (?<b>\w*);'}
  id: {from: {capture: a}}
  emits:
  - edge: {kind: probe_second, from: this_node, to: {from: {capture: b}}}
  confidence: declared
- rule: probe_two
  reads: file
  in: [routes]
  match: {file: '*', filetype: route_file, text: 'probe (?<a>both) (?<b>\w+) (?<c>\w*);'}
  id: {from: {capture: a}}
  emits:
  - edge: {kind: probe_first, from: this_node, to: {from: {capture: b}}}
  - edge: {kind: probe_second, from: this_node, to: {from: {capture: c}}}
  confidence: declared
```

the lines `probe nothing ;` and `probe both one ;`, at 27 and 28, give these rows, and the edge
`probe_first` from `laravel.route::both` to `laravel.route::one`:

```
routes/web.php:27 probe_nothing edge probe_second: no value for capture b
routes/web.php:28 probe_two edge probe_second: no value for capture c
```

An end lacks a value when its capture matched empty text, its template names an empty value and
no absent one, or no resolution step holds, which reads `no resolution step holds for capture b`. A tree rule's row
names the end, as `no value for enclosing_class`, an attribute's argument that is not a text
literal, or the written name a reference rule's step cannot resolve.

An end whose source is absent states no edge, and leaves no row: a capture that took no part,
named directly or by a template no other capture of which took part, a template naming a value nothing gave, a declaration with no written name, an attribute argument
not written, or a data rule's key path that reaches nothing. Packs pick between two rules or two
edges that way, as `drupal_basic` does for a permission with and without a plus sign. An optional
key a file leaves out is silent by design: the file does not state that relation. An id that
names an absent value makes nothing and leaves no row, on a data rule as on a text rule.

A data rule's `where`, `pattern` and `listed_at` pick between edges, so a value they leave out
leaves no row. A data edge leaves its row when it makes no end at all and lost a value its filter
did not leave out: a value that is not text, such as a mapping or a list, a template left without
a value, or, in the list form, a fixed key the entry lacks. A number, true or false is text. This
holds for a single key, a key path with a star and the list form with `each` alike. A key path
that reaches nothing, as an item under a star that lacks the key, gives no value and no row. An
edge that makes an end from some values lists no row for the ones it lost. A `listed_at` path the
entry does not hold lists nothing, so it leaves every end out, as a filter does. A data rule leaves `fired and emitted nothing` only when a key path of its edges
reached a value and it made no edge and left no edge's row. A rule whose filters left out every
value it reached, in the whole map, is listed once under Rules that fired and made nothing. A
binding rule never leaves either row, since it makes no node or edge.

This data rule leaves out every label that starts `tmp_` with its `pattern`:

```yaml
- rule: box_label
  reads: file
  in: [shelves]
  match: {file: '*', filetype: shelf}
  id: {template: '{file_stem}'}
  emits:
  - edge: {kind: labelled, from: this_node, to: {from: {key: labels.*.name}, pattern: '^(?!tmp_)(?<label>.+)$', template: '{label}'}}
  confidence: declared
```

A file whose labels are `tmp_one` and `tmp_two` lists no skipped row: the filter chose. When no
file in the project gives the rule an edge, the report names it once:

```
Rules that fired and made nothing:
  shelf box_label
```

A second file with the label `red` gives an edge to `shelf.label::red`, and the section is empty
again. So read a rule listed there as a filter to check against the files, not as a shape to map.

## A rule that runs long

`periplus map` names on standard error a rule or span that has spent more than 10 seconds on one
file, while it still runs, and gives its time when it ends:

```
periplus map: slow: rule <rule> of rutter <rutter> on <file>: 10.00 s so far, still running
periplus map: slow: rule <rule> of rutter <rutter> on <file>: took 312.45 s
```

The cause is a pattern that backtracks: a quantifier inside a quantifier, as `(?:\w+\s?)+$`, or
optional groups that can match the same text before a greedy tail. On a line that almost matches,
such a pattern tries every way to split it. Remove the nesting or anchor the pattern on a literal,
and map again. `--slow-after SECONDS` changes the limit; the map and the report do not change.
