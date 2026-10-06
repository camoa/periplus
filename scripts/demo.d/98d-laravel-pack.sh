#!/usr/bin/env bash
# The bundled Laravel pack. The project root is a Laravel application's root in the default layout:
# a route file with one closure route and two controller routes, one naming its class in full, a
# base controller and a controller
# whose method returns a view, a model, three Blade views (one extends a layout and includes a
# partial), a config file and a migration. Its settings pin php_basic@0.1.0 and laravel_basic@0.0.5
# and move no folder. The map exits 0 with no problems and nothing not executed, and holds exactly
# the route, view, controller, model, config and migration nodes, the handled_by edge from the
# controller route to its method, the Blade extends and include edges, and php_basic's own class
# and method nodes beside them. The controller's view('books.index') is a renders edge from its
# method; the closure route's view('welcome') gives none. The map is byte-identical across two runs.
# Planted beside them: an api.php whose routes inside a //, /* */ or # comment or a quoted string
# give nothing, while a route after #[Pure], before a trailing comment, or after '/glob/*' still
# maps. A heredoc and a nowdoc whose bodies hold a /*, an apostrophe and a route give no node for
# that route, and the two routes after each still map. So does a route after a backtick string
# holding /*, after a quoted string over three lines whose second holds /* and whose third a route,
# after a string continued by a final backslash, and after inline HTML holding an apostrophe, one
# opened by ?> in a // comment, one in a # comment and one by a bare ?>. So do two routes after a
# double-quoted string whose {$...} interpolation holds a quoted apostrophe. A view whose <x-alert>
# and <x-missing> tags give uses_component edges and whose <x-slot> and {{-- --}} tags give
# nothing. A second site keeps its routes in routing/ and sets only views_root, to
# frontend/resources/views: its route, views and include are all mapped. A third sets routes to
# ./routes/**: GET /x in routes/web.php and in routes/admin/web.php are two nodes.
# A fourth holds route groups: a prefix group with a name prefix, a group nested in it, a closure
# route, an if block and a string holding '})}' inside it, a group written name()->prefix() over
# three lines, and a route outside every group. Each route's id, name and line are asserted. A
# fifth keeps the first site's templates in templates/ and sets views_root there: its view ids
# equal the first site's. Setting views_root to a value holding ** is refused, naming the folder.
# A planted rutter beside laravel_basic on the fourth site holds a text rule that fires and makes
# nothing, and a two-edge text rule whose second capture is empty: two skipped rows, and the
# first edge is made. Two runs of the fourth and fifth sites are byte-identical.
# A sixth site holds a controller whose methods call view('a.b') to an existing view,
# view('no.such'), view($name), config('app.name'), config($key), view('a.b') inside a closure,
# config('no.such.key') and View('a.b'), PHP names being case-insensitive: renders and
# reads_config edges from each method, no.such and no.such.key unresolved, and a skipped row for
# each variable argument.
# config('no.such.key') in a template and config('app.name') in one outside views_root give the
# edges and fires the pack's gaps state. A planted rutter beside it maps routes/extra.php, read as
# PHP, by a declaration rule on Route::get and Route::post calls whose id is the first argument:
# one node per real route, none for a route in a line comment, a block comment, a string, a
# heredoc or inline HTML, a skipped row for Route::get($uri, ...) and Route::get('', ...), and
# nothing for Route::fake('/rejected').
# A seventh site holds config files: each text key of the array a file returns is a node, at every
# depth, with a key_of edge to its file, and so is a key named by the file; a planted case of each
# shape that gives no node gives none, and config/api.php, named like a route file, gets its keys.
# A controller's and a template's reads of an existing key, a missing key, a missing file and a
# whole file end where and in the state the pack's gaps state. Two runs are byte-identical.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
mkdir -p "$site/.periplus" "$site/routes" "$site/app/Http/Controllers" "$site/app/Models" \
    "$site/resources/views/books" "$site/resources/views/layouts" "$site/config" \
    "$site/database/migrations"
cat >"$site/routes/web.php" <<'EOF'
<?php

use App\Http\Controllers\BookController;
use Illuminate\Support\Facades\Route;

Route::get('/', function () {
    return view('welcome');
});

Route::get('/books', [BookController::class, 'index']);
Route::get('/q', [\App\Http\Controllers\BookController::class, 'index']);
EOF
cat >"$site/routes/api.php" <<'EOF'
<?php

use App\Http\Controllers\BookController;
use Illuminate\Support\Facades\Route;

