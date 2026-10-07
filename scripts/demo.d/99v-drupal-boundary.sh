#!/usr/bin/env bash
# The Drupal pack's boundary. A planted module holds a controller that extends ControllerBase
# through a module base class, a config form, an event subscriber, and a class extending a base no
# pack lists; no file of any core class is there. Each listed base the code reaches is a declared
# node drupal_basic draws, with no location. The controller, the module base, the form and the
# subscriber take the type their core ancestor names, with an inferred provenance row. The unlisted
# base stays referenced. The report lists no file for a base and no problem. Two runs give the
# same bytes.
set -euo pipefail
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
site="$work/site"
module="$site/web/modules/custom/my_module"
mkdir -p "$site/.periplus" "$module/src/Controller" "$module/src/Form" "$module/src/EventSubscriber"
printf 'periplus_version: 0\npacks:\n  - drupal_basic@0.3.0\n' >"$site/.periplus/settings.yml"
cat >"$module/src/Controller/ModuleControllerBase.php" <<'EOF2'
<?php

namespace Drupal\my_module\Controller;

use Drupal\Core\Controller\ControllerBase;

abstract class ModuleControllerBase extends ControllerBase {}
EOF2
cat >"$module/src/Controller/ThingController.php" <<'EOF2'
<?php

namespace Drupal\my_module\Controller;

class ThingController extends ModuleControllerBase {}
EOF2
cat >"$module/src/Form/SettingsForm.php" <<'EOF2'
<?php

namespace Drupal\my_module\Form;

use Drupal\Core\Form\ConfigFormBase;

class SettingsForm extends ConfigFormBase {}
EOF2
cat >"$module/src/EventSubscriber/ThingSubscriber.php" <<'EOF2'
<?php

namespace Drupal\my_module\EventSubscriber;

use Symfony\Component\EventDispatcher\EventSubscriberInterface;

class ThingSubscriber implements EventSubscriberInterface {}
EOF2
cat >"$module/src/Helper.php" <<'EOF2'
<?php

namespace Drupal\my_module;

use Vendor\Library\UnlistedBase;

class Helper extends UnlistedBase {}
EOF2
(cd "$site" && "$PERIPLUS" validate drupal_basic >/dev/null)
(cd "$site" && "$PERIPLUS" map --output "$work/first.json" --format json >"$work/report.json")
(cd "$site" && "$PERIPLUS" map --output "$work/second.json" --format json >/dev/null)
cmp "$work/first.json" "$work/second.json"
python3 - "$work/first.json" "$work/report.json" <<'PY'
import json
import sys

document, report = json.load(open(sys.argv[1])), json.load(open(sys.argv[2]))
assert report["problems"] == [] and report["not_executed"] == [], report
assert report["skipped"] == [], report["skipped"]
listed = report["unread"] + report["unlisted"]
nodes = {n["id"]: n for n in document["nodes"]}
own = "php.type::Drupal\\my_module\\"
bases = {
    "php.type::Drupal\\Core\\Controller\\ControllerBase": ("php.class_like", "core_classes"),
    "php.type::Drupal\\Core\\Form\\ConfigFormBase": ("php.class_like", "core_classes"),
    "php.type::Symfony\\Component\\EventDispatcher\\EventSubscriberInterface": (
        "php.interface", "core_interfaces"),
}
for base, (kind, group) in bases.items():
    node = nodes[base]
    assert (node["type"], node["state"], node["locations"]) == (kind, "declared", []), node
    assert "unresolved_detail" not in node, node
    assert node["provenance"] == [{"pack": "drupal_basic", "rule": f"boundary.{group}",
                                   "confidence": "declared", "sets": ["id", "type"]}], node
    short = base.rsplit("\\", 1)[1]
    assert not any(short in json.dumps(row) for row in listed), listed
classified = {
    own + "Controller\\ModuleControllerBase": ("drupal.controller_class", "core_classes"),
    own + "Controller\\ThingController": ("drupal.controller_class", "core_classes"),
    own + "Form\\SettingsForm": ("drupal.config_form_class", "core_classes"),
    own + "EventSubscriber\\ThingSubscriber": ("drupal.event_subscriber_class", "core_interfaces"),
}
for cls, (kind, group) in classified.items():
    node = nodes[cls]
    assert (node["type"], node["state"]) == (kind, "mapped"), node
    rows = [p for p in node["provenance"] if p["rule"].startswith("boundary.")]
    assert rows == [{"pack": "drupal_basic", "rule": f"boundary.{group}",
                     "confidence": "inferred", "sets": ["type"]}], node
helper = nodes[own + "Helper"]
assert helper["type"] == "php.class", helper
unlisted = nodes["php.type::Vendor\\Library\\UnlistedBase"]
assert (unlisted["state"], unlisted["locations"]) == ("referenced", []), unlisted
assert all(p["pack"] == "php_basic" for p in unlisted["provenance"]), unlisted
print("drupal boundary: 3 declared bases, 4 classified classes, 1 referenced base")
PY
echo "drupal boundary ok"
