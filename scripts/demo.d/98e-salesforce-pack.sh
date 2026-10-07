#!/usr/bin/env bash
# The bundled salesforce_basic pack, pinned beside drupal_basic@0.3.0. A mapping's config file
# makes its config node a salesforce.mapping with its Salesforce object and its two standalone
# flags, a maps_bundle edge to <drupal_entity_type>.<drupal_bundle>, a maps_entity_type edge, and a
# maps_field edge to the one field instance its dependencies list; the bundle config it also lists
# gives no maps_field edge. A class in the module's src/Plugin/SalesforceMappingField folder with a
# Plugin annotation makes the mapping field named by its id, joined to its class by plugin_class.
# A subscriber that keys SalesforceEvents::X, by => or by $events[...][] =, subscribes to the
# event named by the constant, which stays referenced; the constant used as a value makes nothing.
# The map and the report are byte-identical across two runs, the report but for the map path it
# names.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
module="$site/web/modules/custom/mymodule"
mkdir -p "$site/.periplus" "$site/config/sync" "$module/src/Plugin/SalesforceMappingField" \
    "$module/src/EventSubscriber"
printf 'name: My module\ntype: module\ncore_version_requirement: ^10\n' >"$module/mymodule.info.yml"
cat >"$site/config/sync/salesforce_mapping.salesforce_mapping.my_mapping.yml" <<'EOF'
dependencies:
  config:
    - field.field.node.my_type.field_my_field
    - node.type.my_type
id: my_mapping
label: My mapping
salesforce_object_type: Contact
drupal_entity_type: node
drupal_bundle: my_type
push_standalone: false
pull_standalone: true
EOF
cat >"$module/src/Plugin/SalesforceMappingField/MyField.php" <<'EOF'
<?php

namespace Drupal\mymodule\Plugin\SalesforceMappingField;

use Drupal\salesforce_mapping\SalesforceMappingFieldPluginBase;

/**
 * @Plugin(
 *   id = "my_field",
 *   label = @Translation("My field"),
 * )
 */
class MyField extends SalesforceMappingFieldPluginBase {
}
EOF
cat >"$module/src/EventSubscriber/MySubscriber.php" <<'EOF'
<?php

namespace Drupal\mymodule\EventSubscriber;

use Drupal\salesforce\Event\SalesforceEvents;
use Symfony\Component\EventDispatcher\EventSubscriberInterface;

class MySubscriber implements EventSubscriberInterface {

  public static function getSubscribedEvents(): array {
    $events[SalesforceEvents::PUSH_PARAMS][] = 'pushParams';
    return $events + [
      SalesforceEvents::PULL_PRESAVE => 'pullPresave',
    ];
  }

  public function check(): bool {
    return isset($this->seen[SalesforceEvents::PUSH_FAIL]);
  }

}
EOF
printf 'periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n  - salesforce_basic@0.0.1\n' \
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
config = "config/sync/salesforce_mapping.salesforce_mapping.my_mapping.yml"
field = "web/modules/custom/mymodule/src/Plugin/SalesforceMappingField/MyField.php"
subscriber = "web/modules/custom/mymodule/src/EventSubscriber/MySubscriber.php"
mapping = "drupal.config::salesforce_mapping.salesforce_mapping.my_mapping"
instance = "drupal.config::field.field.node.my_type.field_my_field"
field_class = "php.type::Drupal\\mymodule\\Plugin\\SalesforceMappingField\\MyField"
sub_class = "php.type::Drupal\\mymodule\\EventSubscriber\\MySubscriber"
sub_method = "php.method::Drupal\\mymodule\\EventSubscriber\\MySubscriber::"
field_base = "php.type::Drupal\\salesforce_mapping\\SalesforceMappingFieldPluginBase"
interface = "php.type::Symfony\\Component\\EventDispatcher\\EventSubscriberInterface"


def load(name):
    return json.load(open(os.path.join(work, name)))


