"""What each bundled contrib pack maps, from the smallest files that show it.

These carry the pack-specific checks of the deleted ``98e-*-pack.sh`` demo scripts. Each case
plants a module and a few files, maps with the pack pinned beside ``drupal_basic``, and asserts
the nodes, the edges and the skipped rows. Edge locations are not checked here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from test_demo_a_support import edges, map_project, nodes, pin, plant

MODULE_DIR = "web/modules/custom/mymodule"
MODULE_INFO = {
    f"{MODULE_DIR}/mymodule.info.yml": (
        "name: My module\ntype: module\ncore_version_requirement: ^10\n"
    )
}


def _map(root: Path, pack: str, files: dict[str, str | bytes]) -> tuple[Any, dict[str, Any]]:
    plant(root, {**MODULE_INFO, **files})
    pin(root, "drupal_basic@0.3.0", f"{pack}@0.0.1")
    report, document = map_project(root)
    assert report.problems == () and report.not_executed == (), report
    return report, document


def _state_label(document: dict[str, Any]) -> dict[str, tuple[str, Any]]:
    return {
        node_id: (node["state"], node.get("attributes", {}).get("label"))
        for node_id, node in nodes(document).items()
    }


def _type_state(document: dict[str, Any]) -> dict[str, tuple[str, str]]:
    return {node_id: (node["type"], node["state"]) for node_id, node in nodes(document).items()}


# pack, type file stem prefix, bundle id prefix, entity type, module that ships the config
BUNDLE_PACKS = [
    ("config_pages_basic", "config_pages.type", "config_pages", "config_pages", "config_pages"),
    ("crop_basic", "crop.type", "crop", "crop", "crop"),
    ("paragraphs_basic", "paragraphs.paragraphs_type", "paragraph", "paragraph", "paragraphs"),
    ("profile_basic", "profile.type", "profile", "profile", "profile"),
]


@pytest.mark.parametrize(("pack", "stem", "bundle", "entity", "owner"), BUNDLE_PACKS)
def test_config_type_file_makes_a_bundle_and_a_settings_file_does_not(
    tmp_path: Path, pack: str, stem: str, bundle: str, entity: str, owner: str
) -> None:
    install = f"{MODULE_DIR}/config/install"
    report, document = _map(
        tmp_path,
        pack,
        {
            f"config/sync/{stem}.my_type.yml": "id: my_type\nlabel: My type\n"
            + ("context: {}\n" if pack == "config_pages_basic" else ""),
            f"{install}/{stem}.my_other_type.yml": "id: my_other_type\nlabel: My other type\n",
            f"config/sync/{owner}.settings.yml": "langcode: en\n",
        },
    )
    assert report.skipped == (), report.skipped
    assert _state_label(document) == {
        f"drupal.bundle::{bundle}.my_other_type": ("mapped", "My other type"),
        f"drupal.bundle::{bundle}.my_type": ("mapped", "My type"),
        f"drupal.config::{owner}.settings": ("mapped", None),
        f"drupal.config::{stem}.my_other_type": ("mapped", None),
        f"drupal.config::{stem}.my_type": ("mapped", None),
        f"drupal.entity_type::{entity}": ("referenced", None),
        "drupal.module::mymodule": ("mapped", None),
        f"drupal.module::{owner}": ("referenced", None),
    }
    assert edges(document) == {
        ("bundle_of", f"drupal.bundle::{bundle}.my_type", f"drupal.entity_type::{entity}"),
        ("configured_by", f"drupal.bundle::{bundle}.my_type", f"drupal.config::{stem}.my_type"),
        ("bundle_of", f"drupal.bundle::{bundle}.my_other_type", f"drupal.entity_type::{entity}"),
        (
            "configured_by",
            f"drupal.bundle::{bundle}.my_other_type",
            f"drupal.config::{stem}.my_other_type",
        ),
        ("config_provided_by", f"drupal.config::{owner}.settings", f"drupal.module::{owner}"),
        ("config_provided_by", f"drupal.config::{stem}.my_type", f"drupal.module::{owner}"),
    }


def test_eck_entity_type_and_bundle_files_make_a_content_entity_type_and_bundles(
    tmp_path: Path,
) -> None:
    report, document = _map(
        tmp_path,
        "eck_basic",
        {
            "config/sync/eck.eck_entity_type.my_entity.yml": (
                "id: my_entity\nlabel: My entity\nuid: true\n"
            ),
            "config/sync/eck.eck_type.my_entity.my_type.yml": (
                'name: My type\ntype: my_type\ndescription: ""\n'
            ),
            f"{MODULE_DIR}/config/install/eck.eck_type.my_entity.my_other_type.yml": (
                "name: My other type\ntype: my_other_type\n"
            ),
        },
    )
    assert report.skipped == (), report.skipped
    assert _state_label(document) == {
        "drupal.bundle::my_entity.my_other_type": ("mapped", "My other type"),
        "drupal.bundle::my_entity.my_type": ("mapped", "My type"),
        "drupal.config::eck.eck_entity_type.my_entity": ("mapped", None),
        "drupal.config::eck.eck_type.my_entity.my_other_type": ("mapped", None),
        "drupal.config::eck.eck_type.my_entity.my_type": ("mapped", None),
        "drupal.entity_type::my_entity": ("mapped", "My entity"),
        "drupal.module::mymodule": ("mapped", None),
        "drupal.module::eck": ("referenced", None),
    }
    assert nodes(document)["drupal.entity_type::my_entity"]["type"] == "drupal.content_entity_type"
    assert edges(document) == {
        ("bundle_of", "drupal.bundle::my_entity.my_type", "drupal.entity_type::my_entity"),
        (
            "configured_by",
            "drupal.bundle::my_entity.my_type",
            "drupal.config::eck.eck_type.my_entity.my_type",
        ),
        ("bundle_of", "drupal.bundle::my_entity.my_other_type", "drupal.entity_type::my_entity"),
        (
            "configured_by",
            "drupal.bundle::my_entity.my_other_type",
            "drupal.config::eck.eck_type.my_entity.my_other_type",
        ),
        (
            "config_provided_by",
            "drupal.config::eck.eck_entity_type.my_entity",
            "drupal.module::eck",
        ),
        (
            "config_provided_by",
            "drupal.config::eck.eck_type.my_entity.my_type",
            "drupal.module::eck",
        ),
    }


def test_advancedqueue_job_type_from_attribute_and_annotation_but_not_a_constant_id(
    tmp_path: Path,
) -> None:
    folder = f"{MODULE_DIR}/src/Plugin/AdvancedQueue/JobType"
    ns = "namespace Drupal\\mymodule\\Plugin\\AdvancedQueue\\JobType;\n"
    base_use = "use Drupal\\advancedqueue\\Plugin\\AdvancedQueue\\JobType\\JobTypeBase;\n"
    report, document = _map(
        tmp_path,
        "advancedqueue_basic",
        {
            f"{folder}/MyJob.php": (
                f"<?php\n\n{ns}\n"
                "use Drupal\\advancedqueue\\Attribute\\AdvancedQueueJobType;\n"
                f"{base_use}"
                "use Drupal\\Core\\StringTranslation\\TranslatableMarkup;\n\n"
                "#[AdvancedQueueJobType(\n"
                "  id: 'my_job',\n"
                "  label: new TranslatableMarkup('My job'),\n"
                ")]\n"
                "class MyJob extends JobTypeBase {\n}\n"
            ),
            f"{folder}/OldJob.php": (
                f"<?php\n\n{ns}\n{base_use}\n"
                "/**\n * @AdvancedQueueJobType(\n"
                ' *   id = "my_old_job",\n'
                ' *   label = @Translation("My old job"),\n'
                " * )\n */\n"
                "class OldJob extends JobTypeBase {\n}\n"
            ),
            f"{folder}/ComputedJob.php": (
                f"<?php\n\n{ns}\n"
                "use Drupal\\advancedqueue\\Attribute\\AdvancedQueueJobType;\n"
                f"{base_use}\n"
                "#[AdvancedQueueJobType(\n"
                "  id: self::ID,\n"
                ")]\n"
                "class ComputedJob extends JobTypeBase {\n"
                "  const ID = 'comp' . 'uted';\n}\n"
            ),
        },
    )
    cls = "php.type::Drupal\\mymodule\\Plugin\\AdvancedQueue\\JobType\\"
    base = "php.type::Drupal\\advancedqueue\\Plugin\\AdvancedQueue\\JobType\\JobTypeBase"
    assert _type_state(document) == {
        "drupal.module::mymodule": ("drupal.module", "mapped"),
        "drupal.plugin.advancedqueue_job_type::my_job": ("drupal.queue_job_type", "mapped"),
        "drupal.plugin.advancedqueue_job_type::my_old_job": ("drupal.queue_job_type", "mapped"),
        cls + "ComputedJob": ("php.class", "mapped"),
        cls + "MyJob": ("php.class", "mapped"),
        cls + "OldJob": ("php.class", "mapped"),
        base: ("php.class_like", "referenced"),
    }
    assert edges(document) == {
        ("plugin_class", "drupal.plugin.advancedqueue_job_type::my_job", cls + "MyJob"),
        ("plugin_class", "drupal.plugin.advancedqueue_job_type::my_old_job", cls + "OldJob"),
        ("inherits", cls + "MyJob", base),
        ("inherits", cls + "OldJob", base),
        ("inherits", cls + "ComputedJob", base),
    }
    assert [(file, rule, why) for file, _, rule, why in report.skipped] == [
        (
            f"{folder}/ComputedJob.php",
            "queue_job_type_from_attribute",
            "argument id is a class constant with no declared text",
        )
    ]


def test_ai_agent_and_function_call_plugins_from_attributes_including_a_constant_id(
    tmp_path: Path,
) -> None:
    plugins = f"{MODULE_DIR}/src/Plugin"
    report, document = _map(
        tmp_path,
        "ai_basic",
        {
            f"{plugins}/AiAgent/MyAgent.php": (
                "<?php\n\nnamespace Drupal\\mymodule\\Plugin\\AiAgent;\n\n"
                "use Drupal\\ai_agents\\Attribute\\AiAgent;\n"
                "use Drupal\\ai_agents\\PluginBase\\AiAgentBase;\n"
                "use Drupal\\Core\\StringTranslation\\TranslatableMarkup;\n\n"
                "#[AiAgent(\n  id: 'my_agent',\n"
                "  label: new TranslatableMarkup('My agent'),\n)]\n"
                "class MyAgent extends AiAgentBase {\n}\n"
            ),
            f"{plugins}/AiFunctionCall/MyFunction.php": (
                "<?php\n\nnamespace Drupal\\mymodule\\Plugin\\AiFunctionCall;\n\n"
                "use Drupal\\ai\\Attribute\\FunctionCall;\n"
                "use Drupal\\ai\\Base\\FunctionCallBase;\n"
                "use Drupal\\Core\\StringTranslation\\TranslatableMarkup;\n\n"
                "#[FunctionCall(\n  id: 'mymodule:my_function',\n"
                "  function_name: 'my_function',\n"
                "  name: new TranslatableMarkup('My function'),\n)]\n"
                "class MyFunction extends FunctionCallBase {\n}\n"
            ),
            f"{plugins}/AiFunctionCall/ComputedFunction.php": (
                "<?php\n\nnamespace Drupal\\mymodule\\Plugin\\AiFunctionCall;\n\n"
                "use Drupal\\ai\\Attribute\\FunctionCall;\n"
                "use Drupal\\ai\\Base\\FunctionCallBase;\n\n"
                "#[FunctionCall(\n  id: self::ID,\n)]\n"
                "class ComputedFunction extends FunctionCallBase {\n"
                "  const ID = 'computed';\n}\n"
            ),
        },
    )
    assert report.skipped == (), report.skipped
    cls = "php.type::Drupal\\mymodule\\Plugin\\"
    agent_base = "php.type::Drupal\\ai_agents\\PluginBase\\AiAgentBase"
    function_base = "php.type::Drupal\\ai\\Base\\FunctionCallBase"
    assert _type_state(document) == {
        "drupal.module::mymodule": ("drupal.module", "mapped"),
        "drupal.plugin.ai_agent::my_agent": ("drupal.ai_agent", "mapped"),
        "drupal.plugin.ai_function_call::mymodule:my_function": (
            "drupal.ai_function_call",
            "mapped",
        ),
        "drupal.plugin.ai_function_call::computed": ("drupal.ai_function_call", "mapped"),
        agent_base: ("php.class_like", "referenced"),
        function_base: ("php.class_like", "referenced"),
        cls + "AiAgent\\MyAgent": ("php.class", "mapped"),
        cls + "AiFunctionCall\\ComputedFunction": ("php.class", "mapped"),
        cls + "AiFunctionCall\\MyFunction": ("php.class", "mapped"),
    }
    assert edges(document) == {
        ("plugin_class", "drupal.plugin.ai_agent::my_agent", cls + "AiAgent\\MyAgent"),
        (
            "plugin_class",
            "drupal.plugin.ai_function_call::mymodule:my_function",
            cls + "AiFunctionCall\\MyFunction",
        ),
        (
            "plugin_class",
            "drupal.plugin.ai_function_call::computed",
            cls + "AiFunctionCall\\ComputedFunction",
        ),
        ("inherits", cls + "AiAgent\\MyAgent", agent_base),
        ("inherits", cls + "AiFunctionCall\\MyFunction", function_base),
        ("inherits", cls + "AiFunctionCall\\ComputedFunction", function_base),
    }


def test_drush_command_from_attribute_and_docblock_tag_but_not_a_positional_name(
    tmp_path: Path,
) -> None:
    folder = f"{MODULE_DIR}/src/Drush/Commands"
    report, document = _map(
        tmp_path,
        "drush_basic",
        {
            f"{folder}/MyCommands.php": (
                "<?php\n\nnamespace Drupal\\mymodule\\Drush\\Commands;\n\n"
                "use Drush\\Attributes as CLI;\n"
                "use Drush\\Commands\\DrushCommands;\n\n"
                "final class MyCommands extends DrushCommands {\n\n"
                "  #[CLI\\Command(name: 'mymodule:sync')]\n"
                "  public function sync(): void {\n  }\n\n"
                "  /**\n   * Runs the old way.\n   *\n   * @command mymodule:old\n   */\n"
                "  public function old(): void {\n  }\n\n"
                "  #[CLI\\Command('mymodule:positional')]\n"
                "  public function positional(): void {\n  }\n\n}\n"
            ),
            f"{folder}/OtherCommands.php": (
                "<?php\n\nnamespace Drupal\\mymodule\\Drush\\Commands;\n\n"
                "use Consolidation\\AnnotatedCommand\\Attributes\\Command;\n\n"
                "final class OtherCommands {\n\n"
                "  #[Command(name: 'mymodule:other')]\n"
                "  public function other(): void {\n  }\n\n}\n"
            ),
        },
    )
    mine = "php.type::Drupal\\mymodule\\Drush\\Commands\\MyCommands"
    other = "php.type::Drupal\\mymodule\\Drush\\Commands\\OtherCommands"
    my_method = "php.method::Drupal\\mymodule\\Drush\\Commands\\MyCommands::"
    other_method = "php.method::Drupal\\mymodule\\Drush\\Commands\\OtherCommands::other"
    base = "php.type::Drush\\Commands\\DrushCommands"
    assert _type_state(document) == {
        "drupal.module::mymodule": ("drupal.module", "mapped"),
        "drush.command::mymodule:old": ("drush.command", "mapped"),
        "drush.command::mymodule:other": ("drush.command", "mapped"),
        "drush.command::mymodule:sync": ("drush.command", "mapped"),
        my_method + "old": ("php.method", "mapped"),
        my_method + "positional": ("php.method", "mapped"),
        my_method + "sync": ("php.method", "mapped"),
        other_method: ("php.method", "mapped"),
        mine: ("php.class", "mapped"),
        other: ("php.class", "mapped"),
        base: ("php.class_like", "referenced"),
    }
    assert edges(document) == {
        ("command_method", "drush.command::mymodule:sync", my_method + "sync"),
        ("command_class", "drush.command::mymodule:sync", mine),
        ("command_method", "drush.command::mymodule:old", my_method + "old"),
        ("command_class", "drush.command::mymodule:old", mine),
        ("command_method", "drush.command::mymodule:other", other_method),
        ("command_class", "drush.command::mymodule:other", other),
        ("contains", mine, my_method + "sync"),
        ("contains", mine, my_method + "old"),
        ("contains", mine, my_method + "positional"),
        ("contains", other, other_method),
        ("inherits", mine, base),
    }
    assert [(file, rule, why) for file, _, rule, why in report.skipped] == [
        (f"{folder}/MyCommands.php", "command_from_attribute", "argument name is missing")
    ]


def test_salesforce_mapping_config_field_plugin_and_event_subscriber(tmp_path: Path) -> None:
    mapping_file = "config/sync/salesforce_mapping.salesforce_mapping.my_mapping.yml"
    src = f"{MODULE_DIR}/src"
    report, document = _map(
        tmp_path,
        "salesforce_basic",
        {
            mapping_file: (
                "dependencies:\n  config:\n"
                "    - field.field.node.my_type.field_my_field\n"
                "    - node.type.my_type\n"
                "id: my_mapping\nlabel: My mapping\nsalesforce_object_type: Contact\n"
                "drupal_entity_type: node\ndrupal_bundle: my_type\n"
                "push_standalone: false\npull_standalone: true\n"
            ),
            f"{src}/Plugin/SalesforceMappingField/MyField.php": (
                "<?php\n\nnamespace Drupal\\mymodule\\Plugin\\SalesforceMappingField;\n\n"
                "use Drupal\\salesforce_mapping\\SalesforceMappingFieldPluginBase;\n\n"
                '/**\n * @Plugin(\n *   id = "my_field",\n'
                ' *   label = @Translation("My field"),\n * )\n */\n'
                "class MyField extends SalesforceMappingFieldPluginBase {\n}\n"
            ),
            f"{src}/EventSubscriber/MySubscriber.php": (
                "<?php\n\nnamespace Drupal\\mymodule\\EventSubscriber;\n\n"
                "use Drupal\\salesforce\\Event\\SalesforceEvents;\n"
                "use Symfony\\Component\\EventDispatcher\\EventSubscriberInterface;\n\n"
                "class MySubscriber implements EventSubscriberInterface {\n\n"
                "  public static function getSubscribedEvents(): array {\n"
                "    $events[SalesforceEvents::PUSH_PARAMS][] = 'pushParams';\n"
                "    return $events + [\n"
                "      SalesforceEvents::PULL_PRESAVE => 'pullPresave',\n    ];\n  }\n\n"
                "  public function check(): bool {\n"
                "    return isset($this->seen[SalesforceEvents::PUSH_FAIL]);\n  }\n\n}\n"
            ),
        },
    )
    assert report.skipped == (), report.skipped
    mapping = "drupal.config::salesforce_mapping.salesforce_mapping.my_mapping"
    instance = "drupal.config::field.field.node.my_type.field_my_field"
    field_class = "php.type::Drupal\\mymodule\\Plugin\\SalesforceMappingField\\MyField"
    sub_class = "php.type::Drupal\\mymodule\\EventSubscriber\\MySubscriber"
    sub_method = "php.method::Drupal\\mymodule\\EventSubscriber\\MySubscriber::"
    field_base = "php.type::Drupal\\salesforce_mapping\\SalesforceMappingFieldPluginBase"
    interface = "php.type::Symfony\\Component\\EventDispatcher\\EventSubscriberInterface"
    assert _type_state(document) == {
        "drupal.bundle::node.my_type": ("drupal.bundle", "referenced"),
        instance: ("drupal.field_instance", "referenced"),
        "drupal.config::node.type.my_type": ("drupal.config_object", "referenced"),
        mapping: ("salesforce.mapping", "mapped"),
        "drupal.entity_type::node": ("drupal.entity_type", "referenced"),
        "drupal.module::mymodule": ("drupal.module", "mapped"),
        "drupal.module::salesforce_mapping": ("drupal.module", "referenced"),
        "drupal.plugin.salesforce_mapping_field::my_field": (
            "drupal.salesforce_mapping_field",
            "mapped",
        ),
        sub_method + "check": ("php.method", "mapped"),
        sub_method + "getSubscribedEvents": ("php.method", "mapped"),
        sub_class: ("drupal.event_subscriber_class", "mapped"),
        field_class: ("php.class", "mapped"),
        field_base: ("php.class_like", "referenced"),
        interface: ("php.interface", "declared"),
        "salesforce.event::SalesforceEvents::PULL_PRESAVE": ("salesforce.event", "referenced"),
        "salesforce.event::SalesforceEvents::PUSH_PARAMS": ("salesforce.event", "referenced"),
    }
    assert nodes(document)[mapping]["attributes"] == {
        "pull_standalone": True,
        "push_standalone": False,
        "salesforce_object": "Contact",
    }
    assert edges(document) == {
        ("maps_bundle", mapping, "drupal.bundle::node.my_type"),
        ("maps_entity_type", mapping, "drupal.entity_type::node"),
        ("maps_field", mapping, instance),
        ("config_depends", mapping, instance),
        ("config_depends", mapping, "drupal.config::node.type.my_type"),
        ("config_provided_by", mapping, "drupal.module::salesforce_mapping"),
        ("plugin_class", "drupal.plugin.salesforce_mapping_field::my_field", field_class),
        ("inherits", field_class, field_base),
        (
            "subscribes_to_salesforce_event",
            sub_class,
            "salesforce.event::SalesforceEvents::PUSH_PARAMS",
        ),
        (
            "subscribes_to_salesforce_event",
            sub_class,
            "salesforce.event::SalesforceEvents::PULL_PRESAVE",
        ),
        ("contains", sub_class, sub_method + "getSubscribedEvents"),
        ("contains", sub_class, sub_method + "check"),
        ("implements", sub_class, interface),
    }


def test_twig_tweak_calls_in_a_module_and_a_theme_but_not_a_variable_or_a_comment(
    tmp_path: Path,
) -> None:
    report, document = _map(
        tmp_path,
        "twig_tweak_basic",
        {
            "web/themes/custom/mytheme/mytheme.info.yml": (
                "name: My theme\ntype: theme\ncore_version_requirement: ^10\n"
            ),
            f"{MODULE_DIR}/templates/my-template.html.twig": (
                '<div class="my-template">\n'
                "  {{ drupal_block('my_block', {label: 'Mine'}) }}\n"
                "  {{ drupal_entity('node', 1) }}\n"
                "  {{ drupal_entity_form(\"node\", null, 'default') }}\n"
                "  {{ drupal_field('field_my_field', 'node', 1) }}\n"
                "  {{ drupal_block(block_id) }}\n"
                "  {# drupal_menu('footer') #}\n</div>\n"
            ),
            "web/themes/custom/mytheme/templates/page.html.twig": (
                "<nav>{{ drupal_menu('main') }}</nav>\n"
            ),
        },
    )
    assert report.skipped == (), report.skipped
    template = "drupal.template::my-template"
    assert _type_state(document) == {
        "drupal.config::field.storage.node.field_my_field": ("drupal.field_storage", "referenced"),
        "drupal.config::system.menu.main": ("drupal.config_object", "referenced"),
        "drupal.entity_type::node": ("drupal.entity_type", "referenced"),
        "drupal.module::mymodule": ("drupal.module", "mapped"),
        "drupal.plugin.block::my_block": ("drupal.block_plugin", "referenced"),
        template: ("drupal.template", "mapped"),
        "drupal.template::page": ("drupal.template", "mapped"),
        "drupal.theme::mytheme": ("drupal.theme", "mapped"),
    }
    assert edges(document) == {
        ("renders_block", template, "drupal.plugin.block::my_block"),
        ("renders_entity_type", template, "drupal.entity_type::node"),
        ("renders_entity_form", template, "drupal.entity_type::node"),
        ("renders_field", template, "drupal.config::field.storage.node.field_my_field"),
        ("renders_menu", "drupal.template::page", "drupal.config::system.menu.main"),
    }
