#!/usr/bin/env bash
# The bundled advancedqueue_basic pack, pinned beside drupal_basic@0.3.0. In the module's
# src/Plugin/AdvancedQueue/JobType folder, a class with the AdvancedQueueJobType attribute and one
# with the AdvancedQueueJobType annotation each make the job type named by its id, joined to its
# class by plugin_class; both end at the same node type. An attribute whose id is not a text
# literal makes no job type and is listed under skipped; a constant declared by expression gets its
# own reason. The map and the report are byte-identical
# across two runs, the report but for the map path it names.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
module="$site/web/modules/custom/mymodule"
jobs="$module/src/Plugin/AdvancedQueue/JobType"
mkdir -p "$site/.periplus" "$jobs"
printf 'name: My module\ntype: module\ncore_version_requirement: ^10\n' >"$module/mymodule.info.yml"
cat >"$jobs/MyJob.php" <<'EOF'
<?php

namespace Drupal\mymodule\Plugin\AdvancedQueue\JobType;

use Drupal\advancedqueue\Attribute\AdvancedQueueJobType;
use Drupal\advancedqueue\Plugin\AdvancedQueue\JobType\JobTypeBase;
use Drupal\Core\StringTranslation\TranslatableMarkup;

#[AdvancedQueueJobType(
  id: 'my_job',
  label: new TranslatableMarkup('My job'),
)]
class MyJob extends JobTypeBase {
}
EOF
cat >"$jobs/OldJob.php" <<'EOF'
<?php

namespace Drupal\mymodule\Plugin\AdvancedQueue\JobType;

use Drupal\advancedqueue\Plugin\AdvancedQueue\JobType\JobTypeBase;

/**
 * @AdvancedQueueJobType(
 *   id = "my_old_job",
 *   label = @Translation("My old job"),
 * )
 */
class OldJob extends JobTypeBase {
}
EOF
cat >"$jobs/ComputedJob.php" <<'EOF'
<?php

namespace Drupal\mymodule\Plugin\AdvancedQueue\JobType;

use Drupal\advancedqueue\Attribute\AdvancedQueueJobType;
use Drupal\advancedqueue\Plugin\AdvancedQueue\JobType\JobTypeBase;

#[AdvancedQueueJobType(
  id: self::ID,
)]
class ComputedJob extends JobTypeBase {
  const ID = 'comp' . 'uted';
}
EOF
printf 'periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n  - advancedqueue_basic@0.0.1\n' \
    >"$site/.periplus/settings.yml"

for run in one two; do
    (cd "$site" && "$PERIPLUS" map --output "$work/$run.json" --format json >"$work/$run-report.json")
done
cmp "$work/one.json" "$work/two.json"

python3 - "$work" "$site" <<'PY'
import json
import os
import sys

work, site = sys.argv[1], sys.argv[2]
folder = "web/modules/custom/mymodule/src/Plugin/AdvancedQueue/JobType"
my_job, old_job, computed = (f"{folder}/{name}.php" for name in ("MyJob", "OldJob", "ComputedJob"))
cls = "php.type::Drupal\\mymodule\\Plugin\\AdvancedQueue\\JobType\\"
base = "php.type::Drupal\\advancedqueue\\Plugin\\AdvancedQueue\\JobType\\JobTypeBase"


def load(name):
    return json.load(open(os.path.join(work, name)))


def line(path, text):
    written = open(os.path.join(site, path)).read().splitlines()
    return next(n for n, found in enumerate(written, 1) if found.strip().lstrip("* ") == text)


document, report, again = load("one.json"), load("one-report.json"), load("two-report.json")
assert {**report, "map": ""} == {**again, "map": ""}
assert report["problems"] == [] and report["not_executed"] == [], report

nodes = {n["id"]: (n["type"], n["state"]) for n in document["nodes"]}
assert nodes == {
    "drupal.module::mymodule": ("drupal.module", "mapped"),
    "drupal.plugin.advancedqueue_job_type::my_job": ("drupal.queue_job_type", "mapped"),
    "drupal.plugin.advancedqueue_job_type::my_old_job": ("drupal.queue_job_type", "mapped"),
    cls + "ComputedJob": ("php.class", "mapped"),
    cls + "MyJob": ("php.class", "mapped"),
    cls + "OldJob": ("php.class", "mapped"),
    base: ("php.class_like", "referenced"),
}, nodes

edges = sorted(
    (e["kind"], e["from"], e["to"], [(loc["file"], loc["line"]) for loc in e["locations"]])
    for e in document["edges"]
)
assert edges == sorted([
    ("plugin_class", "drupal.plugin.advancedqueue_job_type::my_job", cls + "MyJob",
     [(my_job, line(my_job, "#[AdvancedQueueJobType("))]),
    ("plugin_class", "drupal.plugin.advancedqueue_job_type::my_old_job", cls + "OldJob",
     [(old_job, line(old_job, "@AdvancedQueueJobType("))]),
    ("inherits", cls + "MyJob", base, [(my_job, line(my_job, "class MyJob extends JobTypeBase {"))]),
    ("inherits", cls + "OldJob", base,
     [(old_job, line(old_job, "class OldJob extends JobTypeBase {"))]),
    ("inherits", cls + "ComputedJob", base,
     [(computed, line(computed, "class ComputedJob extends JobTypeBase {"))]),
]), edges

skipped = sorted((row["file"], row["line"], row["rule"], row["reason"]) for row in report["skipped"])
assert skipped == [
    (computed, line(computed, "#[AdvancedQueueJobType("), "queue_job_type_from_attribute",
     "argument id is a class constant with no declared text"),
], skipped
PY
echo "advancedqueue pack ok"
