# Reading the map report

`periplus map` writes the map and prints a report on the run. The map says what was found. The
report says how far to trust it: what stopped the run, which files no rule read, and which matches
a rule could not finish. This page lists each part of the report in the order to read it, says what
it means, and says what to do when it is not empty. It runs on a small Drupal module, planted
below, and every command on the page prints what is shown, which a check confirms.

The report comes in two forms. `periplus map` prints text for a person; `periplus map --format
json` prints one JSON document for a script. The JSON keys and the text headings differ, so each
section below names both. The README's [loop](../README.md#the-loop) is the short form of this page.

## The planted project

The project pins three bundled rutters, `drupal_basic`, `js_basic` and `drupal_js_basic`, and its
own rutter `myproject`, planted under [Where a rule belongs](#where-a-rule-belongs).

<!-- nav-file: .periplus/settings.yml -->
```yaml
periplus_version: 0
packs:
  - drupal_basic@0.3.0
  - js_basic@0.0.1
  - drupal_js_basic@0.0.1
  - myproject@0.0.1
```

A module named `greet`:

<!-- nav-file: web/modules/custom/greet/greet.info.yml -->
```yaml
name: Greet
type: module
core_version_requirement: ^10
```

Its libraries file holds two libraries: `banner` lists one script by a path relative to the
module, and `cdn` lists one script by URL only.

<!-- nav-file: web/modules/custom/greet/greet.libraries.yml -->
```yaml
banner:
  js:
    js/banner.js: {}
cdn:
  js:
    https://cdn.example.com/banner.js: {type: external}
```

Its `.module` file attaches the library and one setting, `greetBanner`, with the key `color`
nested below it.

<!-- nav-file: web/modules/custom/greet/greet.module -->
```php
<?php

/**
 * Implements hook_preprocess_page().
 */
function greet_preprocess_page(array &$variables): void {
  $variables['greet'] = [
    '#attached' => [
      'library' => ['greet/banner'],
      'drupalSettings' => [
        'greetBanner' => [
          'color' => 'red',
        ],
      ],
    ],
  ];
}
```

Its script declares one behavior, which reads the setting. It fetches one path written whole and
one joined with `+`.

<!-- nav-file: web/modules/custom/greet/js/banner.js -->
```js
(function (Drupal, drupalSettings) {
  Drupal.behaviors.greetBanner = {
    attach(context) {
      const banner = drupalSettings.greetBanner;
      fetch('/greet/hello');
      fetch('/greet/user/' + banner.color);
    },
  };
})(Drupal, drupalSettings);
```

## Run the map

Run `periplus map` in the project folder. The report is long, because it lists every rule the
pinned rutters and the ones they depend on hold; open it below.

<details>
<summary>The text report</summary>

<!-- nav-run -->
```
$ periplus map
periplus map

Map:
  path    /path/to/project/.periplus/map.json
  nodes   11
  edges   7

Files:
  selected  5
  excluded  0
  unread    3
  unlisted  0

Files no rule read, by ending:
  yaml 2
  yml 1

Files no rule read:
  .periplus/packs/myproject@0.0.1/event.yaml
  .periplus/packs/myproject@0.0.1/pack.yaml
  .periplus/settings.yml

Folders that could not be listed:
  none

Files that did not parse cleanly:
  none

Packs:
  drupal_basic 0.3.0
  drupal_js_basic 0.0.1
  js_basic 0.0.1
  myproject 0.0.1
  php_basic 0.2.0
  twig_basic 0.1.0
  yaml_basic 0.1.0

Rules executed:
  drupal_basic action_from_annotation fired 0
  drupal_basic action_from_annotation_edges fired 0
  drupal_basic action_from_attribute fired 0
  drupal_basic action_from_attribute_edges fired 0
  drupal_basic any_config_file fired 0
  drupal_basic any_config_file_edges fired 0
  drupal_basic block_placement_from_config fired 0
  drupal_basic block_placement_from_config_edges fired 0
  drupal_basic block_plugin_from_annotation fired 0
  drupal_basic block_plugin_from_annotation_edges fired 0
  drupal_basic block_plugin_from_attribute fired 0
  drupal_basic block_plugin_from_attribute_edges fired 0
  drupal_basic block_type_from_config fired 0
  drupal_basic block_type_from_config_edges fired 0
  drupal_basic bundle_comment_from_config fired 0
  drupal_basic bundle_comment_from_config_edges fired 0
  drupal_basic bundle_contact_message_from_config fired 0
  drupal_basic bundle_contact_message_from_config_edges fired 0
  drupal_basic bundle_group_from_config fired 0
  drupal_basic bundle_group_from_config_edges fired 0
  drupal_basic bundle_group_relationship_from_config fired 0
  drupal_basic bundle_group_relationship_from_config_edges fired 0
  drupal_basic bundle_media_from_config fired 0
  drupal_basic bundle_media_from_config_edges fired 0
  drupal_basic bundle_node_from_config fired 0
  drupal_basic bundle_node_from_config_edges fired 0
  drupal_basic bundle_shortcut_from_config fired 0
  drupal_basic bundle_shortcut_from_config_edges fired 0
  drupal_basic bundle_taxonomy_term_from_config fired 0
  drupal_basic bundle_taxonomy_term_from_config_edges fired 0
  drupal_basic calls_through_service_property fired 0
  drupal_basic captcha_point_form fired 0
  drupal_basic component_file fired 0
  drupal_basic component_included_in_template fired 0
  drupal_basic config_entity_type_from_annotation fired 0
  drupal_basic config_entity_type_from_annotation_edges fired 0
  drupal_basic config_entity_type_from_attribute fired 0
  drupal_basic config_entity_type_from_attribute_edges fired 0
  drupal_basic constraint_from_annotation fired 0
  drupal_basic constraint_from_annotation_edges fired 0
  drupal_basic constraint_from_attribute fired 0
  drupal_basic constraint_from_attribute_edges fired 0
  drupal_basic container_entity_call fired 0
  drupal_basic container_get_call fired 0
  drupal_basic container_nullsafe_get_call fired 0
  drupal_basic content_entity_type_from_annotation fired 0
  drupal_basic content_entity_type_from_annotation_edges fired 0
  drupal_basic content_entity_type_from_attribute fired 0
  drupal_basic content_entity_type_from_attribute_edges fired 0
  drupal_basic display_block_type_edges fired 0
  drupal_basic display_bundle_edges fired 0
  drupal_basic display_bundle_of_edges fired 0
  drupal_basic drupal_shortcut_call fired 0
  drupal_basic entity_call_through_typed_manager fired 0
  drupal_basic entity_class_static_call fired 0
  drupal_basic entity_handler_call fired 0
  drupal_basic entity_query_call fired 0
  drupal_basic field_formatter_from_annotation fired 0
  drupal_basic field_formatter_from_annotation_edges fired 0
  drupal_basic field_formatter_from_attribute fired 0
  drupal_basic field_formatter_from_attribute_edges fired 0
  drupal_basic field_instance_block_type_edges fired 0
  drupal_basic field_instance_bundle_edges fired 0
  drupal_basic field_instance_bundle_of_edges fired 0
  drupal_basic field_instance_from_config fired 0
  drupal_basic field_instance_from_config_edges fired 0
  drupal_basic field_storage_from_config fired 0
  drupal_basic field_storage_from_config_edges fired 0
  drupal_basic field_type_from_annotation fired 0
  drupal_basic field_type_from_annotation_edges fired 0
  drupal_basic field_type_from_attribute fired 0
  drupal_basic field_type_from_attribute_edges fired 0
  drupal_basic field_widget_from_annotation fired 0
  drupal_basic field_widget_from_annotation_edges fired 0
  drupal_basic field_widget_from_attribute fired 0
  drupal_basic field_widget_from_attribute_edges fired 0
  drupal_basic form_class_has_id fired 0
  drupal_basic form_display_from_config fired 0
  drupal_basic form_display_from_config_edges fired 0
  drupal_basic form_display_mode_edges fired 0
  drupal_basic form_id_returned fired 0
  drupal_basic form_mode_from_config fired 0
  drupal_basic function_implements_hook fired 1
  drupal_basic honeypot_forms fired 0
  drupal_basic hook_acts_on_entity_type fired 0
  drupal_basic hook_attribute_acts_on_entity_type fired 0
  drupal_basic hook_from_attribute fired 0
  drupal_basic hook_from_function_name fired 1
  drupal_basic hook_from_named_attribute fired 0
  drupal_basic hook_from_theme_include fired 0
  drupal_basic internal_uri_url_call fired 0
  drupal_basic library_from_libraries_file fired 2
  drupal_basic library_from_libraries_file_edges fired 2
  drupal_basic local_action_from_links_file fired 0
  drupal_basic local_action_from_links_file_edges fired 0
  drupal_basic local_manager_entity_call fired 0
  drupal_basic mail_from_attribute fired 0
  drupal_basic mail_from_attribute_edges fired 0
  drupal_basic manager_call fired 0
  drupal_basic manager_call_in fired 0
  drupal_basic manager_nullsafe_call fired 0
  drupal_basic manager_nullsafe_call_in fired 0
  drupal_basic media_source_from_annotation fired 0
  drupal_basic media_source_from_annotation_edges fired 0
  drupal_basic media_source_from_attribute fired 0
  drupal_basic media_source_from_attribute_edges fired 0
  drupal_basic media_source_from_oembed_attribute fired 0
  drupal_basic media_source_from_oembed_attribute_edges fired 0
  drupal_basic menu_link_from_links_file fired 0
  drupal_basic menu_link_from_links_file_edges fired 0
  drupal_basic mode_entity_type_edges fired 0
  drupal_basic module_from_info_file fired 1
  drupal_basic module_from_info_file_edges fired 1
  drupal_basic path_in_template_attribute fired 0
  drupal_basic permission_from_permissions_file fired 0
  drupal_basic queue_worker_from_annotation fired 0
  drupal_basic queue_worker_from_annotation_edges fired 0
  drupal_basic queue_worker_from_attribute fired 0
  drupal_basic queue_worker_from_attribute_edges fired 0
  drupal_basic rest_resource_from_annotation fired 0
  drupal_basic rest_resource_from_annotation_edges fired 0
  drupal_basic rest_resource_from_attribute fired 0
  drupal_basic rest_resource_from_attribute_edges fired 0
  drupal_basic role_from_config fired 0
  drupal_basic role_from_config_edges fired 0
  drupal_basic route_from_routing_file fired 0
  drupal_basic route_from_routing_file_edges fired 0
  drupal_basic route_linked_in_template fired 0
  drupal_basic route_options_from_routing_file fired 0
  drupal_basic route_options_from_routing_file_edges fired 0
  drupal_basic route_requirements_from_routing_file fired 0
  drupal_basic route_requirements_from_routing_file_edges fired 0
  drupal_basic service_alias_from_services_file fired 0
  drupal_basic service_call fired 0
  drupal_basic service_from_services_file fired 0
  drupal_basic service_from_services_file_class fired 0
  drupal_basic service_from_services_file_class_key fired 0
  drupal_basic service_from_services_file_edges fired 0
  drupal_basic service_text_alias_from_services_file fired 0
  drupal_basic simple_config_owner fired 0
  drupal_basic storage_call fired 0
  drupal_basic storage_nullsafe_call fired 0
  drupal_basic template_file fired 1
  drupal_basic template_included_in_template fired 0
  drupal_basic template_suggests_bundle fired 0
  drupal_basic theme_from_info_file fired 0
  drupal_basic theme_from_info_file_edges fired 0
  drupal_basic theme_hook_default_template fired 0
  drupal_basic theme_hook_entry fired 0
  drupal_basic theme_hook_rendered_in_class fired 0
  drupal_basic theme_hook_template_key fired 0
  drupal_basic theme_include_implements_hook fired 0
  drupal_basic user_input_url_call fired 0
  drupal_basic view_display_from_config fired 0
  drupal_basic view_display_from_config_edges fired 0
  drupal_basic view_display_mode_edges fired 0
  drupal_basic view_mode_from_config fired 0
  drupal_basic views_field_from_attribute fired 0
  drupal_basic views_field_from_attribute_edges fired 0
  drupal_basic views_field_from_named_attribute fired 0
  drupal_basic views_field_from_named_attribute_edges fired 0
  drupal_basic views_filter_from_attribute fired 0
  drupal_basic views_filter_from_attribute_edges fired 0
  drupal_basic views_filter_from_named_attribute fired 0
  drupal_basic views_filter_from_named_attribute_edges fired 0
  drupal_basic views_style_from_attribute fired 0
  drupal_basic views_style_from_attribute_edges fired 0
  drupal_basic views_style_from_named_attribute fired 0
  drupal_basic views_style_from_named_attribute_edges fired 0
  drupal_js_basic behavior_attach_call fired 0
  drupal_js_basic behavior_from_arrow fired 0
  drupal_js_basic behavior_from_arrow_in_file fired 0
  drupal_js_basic behavior_from_assignment fired 1
  drupal_js_basic behavior_from_assignment_in_file fired 1
  drupal_js_basic behavior_from_function fired 0
  drupal_js_basic behavior_from_function_in_file fired 0
  drupal_js_basic library_attached_in_array fired 1
  drupal_js_basic library_attached_in_array_in_function fired 1
  drupal_js_basic library_attached_in_class fired 0
  drupal_js_basic library_attached_in_component fired 0
  drupal_js_basic library_attached_in_template fired 0
  drupal_js_basic library_script fired 2
  drupal_js_basic library_stylesheet fired 2
  drupal_js_basic path_in_script_string fired 1
  drupal_js_basic php_function_holds_body fired 1
  drupal_js_basic setting_attached fired 0
  drupal_js_basic setting_attached_in_array fired 1
  drupal_js_basic setting_attached_in_array_in_class fired 1
  drupal_js_basic setting_attached_in_array_in_function fired 1
  drupal_js_basic setting_attached_in_class fired 0
  drupal_js_basic setting_read_in_behavior fired 1
  drupal_js_basic stylesheet_file fired 0
  js_basic function_declaration fired 0
  js_basic function_declaration_in_file fired 0
  js_basic function_from_arrow fired 0
  js_basic function_from_arrow_in_file fired 0
  js_basic function_from_expression fired 0
  js_basic function_from_expression_in_file fired 0
  js_basic script_file fired 1
  myproject event_from_data_track fired 1
  php_basic assigned_value fired 0
  php_basic call_site_method fired 0
  php_basic calls_function fired 0
  php_basic calls_static_method fired 0
  php_basic calls_through_assigned_property fired 0
  php_basic calls_through_property_assigned_here fired 0
  php_basic calls_through_typed_property fired 0
  php_basic contains_method fired 0
  php_basic declares_property fired 0
  php_basic find_call_site fired 0
  php_basic find_class fired 0
  php_basic find_enum fired 0
  php_basic find_function fired 1
  php_basic find_interface fired 0
  php_basic find_member_assignment fired 0
  php_basic find_member_assignment_value fired 0
  php_basic find_method fired 0
  php_basic find_nullable_promoted_property_type fired 0
  php_basic find_nullable_property_type fired 0
  php_basic find_parameter fired 0
  php_basic find_parameter_type fired 0
  php_basic find_promoted_property fired 0
  php_basic find_promoted_property_type fired 0
  php_basic find_property fired 0
  php_basic find_property_type fired 0
  php_basic find_trait fired 0
  php_basic find_union_promoted_property_type fired 0
  php_basic find_union_property_type fired 0
  php_basic find_var_property_type fired 0
  php_basic implements_from_interface_clause fired 0
  php_basic inherits_from_base_clause fired 0
  php_basic mixes_in_from_use_declaration fired 0
  php_basic nullable_promoted_property_typed_as fired 0
  php_basic nullable_property_typed_as fired 0
  php_basic parameter_typed_as fired 0
  php_basic promoted_property_typed_as fired 0
  php_basic property_typed_as fired 0
  php_basic union_promoted_property_typed_as fired 0
  php_basic union_property_typed_as fired 0
  php_basic var_property_typed_as fired 0

Rules that fired zero times:
  drupal_basic action_from_annotation
  drupal_basic action_from_annotation_edges
  drupal_basic action_from_attribute
  drupal_basic action_from_attribute_edges
  drupal_basic any_config_file
  drupal_basic any_config_file_edges
  drupal_basic block_placement_from_config
  drupal_basic block_placement_from_config_edges
  drupal_basic block_plugin_from_annotation
  drupal_basic block_plugin_from_annotation_edges
  drupal_basic block_plugin_from_attribute
  drupal_basic block_plugin_from_attribute_edges
  drupal_basic block_type_from_config
  drupal_basic block_type_from_config_edges
  drupal_basic bundle_comment_from_config
  drupal_basic bundle_comment_from_config_edges
  drupal_basic bundle_contact_message_from_config
  drupal_basic bundle_contact_message_from_config_edges
  drupal_basic bundle_group_from_config
  drupal_basic bundle_group_from_config_edges
  drupal_basic bundle_group_relationship_from_config
  drupal_basic bundle_group_relationship_from_config_edges
  drupal_basic bundle_media_from_config
  drupal_basic bundle_media_from_config_edges
  drupal_basic bundle_node_from_config
  drupal_basic bundle_node_from_config_edges
  drupal_basic bundle_shortcut_from_config
  drupal_basic bundle_shortcut_from_config_edges
  drupal_basic bundle_taxonomy_term_from_config
  drupal_basic bundle_taxonomy_term_from_config_edges
  drupal_basic calls_through_service_property
  drupal_basic captcha_point_form
  drupal_basic component_file
  drupal_basic component_included_in_template
  drupal_basic config_entity_type_from_annotation
  drupal_basic config_entity_type_from_annotation_edges
  drupal_basic config_entity_type_from_attribute
  drupal_basic config_entity_type_from_attribute_edges
  drupal_basic constraint_from_annotation
  drupal_basic constraint_from_annotation_edges
  drupal_basic constraint_from_attribute
  drupal_basic constraint_from_attribute_edges
  drupal_basic container_entity_call
  drupal_basic container_get_call
  drupal_basic container_nullsafe_get_call
  drupal_basic content_entity_type_from_annotation
  drupal_basic content_entity_type_from_annotation_edges
  drupal_basic content_entity_type_from_attribute
  drupal_basic content_entity_type_from_attribute_edges
  drupal_basic display_block_type_edges
  drupal_basic display_bundle_edges
  drupal_basic display_bundle_of_edges
  drupal_basic drupal_shortcut_call
  drupal_basic entity_call_through_typed_manager
  drupal_basic entity_class_static_call
  drupal_basic entity_handler_call
  drupal_basic entity_query_call
  drupal_basic field_formatter_from_annotation
  drupal_basic field_formatter_from_annotation_edges
  drupal_basic field_formatter_from_attribute
  drupal_basic field_formatter_from_attribute_edges
  drupal_basic field_instance_block_type_edges
  drupal_basic field_instance_bundle_edges
  drupal_basic field_instance_bundle_of_edges
  drupal_basic field_instance_from_config
  drupal_basic field_instance_from_config_edges
  drupal_basic field_storage_from_config
  drupal_basic field_storage_from_config_edges
  drupal_basic field_type_from_annotation
  drupal_basic field_type_from_annotation_edges
  drupal_basic field_type_from_attribute
  drupal_basic field_type_from_attribute_edges
  drupal_basic field_widget_from_annotation
  drupal_basic field_widget_from_annotation_edges
  drupal_basic field_widget_from_attribute
  drupal_basic field_widget_from_attribute_edges
  drupal_basic form_class_has_id
  drupal_basic form_display_from_config
  drupal_basic form_display_from_config_edges
  drupal_basic form_display_mode_edges
  drupal_basic form_id_returned
  drupal_basic form_mode_from_config
  drupal_basic honeypot_forms
  drupal_basic hook_acts_on_entity_type
  drupal_basic hook_attribute_acts_on_entity_type
  drupal_basic hook_from_attribute
  drupal_basic hook_from_named_attribute
  drupal_basic hook_from_theme_include
  drupal_basic internal_uri_url_call
  drupal_basic local_action_from_links_file
  drupal_basic local_action_from_links_file_edges
  drupal_basic local_manager_entity_call
  drupal_basic mail_from_attribute
  drupal_basic mail_from_attribute_edges
  drupal_basic manager_call
  drupal_basic manager_call_in
  drupal_basic manager_nullsafe_call
  drupal_basic manager_nullsafe_call_in
  drupal_basic media_source_from_annotation
  drupal_basic media_source_from_annotation_edges
  drupal_basic media_source_from_attribute
  drupal_basic media_source_from_attribute_edges
  drupal_basic media_source_from_oembed_attribute
  drupal_basic media_source_from_oembed_attribute_edges
  drupal_basic menu_link_from_links_file
  drupal_basic menu_link_from_links_file_edges
  drupal_basic mode_entity_type_edges
  drupal_basic path_in_template_attribute
  drupal_basic permission_from_permissions_file
  drupal_basic queue_worker_from_annotation
  drupal_basic queue_worker_from_annotation_edges
  drupal_basic queue_worker_from_attribute
  drupal_basic queue_worker_from_attribute_edges
  drupal_basic rest_resource_from_annotation
  drupal_basic rest_resource_from_annotation_edges
  drupal_basic rest_resource_from_attribute
  drupal_basic rest_resource_from_attribute_edges
  drupal_basic role_from_config
  drupal_basic role_from_config_edges
  drupal_basic route_from_routing_file
  drupal_basic route_from_routing_file_edges
  drupal_basic route_linked_in_template
  drupal_basic route_options_from_routing_file
  drupal_basic route_options_from_routing_file_edges
  drupal_basic route_requirements_from_routing_file
  drupal_basic route_requirements_from_routing_file_edges
  drupal_basic service_alias_from_services_file
  drupal_basic service_call
  drupal_basic service_from_services_file
  drupal_basic service_from_services_file_class
  drupal_basic service_from_services_file_class_key
  drupal_basic service_from_services_file_edges
  drupal_basic service_text_alias_from_services_file
  drupal_basic simple_config_owner
  drupal_basic storage_call
  drupal_basic storage_nullsafe_call
  drupal_basic template_included_in_template
  drupal_basic template_suggests_bundle
  drupal_basic theme_from_info_file
  drupal_basic theme_from_info_file_edges
  drupal_basic theme_hook_default_template
  drupal_basic theme_hook_entry
  drupal_basic theme_hook_rendered_in_class
  drupal_basic theme_hook_template_key
  drupal_basic theme_include_implements_hook
  drupal_basic user_input_url_call
  drupal_basic view_display_from_config
  drupal_basic view_display_from_config_edges
  drupal_basic view_display_mode_edges
  drupal_basic view_mode_from_config
  drupal_basic views_field_from_attribute
  drupal_basic views_field_from_attribute_edges
  drupal_basic views_field_from_named_attribute
  drupal_basic views_field_from_named_attribute_edges
  drupal_basic views_filter_from_attribute
  drupal_basic views_filter_from_attribute_edges
  drupal_basic views_filter_from_named_attribute
  drupal_basic views_filter_from_named_attribute_edges
  drupal_basic views_style_from_attribute
  drupal_basic views_style_from_attribute_edges
  drupal_basic views_style_from_named_attribute
  drupal_basic views_style_from_named_attribute_edges
  drupal_js_basic behavior_attach_call
  drupal_js_basic behavior_from_arrow
  drupal_js_basic behavior_from_arrow_in_file
  drupal_js_basic behavior_from_function
  drupal_js_basic behavior_from_function_in_file
  drupal_js_basic library_attached_in_class
  drupal_js_basic library_attached_in_component
  drupal_js_basic library_attached_in_template
  drupal_js_basic setting_attached
  drupal_js_basic setting_attached_in_class
  drupal_js_basic stylesheet_file
  js_basic function_declaration
  js_basic function_declaration_in_file
  js_basic function_from_arrow
  js_basic function_from_arrow_in_file
  js_basic function_from_expression
  js_basic function_from_expression_in_file
  php_basic assigned_value
  php_basic call_site_method
  php_basic calls_function
  php_basic calls_static_method
  php_basic calls_through_assigned_property
  php_basic calls_through_property_assigned_here
  php_basic calls_through_typed_property
  php_basic contains_method
  php_basic declares_property
  php_basic find_call_site
  php_basic find_class
  php_basic find_enum
  php_basic find_interface
  php_basic find_member_assignment
  php_basic find_member_assignment_value
  php_basic find_method
  php_basic find_nullable_promoted_property_type
  php_basic find_nullable_property_type
  php_basic find_parameter
  php_basic find_parameter_type
  php_basic find_promoted_property
  php_basic find_promoted_property_type
  php_basic find_property
  php_basic find_property_type
  php_basic find_trait
  php_basic find_union_promoted_property_type
  php_basic find_union_property_type
  php_basic find_var_property_type
  php_basic implements_from_interface_clause
  php_basic inherits_from_base_clause
  php_basic mixes_in_from_use_declaration
  php_basic nullable_promoted_property_typed_as
  php_basic nullable_property_typed_as
  php_basic parameter_typed_as
  php_basic promoted_property_typed_as
  php_basic property_typed_as
  php_basic union_promoted_property_typed_as
  php_basic union_property_typed_as
  php_basic var_property_typed_as

Map rule passes:
  pass 1: none

Rules not executed:
  none

Matches skipped:
  web/modules/custom/greet/greet.libraries.yml:4 library_script fired and emitted nothing

Attributes that differ between files:
  none

Problems:
  none
```

</details>

## The report, part by part

Read the parts in this order. The first ones say whether the map can be trusted at all; the later
ones say how the rules spent the run.

### `problems`

Text heading: Problems. Each row is an exit code and a message. A problem stops the run: no map is
written, `map` is `null` (text: `not written`), and the command exits with the lowest code listed.
When it is not empty, fix what the message names first, and run the map again. Nothing else in the
report is worth reading until it is empty.

### `parse_errors`

Text heading: Files that did not parse cleanly. Each row is a file whose parse tree holds an
error, so the rules may have missed part of what it declares. When it is not empty, open the file:
it may hold a syntax error, or a form the grammar does not know.

### `unread`

Text headings: the `unread` count under Files; Files no rule read, by ending; and Files no rule
read, which shows the first 20 and says how many more the JSON report lists. Each row is a file in
the rules' folders that no rule read. The map knows nothing about it. When it is not empty, look at
the endings first: a whole family of files is a rule to write, and a single file may be one to
exclude. On a second run the map's own `.periplus/map.json` is listed too.

### `unlisted`

Text headings: the `unlisted` count under Files, and Folders that could not be listed. Each row is
a folder below the rules' folders that the walk for unread files could not list, most often for
want of permission. Its files are neither read nor counted as unread. When it is not empty, fix
the folder's permissions or exclude it.

### `not_executed`

Text heading: Rules not executed. Each row is a pack, a rule and the reason the engine cannot run
it, such as a key the engine does not support. The rule made nothing. When it is not empty, read
the reason: rewrite the rule in a form the engine runs, or accept the gap.

### `skipped`

Text heading: Matches skipped. Each row is a file, a line, a rule and the reason. The rule matched
there but could not build the node or edge it emits, so nothing was made for that match. When it
is not empty, open the file at the line. The shape there is one the rule does not cover.

### `zero_fires`

Text heading: Rules that fired zero times. Each row is a pack and a rule that ran over the project
and matched nothing. Most rules of a broad rutter fire zero times on a small project, as here.
When a rule you expected to fire is listed, the files hold a shape it does not match: plant that
shape alone in a small project to see why.

### `differing`

Text heading: Attributes that differ between files. Each row is a node and an attribute that two
files give different values. The map writes the attribute as `differs` rather than pick one. When
it is not empty, find the files that declare the node and decide which value is right.

### `executed`

Text heading: Rules executed. Each row is a pack, a rule and how many times it fired. It is the
count behind `zero_fires`. When a count is higher or lower than the files suggest, run the
navigation commands on the nodes the rule makes.

### `map_passes`

Text heading: Map rule passes. Map rules join what the file rules found. Each pass lists the map
rules that fired in it; the last pass adds nothing. An empty list means no map rule runs. There is
nothing to fix here; it explains edges no single file holds.

### `packs`

Text heading: Packs. Each row is a rutter and its version: the ones pinned and the ones they
depend on, such as `php_basic` here. When a version is not the one you pinned, run `periplus
status`.

### `selected`

Text: the `selected` count under Files. How many files the rules read. When it is lower than you
expect, compare it with `unread`.

### `opened`

Not in the text report. The JSON list of the files the rules opened, in order. Use it to confirm a
file was read at all.

### `excluded`

Text: the `excluded` count under Files. How many files the exclude patterns in the settings
removed. When it is higher than you expect, check the patterns.

### `nodes`

Text: the `nodes` count under Map. How many nodes the map holds. When it is lower than you
expect, check `unread` for files no rule read and `skipped` for matches that made
nothing.

### `edges`

Text: the `edges` count under Map. How many edges the map holds. With `nodes`, it is the quickest
sign that a change to a rule did something.

### `map`

Text: the `path` row under Map. Where the map was written, or `null` when a problem stopped the
run. Read the map with the navigation commands in [docs/navigation.md](navigation.md).

## Read the map

The setting `greetBanner` is one node. The `.module` file provides it and the behavior reads it.

<!-- nav-run -->
```
$ periplus show drupal.js_setting::greetBanner
periplus show drupal.js_setting::greetBanner
type: drupal.js_setting
state: mapped
location: web/modules/custom/greet/greet.module:11
provenance: drupal_js_basic:setting_attached_in_array  declared

Outgoing (0):
  none

Incoming (2):
  provides_setting:
    php.function::greet_preprocess_page  php.function  mapped  web/modules/custom/greet/greet.module:11  x1  inferred  drupal_js_basic:setting_attached_in_array_in_function
  reads_setting:
    drupal.js_behavior::greetBanner  drupal.js_behavior  mapped  web/modules/custom/greet/js/banner.js:4  x1  declared  drupal_js_basic:setting_read_in_behavior
```

The script reaches the behavior it declares and the path it fetches whole.

<!-- nav-run -->
```
$ periplus neighbors js.file::web/modules/custom/greet/js/banner.js
periplus neighbors js.file::web/modules/custom/greet/js/banner.js
2 items
  1  drupal.js_behavior::greetBanner  drupal.js_behavior  mapped  via script_declares_behavior from js.file::web/modules/custom/greet/js/banner.js
  1  drupal.url_path::/greet/hello  drupal.url_path  referenced  via script_links_to_path from js.file::web/modules/custom/greet/js/banner.js
```

## A shape the map lacks

The map lacks a node or an edge the code holds. Before you write a rule for it, look for it in two
places: [docs/known-limitations.md](known-limitations.md), and the Known gaps comment at the top of
the `pack.yaml` of the rutter that maps that part of the stack. A shape listed there is a stated
limitation: the rutter's authors saw it and left it out, so it needs a new rule, not a fix.

Do not wait for the report to point at it. A rutter refuses a shape by not matching it, so a
refused shape beside shapes the rule accepts leaves no report row at all: the rule fires on the
accepted ones and is listed under `executed` with its count. The report shows a limitation only
in two cases: a rule that matched nothing in the whole project, under `zero_fires`, and a match the
rule found and could not finish, under `skipped`. The three examples below show both rows, and a
shape that leaves none.

A path joined with `+` is a stated limitation of `drupal_js_basic`. In the planted project its
rule `path_in_script_string` fires once, on the whole path, and the joined path leaves no row. A
second project, `joined-only`, beside the planted one, holds one script with only a joined path.

<!-- nav-file: joined-only/.periplus/settings.yml -->
```yaml
periplus_version: 0
packs:
  - drupal_basic@0.3.0
  - js_basic@0.0.1
  - drupal_js_basic@0.0.1
```

<!-- nav-file: joined-only/js/join.js -->
```js
const id = 7;
fetch('/join/user/' + id);
```

Mapped there, the report lists `path_in_script_string` under `zero_fires`, in the text heading
Rules that fired zero times.

<details>
<summary>The text report of joined-only</summary>

<!-- nav-run: joined-only -->
```
$ periplus map
periplus map

Map:
  path    /path/to/project/.periplus/map.json
  nodes   1
  edges   0

Files:
  selected  1
  excluded  0
  unread    1
  unlisted  0

Files no rule read, by ending:
  yml 1

Files no rule read:
  .periplus/settings.yml

Folders that could not be listed:
  none

Files that did not parse cleanly:
  none

Packs:
  drupal_basic 0.3.0
  drupal_js_basic 0.0.1
  js_basic 0.0.1
  php_basic 0.2.0
  twig_basic 0.1.0
  yaml_basic 0.1.0

Rules executed:
  drupal_basic action_from_annotation fired 0
  drupal_basic action_from_annotation_edges fired 0
  drupal_basic action_from_attribute fired 0
  drupal_basic action_from_attribute_edges fired 0
  drupal_basic any_config_file fired 0
  drupal_basic any_config_file_edges fired 0
  drupal_basic block_placement_from_config fired 0
  drupal_basic block_placement_from_config_edges fired 0
  drupal_basic block_plugin_from_annotation fired 0
  drupal_basic block_plugin_from_annotation_edges fired 0
  drupal_basic block_plugin_from_attribute fired 0
  drupal_basic block_plugin_from_attribute_edges fired 0
  drupal_basic block_type_from_config fired 0
  drupal_basic block_type_from_config_edges fired 0
  drupal_basic bundle_comment_from_config fired 0
  drupal_basic bundle_comment_from_config_edges fired 0
  drupal_basic bundle_contact_message_from_config fired 0
  drupal_basic bundle_contact_message_from_config_edges fired 0
  drupal_basic bundle_group_from_config fired 0
  drupal_basic bundle_group_from_config_edges fired 0
  drupal_basic bundle_group_relationship_from_config fired 0
  drupal_basic bundle_group_relationship_from_config_edges fired 0
  drupal_basic bundle_media_from_config fired 0
  drupal_basic bundle_media_from_config_edges fired 0
  drupal_basic bundle_node_from_config fired 0
  drupal_basic bundle_node_from_config_edges fired 0
  drupal_basic bundle_shortcut_from_config fired 0
  drupal_basic bundle_shortcut_from_config_edges fired 0
  drupal_basic bundle_taxonomy_term_from_config fired 0
  drupal_basic bundle_taxonomy_term_from_config_edges fired 0
  drupal_basic calls_through_service_property fired 0
  drupal_basic captcha_point_form fired 0
  drupal_basic component_file fired 0
  drupal_basic component_included_in_template fired 0
  drupal_basic config_entity_type_from_annotation fired 0
  drupal_basic config_entity_type_from_annotation_edges fired 0
  drupal_basic config_entity_type_from_attribute fired 0
  drupal_basic config_entity_type_from_attribute_edges fired 0
  drupal_basic constraint_from_annotation fired 0
  drupal_basic constraint_from_annotation_edges fired 0
  drupal_basic constraint_from_attribute fired 0
  drupal_basic constraint_from_attribute_edges fired 0
  drupal_basic container_entity_call fired 0
  drupal_basic container_get_call fired 0
  drupal_basic container_nullsafe_get_call fired 0
  drupal_basic content_entity_type_from_annotation fired 0
  drupal_basic content_entity_type_from_annotation_edges fired 0
  drupal_basic content_entity_type_from_attribute fired 0
  drupal_basic content_entity_type_from_attribute_edges fired 0
  drupal_basic display_block_type_edges fired 0
  drupal_basic display_bundle_edges fired 0
  drupal_basic display_bundle_of_edges fired 0
  drupal_basic drupal_shortcut_call fired 0
  drupal_basic entity_call_through_typed_manager fired 0
  drupal_basic entity_class_static_call fired 0
  drupal_basic entity_handler_call fired 0
  drupal_basic entity_query_call fired 0
  drupal_basic field_formatter_from_annotation fired 0
  drupal_basic field_formatter_from_annotation_edges fired 0
  drupal_basic field_formatter_from_attribute fired 0
  drupal_basic field_formatter_from_attribute_edges fired 0
  drupal_basic field_instance_block_type_edges fired 0
  drupal_basic field_instance_bundle_edges fired 0
  drupal_basic field_instance_bundle_of_edges fired 0
  drupal_basic field_instance_from_config fired 0
  drupal_basic field_instance_from_config_edges fired 0
  drupal_basic field_storage_from_config fired 0
  drupal_basic field_storage_from_config_edges fired 0
  drupal_basic field_type_from_annotation fired 0
  drupal_basic field_type_from_annotation_edges fired 0
  drupal_basic field_type_from_attribute fired 0
  drupal_basic field_type_from_attribute_edges fired 0
  drupal_basic field_widget_from_annotation fired 0
  drupal_basic field_widget_from_annotation_edges fired 0
  drupal_basic field_widget_from_attribute fired 0
  drupal_basic field_widget_from_attribute_edges fired 0
  drupal_basic form_class_has_id fired 0
  drupal_basic form_display_from_config fired 0
  drupal_basic form_display_from_config_edges fired 0
  drupal_basic form_display_mode_edges fired 0
  drupal_basic form_id_returned fired 0
  drupal_basic form_mode_from_config fired 0
  drupal_basic function_implements_hook fired 0
  drupal_basic honeypot_forms fired 0
  drupal_basic hook_acts_on_entity_type fired 0
  drupal_basic hook_attribute_acts_on_entity_type fired 0
  drupal_basic hook_from_attribute fired 0
  drupal_basic hook_from_function_name fired 0
  drupal_basic hook_from_named_attribute fired 0
  drupal_basic hook_from_theme_include fired 0
  drupal_basic internal_uri_url_call fired 0
  drupal_basic library_from_libraries_file fired 0
  drupal_basic library_from_libraries_file_edges fired 0
  drupal_basic local_action_from_links_file fired 0
  drupal_basic local_action_from_links_file_edges fired 0
  drupal_basic local_manager_entity_call fired 0
  drupal_basic mail_from_attribute fired 0
  drupal_basic mail_from_attribute_edges fired 0
  drupal_basic manager_call fired 0
  drupal_basic manager_call_in fired 0
  drupal_basic manager_nullsafe_call fired 0
  drupal_basic manager_nullsafe_call_in fired 0
  drupal_basic media_source_from_annotation fired 0
  drupal_basic media_source_from_annotation_edges fired 0
  drupal_basic media_source_from_attribute fired 0
  drupal_basic media_source_from_attribute_edges fired 0
  drupal_basic media_source_from_oembed_attribute fired 0
  drupal_basic media_source_from_oembed_attribute_edges fired 0
  drupal_basic menu_link_from_links_file fired 0
  drupal_basic menu_link_from_links_file_edges fired 0
  drupal_basic mode_entity_type_edges fired 0
  drupal_basic module_from_info_file fired 0
  drupal_basic module_from_info_file_edges fired 0
  drupal_basic path_in_template_attribute fired 0
  drupal_basic permission_from_permissions_file fired 0
  drupal_basic queue_worker_from_annotation fired 0
  drupal_basic queue_worker_from_annotation_edges fired 0
  drupal_basic queue_worker_from_attribute fired 0
  drupal_basic queue_worker_from_attribute_edges fired 0
  drupal_basic rest_resource_from_annotation fired 0
  drupal_basic rest_resource_from_annotation_edges fired 0
  drupal_basic rest_resource_from_attribute fired 0
  drupal_basic rest_resource_from_attribute_edges fired 0
  drupal_basic role_from_config fired 0
  drupal_basic role_from_config_edges fired 0
  drupal_basic route_from_routing_file fired 0
  drupal_basic route_from_routing_file_edges fired 0
  drupal_basic route_linked_in_template fired 0
  drupal_basic route_options_from_routing_file fired 0
  drupal_basic route_options_from_routing_file_edges fired 0
  drupal_basic route_requirements_from_routing_file fired 0
  drupal_basic route_requirements_from_routing_file_edges fired 0
  drupal_basic service_alias_from_services_file fired 0
  drupal_basic service_call fired 0
  drupal_basic service_from_services_file fired 0
  drupal_basic service_from_services_file_class fired 0
  drupal_basic service_from_services_file_class_key fired 0
  drupal_basic service_from_services_file_edges fired 0
  drupal_basic service_text_alias_from_services_file fired 0
  drupal_basic simple_config_owner fired 0
  drupal_basic storage_call fired 0
  drupal_basic storage_nullsafe_call fired 0
  drupal_basic template_file fired 0
  drupal_basic template_included_in_template fired 0
  drupal_basic template_suggests_bundle fired 0
  drupal_basic theme_from_info_file fired 0
  drupal_basic theme_from_info_file_edges fired 0
  drupal_basic theme_hook_default_template fired 0
  drupal_basic theme_hook_entry fired 0
  drupal_basic theme_hook_rendered_in_class fired 0
  drupal_basic theme_hook_template_key fired 0
  drupal_basic theme_include_implements_hook fired 0
  drupal_basic user_input_url_call fired 0
  drupal_basic view_display_from_config fired 0
  drupal_basic view_display_from_config_edges fired 0
  drupal_basic view_display_mode_edges fired 0
  drupal_basic view_mode_from_config fired 0
  drupal_basic views_field_from_attribute fired 0
  drupal_basic views_field_from_attribute_edges fired 0
  drupal_basic views_field_from_named_attribute fired 0
  drupal_basic views_field_from_named_attribute_edges fired 0
  drupal_basic views_filter_from_attribute fired 0
  drupal_basic views_filter_from_attribute_edges fired 0
  drupal_basic views_filter_from_named_attribute fired 0
  drupal_basic views_filter_from_named_attribute_edges fired 0
  drupal_basic views_style_from_attribute fired 0
  drupal_basic views_style_from_attribute_edges fired 0
  drupal_basic views_style_from_named_attribute fired 0
  drupal_basic views_style_from_named_attribute_edges fired 0
  drupal_js_basic behavior_attach_call fired 0
  drupal_js_basic behavior_from_arrow fired 0
  drupal_js_basic behavior_from_arrow_in_file fired 0
  drupal_js_basic behavior_from_assignment fired 0
  drupal_js_basic behavior_from_assignment_in_file fired 0
  drupal_js_basic behavior_from_function fired 0
  drupal_js_basic behavior_from_function_in_file fired 0
  drupal_js_basic library_attached_in_array fired 0
  drupal_js_basic library_attached_in_array_in_function fired 0
  drupal_js_basic library_attached_in_class fired 0
  drupal_js_basic library_attached_in_component fired 0
  drupal_js_basic library_attached_in_template fired 0
  drupal_js_basic library_script fired 0
  drupal_js_basic library_stylesheet fired 0
  drupal_js_basic path_in_script_string fired 0
  drupal_js_basic php_function_holds_body fired 0
  drupal_js_basic setting_attached fired 0
  drupal_js_basic setting_attached_in_array fired 0
  drupal_js_basic setting_attached_in_array_in_class fired 0
  drupal_js_basic setting_attached_in_array_in_function fired 0
  drupal_js_basic setting_attached_in_class fired 0
  drupal_js_basic setting_read_in_behavior fired 0
  drupal_js_basic stylesheet_file fired 0
  js_basic function_declaration fired 0
  js_basic function_declaration_in_file fired 0
  js_basic function_from_arrow fired 0
  js_basic function_from_arrow_in_file fired 0
  js_basic function_from_expression fired 0
  js_basic function_from_expression_in_file fired 0
  js_basic script_file fired 1
  php_basic assigned_value fired 0
  php_basic call_site_method fired 0
  php_basic calls_function fired 0
  php_basic calls_static_method fired 0
  php_basic calls_through_assigned_property fired 0
  php_basic calls_through_property_assigned_here fired 0
  php_basic calls_through_typed_property fired 0
  php_basic contains_method fired 0
  php_basic declares_property fired 0
  php_basic find_call_site fired 0
  php_basic find_class fired 0
  php_basic find_enum fired 0
  php_basic find_function fired 0
  php_basic find_interface fired 0
  php_basic find_member_assignment fired 0
  php_basic find_member_assignment_value fired 0
  php_basic find_method fired 0
  php_basic find_nullable_promoted_property_type fired 0
  php_basic find_nullable_property_type fired 0
  php_basic find_parameter fired 0
  php_basic find_parameter_type fired 0
  php_basic find_promoted_property fired 0
  php_basic find_promoted_property_type fired 0
  php_basic find_property fired 0
  php_basic find_property_type fired 0
  php_basic find_trait fired 0
  php_basic find_union_promoted_property_type fired 0
  php_basic find_union_property_type fired 0
  php_basic find_var_property_type fired 0
  php_basic implements_from_interface_clause fired 0
  php_basic inherits_from_base_clause fired 0
  php_basic mixes_in_from_use_declaration fired 0
  php_basic nullable_promoted_property_typed_as fired 0
  php_basic nullable_property_typed_as fired 0
  php_basic parameter_typed_as fired 0
  php_basic promoted_property_typed_as fired 0
  php_basic property_typed_as fired 0
  php_basic union_promoted_property_typed_as fired 0
  php_basic union_property_typed_as fired 0
  php_basic var_property_typed_as fired 0

Rules that fired zero times:
  drupal_basic action_from_annotation
  drupal_basic action_from_annotation_edges
  drupal_basic action_from_attribute
  drupal_basic action_from_attribute_edges
  drupal_basic any_config_file
  drupal_basic any_config_file_edges
  drupal_basic block_placement_from_config
  drupal_basic block_placement_from_config_edges
  drupal_basic block_plugin_from_annotation
  drupal_basic block_plugin_from_annotation_edges
  drupal_basic block_plugin_from_attribute
  drupal_basic block_plugin_from_attribute_edges
  drupal_basic block_type_from_config
  drupal_basic block_type_from_config_edges
  drupal_basic bundle_comment_from_config
  drupal_basic bundle_comment_from_config_edges
  drupal_basic bundle_contact_message_from_config
  drupal_basic bundle_contact_message_from_config_edges
  drupal_basic bundle_group_from_config
  drupal_basic bundle_group_from_config_edges
  drupal_basic bundle_group_relationship_from_config
  drupal_basic bundle_group_relationship_from_config_edges
  drupal_basic bundle_media_from_config
  drupal_basic bundle_media_from_config_edges
  drupal_basic bundle_node_from_config
  drupal_basic bundle_node_from_config_edges
  drupal_basic bundle_shortcut_from_config
  drupal_basic bundle_shortcut_from_config_edges
  drupal_basic bundle_taxonomy_term_from_config
  drupal_basic bundle_taxonomy_term_from_config_edges
  drupal_basic calls_through_service_property
  drupal_basic captcha_point_form
  drupal_basic component_file
  drupal_basic component_included_in_template
  drupal_basic config_entity_type_from_annotation
  drupal_basic config_entity_type_from_annotation_edges
  drupal_basic config_entity_type_from_attribute
  drupal_basic config_entity_type_from_attribute_edges
  drupal_basic constraint_from_annotation
  drupal_basic constraint_from_annotation_edges
  drupal_basic constraint_from_attribute
  drupal_basic constraint_from_attribute_edges
  drupal_basic container_entity_call
  drupal_basic container_get_call
  drupal_basic container_nullsafe_get_call
  drupal_basic content_entity_type_from_annotation
  drupal_basic content_entity_type_from_annotation_edges
  drupal_basic content_entity_type_from_attribute
  drupal_basic content_entity_type_from_attribute_edges
  drupal_basic display_block_type_edges
  drupal_basic display_bundle_edges
  drupal_basic display_bundle_of_edges
  drupal_basic drupal_shortcut_call
  drupal_basic entity_call_through_typed_manager
  drupal_basic entity_class_static_call
  drupal_basic entity_handler_call
  drupal_basic entity_query_call
  drupal_basic field_formatter_from_annotation
  drupal_basic field_formatter_from_annotation_edges
  drupal_basic field_formatter_from_attribute
  drupal_basic field_formatter_from_attribute_edges
  drupal_basic field_instance_block_type_edges
  drupal_basic field_instance_bundle_edges
  drupal_basic field_instance_bundle_of_edges
  drupal_basic field_instance_from_config
  drupal_basic field_instance_from_config_edges
  drupal_basic field_storage_from_config
  drupal_basic field_storage_from_config_edges
  drupal_basic field_type_from_annotation
  drupal_basic field_type_from_annotation_edges
  drupal_basic field_type_from_attribute
  drupal_basic field_type_from_attribute_edges
  drupal_basic field_widget_from_annotation
  drupal_basic field_widget_from_annotation_edges
  drupal_basic field_widget_from_attribute
  drupal_basic field_widget_from_attribute_edges
  drupal_basic form_class_has_id
  drupal_basic form_display_from_config
  drupal_basic form_display_from_config_edges
  drupal_basic form_display_mode_edges
  drupal_basic form_id_returned
  drupal_basic form_mode_from_config
  drupal_basic function_implements_hook
  drupal_basic honeypot_forms
  drupal_basic hook_acts_on_entity_type
  drupal_basic hook_attribute_acts_on_entity_type
  drupal_basic hook_from_attribute
  drupal_basic hook_from_function_name
  drupal_basic hook_from_named_attribute
  drupal_basic hook_from_theme_include
  drupal_basic internal_uri_url_call
  drupal_basic library_from_libraries_file
  drupal_basic library_from_libraries_file_edges
  drupal_basic local_action_from_links_file
  drupal_basic local_action_from_links_file_edges
  drupal_basic local_manager_entity_call
  drupal_basic mail_from_attribute
  drupal_basic mail_from_attribute_edges
  drupal_basic manager_call
  drupal_basic manager_call_in
  drupal_basic manager_nullsafe_call
  drupal_basic manager_nullsafe_call_in
  drupal_basic media_source_from_annotation
  drupal_basic media_source_from_annotation_edges
  drupal_basic media_source_from_attribute
  drupal_basic media_source_from_attribute_edges
  drupal_basic media_source_from_oembed_attribute
  drupal_basic media_source_from_oembed_attribute_edges
  drupal_basic menu_link_from_links_file
  drupal_basic menu_link_from_links_file_edges
  drupal_basic mode_entity_type_edges
  drupal_basic module_from_info_file
  drupal_basic module_from_info_file_edges
  drupal_basic path_in_template_attribute
  drupal_basic permission_from_permissions_file
  drupal_basic queue_worker_from_annotation
  drupal_basic queue_worker_from_annotation_edges
  drupal_basic queue_worker_from_attribute
  drupal_basic queue_worker_from_attribute_edges
  drupal_basic rest_resource_from_annotation
  drupal_basic rest_resource_from_annotation_edges
  drupal_basic rest_resource_from_attribute
  drupal_basic rest_resource_from_attribute_edges
  drupal_basic role_from_config
  drupal_basic role_from_config_edges
  drupal_basic route_from_routing_file
  drupal_basic route_from_routing_file_edges
  drupal_basic route_linked_in_template
  drupal_basic route_options_from_routing_file
  drupal_basic route_options_from_routing_file_edges
  drupal_basic route_requirements_from_routing_file
  drupal_basic route_requirements_from_routing_file_edges
  drupal_basic service_alias_from_services_file
  drupal_basic service_call
  drupal_basic service_from_services_file
  drupal_basic service_from_services_file_class
  drupal_basic service_from_services_file_class_key
  drupal_basic service_from_services_file_edges
  drupal_basic service_text_alias_from_services_file
  drupal_basic simple_config_owner
  drupal_basic storage_call
  drupal_basic storage_nullsafe_call
  drupal_basic template_file
  drupal_basic template_included_in_template
  drupal_basic template_suggests_bundle
  drupal_basic theme_from_info_file
  drupal_basic theme_from_info_file_edges
  drupal_basic theme_hook_default_template
  drupal_basic theme_hook_entry
  drupal_basic theme_hook_rendered_in_class
  drupal_basic theme_hook_template_key
  drupal_basic theme_include_implements_hook
  drupal_basic user_input_url_call
  drupal_basic view_display_from_config
  drupal_basic view_display_from_config_edges
  drupal_basic view_display_mode_edges
  drupal_basic view_mode_from_config
  drupal_basic views_field_from_attribute
  drupal_basic views_field_from_attribute_edges
  drupal_basic views_field_from_named_attribute
  drupal_basic views_field_from_named_attribute_edges
  drupal_basic views_filter_from_attribute
  drupal_basic views_filter_from_attribute_edges
  drupal_basic views_filter_from_named_attribute
  drupal_basic views_filter_from_named_attribute_edges
  drupal_basic views_style_from_attribute
  drupal_basic views_style_from_attribute_edges
  drupal_basic views_style_from_named_attribute
  drupal_basic views_style_from_named_attribute_edges
  drupal_js_basic behavior_attach_call
  drupal_js_basic behavior_from_arrow
  drupal_js_basic behavior_from_arrow_in_file
  drupal_js_basic behavior_from_assignment
  drupal_js_basic behavior_from_assignment_in_file
  drupal_js_basic behavior_from_function
  drupal_js_basic behavior_from_function_in_file
  drupal_js_basic library_attached_in_array
  drupal_js_basic library_attached_in_array_in_function
  drupal_js_basic library_attached_in_class
  drupal_js_basic library_attached_in_component
  drupal_js_basic library_attached_in_template
  drupal_js_basic library_script
  drupal_js_basic library_stylesheet
  drupal_js_basic path_in_script_string
  drupal_js_basic php_function_holds_body
  drupal_js_basic setting_attached
  drupal_js_basic setting_attached_in_array
  drupal_js_basic setting_attached_in_array_in_class
  drupal_js_basic setting_attached_in_array_in_function
  drupal_js_basic setting_attached_in_class
  drupal_js_basic setting_read_in_behavior
  drupal_js_basic stylesheet_file
  js_basic function_declaration
  js_basic function_declaration_in_file
  js_basic function_from_arrow
  js_basic function_from_arrow_in_file
  js_basic function_from_expression
  js_basic function_from_expression_in_file
  php_basic assigned_value
  php_basic call_site_method
  php_basic calls_function
  php_basic calls_static_method
  php_basic calls_through_assigned_property
  php_basic calls_through_property_assigned_here
  php_basic calls_through_typed_property
  php_basic contains_method
  php_basic declares_property
  php_basic find_call_site
  php_basic find_class
  php_basic find_enum
  php_basic find_function
  php_basic find_interface
  php_basic find_member_assignment
  php_basic find_member_assignment_value
  php_basic find_method
  php_basic find_nullable_promoted_property_type
  php_basic find_nullable_property_type
  php_basic find_parameter
  php_basic find_parameter_type
  php_basic find_promoted_property
  php_basic find_promoted_property_type
  php_basic find_property
  php_basic find_property_type
  php_basic find_trait
  php_basic find_union_promoted_property_type
  php_basic find_union_property_type
  php_basic find_var_property_type
  php_basic implements_from_interface_clause
  php_basic inherits_from_base_clause
  php_basic mixes_in_from_use_declaration
  php_basic nullable_promoted_property_typed_as
  php_basic nullable_property_typed_as
  php_basic parameter_typed_as
  php_basic promoted_property_typed_as
  php_basic property_typed_as
  php_basic union_promoted_property_typed_as
  php_basic union_property_typed_as
  php_basic var_property_typed_as

Map rule passes:
  pass 1: none

Rules not executed:
  none

Matches skipped:
  none

Attributes that differ between files:
  none

Problems:
  none
```

</details>

A library that lists only a URL is a stated limitation too: the URL names no file to map. The rule
`library_script` matches the entry of the library `cdn` in the planted libraries file and cannot
build an edge from it, so the report of the planted project lists it under `skipped`, in the text
heading Matches skipped, at its libraries file.

<details>
<summary>The text report of the planted project</summary>

<!-- nav-run -->
```
$ periplus map
periplus map

Map:
  path    /path/to/project/.periplus/map.json
  nodes   11
  edges   7

Files:
  selected  5
  excluded  0
  unread    4
  unlisted  0

Files no rule read, by ending:
  yaml 2
  json 1
  yml 1

Files no rule read:
  .periplus/map.json
  .periplus/packs/myproject@0.0.1/event.yaml
  .periplus/packs/myproject@0.0.1/pack.yaml
  .periplus/settings.yml

Folders that could not be listed:
  none

Files that did not parse cleanly:
  none

Packs:
  drupal_basic 0.3.0
  drupal_js_basic 0.0.1
  js_basic 0.0.1
  myproject 0.0.1
  php_basic 0.2.0
  twig_basic 0.1.0
  yaml_basic 0.1.0

Rules executed:
  drupal_basic action_from_annotation fired 0
  drupal_basic action_from_annotation_edges fired 0
  drupal_basic action_from_attribute fired 0
  drupal_basic action_from_attribute_edges fired 0
  drupal_basic any_config_file fired 0
  drupal_basic any_config_file_edges fired 0
  drupal_basic block_placement_from_config fired 0
  drupal_basic block_placement_from_config_edges fired 0
  drupal_basic block_plugin_from_annotation fired 0
  drupal_basic block_plugin_from_annotation_edges fired 0
  drupal_basic block_plugin_from_attribute fired 0
  drupal_basic block_plugin_from_attribute_edges fired 0
  drupal_basic block_type_from_config fired 0
  drupal_basic block_type_from_config_edges fired 0
  drupal_basic bundle_comment_from_config fired 0
  drupal_basic bundle_comment_from_config_edges fired 0
  drupal_basic bundle_contact_message_from_config fired 0
  drupal_basic bundle_contact_message_from_config_edges fired 0
  drupal_basic bundle_group_from_config fired 0
  drupal_basic bundle_group_from_config_edges fired 0
  drupal_basic bundle_group_relationship_from_config fired 0
  drupal_basic bundle_group_relationship_from_config_edges fired 0
  drupal_basic bundle_media_from_config fired 0
  drupal_basic bundle_media_from_config_edges fired 0
  drupal_basic bundle_node_from_config fired 0
  drupal_basic bundle_node_from_config_edges fired 0
  drupal_basic bundle_shortcut_from_config fired 0
  drupal_basic bundle_shortcut_from_config_edges fired 0
  drupal_basic bundle_taxonomy_term_from_config fired 0
  drupal_basic bundle_taxonomy_term_from_config_edges fired 0
  drupal_basic calls_through_service_property fired 0
  drupal_basic captcha_point_form fired 0
  drupal_basic component_file fired 0
  drupal_basic component_included_in_template fired 0
  drupal_basic config_entity_type_from_annotation fired 0
  drupal_basic config_entity_type_from_annotation_edges fired 0
  drupal_basic config_entity_type_from_attribute fired 0
  drupal_basic config_entity_type_from_attribute_edges fired 0
  drupal_basic constraint_from_annotation fired 0
  drupal_basic constraint_from_annotation_edges fired 0
  drupal_basic constraint_from_attribute fired 0
  drupal_basic constraint_from_attribute_edges fired 0
  drupal_basic container_entity_call fired 0
  drupal_basic container_get_call fired 0
  drupal_basic container_nullsafe_get_call fired 0
  drupal_basic content_entity_type_from_annotation fired 0
  drupal_basic content_entity_type_from_annotation_edges fired 0
  drupal_basic content_entity_type_from_attribute fired 0
  drupal_basic content_entity_type_from_attribute_edges fired 0
  drupal_basic display_block_type_edges fired 0
  drupal_basic display_bundle_edges fired 0
  drupal_basic display_bundle_of_edges fired 0
  drupal_basic drupal_shortcut_call fired 0
  drupal_basic entity_call_through_typed_manager fired 0
  drupal_basic entity_class_static_call fired 0
  drupal_basic entity_handler_call fired 0
  drupal_basic entity_query_call fired 0
  drupal_basic field_formatter_from_annotation fired 0
  drupal_basic field_formatter_from_annotation_edges fired 0
  drupal_basic field_formatter_from_attribute fired 0
  drupal_basic field_formatter_from_attribute_edges fired 0
  drupal_basic field_instance_block_type_edges fired 0
  drupal_basic field_instance_bundle_edges fired 0
  drupal_basic field_instance_bundle_of_edges fired 0
  drupal_basic field_instance_from_config fired 0
  drupal_basic field_instance_from_config_edges fired 0
  drupal_basic field_storage_from_config fired 0
  drupal_basic field_storage_from_config_edges fired 0
  drupal_basic field_type_from_annotation fired 0
  drupal_basic field_type_from_annotation_edges fired 0
  drupal_basic field_type_from_attribute fired 0
  drupal_basic field_type_from_attribute_edges fired 0
  drupal_basic field_widget_from_annotation fired 0
  drupal_basic field_widget_from_annotation_edges fired 0
  drupal_basic field_widget_from_attribute fired 0
  drupal_basic field_widget_from_attribute_edges fired 0
  drupal_basic form_class_has_id fired 0
  drupal_basic form_display_from_config fired 0
  drupal_basic form_display_from_config_edges fired 0
  drupal_basic form_display_mode_edges fired 0
  drupal_basic form_id_returned fired 0
  drupal_basic form_mode_from_config fired 0
  drupal_basic function_implements_hook fired 1
  drupal_basic honeypot_forms fired 0
  drupal_basic hook_acts_on_entity_type fired 0
  drupal_basic hook_attribute_acts_on_entity_type fired 0
  drupal_basic hook_from_attribute fired 0
  drupal_basic hook_from_function_name fired 1
  drupal_basic hook_from_named_attribute fired 0
  drupal_basic hook_from_theme_include fired 0
  drupal_basic internal_uri_url_call fired 0
  drupal_basic library_from_libraries_file fired 2
  drupal_basic library_from_libraries_file_edges fired 2
  drupal_basic local_action_from_links_file fired 0
  drupal_basic local_action_from_links_file_edges fired 0
  drupal_basic local_manager_entity_call fired 0
  drupal_basic mail_from_attribute fired 0
  drupal_basic mail_from_attribute_edges fired 0
  drupal_basic manager_call fired 0
  drupal_basic manager_call_in fired 0
  drupal_basic manager_nullsafe_call fired 0
  drupal_basic manager_nullsafe_call_in fired 0
  drupal_basic media_source_from_annotation fired 0
  drupal_basic media_source_from_annotation_edges fired 0
  drupal_basic media_source_from_attribute fired 0
  drupal_basic media_source_from_attribute_edges fired 0
  drupal_basic media_source_from_oembed_attribute fired 0
  drupal_basic media_source_from_oembed_attribute_edges fired 0
  drupal_basic menu_link_from_links_file fired 0
  drupal_basic menu_link_from_links_file_edges fired 0
  drupal_basic mode_entity_type_edges fired 0
  drupal_basic module_from_info_file fired 1
  drupal_basic module_from_info_file_edges fired 1
  drupal_basic path_in_template_attribute fired 0
  drupal_basic permission_from_permissions_file fired 0
  drupal_basic queue_worker_from_annotation fired 0
  drupal_basic queue_worker_from_annotation_edges fired 0
  drupal_basic queue_worker_from_attribute fired 0
  drupal_basic queue_worker_from_attribute_edges fired 0
  drupal_basic rest_resource_from_annotation fired 0
  drupal_basic rest_resource_from_annotation_edges fired 0
  drupal_basic rest_resource_from_attribute fired 0
  drupal_basic rest_resource_from_attribute_edges fired 0
  drupal_basic role_from_config fired 0
  drupal_basic role_from_config_edges fired 0
  drupal_basic route_from_routing_file fired 0
  drupal_basic route_from_routing_file_edges fired 0
  drupal_basic route_linked_in_template fired 0
  drupal_basic route_options_from_routing_file fired 0
  drupal_basic route_options_from_routing_file_edges fired 0
  drupal_basic route_requirements_from_routing_file fired 0
  drupal_basic route_requirements_from_routing_file_edges fired 0
  drupal_basic service_alias_from_services_file fired 0
  drupal_basic service_call fired 0
  drupal_basic service_from_services_file fired 0
  drupal_basic service_from_services_file_class fired 0
  drupal_basic service_from_services_file_class_key fired 0
  drupal_basic service_from_services_file_edges fired 0
  drupal_basic service_text_alias_from_services_file fired 0
  drupal_basic simple_config_owner fired 0
  drupal_basic storage_call fired 0
  drupal_basic storage_nullsafe_call fired 0
  drupal_basic template_file fired 1
  drupal_basic template_included_in_template fired 0
  drupal_basic template_suggests_bundle fired 0
  drupal_basic theme_from_info_file fired 0
  drupal_basic theme_from_info_file_edges fired 0
  drupal_basic theme_hook_default_template fired 0
  drupal_basic theme_hook_entry fired 0
  drupal_basic theme_hook_rendered_in_class fired 0
  drupal_basic theme_hook_template_key fired 0
  drupal_basic theme_include_implements_hook fired 0
  drupal_basic user_input_url_call fired 0
  drupal_basic view_display_from_config fired 0
  drupal_basic view_display_from_config_edges fired 0
  drupal_basic view_display_mode_edges fired 0
  drupal_basic view_mode_from_config fired 0
  drupal_basic views_field_from_attribute fired 0
  drupal_basic views_field_from_attribute_edges fired 0
  drupal_basic views_field_from_named_attribute fired 0
  drupal_basic views_field_from_named_attribute_edges fired 0
  drupal_basic views_filter_from_attribute fired 0
  drupal_basic views_filter_from_attribute_edges fired 0
  drupal_basic views_filter_from_named_attribute fired 0
  drupal_basic views_filter_from_named_attribute_edges fired 0
  drupal_basic views_style_from_attribute fired 0
  drupal_basic views_style_from_attribute_edges fired 0
  drupal_basic views_style_from_named_attribute fired 0
  drupal_basic views_style_from_named_attribute_edges fired 0
  drupal_js_basic behavior_attach_call fired 0
  drupal_js_basic behavior_from_arrow fired 0
  drupal_js_basic behavior_from_arrow_in_file fired 0
  drupal_js_basic behavior_from_assignment fired 1
  drupal_js_basic behavior_from_assignment_in_file fired 1
  drupal_js_basic behavior_from_function fired 0
  drupal_js_basic behavior_from_function_in_file fired 0
  drupal_js_basic library_attached_in_array fired 1
  drupal_js_basic library_attached_in_array_in_function fired 1
  drupal_js_basic library_attached_in_class fired 0
  drupal_js_basic library_attached_in_component fired 0
  drupal_js_basic library_attached_in_template fired 0
  drupal_js_basic library_script fired 2
  drupal_js_basic library_stylesheet fired 2
  drupal_js_basic path_in_script_string fired 1
  drupal_js_basic php_function_holds_body fired 1
  drupal_js_basic setting_attached fired 0
  drupal_js_basic setting_attached_in_array fired 1
  drupal_js_basic setting_attached_in_array_in_class fired 1
  drupal_js_basic setting_attached_in_array_in_function fired 1
  drupal_js_basic setting_attached_in_class fired 0
  drupal_js_basic setting_read_in_behavior fired 1
  drupal_js_basic stylesheet_file fired 0
  js_basic function_declaration fired 0
  js_basic function_declaration_in_file fired 0
  js_basic function_from_arrow fired 0
  js_basic function_from_arrow_in_file fired 0
  js_basic function_from_expression fired 0
  js_basic function_from_expression_in_file fired 0
  js_basic script_file fired 1
  myproject event_from_data_track fired 1
  php_basic assigned_value fired 0
  php_basic call_site_method fired 0
  php_basic calls_function fired 0
  php_basic calls_static_method fired 0
  php_basic calls_through_assigned_property fired 0
  php_basic calls_through_property_assigned_here fired 0
  php_basic calls_through_typed_property fired 0
  php_basic contains_method fired 0
  php_basic declares_property fired 0
  php_basic find_call_site fired 0
  php_basic find_class fired 0
  php_basic find_enum fired 0
  php_basic find_function fired 1
  php_basic find_interface fired 0
  php_basic find_member_assignment fired 0
  php_basic find_member_assignment_value fired 0
  php_basic find_method fired 0
  php_basic find_nullable_promoted_property_type fired 0
  php_basic find_nullable_property_type fired 0
  php_basic find_parameter fired 0
  php_basic find_parameter_type fired 0
  php_basic find_promoted_property fired 0
  php_basic find_promoted_property_type fired 0
  php_basic find_property fired 0
  php_basic find_property_type fired 0
  php_basic find_trait fired 0
  php_basic find_union_promoted_property_type fired 0
  php_basic find_union_property_type fired 0
  php_basic find_var_property_type fired 0
  php_basic implements_from_interface_clause fired 0
  php_basic inherits_from_base_clause fired 0
  php_basic mixes_in_from_use_declaration fired 0
  php_basic nullable_promoted_property_typed_as fired 0
  php_basic nullable_property_typed_as fired 0
  php_basic parameter_typed_as fired 0
  php_basic promoted_property_typed_as fired 0
  php_basic property_typed_as fired 0
  php_basic union_promoted_property_typed_as fired 0
  php_basic union_property_typed_as fired 0
  php_basic var_property_typed_as fired 0

Rules that fired zero times:
  drupal_basic action_from_annotation
  drupal_basic action_from_annotation_edges
  drupal_basic action_from_attribute
  drupal_basic action_from_attribute_edges
  drupal_basic any_config_file
  drupal_basic any_config_file_edges
  drupal_basic block_placement_from_config
  drupal_basic block_placement_from_config_edges
  drupal_basic block_plugin_from_annotation
  drupal_basic block_plugin_from_annotation_edges
  drupal_basic block_plugin_from_attribute
  drupal_basic block_plugin_from_attribute_edges
  drupal_basic block_type_from_config
  drupal_basic block_type_from_config_edges
  drupal_basic bundle_comment_from_config
  drupal_basic bundle_comment_from_config_edges
  drupal_basic bundle_contact_message_from_config
  drupal_basic bundle_contact_message_from_config_edges
  drupal_basic bundle_group_from_config
  drupal_basic bundle_group_from_config_edges
  drupal_basic bundle_group_relationship_from_config
  drupal_basic bundle_group_relationship_from_config_edges
  drupal_basic bundle_media_from_config
  drupal_basic bundle_media_from_config_edges
  drupal_basic bundle_node_from_config
  drupal_basic bundle_node_from_config_edges
  drupal_basic bundle_shortcut_from_config
  drupal_basic bundle_shortcut_from_config_edges
  drupal_basic bundle_taxonomy_term_from_config
  drupal_basic bundle_taxonomy_term_from_config_edges
  drupal_basic calls_through_service_property
  drupal_basic captcha_point_form
  drupal_basic component_file
  drupal_basic component_included_in_template
  drupal_basic config_entity_type_from_annotation
  drupal_basic config_entity_type_from_annotation_edges
  drupal_basic config_entity_type_from_attribute
  drupal_basic config_entity_type_from_attribute_edges
  drupal_basic constraint_from_annotation
  drupal_basic constraint_from_annotation_edges
  drupal_basic constraint_from_attribute
  drupal_basic constraint_from_attribute_edges
  drupal_basic container_entity_call
  drupal_basic container_get_call
  drupal_basic container_nullsafe_get_call
  drupal_basic content_entity_type_from_annotation
  drupal_basic content_entity_type_from_annotation_edges
  drupal_basic content_entity_type_from_attribute
  drupal_basic content_entity_type_from_attribute_edges
  drupal_basic display_block_type_edges
  drupal_basic display_bundle_edges
  drupal_basic display_bundle_of_edges
  drupal_basic drupal_shortcut_call
  drupal_basic entity_call_through_typed_manager
  drupal_basic entity_class_static_call
  drupal_basic entity_handler_call
  drupal_basic entity_query_call
  drupal_basic field_formatter_from_annotation
  drupal_basic field_formatter_from_annotation_edges
  drupal_basic field_formatter_from_attribute
  drupal_basic field_formatter_from_attribute_edges
  drupal_basic field_instance_block_type_edges
  drupal_basic field_instance_bundle_edges
  drupal_basic field_instance_bundle_of_edges
  drupal_basic field_instance_from_config
  drupal_basic field_instance_from_config_edges
  drupal_basic field_storage_from_config
  drupal_basic field_storage_from_config_edges
  drupal_basic field_type_from_annotation
  drupal_basic field_type_from_annotation_edges
  drupal_basic field_type_from_attribute
  drupal_basic field_type_from_attribute_edges
  drupal_basic field_widget_from_annotation
  drupal_basic field_widget_from_annotation_edges
  drupal_basic field_widget_from_attribute
  drupal_basic field_widget_from_attribute_edges
  drupal_basic form_class_has_id
  drupal_basic form_display_from_config
  drupal_basic form_display_from_config_edges
  drupal_basic form_display_mode_edges
  drupal_basic form_id_returned
  drupal_basic form_mode_from_config
  drupal_basic honeypot_forms
  drupal_basic hook_acts_on_entity_type
  drupal_basic hook_attribute_acts_on_entity_type
  drupal_basic hook_from_attribute
  drupal_basic hook_from_named_attribute
  drupal_basic hook_from_theme_include
  drupal_basic internal_uri_url_call
  drupal_basic local_action_from_links_file
  drupal_basic local_action_from_links_file_edges
  drupal_basic local_manager_entity_call
  drupal_basic mail_from_attribute
  drupal_basic mail_from_attribute_edges
  drupal_basic manager_call
  drupal_basic manager_call_in
  drupal_basic manager_nullsafe_call
  drupal_basic manager_nullsafe_call_in
  drupal_basic media_source_from_annotation
  drupal_basic media_source_from_annotation_edges
  drupal_basic media_source_from_attribute
  drupal_basic media_source_from_attribute_edges
  drupal_basic media_source_from_oembed_attribute
  drupal_basic media_source_from_oembed_attribute_edges
  drupal_basic menu_link_from_links_file
  drupal_basic menu_link_from_links_file_edges
  drupal_basic mode_entity_type_edges
  drupal_basic path_in_template_attribute
  drupal_basic permission_from_permissions_file
  drupal_basic queue_worker_from_annotation
  drupal_basic queue_worker_from_annotation_edges
  drupal_basic queue_worker_from_attribute
  drupal_basic queue_worker_from_attribute_edges
  drupal_basic rest_resource_from_annotation
  drupal_basic rest_resource_from_annotation_edges
  drupal_basic rest_resource_from_attribute
  drupal_basic rest_resource_from_attribute_edges
  drupal_basic role_from_config
  drupal_basic role_from_config_edges
  drupal_basic route_from_routing_file
  drupal_basic route_from_routing_file_edges
  drupal_basic route_linked_in_template
  drupal_basic route_options_from_routing_file
  drupal_basic route_options_from_routing_file_edges
  drupal_basic route_requirements_from_routing_file
  drupal_basic route_requirements_from_routing_file_edges
  drupal_basic service_alias_from_services_file
  drupal_basic service_call
  drupal_basic service_from_services_file
  drupal_basic service_from_services_file_class
  drupal_basic service_from_services_file_class_key
  drupal_basic service_from_services_file_edges
  drupal_basic service_text_alias_from_services_file
  drupal_basic simple_config_owner
  drupal_basic storage_call
  drupal_basic storage_nullsafe_call
  drupal_basic template_included_in_template
  drupal_basic template_suggests_bundle
  drupal_basic theme_from_info_file
  drupal_basic theme_from_info_file_edges
  drupal_basic theme_hook_default_template
  drupal_basic theme_hook_entry
  drupal_basic theme_hook_rendered_in_class
  drupal_basic theme_hook_template_key
  drupal_basic theme_include_implements_hook
  drupal_basic user_input_url_call
  drupal_basic view_display_from_config
  drupal_basic view_display_from_config_edges
  drupal_basic view_display_mode_edges
  drupal_basic view_mode_from_config
  drupal_basic views_field_from_attribute
  drupal_basic views_field_from_attribute_edges
  drupal_basic views_field_from_named_attribute
  drupal_basic views_field_from_named_attribute_edges
  drupal_basic views_filter_from_attribute
  drupal_basic views_filter_from_attribute_edges
  drupal_basic views_filter_from_named_attribute
  drupal_basic views_filter_from_named_attribute_edges
  drupal_basic views_style_from_attribute
  drupal_basic views_style_from_attribute_edges
  drupal_basic views_style_from_named_attribute
  drupal_basic views_style_from_named_attribute_edges
  drupal_js_basic behavior_attach_call
  drupal_js_basic behavior_from_arrow
  drupal_js_basic behavior_from_arrow_in_file
  drupal_js_basic behavior_from_function
  drupal_js_basic behavior_from_function_in_file
  drupal_js_basic library_attached_in_class
  drupal_js_basic library_attached_in_component
  drupal_js_basic library_attached_in_template
  drupal_js_basic setting_attached
  drupal_js_basic setting_attached_in_class
  drupal_js_basic stylesheet_file
  js_basic function_declaration
  js_basic function_declaration_in_file
  js_basic function_from_arrow
  js_basic function_from_arrow_in_file
  js_basic function_from_expression
  js_basic function_from_expression_in_file
  php_basic assigned_value
  php_basic call_site_method
  php_basic calls_function
  php_basic calls_static_method
  php_basic calls_through_assigned_property
  php_basic calls_through_property_assigned_here
  php_basic calls_through_typed_property
  php_basic contains_method
  php_basic declares_property
  php_basic find_call_site
  php_basic find_class
  php_basic find_enum
  php_basic find_interface
  php_basic find_member_assignment
  php_basic find_member_assignment_value
  php_basic find_method
  php_basic find_nullable_promoted_property_type
  php_basic find_nullable_property_type
  php_basic find_parameter
  php_basic find_parameter_type
  php_basic find_promoted_property
  php_basic find_promoted_property_type
  php_basic find_property
  php_basic find_property_type
  php_basic find_trait
  php_basic find_union_promoted_property_type
  php_basic find_union_property_type
  php_basic find_var_property_type
  php_basic implements_from_interface_clause
  php_basic inherits_from_base_clause
  php_basic mixes_in_from_use_declaration
  php_basic nullable_promoted_property_typed_as
  php_basic nullable_property_typed_as
  php_basic parameter_typed_as
  php_basic promoted_property_typed_as
  php_basic property_typed_as
  php_basic union_promoted_property_typed_as
  php_basic union_property_typed_as
  php_basic var_property_typed_as

Map rule passes:
  pass 1: none

Rules not executed:
  none

Matches skipped:
  web/modules/custom/greet/greet.libraries.yml:4 library_script fired and emitted nothing

Attributes that differ between files:
  none

Problems:
  none
```

</details>

A setting key nested below a first-level key is the third. The rule `setting_attached_in_array`
fires on the first-level key `greetBanner` of the planted `.module` file, and the nested key
`color` appears nowhere: no node, no report row.

<!-- nav-run -->
```
$ periplus show drupal.js_setting::greetBanner
periplus show drupal.js_setting::greetBanner
type: drupal.js_setting
state: mapped
location: web/modules/custom/greet/greet.module:11
provenance: drupal_js_basic:setting_attached_in_array  declared

Outgoing (0):
  none

Incoming (2):
  provides_setting:
    php.function::greet_preprocess_page  php.function  mapped  web/modules/custom/greet/greet.module:11  x1  inferred  drupal_js_basic:setting_attached_in_array_in_function
  reads_setting:
    drupal.js_behavior::greetBanner  drupal.js_behavior  mapped  web/modules/custom/greet/js/banner.js:4  x1  declared  drupal_js_basic:setting_read_in_behavior
```

<!-- nav-run -->
```
$ periplus find color
periplus find

no matches
```

## Where a rule belongs

A rule for a convention only this project uses stays in the project's own rutter, a folder under
`.periplus/packs` named `<pack>@<version>` with a `pack.yaml`. A rule for a shape any project on
the stack can hold goes to the bundled rutter for that stack, so every project gets it. Write a
rule in the project first, and move it once a second project needs it. The pins sit in
`.periplus/settings.yml`, and a bundled rutter loads by its pin alone; `periplus status` lists the
search path the pins are found on: the project's packs, the user configuration folder, the bundled
rutters, and any `pack_paths`.

The bundled example is `path_in_script_string` in `drupal_js_basic`: a path written whole in a
script string, `fetch('/greet/hello')`, is plain JavaScript on any Drupal site, so the rule ships
with the rutter.

The project-only example is the rule `event_from_data_track` of the planted project's rutter
`myproject@0.0.1`. The planted templates mark an element to track with a `data-track` attribute, a
convention of this project and no other, so the rule stays in the project. Its `pack.yaml` depends
on `drupal_basic`, whose type `drupal_template_text` the rule reads. Its `event.yaml` declares the
node type `myproject.event` and holds the rule.

<!-- nav-file: .periplus/packs/myproject@0.0.1/pack.yaml -->
```yaml
# Known gaps. This project's own rutter: its templates mark an element to track with a data-track
# attribute, a convention no other project shares. event.yaml declares the node type
# myproject.event and reads drupal_basic's type drupal_template_text for the attribute.
# - A value written by Twig, data-track="{{ name }}", makes no node.
pack: myproject
version: 0.0.1
depends: [drupal_basic]
```

<!-- nav-file: .periplus/packs/myproject@0.0.1/event.yaml -->
```yaml
node_types:
- name: myproject.event
  id_namespace: myproject.event

rules:
# data-track="name" in a template: the event the element sends.
- rule: event_from_data_track
  reads: file
  in: [module_root, theme_root]
  match:
    file: '*.html'
    filetype: drupal_template_text
    text: 'data-track="(?<event>[\w-]+)"'
  id: {template: '{event}'}
  line: {capture: event}
  emits: [{node: {type: myproject.event}}]
  confidence: declared
```

A template of the `greet` module carries the attribute.

<!-- nav-file: web/modules/custom/greet/templates/card.html.twig -->
```twig
<div class="card" data-track="card-open">{{ title }}</div>
```

The map holds the event.

<!-- nav-run -->
```
$ periplus show myproject.event::card-open
periplus show myproject.event::card-open
type: myproject.event
state: mapped
location: web/modules/custom/greet/templates/card.html.twig:1
provenance: myproject:event_from_data_track  declared

Outgoing (0):
  none

Incoming (0):
  none
```

## When a gap is the engine's

A gap is the engine's only when no rule can state the shape. The test is to write the rule: if
`periplus validate` refuses it, or the map command refuses it with an engine message, the engine
cannot run that rule. Any other gap is a rule not yet written. A gap no rule can state is the only
reason to touch the engine; quote the engine's message when you report it.

A third project, `broken`, beside the planted one, pins its own rutter `own@0.0.1`. Its one rule
takes the node's id from a call's argument and also sets `match.body_child`.

<!-- nav-file: broken/.periplus/settings.yml -->
```yaml
periplus_version: 0
packs:
  - own@0.0.1
```

<!-- nav-file: broken/.periplus/packs/own@0.0.1/pack.yaml -->
```yaml
pack: own
version: 0.0.1
depends: [php_basic]
```

<!-- nav-file: broken/.periplus/packs/own@0.0.1/rules/own.yaml -->
```yaml
node_types:
- {name: own.entry, id_namespace: own.entry}

rules:
- rule: group
  reads: file
  in: [source]
  match:
    declaration: scoped_call_expression
    name_child: name
    body_child: arguments
    filetype: php
  id: {from: {argument: 0}}
  emits: [{node: {type: own.entry}}]
  confidence: declared
```

The map command refuses the whole project and writes no map, with the engine's message under
Problems and exit 26.

<!-- nav-run: broken -->
```
$ periplus map
periplus map

Map:
  path    not written
  nodes   0
  edges   0

Files:
  selected  0
  excluded  0
  unread    0
  unlisted  0

Files no rule read, by ending:
  none

Files no rule read:
  none

Folders that could not be listed:
  none

Files that did not parse cleanly:
  none

Packs:
  none

Rules executed:
  none

Rules that fired zero times:
  none

Map rule passes:
  none

Rules not executed:
  none

Matches skipped:
  none

Attributes that differ between files:
  none

Problems:
  26 own/rules/own.yaml: the rule group cannot be executed: an id from a call's argument cannot be combined with match.body_child
(exit 26)
```