// Route::get('/line', [BookController::class, 'index']);
/* Route::get('/block', [BookController::class, 'index']); */
# Route::get('/hash', [BookController::class, 'index']);
$a = "Route::get('/dq', [BookController::class, 'index'])";
$b = 'Route::get("/sq", [BookController::class, "index"])';
Route::get('/attr', #[Pure] fn () => 1); Route::get('/after-attr', fn () => 2);
Route::get('/trail', [BookController::class, 'index']); // Route::get('/after', [BookController::class, 'index']);
Route::get('/glob/*', [BookController::class, 'index']);
Route::get('/last', [BookController::class, 'index']);
$help = <<<TXT
    /* opens nothing
    Don't
    Route::get('/in-heredoc', [BookController::class, 'index']);
    TXT;
Route::get('/heredoc-one', [BookController::class, 'index']);
Route::get('/heredoc-two', [BookController::class, 'index']);
$raw = <<<'NOW'
/* opens nothing
It's
Route::get('/in-nowdoc', [BookController::class, 'index']);
NOW;
Route::get('/nowdoc-one', [BookController::class, 'index']);
Route::get('/nowdoc-two', [BookController::class, 'index']);
$out = `ls /tmp/*`;
Route::get('/backtick', [BookController::class, 'index']);
$m = 'first line
second /* line
Route::get("/in-multiline", [BookController::class, "index"]);
third';
Route::get('/multiline', [BookController::class, 'index']);
$e = "ends in a backslash \
next"; Route::get('/backslash-one', [BookController::class, 'index']);
Route::get('/backslash-two', [BookController::class, 'index']);
// PHP stops here ?>
<p>Don't</p>
<?php
Route::get('/comment-html', [BookController::class, 'index']);
?>
<p>Don't</p>
<?php
Route::get('/html', [BookController::class, 'index']);
$j = "{$o->m("it's")}"; Route::get('/interp-one', [BookController::class, 'index']);
Route::get('/interp-two', [BookController::class, 'index']);
# PHP stops here too ?>
<p>Don't</p>
<?php
Route::get('/hash-html', [BookController::class, 'index']);
EOF
cat >"$site/app/Http/Controllers/Controller.php" <<'EOF'
<?php

namespace App\Http\Controllers;

abstract class Controller
{
}
EOF
cat >"$site/app/Http/Controllers/BookController.php" <<'EOF'
<?php

namespace App\Http\Controllers;

use App\Models\Book;

class BookController extends Controller
{
    public function index()
    {
        return view('books.index', ['books' => Book::all()]);
    }
}
EOF
cat >"$site/app/Models/Book.php" <<'EOF'
<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;

class Book extends Model
{
}
EOF
cat >"$site/resources/views/layouts/app.blade.php" <<'EOF'
<html>
<head><title>{{ config('app.name') }}</title></head>
<body>@yield('content')</body>
</html>
EOF
cat >"$site/resources/views/books/index.blade.php" <<'EOF'
@extends('layouts.app')

@section('content')
    @foreach ($books as $book)
        @include('books.row', ['book' => $book])
    @endforeach
@endsection
EOF
printf '<li>{{ $book->title }}</li>\n' >"$site/resources/views/books/row.blade.php"
printf '<h1>Welcome</h1>\n' >"$site/resources/views/welcome.blade.php"
mkdir -p "$site/resources/views/components"
printf '<div>{{ $slot }}</div>\n' >"$site/resources/views/components/alert.blade.php"
cat >"$site/resources/views/dashboard.blade.php" <<'EOF'
<x-alert type="ok">
    <x-slot name="title">T</x-slot>
</x-alert>
<x-missing />
{{-- <x-hidden /> --}}
EOF
cat >"$site/config/app.php" <<'EOF'
<?php

return [
    'name' => env('APP_NAME', 'Laravel'),
];
EOF
cat >"$site/database/migrations/2024_01_01_000000_create_books_table.php" <<'EOF'
<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('books', function (Blueprint $table) {
            $table->id();
        });
    }
};
EOF
printf 'periplus_version: 0\npacks:\n  - php_basic@0.1.0\n  - laravel_basic@0.0.5\n' \
    >"$site/.periplus/settings.yml"

moved="$work/moved"
mkdir -p "$moved/.periplus" "$moved/routing" "$moved/app/Http/Controllers" \
    "$moved/frontend/resources/views/books"
cp "$site/app/Http/Controllers/BookController.php" "$site/app/Http/Controllers/Controller.php" \
    "$moved/app/Http/Controllers/"
cp "$site/resources/views/books/index.blade.php" "$site/resources/views/books/row.blade.php" \
    "$moved/frontend/resources/views/books/"
cat >"$moved/routing/web.php" <<'EOF'
<?php

use App\Http\Controllers\BookController;
use Illuminate\Support\Facades\Route;

Route::get('/books', [BookController::class, 'index']);
EOF
printf 'periplus_version: 0\npacks:\n  - php_basic@0.1.0\n  - laravel_basic@0.0.5\nfolders:\n  routes: ./routing\n  views_root: ./frontend/resources/views\n' \
    >"$moved/.periplus/settings.yml"

nested="$work/nested"
mkdir -p "$nested/.periplus" "$nested/routes/admin"
printf "<?php\nRoute::get('/x', fn () => 1);\n" >"$nested/routes/web.php"
printf "<?php\nRoute::get('/x', fn () => 2);\n" >"$nested/routes/admin/web.php"
printf 'periplus_version: 0\npacks:\n  - php_basic@0.1.0\n  - laravel_basic@0.0.5\nfolders:\n  routes: ./routes/**\n' \
    >"$nested/.periplus/settings.yml"
(cd "$nested" && "$PERIPLUS" map --output "$work/nested.json" --format json >"$work/nested-report.json")

for run in one two; do
    (cd "$site" && "$PERIPLUS" map --output "$work/$run.json" --format json >"$work/$run-report.json")
    (cd "$moved" && "$PERIPLUS" map --output "$work/moved-$run.json" --format json \
        >"$work/moved-$run-report.json")
done
cmp "$work/one.json" "$work/two.json"
cmp "$work/moved-one.json" "$work/moved-two.json"

python3 - "$work" <<'PY'
import json
import os
import sys

work = sys.argv[1]
document = json.load(open(os.path.join(work, "one.json")))
report = json.load(open(os.path.join(work, "one-report.json")))
assert report["problems"] == [] and report["not_executed"] == [], report

ids = sorted(n["id"] for n in document["nodes"])
# php.type::...BookController is php_basic's own node for the controller class: the two packs
# coexist. The view() and Book::all() calls are php_basic's unresolved ends.
assert ids == [
    "laravel.config::app",
    "laravel.config_key::app",
    "laravel.config_key::app.name",
    "laravel.controller::App\\Http\\Controllers\\BookController",
    "laravel.controller::App\\Http\\Controllers\\Controller",
    "laravel.migration::2024_01_01_000000_create_books_table",
    "laravel.model::App\\Models\\Book",
    "laravel.route::api:GET /after-attr",
    "laravel.route::api:GET /attr",
    "laravel.route::api:GET /backslash-one",
    "laravel.route::api:GET /backslash-two",
    "laravel.route::api:GET /backtick",
    "laravel.route::api:GET /comment-html",
    "laravel.route::api:GET /glob/*",
    "laravel.route::api:GET /hash-html",
    "laravel.route::api:GET /heredoc-one",
    "laravel.route::api:GET /heredoc-two",
    "laravel.route::api:GET /html",
    "laravel.route::api:GET /interp-one",
    "laravel.route::api:GET /interp-two",
    "laravel.route::api:GET /last",
    "laravel.route::api:GET /multiline",
    "laravel.route::api:GET /nowdoc-one",
    "laravel.route::api:GET /nowdoc-two",
    "laravel.route::api:GET /trail",
    "laravel.route::web:GET /",
    "laravel.route::web:GET /books",
    "laravel.route::web:GET /q",
    "laravel.view::books.index",
    "laravel.view::books.row",
    "laravel.view::components.alert",
    "laravel.view::components.missing",
    "laravel.view::dashboard",
    "laravel.view::layouts.app",
    "laravel.view::welcome",
    "php.function::App\\Http\\Controllers\\view",
    "php.method::App\\Http\\Controllers\\BookController::index",
    "php.method::App\\Models\\Book::all",
    "php.type::App\\Http\\Controllers\\BookController",
    "php.type::App\\Http\\Controllers\\Controller",
    "php.type::App\\Models\\Book",
    "php.type::Illuminate\\Database\\Eloquent\\Model",
], ids

edges = sorted(
    (e["kind"], e["from"], e["to"], [(loc["file"], loc["line"]) for loc in e["locations"]])
    for e in document["edges"]
)
controller = "app/Http/Controllers/BookController.php"
# No route_renders edge: the closure route's view('welcome') is not stated. The controller's
# view('books.index') is a renders edge from its method.
assert edges == [
    ("calls", "php.method::App\\Http\\Controllers\\BookController::index",
     "php.function::App\\Http\\Controllers\\view", [(controller, 11)]),
    ("calls", "php.method::App\\Http\\Controllers\\BookController::index",
     "php.method::App\\Models\\Book::all", [(controller, 11)]),
    ("contains", "php.type::App\\Http\\Controllers\\BookController",
     "php.method::App\\Http\\Controllers\\BookController::index", [(controller, 9)]),
    ("extends_view", "laravel.view::books.index", "laravel.view::layouts.app",
     [("resources/views/books/index.blade.php", 1)]),
    ("handled_by", "laravel.route::api:GET /backslash-one",
     "php.method::App\\Http\\Controllers\\BookController::index", [("routes/api.php", 37)]),
    ("handled_by", "laravel.route::api:GET /backslash-two",
     "php.method::App\\Http\\Controllers\\BookController::index", [("routes/api.php", 38)]),
    ("handled_by", "laravel.route::api:GET /backtick",
     "php.method::App\\Http\\Controllers\\BookController::index", [("routes/api.php", 30)]),
    ("handled_by", "laravel.route::api:GET /comment-html",
     "php.method::App\\Http\\Controllers\\BookController::index", [("routes/api.php", 42)]),
    ("handled_by", "laravel.route::api:GET /glob/*",
     "php.method::App\\Http\\Controllers\\BookController::index", [("routes/api.php", 13)]),
    ("handled_by", "laravel.route::api:GET /hash-html",
     "php.method::App\\Http\\Controllers\\BookController::index", [("routes/api.php", 52)]),
    ("handled_by", "laravel.route::api:GET /heredoc-one",
     "php.method::App\\Http\\Controllers\\BookController::index", [("routes/api.php", 20)]),
    ("handled_by", "laravel.route::api:GET /heredoc-two",
     "php.method::App\\Http\\Controllers\\BookController::index", [("routes/api.php", 21)]),
    ("handled_by", "laravel.route::api:GET /html",
     "php.method::App\\Http\\Controllers\\BookController::index", [("routes/api.php", 46)]),
    ("handled_by", "laravel.route::api:GET /interp-one",
     "php.method::App\\Http\\Controllers\\BookController::index", [("routes/api.php", 47)]),
    ("handled_by", "laravel.route::api:GET /interp-two",
     "php.method::App\\Http\\Controllers\\BookController::index", [("routes/api.php", 48)]),
    ("handled_by", "laravel.route::api:GET /last",
     "php.method::App\\Http\\Controllers\\BookController::index", [("routes/api.php", 14)]),
    ("handled_by", "laravel.route::api:GET /multiline",
     "php.method::App\\Http\\Controllers\\BookController::index", [("routes/api.php", 35)]),
    ("handled_by", "laravel.route::api:GET /nowdoc-one",
     "php.method::App\\Http\\Controllers\\BookController::index", [("routes/api.php", 27)]),
    ("handled_by", "laravel.route::api:GET /nowdoc-two",
     "php.method::App\\Http\\Controllers\\BookController::index", [("routes/api.php", 28)]),
    ("handled_by", "laravel.route::api:GET /trail",
     "php.method::App\\Http\\Controllers\\BookController::index", [("routes/api.php", 12)]),
    ("handled_by", "laravel.route::web:GET /books",
     "php.method::App\\Http\\Controllers\\BookController::index", [("routes/web.php", 10)]),
    ("handled_by", "laravel.route::web:GET /q",
     "php.method::App\\Http\\Controllers\\BookController::index", [("routes/web.php", 11)]),
    ("implemented_by", "laravel.controller::App\\Http\\Controllers\\BookController",
     "php.type::App\\Http\\Controllers\\BookController", [(controller, 7)]),
    ("implemented_by", "laravel.controller::App\\Http\\Controllers\\Controller",
     "php.type::App\\Http\\Controllers\\Controller",
     [("app/Http/Controllers/Controller.php", 5)]),
    ("implemented_by", "laravel.model::App\\Models\\Book", "php.type::App\\Models\\Book",
     [("app/Models/Book.php", 7)]),
    ("includes_view", "laravel.view::books.index", "laravel.view::books.row",
     [("resources/views/books/index.blade.php", 5)]),
    ("inherits", "php.type::App\\Http\\Controllers\\BookController",
     "php.type::App\\Http\\Controllers\\Controller", [(controller, 7)]),
    ("inherits", "php.type::App\\Models\\Book", "php.type::Illuminate\\Database\\Eloquent\\Model",
     [("app/Models/Book.php", 7)]),
    ("key_of", "laravel.config_key::app", "laravel.config::app",
     [("config/app.php", 1), ("resources/views/layouts/app.blade.php", 2)]),
    ("key_of", "laravel.config_key::app.name", "laravel.config::app", [("config/app.php", 4)]),
    ("reads_config", "laravel.view::layouts.app", "laravel.config_key::app.name",
     [("resources/views/layouts/app.blade.php", 2)]),
    ("renders", "php.method::App\\Http\\Controllers\\BookController::index",
     "laravel.view::books.index", [(controller, 11)]),
    ("uses_component", "laravel.view::dashboard", "laravel.view::components.alert",
     [("resources/views/dashboard.blade.php", 1)]),
    ("uses_component", "laravel.view::dashboard", "laravel.view::components.missing",
     [("resources/views/dashboard.blade.php", 4)]),
], edges

states = {n["id"]: n["state"] for n in document["nodes"]}
assert states["php.method::App\\Http\\Controllers\\BookController::index"] == "mapped", states
assert states["laravel.view::components.missing"] == "unresolved", states

# The moved site: the route file in routing/ is named web, and views_root alone reads every
# template below it.
document = json.load(open(os.path.join(work, "moved-one.json")))
report = json.load(open(os.path.join(work, "moved-one-report.json")))
assert report["problems"] == [] and report["not_executed"] == [] and report["skipped"] == [], report
ids = sorted(
    n["id"] for n in document["nodes"] if n["id"].startswith("laravel.") and n["state"] == "mapped"
)
assert ids == [
    "laravel.controller::App\\Http\\Controllers\\BookController",
    "laravel.controller::App\\Http\\Controllers\\Controller",
    "laravel.route::web:GET /books",
    "laravel.view::books.index",
    "laravel.view::books.row",
], ids
edges = sorted(
    (e["kind"], e["from"], e["to"], [(loc["file"], loc["line"]) for loc in e["locations"]])
    for e in document["edges"] if e["kind"] in ("handled_by", "includes_view")
)
assert edges == [
    ("handled_by", "laravel.route::web:GET /books",
     "php.method::App\\Http\\Controllers\\BookController::index", [("routing/web.php", 6)]),
    ("includes_view", "laravel.view::books.index", "laravel.view::books.row",
     [("frontend/resources/views/books/index.blade.php", 5)]),
], edges

# The nested site: a route file is named by its path below routes, so one verb and URI in two files
# are two nodes.
document = json.load(open(os.path.join(work, "nested.json")))
report = json.load(open(os.path.join(work, "nested-report.json")))
assert report["problems"] == [] and report["not_executed"] == [], report
routes = sorted(
    (n["id"], [loc["file"] for loc in n["locations"]])
    for n in document["nodes"] if n["id"].startswith("laravel.route::")
)
assert routes == [
    ("laravel.route::admin/web:GET /x", ["routes/admin/web.php"]),
    ("laravel.route::web:GET /x", ["routes/web.php"]),
], routes
PY

# The fourth site: route groups, and a planted rutter whose two rules leave skipped rows.
groups="$work/groups"
mkdir -p "$groups/routes" "$groups/app/Http/Controllers" "$groups/.periplus/packs/probe@0.0.1/rules"
cp "$site/app/Http/Controllers/BookController.php" "$site/app/Http/Controllers/Controller.php" \
    "$groups/app/Http/Controllers/"
cat >"$groups/routes/web.php" <<'EOF'
<?php

use App\Http\Controllers\BookController;
use Illuminate\Support\Facades\Route;

Route::get('/home', [BookController::class, 'index'])->name('home');
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
    Route::get('/after-nested', [BookController::class, 'index'])->name('after');
});
Route::name('n.')
    ->prefix('n')
    ->group(function () {
        Route::post('/form', [BookController::class, 'index'])->name('form');
    });
Route::get('/outside', [BookController::class, 'index'])->name('outside');
probe nothing ;
probe both one ;
EOF
cat >"$groups/.periplus/packs/probe@0.0.1/pack.yaml" <<'YAML'
pack: probe
version: 0.0.1
depends: [laravel_basic]
YAML
cat >"$groups/.periplus/packs/probe@0.0.1/rules/probe.yaml" <<'YAML'
edge_kinds:
- {kind: probe_first, from: laravel.route, to: laravel.route}
- {kind: probe_second, from: laravel.route, to: laravel.route}
rules:
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
YAML
printf 'periplus_version: 0\npacks:\n  - php_basic@0.1.0\n  - laravel_basic@0.0.5\n  - probe@0.0.1\n' \
    >"$groups/.periplus/settings.yml"

# The fifth site: the first site's templates under templates/, with views_root set there.
viewsroot="$work/viewsroot"
mkdir -p "$viewsroot/.periplus" "$viewsroot/templates"
cp -r "$site/resources/views/." "$viewsroot/templates/"
printf 'periplus_version: 0\npacks:\n  - php_basic@0.1.0\n  - laravel_basic@0.0.5\nfolders:\n  views_root: ./templates\n' \
    >"$viewsroot/.periplus/settings.yml"
for run in one two; do
    (cd "$groups" && "$PERIPLUS" map --output "$work/groups-$run.json" --format json \
        >"$work/groups-$run-report.json")
    (cd "$viewsroot" && "$PERIPLUS" map --output "$work/viewsroot-$run.json" --format json \
        >"$work/viewsroot-$run-report.json")
done
cmp "$work/groups-one.json" "$work/groups-two.json"
cmp "$work/viewsroot-one.json" "$work/viewsroot-two.json"

# views_root holding ** is refused before any file is read, and the message names the folder.
printf 'periplus_version: 0\npacks:\n  - php_basic@0.1.0\n  - laravel_basic@0.0.5\nfolders:\n  views_root: ./templates/**\n' \
    >"$viewsroot/.periplus/settings.yml"
code=0
(cd "$viewsroot" && "$PERIPLUS" map --output "$work/deep.json" --format json >"$work/deep-report.json") \
    || code=$?
[ "$code" = 18 ] || { echo "views_root holding ** exited $code"; exit 1; }
[ ! -e "$work/deep.json" ] || { echo "views_root holding ** wrote a map"; exit 1; }
grep -q 'the folder views_root, which a path value is relative_to, holds \*\*' "$work/deep-report.json" \
    || { cat "$work/deep-report.json"; echo "the refusal does not name views_root"; exit 1; }

python3 - "$work" <<'PY'
import json
import os
import sys

work = sys.argv[1]
document = json.load(open(os.path.join(work, "groups-one.json")))
report = json.load(open(os.path.join(work, "groups-one-report.json")))
assert report["problems"] == [] and report["not_executed"] == [], report
routes = sorted(
    (n["id"], n.get("attributes", {}).get("name"), [loc["line"] for loc in n["locations"]])
    for n in document["nodes"] if n["id"].startswith("laravel.route::") and n["state"] == "mapped"
)
# Laravel joins prefixes with a slash and trims the slashes at each joint; name prefixes are
# written before the name as they are. The closure route's name is not read (a known gap).
assert routes == [
    ("laravel.route::web:GET /home", "home", [6]),
    ("laravel.route::web:GET /outside", "outside", [26]),
    ("laravel.route::web:GET admin/after-nested", "admin.after", [19]),
    ("laravel.route::web:GET admin/inside-if", None, [13]),
    ("laravel.route::web:GET admin/stats", "admin.stats", [8]),
    ("laravel.route::web:GET admin/v1", "admin.v1.root", [17]),
    ("laravel.route::web:GET admin/x", None, [9]),
    ("laravel.route::web:POST n/form", "n.form", [24]),
], routes
handled = sorted(
    (e["from"], [loc["line"] for loc in e["locations"]])
    for e in document["edges"] if e["kind"] == "handled_by"
)
assert handled == [
    ("laravel.route::web:GET /home", [6]),
    ("laravel.route::web:GET /outside", [26]),
    ("laravel.route::web:GET admin/after-nested", [19]),
    ("laravel.route::web:GET admin/inside-if", [13]),
    ("laravel.route::web:GET admin/stats", [8]),
    ("laravel.route::web:GET admin/v1", [17]),
    ("laravel.route::web:POST n/form", [24]),
], handled

rows = sorted((r["file"], r["line"], r["rule"], r["reason"]) for r in report["skipped"])
assert rows == [
    ("routes/web.php", 27, "probe_nothing", "edge probe_second: no value for capture b"),
    ("routes/web.php", 28, "probe_two", "edge probe_second: no value for capture c"),
], rows
probes = sorted((e["kind"], e["from"], e["to"]) for e in document["edges"] if e["kind"].startswith("probe"))
assert probes == [("probe_first", "laravel.route::both", "laravel.route::one")], probes

# The fifth site's views are the first site's, by id.
def views(name):
    nodes = json.load(open(os.path.join(work, name)))["nodes"]
    return sorted(n["id"] for n in nodes if n["type"] == "laravel.view" and n["state"] == "mapped")

assert views("viewsroot-one.json") == views("one.json") != [], (views("viewsroot-one.json"), views("one.json"))
PY

# The sixth site: view() and config() calls in a controller, and a planted route rutter.
calls="$work/calls"
mkdir -p "$calls/app/Http/Controllers" "$calls/resources/views/a" "$calls/config" "$calls/routes" \
    "$calls/resources/outside" "$calls/.periplus/packs/planted@0.0.1/rules"
printf '<p>b</p>\n' >"$calls/resources/views/a/b.blade.php"
printf "<p>{{ config('no.such.key') }}</p>\n" >"$calls/resources/views/a/c.blade.php"
printf "<p>{{ config('app.name') }}</p>\n" >"$calls/resources/outside/o.blade.php"
cp "$site/config/app.php" "$calls/config/"
cat >"$calls/app/Http/Controllers/PageController.php" <<'EOF'
<?php

namespace App\Http\Controllers;

class PageController
{
    public function show()
    {
        return view('a.b');
    }

    public function missing()
    {
        return view('no.such');
    }

    public function dynamic($name)
    {
        return view($name);
    }

    public function title()
    {
        return config('app.name');
    }

    public function setting($key)
    {
        return config($key);
    }

    public function later()
    {
        return function () {
            return view('a.b');
        };
    }

    public function unknown()
    {
        return config('no.such.key');
    }

    public function upper()
    {
        return View('a.b');
    }
}
EOF
cat >"$calls/routes/extra.php" <<'EOF'
<?php

use Illuminate\Support\Facades\Route;

Route::get('/one', [PageController::class, 'show']);
Route::post('/two', fn () => 1)->name('two');
Route::get($uri, fn () => 2);
Route::fake('/rejected');
// Route::get('/line', 1);
/* Route::get('/block', 1); */
$s = "Route::get('/string', 1)";
$h = <<<TXT
Route::get('/heredoc', 1);
TXT;
?>
<p>Route::get('/html', 1);</p>
<?php
Route::get('/last', 1);
Route::get('', fn () => 3);
EOF
cat >"$calls/.periplus/packs/planted@0.0.1/pack.yaml" <<'YAML'
pack: planted
version: 0.0.1
depends: [php_basic]
folders:
  planted_routes: ./routes
YAML
cat >"$calls/.periplus/packs/planted@0.0.1/rules/routes.yaml" <<'YAML'
node_types:
- {name: planted.route, id_namespace: planted.route}
rules:
- rule: planted_route
  reads: file
  in: [planted_routes]
  match:
    declaration: scoped_call_expression
    name_child: name
    filetype: php
    where: [{name_matches: 'get|post'}]
  id: {from: {argument: 0}}
  emits: [{node: {type: planted.route}}]
  confidence: declared
YAML
printf 'periplus_version: 0\npacks:\n  - php_basic@0.1.0\n  - laravel_basic@0.0.5\n  - planted@0.0.1\nfolders:\n  views: ./resources/**\n' \
    >"$calls/.periplus/settings.yml"
(cd "$calls" && "$PERIPLUS" map --output "$work/calls.json" --format json >"$work/calls-report.json")

python3 - "$work" <<'PY'
import json
import os
import sys

work = sys.argv[1]
document = json.load(open(os.path.join(work, "calls.json")))
report = json.load(open(os.path.join(work, "calls-report.json")))
assert report["problems"] == [] and report["not_executed"] == [], report
page = "app/Http/Controllers/PageController.php"
missing_key, outside = "resources/views/a/c.blade.php", "resources/outside/o.blade.php"
method = "php.method::App\\Http\\Controllers\\PageController::"
edges = sorted(
    (e["kind"], e["from"], e["to"], [(loc["file"], loc["line"]) for loc in e["locations"]])
    for e in document["edges"] if e["kind"] in ("renders", "reads_config")
)
# The closure's view() call counts the method around it.
assert edges == [
    ("reads_config", "laravel.view::a.c", "laravel.config_key::no.such.key", [(missing_key, 1)]),
    ("reads_config", method + "title", "laravel.config_key::app.name", [(page, 24)]),
    ("reads_config", method + "unknown", "laravel.config_key::no.such.key", [(page, 41)]),
    ("renders", method + "later", "laravel.view::a.b", [(page, 35)]),
    ("renders", method + "missing", "laravel.view::no.such", [(page, 14)]),
    ("renders", method + "show", "laravel.view::a.b", [(page, 9)]),
    ("renders", method + "upper", "laravel.view::a.b", [(page, 46)]),
], edges
nodes = {n["id"]: n for n in document["nodes"]}
assert nodes["laravel.view::a.b"]["state"] == "mapped", nodes["laravel.view::a.b"]
missing = nodes["laravel.view::no.such"]
assert missing["state"] == "unresolved", missing
assert missing["unresolved_detail"]["searched_for"] == "no.such", missing
assert missing["unresolved_detail"]["types_tried"] == ["laravel.view"], missing
assert nodes["laravel.config_key::app.name"]["state"] == "mapped", nodes
# config/app.php declares app.name. no.such.key, read from PHP and from Blade, is one node,
# unresolved by the PHP read; the missing file no is marked only from Blade, by a key_of edge from
# the key no. A template outside views_root gives no reads_config edge and no row, but its key_of
# edge from the key app is made and both Blade config rules count its fire.
assert nodes["laravel.config_key::no.such.key"]["state"] == "unresolved", nodes
assert nodes["laravel.config::no"]["state"] == "unresolved", nodes["laravel.config::no"]
key_of = sorted(
    (e["from"], e["to"], [(loc["file"], loc["line"]) for loc in e["locations"]])
    for e in document["edges"] if e["kind"] == "key_of"
)
assert key_of == [
    ("laravel.config_key::app", "laravel.config::app", [("config/app.php", 1), (outside, 1)]),
    ("laravel.config_key::app.name", "laravel.config::app", [("config/app.php", 4)]),
    ("laravel.config_key::no", "laravel.config::no", [(missing_key, 1)]),
], key_of
fires = {r["rule"]: r["fires"] for r in report["executed"]}
assert fires["config_read_in_view"] == fires["config_key_in_file"] == 2, fires
assert not [r for r in report["skipped"] if r["file"] == outside], report["skipped"]
rows = sorted(
    (r["file"], r["line"], r["rule"], r["reason"])
    for r in report["skipped"] if r["rule"] in ("view_call", "config_call", "planted_route")
)
assert rows == [
    (page, 19, "view_call", "argument 0 is not a text literal"),
    (page, 29, "config_call", "argument 0 is not a text literal"),
    ("routes/extra.php", 7, "planted_route", "argument 0 is not a text literal"),
    ("routes/extra.php", 19, "planted_route", "argument 0 is empty"),
], rows
routes = sorted(
    (n["id"], [(loc["file"], loc["line"]) for loc in n["locations"]])
    for n in document["nodes"] if n["type"] == "planted.route"
)
assert routes == [
    ("planted.route::/last", [("routes/extra.php", 18)]),
    ("planted.route::/one", [("routes/extra.php", 5)]),
    ("planted.route::/two", [("routes/extra.php", 6)]),
], routes
PY

# The seventh site: config keys and reads. config/keys.php returns keys five deep and one shape
# of each kind that gives no node; config/oldstyle.php returns old array( ) syntax; config/api.php
# is named like a route file. A controller and a template each read an existing key, a missing
# key, a key of a missing file and a whole file.
configs="$work/configs"
mkdir -p "$configs/.periplus" "$configs/config" "$configs/app/Http/Controllers" \
    "$configs/resources/views"
cat >"$configs/config/keys.php" <<'EOF'
<?php

use Illuminate\Support\Facades\Facade;

$above = ['host' => 1];
$rows = [['above' => 1]];

return [
    // 'line_comment' => 1,
    /* 'block_comment' => 2, */
    # 'hash_comment' => 3,
    'name' => 'text with \'fake\' => 1 and "quoted" => 2',
    'one' => [
        'two' => [
            'three' => [
                'four' => [
                    'five' => 5,
                ],
            ],
        ],
        'sibling' => true,
    ],
    'list' => ['a', 'b'],
    'maps' => [['inlist' => 1], ['inlist2' => 2]],
    1 => 'numeric',
    SOME_CONSTANT => 'x',
    'aliases' => Facade::defaultAliases()->merge(['Activity' => 1])->toArray(),
    'env' => env('X', ['incall' => 2]),
    'closure' => function () { return ['inclosure' => 1]; },
    'body' => function () { $a = ['inbody' => 1]; return $a; },
    'arrow' => fn () => ['inarrow' => 1],
    'match' => fn ($v) => match ($v) { 'inmatch' => 1, default => 2 },
    'old' => array('inold' => 1),
    'dotted.key' => 1,
    'parent.dot' => ['child' => 1],
    "double" => ["inner" => 1],
    'tight'=>['a'=>1,'b'=>['c'=>2]],
    'same' => ['same' => 1],
    'plus' => ['p' => 1] + ['z' => 1],
    'doc' => <<<TXT
        'inheredoc' => 1
        TXT,
    'shell' => `echo 'tick' => 1`,
    'dq' => "x 'dqfake' => 1",
    'interp' => "{$o->m("it's")} 'ifake' => 1",
    Foo::class => ['cls' => 1],
    "{$p}_x" => 1,
    'it\'s' => ['esc' => 1],
// a comment line, then a key at the start of the next line
'start' => ['under' => 1],
    'after' => 'last',
];
EOF
cat >"$configs/config/oldstyle.php" <<'EOF'
<?php

return array(
    'a' => 1,
    'b' => array('c' => 2),
);
EOF
cat >"$configs/config/api.php" <<'EOF'
<?php

return [
    'default_item_count' => 100,
    'nested' => ['x' => 1],
    'list' => [['inlist' => 1]],
    'old' => array('inold' => 1),
    'match' => fn ($v) => match ($v) { 'inmatch' => 1 },
    FOO . '_bar' => 1,
    'driver' => ['da' => 'x'][env('M')],
];
$above = ['host' => 1];
EOF
# Keys that end in a text literal but are not one, arrays indexed at once, and comments near a key.
cat >"$configs/config/shapes.php" <<'EOF'
<?php

return [
    FOO . '_bar' => 1,
    'a' . 'b' => 1,
    self::X . 'y' => 1,
    $c ? 'tern' : 'ary' => 1,
    'pre' . 'x' => ['k' => 1],
    FOO .
        'nl' => 1,
    'driver' => ['da' => 'x', 'db' => 'y'][env('MODE')],
    'outer' => ['inner' => ['ia' => 1]['ia'], 'kept' => 1],
    'deep' => ['d1' => ['d2' => ['d3' => 1]]][env('M')],
    'deeper' => ['e1' => ['e2' => ['e3' => ['e4' => 1]]]][env('M')],
    'strbr' => ['sa' => ']'][env('M')],
    'endc' => 1, // trailing note
'afterend' => ['ae' => 1],
    /* c */'tightc' => ['tc' => 1],
    'midc' /* c */ => ['mc' => 1],
    'arrc' => /* c */ ['ac' => 1],
    'last' => 1, # trailing note
'afterhash' => 1,
];
EOF
cat >"$configs/config/picked.php" <<'EOF'
<?php

return ['pa' => 1, 'pb' => ['pc' => 2]][env('PICK', 'pa')];
EOF
cat >"$configs/config/console.php" <<'EOF'
<?php

return ['ca' => 1][env('C')];
EOF
cat >"$configs/config/branch.php" <<'EOF'
<?php

if (env('X')) return ['early' => 1];

return [
    'main' => 1,
];
EOF
cat >"$configs/app/Http/Controllers/ReadController.php" <<'EOF'
<?php

namespace App\Http\Controllers;

class ReadController
{
    public function reads()
    {
        $a = config('keys.one.two');
        $b = config('keys.nosuch');
        $c = config('nofile.key');
        $d = config('keys');
        $e = config('api.nested.x');
        return config('keys.name') . config('keys.name');
    }

    public function runtime()
    {
        config(['keys.runtime' => 1]);
        config()->set('keys.set', 2);
        return config('keys.runtime');
    }
}
EOF
cat >"$configs/resources/views/reads.blade.php" <<'EOF'
{{ config('keys.one.two.three') }}
{{ config('keys.bladenosuch') }}
{{ config('bladefile.key') }}
{{ config('keys') }}
EOF
printf 'periplus_version: 0\npacks:\n  - php_basic@0.1.0\n  - laravel_basic@0.0.5\n' \
    >"$configs/.periplus/settings.yml"
for run in one two; do
    (cd "$configs" && "$PERIPLUS" map --output "$work/configs-$run.json" --format json \
        >"$work/configs-$run-report.json")
done
cmp "$work/configs-one.json" "$work/configs-two.json"

python3 - "$work" <<'PY'
import json
import os
import sys

work = sys.argv[1]
document = json.load(open(os.path.join(work, "configs-one.json")))
report = json.load(open(os.path.join(work, "configs-one-report.json")))
assert report["problems"] == [] and report["not_executed"] == [], report
nodes = {n["id"]: n for n in document["nodes"]}
keys_php, api_php, old_php = "config/keys.php", "config/api.php", "config/oldstyle.php"
shapes_php, branch_php = "config/shapes.php", "config/branch.php"
# Each text key of the returned array, at every depth, and a key per file named by the file. No
# node for a key in a comment, a string, a heredoc or a backtick string, a key that is not a text
# literal, a list entry or a key below one, an array assigned above or after the return, in a
# call's argument, returned by a closure or an arrow function, in a match, in old array( ) syntax,
# after + or below a key holding a dot, a key holding a dot, or a key at the start of a line after
# a comment and the keys below it. No node for a key written after . ? or :, FOO . '_bar', nor for
# the keys of an array indexed at once, as the returned array or a key's value: driver is a
# scalar. Nor for a key after a comment with no space, a key with a comment before its =>, or the
# keys of an array after => and a comment. Three false results stay, as the gaps block states:
# deeper.e1 and below, in an indexed array that holds arrays three deep; strbr.sa, in an indexed
# array that holds a ] in a string; and branch.early, returned on one branch only.
declared = sorted(
    (n["id"], [(loc["file"], loc["line"]) for loc in n["locations"]])
    for n in document["nodes"] if n["type"] == "laravel.config_key" and n["state"] == "mapped"
)
assert declared == [
    ("laravel.config_key::api", [(api_php, 1)]),
    ("laravel.config_key::api.default_item_count", [(api_php, 4)]),
    ("laravel.config_key::api.driver", [(api_php, 10)]),
    ("laravel.config_key::api.list", [(api_php, 6)]),
    ("laravel.config_key::api.match", [(api_php, 8)]),
    ("laravel.config_key::api.nested", [(api_php, 5)]),
    ("laravel.config_key::api.nested.x", [(api_php, 5)]),
    ("laravel.config_key::api.old", [(api_php, 7)]),
    ("laravel.config_key::branch", [(branch_php, 1)]),
    ("laravel.config_key::branch.early", [(branch_php, 3)]),
    ("laravel.config_key::branch.main", [(branch_php, 6)]),
    ("laravel.config_key::console", [("config/console.php", 1)]),
    ("laravel.config_key::keys", [(keys_php, 1)]),
    ("laravel.config_key::keys.after", [(keys_php, 51)]),
    ("laravel.config_key::keys.aliases", [(keys_php, 27)]),
    ("laravel.config_key::keys.arrow", [(keys_php, 31)]),
    ("laravel.config_key::keys.body", [(keys_php, 30)]),
    ("laravel.config_key::keys.closure", [(keys_php, 29)]),
    ("laravel.config_key::keys.doc", [(keys_php, 40)]),
    ("laravel.config_key::keys.double", [(keys_php, 36)]),
    ("laravel.config_key::keys.double.inner", [(keys_php, 36)]),
    ("laravel.config_key::keys.dq", [(keys_php, 44)]),
    ("laravel.config_key::keys.env", [(keys_php, 28)]),
    ("laravel.config_key::keys.interp", [(keys_php, 45)]),
    ("laravel.config_key::keys.list", [(keys_php, 23)]),
    ("laravel.config_key::keys.maps", [(keys_php, 24)]),
    ("laravel.config_key::keys.match", [(keys_php, 32)]),
    ("laravel.config_key::keys.name", [(keys_php, 12)]),
    ("laravel.config_key::keys.old", [(keys_php, 33)]),
    ("laravel.config_key::keys.one", [(keys_php, 13)]),
    ("laravel.config_key::keys.one.sibling", [(keys_php, 21)]),
    ("laravel.config_key::keys.one.two", [(keys_php, 14)]),
    ("laravel.config_key::keys.one.two.three", [(keys_php, 15)]),
    ("laravel.config_key::keys.one.two.three.four", [(keys_php, 16)]),
    ("laravel.config_key::keys.one.two.three.four.five", [(keys_php, 17)]),
    ("laravel.config_key::keys.plus", [(keys_php, 39)]),
    ("laravel.config_key::keys.plus.p", [(keys_php, 39)]),
    ("laravel.config_key::keys.same", [(keys_php, 38)]),
    ("laravel.config_key::keys.same.same", [(keys_php, 38)]),
    ("laravel.config_key::keys.shell", [(keys_php, 43)]),
    ("laravel.config_key::keys.tight", [(keys_php, 37)]),
    ("laravel.config_key::keys.tight.a", [(keys_php, 37)]),
    ("laravel.config_key::keys.tight.b", [(keys_php, 37)]),
    ("laravel.config_key::keys.tight.b.c", [(keys_php, 37)]),
    ("laravel.config_key::oldstyle", [(old_php, 1)]),
    ("laravel.config_key::picked", [("config/picked.php", 1)]),
    ("laravel.config_key::shapes", [(shapes_php, 1)]),
    ("laravel.config_key::shapes.arrc", [(shapes_php, 20)]),
    ("laravel.config_key::shapes.deep", [(shapes_php, 13)]),
    ("laravel.config_key::shapes.deeper", [(shapes_php, 14)]),
    ("laravel.config_key::shapes.deeper.e1", [(shapes_php, 14)]),
    ("laravel.config_key::shapes.deeper.e1.e2", [(shapes_php, 14)]),
    ("laravel.config_key::shapes.deeper.e1.e2.e3", [(shapes_php, 14)]),
    ("laravel.config_key::shapes.deeper.e1.e2.e3.e4", [(shapes_php, 14)]),
    ("laravel.config_key::shapes.driver", [(shapes_php, 11)]),
    ("laravel.config_key::shapes.endc", [(shapes_php, 16)]),
    ("laravel.config_key::shapes.last", [(shapes_php, 21)]),
    ("laravel.config_key::shapes.outer", [(shapes_php, 12)]),
    ("laravel.config_key::shapes.outer.inner", [(shapes_php, 12)]),
    ("laravel.config_key::shapes.outer.kept", [(shapes_php, 12)]),
    ("laravel.config_key::shapes.strbr", [(shapes_php, 15)]),
    ("laravel.config_key::shapes.strbr.sa", [(shapes_php, 15)]),
], declared
# Each mapped key has one key_of edge to its file, from the line that declares it.
key_of = sorted(
    (e["from"], e["to"], [(loc["file"], loc["line"]) for loc in e["locations"]])
    for e in document["edges"] if e["kind"] == "key_of"
)
expected = [
    (key, "laravel.config::" + key.split("::")[1].split(".")[0], lines) for key, lines in declared
]
blade = "resources/views/reads.blade.php"
# A Blade read adds its line to the key_of edge of the key named by the file, keys, and no key_of
# edge for the key it reads: keys.bladenosuch, which keys.php does not declare, has none. A read
# of the missing file bladefile gives the key bladefile a key_of edge to it.
expected = sorted(
    [
        (key, file, lines + [(blade, 1), (blade, 2), (blade, 4)] if key.endswith("::keys") else lines)
        for key, file, lines in expected
    ]
    + [("laravel.config_key::bladefile", "laravel.config::bladefile", [(blade, 3)])]
)
assert key_of == expected, key_of
assert nodes["laravel.config_key::bladefile"]["state"] == "referenced", nodes["laravel.config_key::bladefile"]
for name in ("api", "keys", "oldstyle"):
    assert nodes["laravel.config::" + name]["state"] == "mapped", nodes["laravel.config::" + name]
assert nodes["laravel.config::bladefile"]["state"] == "unresolved", nodes["laravel.config::bladefile"]

# The reads: from PHP, a missing key or file is unresolved and a whole file ends on its key; from
# Blade, a missing key or file is referenced. Two identical calls on one line are one location.
controller = "app/Http/Controllers/ReadController.php"
method = "php.method::App\\Http\\Controllers\\ReadController::"
reads = sorted(
    (e["from"], e["to"], nodes[e["to"]]["state"], [(loc["file"], loc["line"]) for loc in e["locations"]])
    for e in document["edges"] if e["kind"] == "reads_config"
)
assert reads == [
    ("laravel.view::reads", "laravel.config_key::bladefile.key", "referenced", [(blade, 3)]),
    ("laravel.view::reads", "laravel.config_key::keys", "mapped", [(blade, 4)]),
    ("laravel.view::reads", "laravel.config_key::keys.bladenosuch", "referenced", [(blade, 2)]),
    ("laravel.view::reads", "laravel.config_key::keys.one.two.three", "mapped", [(blade, 1)]),
    (method + "reads", "laravel.config_key::api.nested.x", "mapped", [(controller, 13)]),
    (method + "reads", "laravel.config_key::keys", "mapped", [(controller, 12)]),
    (method + "reads", "laravel.config_key::keys.name", "mapped", [(controller, 14)]),
    (method + "reads", "laravel.config_key::keys.nosuch", "unresolved", [(controller, 10)]),
    (method + "reads", "laravel.config_key::keys.one.two", "mapped", [(controller, 9)]),
    (method + "reads", "laravel.config_key::nofile.key", "unresolved", [(controller, 11)]),
    (method + "runtime", "laravel.config_key::keys.runtime", "unresolved", [(controller, 21)]),
], reads
for key in ("keys.nosuch", "nofile.key", "keys.runtime"):
    detail = nodes["laravel.config_key::" + key]["unresolved_detail"]
    assert detail["searched_for"] == key and detail["types_tried"] == ["laravel.config_key"], detail
# A key set at run time is not declared: config([...]) and config()->set(...) give no edge.
rows = sorted(
    (r["file"], r["line"], r["rule"], r["reason"])
    for r in report["skipped"] if r["rule"] == "config_call"
)
assert rows == [
    (controller, 19, "config_call", "argument 0 is not a text literal"),
    (controller, 20, "config_call", "argument 0 is missing"),
], rows
PY
echo "laravel pack ok"
