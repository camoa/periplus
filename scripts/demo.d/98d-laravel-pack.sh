#!/usr/bin/env bash
# The bundled Laravel pack, on one site. The project root is a Laravel application's root in the
# default layout: a web route file with one closure route and two controller routes, one naming its
# class in full, a base controller and a controller whose method returns a view, a model, Blade
# views (one extends a layout and includes a partial, one uses components), a config file and a
# migration. Its settings pin php_basic@0.2.0 and laravel_basic@0.0.5 and move no folder. The map
# exits 0 with no problems and nothing not executed, and holds exactly the route, view, controller,
# model, config and migration nodes, the handled_by edge from each controller route to its method,
# the Blade extends and include edges, the uses_component edges (<x-slot> and {{-- --}} tags give
# none), and php_basic's own class and method nodes beside them. The controller's view('books.index')
# is a renders edge from its method; the closure route's view('welcome') gives none.
# An api.php route file is planted with routes inside a //, /* */ or # comment or a quoted string
# (no node), and routes after #[Pure], a trailing comment, '/glob/*', a heredoc, a nowdoc, a
# backtick string, a multi-line string, a string ending in a backslash, inline HTML and a {$...}
# interpolation (all mapped).
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
printf 'periplus_version: 0\npacks:\n  - php_basic@0.2.0\n  - laravel_basic@0.0.5\n' \
    >"$site/.periplus/settings.yml"

(cd "$site" && "$PERIPLUS" map --output "$work/one.json" --format json >"$work/one-report.json")

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
PY
echo "laravel pack ok"
