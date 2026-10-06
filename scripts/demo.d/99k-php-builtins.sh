#!/usr/bin/env bash
# PHP builtins: php_basic lists the functions PHP reports as internal under calls_function's
# skip_names. A planted project calls json_decode, count, strlen and in_array inside a namespace,
# beside a call to a function it declares: the map holds no function node for any of the four, and
# the declared function keeps its calls edge. periplus validate accepts php_basic.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
site="$work/site"
mkdir -p "$site/.periplus" "$site/src"
printf 'periplus_version: 0\npacks:\n  - php_basic@0.2.0\n' >"$site/.periplus/settings.yml"
cat >"$site/src/Main.php" <<'EOF'
<?php

namespace App;

function own()
{
}

function caller($text, $list)
{
    $data = json_decode($text);
    $n = count($list);
    $len = strlen($text);
    $has = in_array('x', $list);
    own();
}
EOF
(cd "$site" && "$PERIPLUS" validate php_basic >/dev/null)
(cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json")
python3 - "$work/map.json" "$work/report.json" <<'PY'
import json
import sys

document, report = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
assert report["not_executed"] == [] and report["problems"] == [], report
builtins = ("json_decode", "count", "strlen", "in_array")
functions = sorted(n["id"] for n in document["nodes"] if n["type"] == "php.function")
assert functions == ["php.function::App\\caller", "php.function::App\\own"], functions
calls = sorted((e["from"], e["to"]) for e in document["edges"] if e["kind"] == "calls")
assert calls == [("php.function::App\\caller", "php.function::App\\own")], calls
assert not [s for s in report["skipped"] if s.get("rule") == "calls_function"], report["skipped"]
print(f"php builtins: no node for {', '.join(builtins)}; own() keeps its edge")
PY
echo "php builtins ok"
