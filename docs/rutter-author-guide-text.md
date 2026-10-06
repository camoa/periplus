# Text spans, enclosing values and two skipped rows

Read [Writing a rutter](rutter-author-guide.md) first. This page covers the keys a text rutter uses
for nested regions of a file, for a node's line, and for a path below a folder; and the two rows
a map report adds when a rule fires and makes less than it names. Check 98d-laravel-pack proves
each key on `laravel_basic`, and `tests/test_spans.py` on a planted rutter.

## Spans

A span is a region of a text file that holds other matches, such as a Laravel route group. A file
type declares its spans beside its sections, each with a `name`, an `open` pattern and a
`balance` pair of characters:

```yaml laravel_basic@0.0.5/pack.yaml
spans:
- name: group
  open: 'Route::(?:(?:prefix\(\s*[''"](?<prefix>[^''"]*)[''"]\s*\)|name\(\s*[''"](?<name>[^''"]*)[''"]\s*\)|middleware\((?:[^()''"]|''[^'']*''|"[^"]*")*\))\s*->\s*)+group(?=\s*\()'
  balance: ['(', ')']
```

A span starts at each match of `open` outside the type's sections. From the end of that match,
each opening character outside the sections counts one up and each closing character one down.
The span ends after the closing character that brings the count to zero or below, or at the end
of the file when none does. So the open must stop before its first opening character, as above.
An open that takes it starts the count one short, and the span ends at the first inner pair.

Sections matter here: a closing character inside a string or a comment does not count. Spans of
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
default. A span whose capture took no part, or is empty, adds nothing. No such span gives the
empty value. Then `normalize` and `case` run, as for any value. The `/` route above gets the
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
executed, and the report says which.

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

An end lacks a value when its capture matched empty text, its template names an empty value, or
no resolution step holds, which reads `no resolution step holds for capture b`. A tree rule's row
names the end, as `no value for enclosing_class`, an attribute's argument that is not a text
literal, or the written name a reference rule's step cannot resolve.

An end whose source is absent states no edge, and leaves no row: a capture that took no part, a
template naming a value nothing gave, a declaration with no written name, an attribute argument
not written, or a data rule's key path that reaches nothing. Packs pick between two rules or two
edges that way, as `drupal_basic` does for a permission with and without a plus sign. An optional
key a file leaves out is silent by design: the file does not state that relation. An id that
names an absent value makes nothing and leaves no row, on a data rule as on a text rule.

A data rule's `where`, `pattern` and `listed_at` pick between edges. So a data edge leaves its row
only when it has none of them and its key path reached a value that gives no end, such as a
mapping. A data rule leaves `fired and emitted nothing` only when a key path of its edges reached
a value and it made no edge and left no edge's row. A binding rule never leaves either row, since
it makes no node or edge.
