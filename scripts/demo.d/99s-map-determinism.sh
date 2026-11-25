#!/usr/bin/env bash
# The map and its inputs record are the same bytes under two hash seeds and two locales. A hash
# seed and a locale differ only between processes, so each map is a run of its own. The project
# has many nodes and edges of one kind, so a set iterated in place of a sorted list orders them one
# way under one seed and another under the next. C and C.UTF-8 are on a plain machine; a missing
# one fails the run.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
export PERIPLUS_CONFIG_DIR="$work/userconf"
mkdir "$PERIPLUS_CONFIG_DIR"
site="$work/site"
mkdir -p "$site/.periplus" "$site/src/Service" "$site/src/Web"
printf 'periplus_version: 0\npacks:\n  - php_basic@0.2.0\n' >"$site/.periplus/settings.yml"
python="$(head -1 "$(command -v "$PERIPLUS")" | sed 's/^#!//')"

for pair in Alpha:one Beta:two Gamma:three Delta:four; do
    printf '<?php\n\nnamespace App\\Service;\n\nclass %s\n{\n    public function %s() {}\n}\n' \
        "${pair%%:*}" "${pair#*:}" >"$site/src/Service/${pair%%:*}.php"
done
cat >"$site/src/Web/Page.php" <<'PHP'
<?php

namespace App\Web;

use App\Service\Alpha;
use App\Service\Beta;
use App\Service\Gamma;
use App\Service\Delta;

class Base
{
    public function boot() {}
}

class Page extends Base
{
    private Alpha $alpha;

    private Beta $beta;

    private Gamma $gamma;

    public function __construct(private Delta $delta)
    {
    }

    public function run(): void
    {
        $this->alpha->one();
        $this->beta->two();
        $this->gamma->three();
        $this->delta->four();
        $this->boot();
    }
}
PHP

for loc in C C.UTF-8; do
    LC_ALL="$loc" "$python" -c 'import locale; locale.setlocale(locale.LC_ALL, "")' \
        || { echo "the locale $loc is not installed"; exit 1; }
done

for run in 0:C 2:C 0:C.UTF-8 2:C.UTF-8; do
    seed="${run%%:*}" loc="${run#*:}"
    (cd "$site" && PYTHONHASHSEED="$seed" LC_ALL="$loc" "$PERIPLUS" map \
        --output "$work/map-$seed-$loc.json" >"$work/report-$seed-$loc.txt") \
        || { echo "map failed under seed $seed, locale $loc"; cat "$work/report-$seed-$loc.txt"; exit 1; }
done

methods="$(grep -o '"php.method::[^"]*"' "$work/map-0-C.json" | sort -u | wc -l)"
[ "$methods" -ge 6 ] || { echo "the map holds $methods methods, expected at least 6"; exit 1; }
for other in 2-C 0-C.UTF-8 2-C.UTF-8; do
    cmp "$work/map-0-C.json" "$work/map-$other.json" \
        || { echo "the map under $other differs from the map under 0-C"; exit 1; }
    cmp "$work/map-0-C.inputs.json" "$work/map-$other.inputs.json" \
        || { echo "the inputs record under $other differs from the one under 0-C"; exit 1; }
done
echo "map determinism ok"