def line(path, text):
    written = open(os.path.join(site, path)).read().splitlines()
    return next(n for n, found in enumerate(written, 1) if found.strip().lstrip("*- ") == text)


document, report, again = load("one.json"), load("one-report.json"), load("two-report.json")
assert {**report, "map": ""} == {**again, "map": ""}
assert report["problems"] == [] and report["not_executed"] == [], report
assert report["skipped"] == [], report["skipped"]

nodes = {n["id"]: (n["type"], n["state"]) for n in document["nodes"]}
assert nodes == {
    "drupal.bundle::node.my_type": ("drupal.bundle", "referenced"),
    instance: ("drupal.field_instance", "referenced"),
    "drupal.config::node.type.my_type": ("drupal.config_object", "referenced"),
    mapping: ("salesforce.mapping", "mapped"),
    "drupal.entity_type::node": ("drupal.entity_type", "referenced"),
    "drupal.module::mymodule": ("drupal.module", "mapped"),
    "drupal.plugin.salesforce_mapping_field::my_field": (
        "drupal.salesforce_mapping_field", "mapped"),
    sub_method + "check": ("php.method", "mapped"),
    sub_method + "getSubscribedEvents": ("php.method", "mapped"),
    sub_class: ("php.class", "mapped"),
    field_class: ("php.class", "mapped"),
    field_base: ("php.class_like", "referenced"),
    interface: ("php.interface", "referenced"),
    "salesforce.event::SalesforceEvents::PULL_PRESAVE": ("salesforce.event", "referenced"),
    "salesforce.event::SalesforceEvents::PUSH_PARAMS": ("salesforce.event", "referenced"),
}, nodes
attributes = next(n["attributes"] for n in document["nodes"] if n["id"] == mapping)
assert attributes == {
    "pull_standalone": True, "push_standalone": False, "salesforce_object": "Contact",
}, attributes

entity_line = [(config, line(config, "drupal_entity_type: node"))]
edges = sorted(
    (e["kind"], e["from"], e["to"], [(loc["file"], loc["line"]) for loc in e["locations"]])
    for e in document["edges"]
)
assert edges == sorted([
    ("maps_bundle", mapping, "drupal.bundle::node.my_type", entity_line),
    ("maps_entity_type", mapping, "drupal.entity_type::node", entity_line),
    ("maps_field", mapping, instance,
     [(config, line(config, "field.field.node.my_type.field_my_field"))]),
    ("config_depends", mapping, instance,
     [(config, line(config, "field.field.node.my_type.field_my_field"))]),
    ("config_depends", mapping, "drupal.config::node.type.my_type",
     [(config, line(config, "node.type.my_type"))]),
    ("plugin_class", "drupal.plugin.salesforce_mapping_field::my_field", field_class,
     [(field, line(field, "@Plugin("))]),
    ("inherits", field_class, field_base,
     [(field, line(field, "class MyField extends SalesforceMappingFieldPluginBase {"))]),
    ("subscribes_to_salesforce_event", sub_class,
     "salesforce.event::SalesforceEvents::PUSH_PARAMS",
     [(subscriber, line(subscriber, "$events[SalesforceEvents::PUSH_PARAMS][] = 'pushParams';"))]),
    ("subscribes_to_salesforce_event", sub_class,
     "salesforce.event::SalesforceEvents::PULL_PRESAVE",
     [(subscriber, line(subscriber, "SalesforceEvents::PULL_PRESAVE => 'pullPresave',"))]),
    ("contains", sub_class, sub_method + "getSubscribedEvents",
     [(subscriber, line(subscriber, "public static function getSubscribedEvents(): array {"))]),
    ("contains", sub_class, sub_method + "check",
     [(subscriber, line(subscriber, "public function check(): bool {"))]),
    ("implements", sub_class, interface,
     [(subscriber, line(subscriber, "class MySubscriber implements EventSubscriberInterface {"))]),
]), edges
PY
echo "salesforce pack ok"
