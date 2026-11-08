#!/usr/bin/env bash
# The bundled Drupal rutters drupal_more@0.1.0 and drupal_next@0.1.0, pinned with their
# dependencies. A module holds an entity class whose annotation names a storage handler and whose
# baseFieldDefinitions declares one field, and a class calling ->hasPermission('view content').
# The site config holds a Next.js site and a per-bundle Next.js config for node.article, and a
# TypeScript file calls drupal.fetch('/node/1'). The check names each node type and edge kind the
# map must hold, and fails naming the ones missing.
set -euo pipefail

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

site="$work/site"
module="$site/web/modules/custom/mymodule"
mkdir -p "$site/.periplus" "$site/config/sync" "$site/frontend/lib" \
    "$module/src/Entity" "$module/src/Access"
printf 'name: My module\ntype: module\ncore_version_requirement: ^10\n' >"$module/mymodule.info.yml"
cat >"$module/src/Entity/Item.php" <<'PHP'
<?php

namespace Drupal\mymodule\Entity;

use Drupal\Core\Entity\ContentEntityBase;
use Drupal\Core\Entity\EntityTypeInterface;
use Drupal\Core\Field\BaseFieldDefinition;

/**
 * @ContentEntityType(
 *   id = "mymodule_item",
 *   label = @Translation("Item"),
 *   handlers = {
 *     "storage" = "Drupal\mymodule\ItemStorage",
 *   },
 * )
 */
class Item extends ContentEntityBase {

  public static function baseFieldDefinitions(EntityTypeInterface $entity_type) {
    $fields = parent::baseFieldDefinitions($entity_type);
    $fields['title'] = BaseFieldDefinition::create('string');
    return $fields;
  }

}
PHP
cat >"$module/src/Access/ItemAccess.php" <<'PHP'
<?php

namespace Drupal\mymodule\Access;

class ItemAccess {

  public function check($account) {
    return $account->hasPermission('view content');
  }

}
PHP
printf 'id: demo\nlabel: Demo\nbase_url: https://example.com\npreview_url: https://example.com/api/preview\n' \
    >"$site/config/sync/next.next_site.demo.yml"
printf 'id: node.article\nsite_resolver: site_selector\nconfiguration:\n  sites:\n    demo: demo\n' \
    >"$site/config/sync/next.next_entity_type_config.node.article.yml"
cat >"$site/frontend/lib/items.ts" <<'TS'
export async function loadNode(drupal: { fetch: (path: string) => Promise<Response> }) {
  return drupal.fetch('/node/1');
}
TS
cat >"$site/.periplus/settings.yml" <<'YML'
periplus_version: 0
packs:
  - drupal_basic@0.3.0
  - php_basic@0.2.0
  - advancedqueue_basic@0.0.1
  - typescript@0.1.0
  - react@0.1.0
  - nextjs@0.2.0
  - drupal_more@0.1.0
  - drupal_next@0.1.0
values:
  typescript_alias_root: frontend
YML

(cd "$site" && "$PERIPLUS" map --output "$work/map.json" --format json >"$work/report.json")

python3 - "$work" <<'PY'
import json
import os
import sys

work = sys.argv[1]
document = json.load(open(os.path.join(work, "map.json")))
report = json.load(open(os.path.join(work, "report.json")))
assert report["problems"] == [] and report["not_executed"] == [], report

types = {n["type"] for n in document["nodes"]}
kinds = {e["kind"] for e in document["edges"]}
missing = [t for t in ("drupal_more.base_field", "drupal_next.site") if t not in types]
missing += [k for k in ("has_handler", "checks_permission", "next_config_for_bundle",
                        "calls_endpoint") if k not in kinds]
if missing:
    sys.exit(f"drupal next: the map lacks {', '.join(missing)}")
PY
echo "drupal next ok"
