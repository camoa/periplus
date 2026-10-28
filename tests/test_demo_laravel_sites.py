"""The bundled Laravel pack on small planted sites: folders, route groups, calls and config keys.

These cover the sites the Laravel demo script used to check. Each test plants the files it needs
under ``tmp_path`` and maps in-process.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from test_demo_a_support import map_project, mapped, nodes, pin, plant, rutter

from periplus.errors import ExitCode
from periplus.map import MapReport

LARAVEL = ("php_basic@0.2.0", "laravel_basic@0.0.5")
BOOKS = "app/Http/Controllers/BookController.php"
INDEX = "App\\Http\\Controllers\\BookController::index"

CONTROLLER_BASE = r'''<?php

namespace App\Http\Controllers;

abstract class Controller
{
}
'''

BOOK_CONTROLLER = r'''<?php

namespace App\Http\Controllers;

use App\Models\Book;

class BookController extends Controller
{
    public function index()
    {
        return view('books.index', ['books' => Book::all()]);
    }
}
'''

INDEX_VIEW = r'''@extends('layouts.app')

@section('content')
    @foreach ($books as $book)
        @include('books.row', ['book' => $book])
    @endforeach
@endsection
'''

GROUP_ROUTES = r'''<?php

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
'''

PAGE_CONTROLLER = r'''<?php

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
'''

EXTRA_ROUTES = r'''<?php

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
'''

KEYS_PHP = r'''<?php

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
'''

API_PHP = r'''<?php

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
'''

SHAPES_PHP = r'''<?php

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
'''

READ_CONTROLLER = r'''<?php

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
'''

READS_VIEW = r'''{{ config('keys.one.two.three') }}
{{ config('keys.bladenosuch') }}
{{ config('bladefile.key') }}
{{ config('keys') }}
'''

PROBE_RULES = r'''edge_kinds:
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
'''

PLANTED_RULES = r'''node_types:
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
'''

DECLARED_KEYS = [
    ("laravel.config_key::api", "config/api.php", 1),
    ("laravel.config_key::api.default_item_count", "config/api.php", 4),
    ("laravel.config_key::api.driver", "config/api.php", 10),
    ("laravel.config_key::api.list", "config/api.php", 6),
    ("laravel.config_key::api.match", "config/api.php", 8),
    ("laravel.config_key::api.nested", "config/api.php", 5),
    ("laravel.config_key::api.nested.x", "config/api.php", 5),
    ("laravel.config_key::api.old", "config/api.php", 7),
    ("laravel.config_key::keys", "config/keys.php", 1),
    ("laravel.config_key::keys.after", "config/keys.php", 51),
    ("laravel.config_key::keys.aliases", "config/keys.php", 27),
    ("laravel.config_key::keys.arrow", "config/keys.php", 31),
    ("laravel.config_key::keys.body", "config/keys.php", 30),
    ("laravel.config_key::keys.closure", "config/keys.php", 29),
    ("laravel.config_key::keys.doc", "config/keys.php", 40),
    ("laravel.config_key::keys.double", "config/keys.php", 36),
    ("laravel.config_key::keys.double.inner", "config/keys.php", 36),
    ("laravel.config_key::keys.dq", "config/keys.php", 44),
    ("laravel.config_key::keys.env", "config/keys.php", 28),
    ("laravel.config_key::keys.interp", "config/keys.php", 45),
    ("laravel.config_key::keys.list", "config/keys.php", 23),
    ("laravel.config_key::keys.maps", "config/keys.php", 24),
    ("laravel.config_key::keys.match", "config/keys.php", 32),
    ("laravel.config_key::keys.name", "config/keys.php", 12),
    ("laravel.config_key::keys.old", "config/keys.php", 33),
    ("laravel.config_key::keys.one", "config/keys.php", 13),
    ("laravel.config_key::keys.one.sibling", "config/keys.php", 21),
    ("laravel.config_key::keys.one.two", "config/keys.php", 14),
    ("laravel.config_key::keys.one.two.three", "config/keys.php", 15),
    ("laravel.config_key::keys.one.two.three.four", "config/keys.php", 16),
    ("laravel.config_key::keys.one.two.three.four.five", "config/keys.php", 17),
    ("laravel.config_key::keys.plus", "config/keys.php", 39),
    ("laravel.config_key::keys.plus.p", "config/keys.php", 39),
    ("laravel.config_key::keys.same", "config/keys.php", 38),
    ("laravel.config_key::keys.same.same", "config/keys.php", 38),
    ("laravel.config_key::keys.shell", "config/keys.php", 43),
    ("laravel.config_key::keys.tight", "config/keys.php", 37),
    ("laravel.config_key::keys.tight.a", "config/keys.php", 37),
    ("laravel.config_key::keys.tight.b", "config/keys.php", 37),
    ("laravel.config_key::keys.tight.b.c", "config/keys.php", 37),
    ("laravel.config_key::shapes", "config/shapes.php", 1),
    ("laravel.config_key::shapes.arrc", "config/shapes.php", 20),
    ("laravel.config_key::shapes.deep", "config/shapes.php", 13),
    ("laravel.config_key::shapes.deeper", "config/shapes.php", 14),
    ("laravel.config_key::shapes.deeper.e1", "config/shapes.php", 14),
    ("laravel.config_key::shapes.deeper.e1.e2", "config/shapes.php", 14),
    ("laravel.config_key::shapes.deeper.e1.e2.e3", "config/shapes.php", 14),
    ("laravel.config_key::shapes.deeper.e1.e2.e3.e4", "config/shapes.php", 14),
    ("laravel.config_key::shapes.driver", "config/shapes.php", 11),
    ("laravel.config_key::shapes.endc", "config/shapes.php", 16),
    ("laravel.config_key::shapes.last", "config/shapes.php", 21),
    ("laravel.config_key::shapes.outer", "config/shapes.php", 12),
    ("laravel.config_key::shapes.outer.inner", "config/shapes.php", 12),
    ("laravel.config_key::shapes.outer.kept", "config/shapes.php", 12),
    ("laravel.config_key::shapes.strbr", "config/shapes.php", 15),
    ("laravel.config_key::shapes.strbr.sa", "config/shapes.php", 15),
]

ROW_VIEW = "<li>{{ $book->title }}</li>\n"
CONTROLLERS = {
    "app/Http/Controllers/Controller.php": CONTROLLER_BASE,
    BOOKS: BOOK_CONTROLLER,
}


def _settings(root: Path, folders: str = "", *packs: str) -> None:
    """Pin the Laravel packs (and any more) and set the given ``folders:`` lines."""
    pin(root, *LARAVEL, *packs)
    if folders:
        path = root / ".periplus" / "settings.yml"
        path.write_text(path.read_text() + "folders:\n" + folders)


def _located(
    document: dict[str, Any], *kinds: str
) -> list[tuple[str, str, str, list[tuple[str, int]]]]:
    return sorted(
        (e["kind"], e["from"], e["to"], [(loc["file"], loc["line"]) for loc in e["locations"]])
        for e in document["edges"]
        if e["kind"] in kinds
    )


def _skipped(report: MapReport, *rules: str) -> list[tuple[str, int, str, str]]:
    return sorted(row for row in report.skipped if row[2] in rules)


# --- folders: routes and views_root move on their own ---------------------------------------


def test_routes_and_views_root_set_in_settings_move_the_folders_they_read(tmp_path: Path) -> None:
    plant(tmp_path, CONTROLLERS)
    plant(tmp_path, {
        "routing/web.php": "<?php\n\nuse App\\Http\\Controllers\\BookController;\n"
        "use Illuminate\\Support\\Facades\\Route;\n\n"
        "Route::get('/books', [BookController::class, 'index']);\n",
        "frontend/resources/views/books/index.blade.php": INDEX_VIEW,
        "frontend/resources/views/books/row.blade.php": ROW_VIEW,
    })
    _settings(
        tmp_path, "  routes: ./routing\n  views_root: ./frontend/resources/views\n"
    )
    report, document = map_project(tmp_path)
    assert report.problems == () and report.not_executed == () and report.skipped == ()
    assert _located(document, "handled_by", "includes_view") == [
        ("handled_by", "laravel.route::web:GET /books", "php.method::" + INDEX,
         [("routing/web.php", 6)]),
        ("includes_view", "laravel.view::books.index", "laravel.view::books.row",
         [("frontend/resources/views/books/index.blade.php", 5)]),
    ]


def test_a_route_file_is_named_by_its_path_below_routes(tmp_path: Path) -> None:
    plant(tmp_path, {
        "routes/web.php": "<?php\nRoute::get('/x', fn () => 1);\n",
        "routes/admin/web.php": "<?php\nRoute::get('/x', fn () => 2);\n",
    })
    _settings(tmp_path, "  routes: ./routes/**\n")
    document = mapped(tmp_path)
    routes = sorted(
        (n["id"], [loc["file"] for loc in n["locations"]])
        for n in document["nodes"]
        if n["id"].startswith("laravel.route::")
    )
    assert routes == [
        ("laravel.route::admin/web:GET /x", ["routes/admin/web.php"]),
        ("laravel.route::web:GET /x", ["routes/web.php"]),
    ]


def _views(folder: str) -> dict[str, str]:
    return {
        f"{folder}/layouts/app.blade.php": "<body>@yield('content')</body>\n",
        f"{folder}/books/index.blade.php": INDEX_VIEW,
        f"{folder}/books/row.blade.php": ROW_VIEW,
        f"{folder}/welcome.blade.php": "<h1>Welcome</h1>\n",
    }


def test_views_root_alone_gives_the_same_view_ids_as_the_default_folder(tmp_path: Path) -> None:
    default, moved = tmp_path / "default", tmp_path / "moved"
    plant(default, _views("resources/views"))
    _settings(default)
    plant(moved, _views("templates"))
    _settings(moved, "  views_root: ./templates\n")

    def views(root: Path) -> list[str]:
        return sorted(
            n["id"]
            for n in mapped(root)["nodes"]
            if n["type"] == "laravel.view" and n["state"] == "mapped"
        )

    assert views(moved) == views(default) != []


def test_views_root_holding_a_double_star_is_refused_naming_the_folder(tmp_path: Path) -> None:
    plant(tmp_path, _views("templates"))
    _settings(tmp_path, "  views_root: ./templates/**\n")
    report, _ = map_project(tmp_path)
    assert report.exit_code == ExitCode.FOLDER_UNRESOLVED
    assert any("views_root" in problem.message for problem in report.problems), report.problems
    assert report.map_path is None
    assert not (tmp_path / "map.json").exists()


# --- route groups ---------------------------------------------------------------------------


def _groups(root: Path, *packs: str) -> None:
    plant(root, CONTROLLERS)
    plant(root, {"routes/web.php": GROUP_ROUTES})
    _settings(root, "", *packs)


def test_route_groups_join_prefixes_and_names_and_keep_each_routes_line(tmp_path: Path) -> None:
    _groups(tmp_path)
    document = mapped(tmp_path)
    routes = sorted(
        (n["id"], n.get("attributes", {}).get("name"), [loc["line"] for loc in n["locations"]])
        for n in document["nodes"]
        if n["id"].startswith("laravel.route::") and n["state"] == "mapped"
    )
    # Slashes are trimmed at each joint; a closure route's name is not read (a known gap).
    assert routes == [
        ("laravel.route::web:GET /home", "home", [6]),
        ("laravel.route::web:GET /outside", "outside", [26]),
        ("laravel.route::web:GET admin/after-nested", "admin.after", [19]),
        ("laravel.route::web:GET admin/inside-if", None, [13]),
        ("laravel.route::web:GET admin/stats", "admin.stats", [8]),
        ("laravel.route::web:GET admin/v1", "admin.v1.root", [17]),
        ("laravel.route::web:GET admin/x", None, [9]),
        ("laravel.route::web:POST n/form", "n.form", [24]),
    ]
    handled = sorted(
        (e["from"], [loc["line"] for loc in e["locations"]])
        for e in document["edges"]
        if e["kind"] == "handled_by"
    )
    assert handled == [
        (route, lines) for route, name, lines in routes if route != "laravel.route::web:GET admin/x"
    ]


def test_a_text_rule_that_makes_nothing_or_lacks_a_capture_leaves_a_skipped_row(
    tmp_path: Path,
) -> None:
    _groups(tmp_path, "probe@0.0.1")
    rutter(
        tmp_path, "probe", "pack: probe\nversion: 0.0.1\ndepends: [laravel_basic]\n",
        {"probe.yaml": PROBE_RULES},
    )
    report, document = map_project(tmp_path)
    assert report.problems == () and report.not_executed == ()
    assert _skipped(report, "probe_nothing", "probe_two") == [
        ("routes/web.php", 27, "probe_nothing", "edge probe_second: no value for capture b"),
        ("routes/web.php", 28, "probe_two", "edge probe_second: no value for capture c"),
    ]
    probes = [
        (e["kind"], e["from"], e["to"])
        for e in document["edges"]
        if e["kind"].startswith("probe")
    ]
    assert probes == [("probe_first", "laravel.route::both", "laravel.route::one")]


# --- view() and config() calls, and a planted route rutter ----------------------------------

PAGE = "app/Http/Controllers/PageController.php"
METHOD = "php.method::App\\Http\\Controllers\\PageController::"
MISSING_KEY = "resources/views/a/c.blade.php"
OUTSIDE = "resources/outside/o.blade.php"


@pytest.fixture(scope="module")
def calls(tmp_path_factory: pytest.TempPathFactory) -> tuple[MapReport, dict[str, Any]]:
    root = tmp_path_factory.mktemp("calls")
    plant(root, {
        PAGE: PAGE_CONTROLLER,
        "resources/views/a/b.blade.php": "<p>b</p>\n",
        MISSING_KEY: "<p>{{ config('no.such.key') }}</p>\n",
        OUTSIDE: "<p>{{ config('app.name') }}</p>\n",
        "config/app.php": "<?php\n\nreturn [\n    'name' => env('APP_NAME', 'Laravel'),\n];\n",
        "routes/extra.php": EXTRA_ROUTES,
    })
    rutter(
        root, "planted",
        "pack: planted\nversion: 0.0.1\ndepends: [php_basic]\nfolders:\n"
        "  planted_routes: ./routes\n",
        {"routes.yaml": PLANTED_RULES},
    )
    _settings(root, "  views: ./resources/**\n", "planted@0.0.1")
    report, document = map_project(root)
    assert report.problems == () and report.not_executed == (), report
    return report, document


def test_view_and_config_calls_in_methods_give_renders_and_reads_config_edges(
    calls: tuple[MapReport, dict[str, Any]],
) -> None:
    _, document = calls
    # The closure's view() call counts the method around it; View('a.b') is the same call.
    assert _located(document, "renders", "reads_config") == [
        ("reads_config", "laravel.view::a.c", "laravel.config_key::no.such.key",
         [(MISSING_KEY, 1)]),
        ("reads_config", METHOD + "title", "laravel.config_key::app.name", [(PAGE, 24)]),
        ("reads_config", METHOD + "unknown", "laravel.config_key::no.such.key", [(PAGE, 41)]),
        ("renders", METHOD + "later", "laravel.view::a.b", [(PAGE, 35)]),
        ("renders", METHOD + "missing", "laravel.view::no.such", [(PAGE, 14)]),
        ("renders", METHOD + "show", "laravel.view::a.b", [(PAGE, 9)]),
        ("renders", METHOD + "upper", "laravel.view::a.b", [(PAGE, 46)]),
    ]


def test_a_view_or_config_key_that_nothing_declares_is_unresolved_with_what_was_searched(
    calls: tuple[MapReport, dict[str, Any]],
) -> None:
    _, document = calls
    found = nodes(document)
    assert found["laravel.view::a.b"]["state"] == "mapped"
    assert found["laravel.config_key::app.name"]["state"] == "mapped"
    missing = found["laravel.view::no.such"]
    assert missing["state"] == "unresolved"
    assert missing["unresolved_detail"]["searched_for"] == "no.such"
    assert missing["unresolved_detail"]["types_tried"] == ["laravel.view"]
    assert found["laravel.config_key::no.such.key"]["state"] == "unresolved"
    assert found["laravel.config::no"]["state"] == "unresolved"


def test_a_template_outside_views_root_gives_its_key_edge_but_no_read_edge_or_row(
    calls: tuple[MapReport, dict[str, Any]],
) -> None:
    report, document = calls
    assert _located(document, "key_of") == [
        ("key_of", "laravel.config_key::app", "laravel.config::app",
         [("config/app.php", 1), (OUTSIDE, 1)]),
        ("key_of", "laravel.config_key::app.name", "laravel.config::app", [("config/app.php", 4)]),
        ("key_of", "laravel.config_key::no", "laravel.config::no", [(MISSING_KEY, 1)]),
    ]
    assert not [row for row in report.skipped if row[0] == OUTSIDE]
    assert not [e for e in document["edges"] if e["kind"] == "reads_config" and
                OUTSIDE in [loc["file"] for loc in e["locations"]]]


def test_a_variable_argument_to_view_or_config_leaves_a_skipped_row(
    calls: tuple[MapReport, dict[str, Any]],
) -> None:
    report, _ = calls
    assert _skipped(report, "view_call", "config_call") == [
        (PAGE, 19, "view_call", "argument 0 is not a text literal"),
        (PAGE, 29, "config_call", "argument 0 is not a text literal"),
    ]


def test_a_planted_declaration_rule_makes_one_node_per_real_route_call(
    calls: tuple[MapReport, dict[str, Any]],
) -> None:
    report, document = calls
    routes = sorted(
        (n["id"], [(loc["file"], loc["line"]) for loc in n["locations"]])
        for n in document["nodes"]
        if n["type"] == "planted.route"
    )
    # Nothing for a route in a comment, a string, a heredoc or inline HTML, or for Route::fake.
    assert routes == [
        ("planted.route::/last", [("routes/extra.php", 18)]),
        ("planted.route::/one", [("routes/extra.php", 5)]),
        ("planted.route::/two", [("routes/extra.php", 6)]),
    ]
    assert _skipped(report, "planted_route") == [
        ("routes/extra.php", 7, "planted_route", "argument 0 is not a text literal"),
        ("routes/extra.php", 19, "planted_route", "argument 0 is empty"),
    ]


# --- config keys ----------------------------------------------------------------------------

READS = "resources/views/reads.blade.php"
READER = "app/Http/Controllers/ReadController.php"
READ_METHOD = "php.method::App\\Http\\Controllers\\ReadController::"


@pytest.fixture(scope="module")
def configs(tmp_path_factory: pytest.TempPathFactory) -> tuple[MapReport, dict[str, Any]]:
    root = tmp_path_factory.mktemp("configs")
    plant(root, {
        "config/keys.php": KEYS_PHP,
        "config/api.php": API_PHP,
        "config/shapes.php": SHAPES_PHP,
        READER: READ_CONTROLLER,
        READS: READS_VIEW,
    })
    _settings(root)
    report, document = map_project(root)
    assert report.problems == () and report.not_executed == (), report
    return report, document


def test_each_text_key_of_the_returned_array_is_a_node_and_the_shapes_that_are_not_give_none(
    configs: tuple[MapReport, dict[str, Any]],
) -> None:
    _, document = configs
    ours = {"api", "keys", "shapes"}
    declared = sorted(
        (n["id"], n["locations"][0]["file"], n["locations"][0]["line"])
        for n in document["nodes"]
        if n["type"] == "laravel.config_key"
        and n["state"] == "mapped"
        and n["id"].split("::")[1].split(".")[0] in ours
    )
    # Absent on purpose: keys in comments, strings, heredocs, closures, match arms, old array(),
    # lists, after . ? : or +, or dotted. Two false results stay: shapes.deeper.e1 and below, and
    # shapes.strbr.sa, are made though they should not be.
    assert declared == sorted(DECLARED_KEYS)


def test_every_mapped_key_has_a_key_edge_to_the_file_it_is_declared_in(
    configs: tuple[MapReport, dict[str, Any]],
) -> None:
    _, document = configs
    edges = {(e["from"], e["to"]) for e in document["edges"] if e["kind"] == "key_of"}
    for key, _file, _line in DECLARED_KEYS:
        assert (key, "laravel.config::" + key.split("::")[1].split(".")[0]) in edges, key
    assert (
        "laravel.config_key::bladefile", "laravel.config::bladefile"
    ) in edges


def test_reads_of_a_present_missing_or_whole_config_end_where_the_gaps_state_puts_them(
    configs: tuple[MapReport, dict[str, Any]],
) -> None:
    _, document = configs
    found = nodes(document)
    reads = sorted(
        (e["from"], e["to"], found[e["to"]]["state"],
         [(loc["file"], loc["line"]) for loc in e["locations"]])
        for e in document["edges"]
        if e["kind"] == "reads_config"
    )
    assert reads == [
        ("laravel.view::reads", "laravel.config_key::bladefile.key", "referenced", [(READS, 3)]),
        ("laravel.view::reads", "laravel.config_key::keys", "mapped", [(READS, 4)]),
        ("laravel.view::reads", "laravel.config_key::keys.bladenosuch", "referenced",
         [(READS, 2)]),
        ("laravel.view::reads", "laravel.config_key::keys.one.two.three", "mapped", [(READS, 1)]),
        (READ_METHOD + "reads", "laravel.config_key::api.nested.x", "mapped", [(READER, 13)]),
        (READ_METHOD + "reads", "laravel.config_key::keys", "mapped", [(READER, 12)]),
        (READ_METHOD + "reads", "laravel.config_key::keys.name", "mapped", [(READER, 14)]),
        (READ_METHOD + "reads", "laravel.config_key::keys.nosuch", "unresolved", [(READER, 10)]),
        (READ_METHOD + "reads", "laravel.config_key::keys.one.two", "mapped", [(READER, 9)]),
        (READ_METHOD + "reads", "laravel.config_key::nofile.key", "unresolved", [(READER, 11)]),
        (READ_METHOD + "runtime", "laravel.config_key::keys.runtime", "unresolved",
         [(READER, 21)]),
    ]
    assert found["laravel.config::bladefile"]["state"] == "unresolved"
    for key in ("keys.nosuch", "nofile.key", "keys.runtime"):
        detail = found["laravel.config_key::" + key]["unresolved_detail"]
        assert detail["searched_for"] == key
        assert detail["types_tried"] == ["laravel.config_key"]


def test_a_config_key_set_at_run_time_is_not_declared_and_leaves_a_skipped_row(
    configs: tuple[MapReport, dict[str, Any]],
) -> None:
    report, _ = configs
    assert _skipped(report, "config_call") == [
        (READER, 19, "config_call", "argument 0 is not a text literal"),
        (READER, 20, "config_call", "argument 0 is missing"),
    ]
