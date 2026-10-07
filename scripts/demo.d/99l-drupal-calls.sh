#!/usr/bin/env bash
# Drupal calls that name a service or an entity type by a text literal. A planted module declares
# the service my_module.helper and the content entity type thing, and calls them from a controller.
# \Drupal::service gives uses_service to the mapped service for a declared name and to a
# referenced service for an undeclared one; a variable argument gives a skipped row; Other::service
# gives nothing. \Drupal::entityQuery gives uses_entity_type at declared. getStorage on an object
# ending in entityTypeManager, with or without a call and through ?->, gives uses_entity_type at
# inferred; on another object it gives nothing; a variable argument gives a skipped row.
# \Drupal::entityTypeManager() gives uses_service to entity_type.manager at inferred. get on an
# object written $container, $this->container or \Drupal::getContainer() gives uses_service at
# inferred; get on config, a request, a form state, another object or Drush's container gives
# nothing, as does get on $containerBuilder; a variable argument gives a skipped row. In a
# procedural function of my_module.module, the edge starts at the php.function node.
# periplus validate accepts drupal_basic.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
site="$work/site"
module="$site/web/modules/custom/my_module"
mkdir -p "$site/.periplus" "$module/src/Entity" "$module/src/Controller" "$module/src/Form"
printf 'periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n' >"$site/.periplus/settings.yml"
cat >"$module/my_module.services.yml" <<'EOF'
services:
  my_module.helper:
    class: Drupal\my_module\Helper
EOF
cat >"$module/src/Entity/Thing.php" <<'EOF'
<?php

namespace Drupal\my_module\Entity;

use Drupal\Core\Entity\Attribute\ContentEntityType;
use Drupal\Core\Entity\ContentEntityBase;

#[ContentEntityType(id: 'thing', label: 'Thing')]
class Thing extends ContentEntityBase {
}
EOF
main="$module/src/Controller/ThingController.php"
cat >"$main" <<'EOF'
<?php

namespace Drupal\my_module\Controller;

class ThingController {

  public function services($name) {
    $helper = \Drupal::service('my_module.helper');
    $path = \Drupal::service('path.current');
    $other = \Drupal::service($name);
    $not = Other::service('my_module.other');
  }

  public function entities($type) {
    $query = \Drupal::entityQuery('thing');
    $mine = $this->entityTypeManager->getStorage('thing');
    $nodes = \Drupal::entityTypeManager()->getStorage('node');
    $safe = $this->entityTypeManager?->getStorage('safe_thing');
    $bar = $this->other->getStorage('bar');
    $any = $this->entityTypeManager->getStorage($type);
  }

}
EOF
form="$module/src/Form/ThingForm.php"
cat >"$form" <<'EOF'
<?php

namespace Drupal\my_module\Form;

use Symfony\Component\DependencyInjection\ContainerInterface;

class ThingForm {

  public static function create(ContainerInterface $container) {
    $helper = $container->get('my_module.helper');
    $manager = $container->get('entity_type.manager');
    $any = $container->get($name);
  }

  public function setUp() {
    $path = $this->container->get('path.current');
    $global = \Drupal::getContainer()->get('my_module.helper');
  }

  public function negatives($request, $form_state, $other) {
    $a = $this->config->get('my_module.settings');
    $b = $request->get('page');
    $c = $form_state->get('step');
    $d = $other->get('my_module.helper');
    $e = Drush::getContainer()->get('drush.helper');
    $e2 = $containerBuilder->get('my_module.helper');
  }

}
EOF
procedural="$module/my_module.module"
cat >"$procedural" <<'EOF'
<?php

function helper_lookup() {
  $s = \Drupal::getContainer()->get('my_module.helper');
}
EOF
(cd "$site" && "$PERIPLUS" validate drupal_basic >/dev/null)
(cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json")
python3 - "$work/map.json" "$work/report.json" "$main" "$form" "$procedural" <<'PY'
import json
import sys

document, report = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
lines = open(sys.argv[3]).read().splitlines()
form_lines = open(sys.argv[4]).read().splitlines()
procedural_lines = open(sys.argv[5]).read().splitlines()
assert report["not_executed"] == [] and report["problems"] == [], report


def line(text, lines=lines):
    return next(n for n, written in enumerate(lines, 1) if written.strip() == text)


def form_line(text):
    return line(text, form_lines)


nodes = {n["id"]: n for n in document["nodes"]}
services = "php.method::Drupal\\my_module\\Controller\\ThingController::services"
entities = "php.method::Drupal\\my_module\\Controller\\ThingController::entities"
create = "php.method::Drupal\\my_module\\Form\\ThingForm::create"
set_up = "php.method::Drupal\\my_module\\Form\\ThingForm::setUp"
helper_lookup = "php.function::helper_lookup"
found = {
    (e["kind"], e["from"], e["to"], place["line"])
    for e in document["edges"]
    if e["kind"] in ("uses_service", "uses_entity_type")
    for place in e["locations"]
}
expected = {
    ("uses_service", services, "drupal.service::my_module.helper",
     line("$helper = \\Drupal::service('my_module.helper');")),
    ("uses_service", services, "drupal.service::path.current",
     line("$path = \\Drupal::service('path.current');")),
    ("uses_entity_type", entities, "drupal.entity_type::thing",
     line("$query = \\Drupal::entityQuery('thing');")),
    ("uses_entity_type", entities, "drupal.entity_type::thing",
     line("$mine = $this->entityTypeManager->getStorage('thing');")),
    ("uses_entity_type", entities, "drupal.entity_type::node",
     line("$nodes = \\Drupal::entityTypeManager()->getStorage('node');")),
    ("uses_service", entities, "drupal.service::entity_type.manager",
     line("$nodes = \\Drupal::entityTypeManager()->getStorage('node');")),
    ("uses_entity_type", entities, "drupal.entity_type::safe_thing",
     line("$safe = $this->entityTypeManager?->getStorage('safe_thing');")),
    ("uses_service", create, "drupal.service::my_module.helper",
     form_line("$helper = $container->get('my_module.helper');")),
    ("uses_service", create, "drupal.service::entity_type.manager",
     form_line("$manager = $container->get('entity_type.manager');")),
    ("uses_service", set_up, "drupal.service::path.current",
     form_line("$path = $this->container->get('path.current');")),
    ("uses_service", set_up, "drupal.service::my_module.helper",
     form_line("$global = \\Drupal::getContainer()->get('my_module.helper');")),
    ("uses_service", helper_lookup, "drupal.service::my_module.helper",
     line("$s = \\Drupal::getContainer()->get('my_module.helper');", procedural_lines)),
}
assert found == expected, sorted(found ^ expected)
confidence = {
    (e["to"], p["rule"], p["confidence"])
    for e in document["edges"]
    if e["kind"] in ("uses_service", "uses_entity_type")
    for p in e["provenance"]
}
assert confidence == {
    ("drupal.service::my_module.helper", "service_call", "declared"),
    ("drupal.service::path.current", "service_call", "declared"),
    ("drupal.entity_type::thing", "entity_query_call", "declared"),
    ("drupal.entity_type::thing", "storage_call", "inferred"),
    ("drupal.entity_type::node", "storage_call", "inferred"),
    ("drupal.entity_type::safe_thing", "storage_nullsafe_call", "inferred"),
    ("drupal.service::my_module.helper", "container_get_call", "inferred"),
    ("drupal.service::entity_type.manager", "container_get_call", "inferred"),
    ("drupal.service::path.current", "container_get_call", "inferred"),
    ("drupal.service::entity_type.manager", "drupal_shortcut_call", "inferred"),
}, sorted(confidence)
assert nodes["drupal.service::my_module.helper"]["state"] == "mapped", nodes
assert nodes["drupal.service::path.current"]["state"] == "referenced", nodes
assert nodes["drupal.service::entity_type.manager"]["state"] == "referenced", nodes
assert nodes["drupal.entity_type::thing"]["type"] == "drupal.content_entity_type", nodes
assert nodes["drupal.entity_type::node"]["state"] == "referenced", nodes
skipped = sorted(
    (row["rule"], row["line"])
    for row in report["skipped"]
    if row["rule"] in ("service_call", "entity_query_call", "storage_call", "container_get_call")
)
assert skipped == sorted([
    ("service_call", line("$other = \\Drupal::service($name);")),
    ("storage_call", line("$any = $this->entityTypeManager->getStorage($type);")),
    ("container_get_call", form_line("$any = $container->get($name);")),
]), skipped
assert nodes[helper_lookup]["type"] == "php.function", nodes[helper_lookup]
print("drupal calls: eight service uses, four entity type uses, three skipped, none for other receivers")
PY
echo "drupal calls ok"
