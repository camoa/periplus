# Documentation rules: a worked example

These rules are an example to adapt to the project's own habits, not a rutter to install. They
were written for one small invented project. Keep the shape: one small rule per way of writing,
and one join rule per form of a code name. Change the patterns to what the project's pages
really write. Prove each rule with `periplus validate` and a tiny fixture, as the periplus-rutter
skill says.

## The project

A small invoicing app in PHP, with six Markdown pages that mix their habits:

- `README.md` links to four guides and names `App\Billing\Invoice`.
- `docs/billing.md` has one section per step. It names classes in full (`App\Billing\Invoice`),
  and methods as `Invoice::addLine()`, `Invoice::total` and `Invoice::archive()`. The last one
  does not exist. It also holds inline code that is no code name: `billing.currency`, `true`.
- `docs/payments.md` uses short names: `Refund`, `Refund::process()`.
- `docs/sending.md` links to source files, to a section of another page, and to a decision
  record.
- `docs/reports.md` writes `Invoice`, which fits two classes, and holds fenced code examples.
- `docs/adr/0001-payment-gateway.md` is a decision record: a title, `Status: Accepted`, and a
  "Related" list that names `App\Payments\Payment` and `TaxRate`, a class that does not exist.

The project pins its code rutter and its own rutter. No rule reads a file under `.periplus`, so
the conventions page is not read as documentation:

<!-- example docs: .periplus/settings.yml -->
```yaml
periplus_version: 0
packs:
  - php_basic@0.3.0
  - invoicing@0.1.0
```

All the documentation rules live in the project's own rutter, `invoicing`, one rule file per
habit. The `docs_*` files know only Markdown and suit any project. The `php_*` files join the
names to one stack's code: a project on another stack keeps the `docs_*` files and writes its own
joins.

<!-- example docs: .periplus/packs/invoicing@0.1.0/pack.yaml -->
```yaml
pack: invoicing
version: 0.1.0
depends: [php_basic]
# This project's own rules: its Markdown pages, and how they name its PHP code.
folders:
  docs: ./**
files:
  types:
    markdown:
      endings: [md]
      reader: text
      path_values:
        page:
          pattern: '^(?<p>.+)$'
          template: '{p}'
        page_dir:
          pattern: '^(?<d>.*?)/?[^/]*$'
          template: '{d}'
      # Fenced code is an example, not prose: no rule reads inside it.
      sections:
      - name: fence
        open: '(?m)^```'
        close: '(?m)^```'
      # A section runs from its heading to the next heading of any level.
      spans:
      - name: section
        open: '(?m)^#{1,6}[ \t]+(?<title>[^\n]+)'
        balance: ['\x00', '(?m)^#{1,6}[ \t]']
# Capitalised words in inline code that are not class names.
tables:
  not_code_names:
    JSON: data format
    README: file name
```

The folder `./**` reads every Markdown file in the project. Narrow it to where the pages are, or
add each folder that is not documentation under `exclude` in the settings. A fenced block is a
file section that no rule reads: a code example shows use, it says nothing about the code.

## The generic Markdown rules

**Pages, sections and titles.** A page is a file. A section runs from its heading to the next
heading, and its id is `page#anchor`.

<!-- example docs: .periplus/packs/invoicing@0.1.0/rules/docs_pages.yaml -->
```yaml
node_types:
- name: md.part
  id_namespace: md.doc
  abstract: true
  description: "a Markdown page or a section of one"
- name: md.page
  parent: md.part
  description: "a Markdown file, named by its path"
- name: md.section
  parent: md.part
  description: "a heading of a Markdown page and the text up to the next heading, named page#anchor"
edge_kinds:
- kind: section_of
  from: md.section
  to: md.page
  groups: true
  description: "the section sits in that page"
attributes:
- name: title
  on: [md.part]
  description: The text of the page's first heading, or of the section's heading.
rules:
- rule: page
  reads: file
  in: [docs]
  match: {file: '**', filetype: markdown}
  id: {template: '{page}'}
  emits: [{node: {type: md.page}}]
  confidence: declared
- rule: page_title
  reads: file
  in: [docs]
  match: {file: '**', filetype: markdown, text: '\A#[ \t]+(?<title>[^\n]+)'}
  id: {template: '{page}'}
  emits: [{node: {type: md.page}}, {attribute: {name: title, from: {capture: title}}}]
  confidence: declared
- rule: section
  reads: file
  in: [docs]
  match: {file: '**', filetype: markdown, text: '(?m)^#{1,6}[ \t]+(?<title>[^\n]+)'}
  values:
    anchor:
      from: {capture: title}
      case: lower
      normalize:
      - {replace: '[^\w\- ]', with: ''}
      - {replace: ' ', with: '-'}
  id: {template: '{page}#{anchor}'}
  emits:
  - node: {type: md.section}
  - attribute: {name: title, from: {capture: title}}
  confidence: declared
- rule: section_in_page
  reads: file
  in: [docs]
  match: {file: '**', filetype: markdown, text: '(?m)^#{1,6}[ \t]+(?<title>[^\n]+)'}
  values:
    anchor:
      from: {capture: title}
      case: lower
      normalize:
      - {replace: '[^\w\- ]', with: ''}
      - {replace: ' ', with: '-'}
  id: {template: '{page}#{anchor}'}
  emits:
  - edge: {kind: section_of, from: this_node, to: {template: '{page}'}}
  confidence: declared
```

**A decision record's Status line.** One rule, one attribute.

<!-- example docs: .periplus/packs/invoicing@0.1.0/rules/docs_status.yaml -->
```yaml
# Way: a decision record's Status line, such as `Status: Accepted`.
attributes:
- name: status
  on: [md.page]
  description: The value of a Status line, as a decision record writes it.
rules:
- rule: page_status
  reads: file
  in: [docs]
  match: {file: '**', filetype: markdown, text: '(?m)^Status:[ \t]*(?<status>\w+)'}
  id: {template: '{page}'}
  emits: [{node: {type: md.page}}, {attribute: {name: status, from: {capture: status}}}]
  confidence: declared
```

**Links.** One rule for a link to a page, one for a link to a section, one for a link to any
other file. A link to a page that does not exist leaves that page `unresolved`.

<!-- example docs: .periplus/packs/invoicing@0.1.0/rules/docs_links.yaml -->
```yaml
node_types:
- name: md.file
  id_namespace: md.file
  description: "a file a Markdown link points at that is not a Markdown page, named by its path from the project folder"
edge_kinds:
- kind: links_to
  from: md.page
  to: md.part
  cause: touch
  description: "the page holds a Markdown link to that page, or to that section by its anchor"
- kind: links_to_file
  from: md.page
  to: md.file
  cause: touch
  description: "the page holds a Markdown link to that file"
rules:
# [text](other.md), relative to the page's folder.
- rule: link_page
  reads: file
  in: [docs]
  match: {file: '**', filetype: markdown, text: '\]\((?<target>[^)#\s:]+\.md)\)'}
  values:
    to_page: &resolve
      template: '{page_dir}/{target}'
      normalize:
      - {replace: '^/', with: ''}
      - {replace: '(^|/)\./', with: '$1'}
      - {replace: '[^/]+/\.\./', with: ''}
      - {replace: '[^/]+/\.\./', with: ''}
      - {replace: '[^/]+/\.\./', with: ''}
  id: {template: '{page}'}
  emits:
  - edge: {kind: links_to, from: this_node, to: {template: '{to_page}', type: md.page, on_miss: unresolved}}
  confidence: declared
# [text](other.md#anchor): the section of that page.
- rule: link_section
  reads: file
  in: [docs]
  match: {file: '**', filetype: markdown, text: '\]\((?<target>[^)#\s:]+\.md)#(?<anchor>[^)\s]+)\)'}
  values:
    to_page: *resolve
  id: {template: '{page}'}
  emits:
  - edge: {kind: links_to, from: this_node, to: {template: '{to_page}#{anchor}', type: md.section, on_miss: unresolved}}
  confidence: declared
# [text](path/to/file.ext) where the ending is not .md.
- rule: link_file
  reads: file
  in: [docs]
  match: {file: '**', filetype: markdown, text: '\]\((?<target>[^)#\s:]+\.(?:[^m)#\s./]|m[^d)#\s./]|md[^)#\s./])[^)#\s./]*)(?:#[^)\s]*)?\)'}
  values:
    to_file: *resolve
  id: {template: '{page}'}
  emits:
  - edge: {kind: links_to_file, from: this_node, to: {template: '{to_file}'}}
  confidence: declared
```

**Names written as inline code.** Two internal types carry every name: one node per name, which
the joins read, and one node per section and name, which puts each link at the page's line.
Inline code with a space, such as `composer install`, is not a name.

<!-- example docs: .periplus/packs/invoicing@0.1.0/rules/docs_names.yaml -->
```yaml
# The two internal types every way of writing a name emits. Each way is its own file with two
# rules: the name hub (md.name::<name>) and the mention in its section (md.mention::<part>|<name>).
# The php_*.yaml joins read md.mention ids as part|name.
node_types:
- name: md.name
  id_namespace: md.name
  internal: true
  description: "a name some page writes as inline code without spaces, one node per name, for the join rules to read"
- name: md.mention
  id_namespace: md.mention
  internal: true
  description: "one section's inline-code name, named part|name, at the lines that write it"
```

Each way of writing a name is its own file with two rules. A bare name, `Invoice` or
`Invoice::total`:

<!-- example docs: .periplus/packs/invoicing@0.1.0/rules/docs_names_bare.yaml -->
```yaml
# Way: inline code holding a bare name, `Invoice` or `Invoice::total`.
rules:
- rule: bare_name
  reads: file
  in: [docs]
  match: {file: '**', filetype: markdown, text: '`(?<name>[^`\s()]+)`'}
  id: {template: '{name}'}
  emits: [{node: {type: md.name}}]
  confidence: mentioned
- rule: bare_mention
  reads: file
  in: [docs]
  match: {file: '**', filetype: markdown, text: '`(?<name>[^`\s()]+)`'}
  values:
    section_anchor:
      from: {enclosing: section, capture: title}
      join: '|'
      case: lower
      normalize:
      - {replace: '^.*\|', with: ''}
      - {replace: '[^\w\- ]', with: ''}
      - {replace: ' ', with: '-'}
    part: {template: '{page}#{section_anchor}', normalize: [{replace: '#$', with: ''}]}
  id: {template: '{part}|{name}'}
  emits: [{node: {type: md.mention}}]
  confidence: mentioned
```

A call, `Invoice::send()`, kept without its parentheses:

<!-- example docs: .periplus/packs/invoicing@0.1.0/rules/docs_names_call.yaml -->
```yaml
# Way: inline code holding a call, `Invoice::send()`; the name is kept without the parentheses.
rules:
- rule: call_name
  reads: file
  in: [docs]
  match: {file: '**', filetype: markdown, text: '`(?<name>[^`\s()]+)\([^`)]*\)`'}
  id: {template: '{name}'}
  emits: [{node: {type: md.name}}]
  confidence: mentioned
- rule: call_mention
  reads: file
  in: [docs]
  match: {file: '**', filetype: markdown, text: '`(?<name>[^`\s()]+)\([^`)]*\)`'}
  values:
    section_anchor:
      from: {enclosing: section, capture: title}
      join: '|'
      case: lower
      normalize:
      - {replace: '^.*\|', with: ''}
      - {replace: '[^\w\- ]', with: ''}
      - {replace: ' ', with: '-'}
    part: {template: '{page}#{section_anchor}', normalize: [{replace: '#$', with: ''}]}
  id: {template: '{part}|{name}'}
  emits: [{node: {type: md.mention}}]
  confidence: mentioned
```

## The bridge rules for one stack

**A way of writing that only this stack has.** A PHP name with a leading backslash. Dropping
the backslash is PHP's convention, not Markdown's, so this rule lives with the joins and not in
the `docs_*` files. It reads the `markdown` file type and the `docs` folder like the others.

This file shows what one rule per way of writing buys. `docs/reports.md` writes
`` `\App\Reports\MonthlyReport` ``. Without this file, the class has no incoming link and no
mark. Adding this file, and changing no other, gives one edge and removes nothing:

```console
$ periplus diff map-new-way-before.json map-new-way-after.json
things: 0 added, 0 removed, 0 changed
edges: 1 added, 0 removed, 0 changed
  added by kind: documents 1
edges added:
  documents  md.doc::docs/reports.md#columns -> php.type::App\\Reports\\MonthlyReport
```

The join, gate and `documents` rules picked the new name up unchanged. A name takes two rules
because a file rule emits one node: one for the name, one for its mention in the section.

<!-- example docs: .periplus/packs/invoicing@0.1.0/rules/php_names_backslash.yaml -->
```yaml
# Way: inline code holding a fully qualified PHP name, `\App\Billing\Invoice`; the name is kept
# without the leading backslash. Same two nodes as docs_names_bare.yaml.
rules:
- rule: leading_backslash_name
  reads: file
  in: [docs]
  match: {file: '**', filetype: markdown, text: '`\\(?<name>[A-Za-z_][\w\\]*(?:::\w+)?)(?:\([^`)]*\))?`'}
  id: {template: '{name}'}
  emits: [{node: {type: md.name}}]
  confidence: mentioned
- rule: leading_backslash_mention
  reads: file
  in: [docs]
  match: {file: '**', filetype: markdown, text: '`\\(?<name>[A-Za-z_][\w\\]*(?:::\w+)?)(?:\([^`)]*\))?`'}
  values:
    section_anchor:
      from: {enclosing: section, capture: title}
      join: '|'
      case: lower
      normalize:
      - {replace: '^.*\|', with: ''}
      - {replace: '[^\w\- ]', with: ''}
      - {replace: ' ', with: '-'}
    part: {template: '{page}#{section_anchor}', normalize: [{replace: '#$', with: ''}]}
  id: {template: '{part}|{name}'}
  emits: [{node: {type: md.mention}}]
  confidence: mentioned
```

**One join rule per form of a code name.** Each rule starts at a class or method and steps to
the name node that spells it one way. A fifth form is a fifth rule.

<!-- example docs: .periplus/packs/invoicing@0.1.0/rules/php_fits.yaml -->
```yaml
# One rule per form of a PHP name: full class, short class, full method, Class::method.
edge_kinds:
- kind: name_fits
  from: md.name
  to: [php.class_like, php.method]
  cause: none
  description: "the inline-code name is that PHP class or method's full or short name"
rules:
- rule: fits_class_full
  reads: map
  match:
    node_type: php.class_like
    where: [{id_matches: '^php\.type::(?<full>.+)$'}]
    follow: [{node: 'md.name::{full}'}]
  emits: [{edge: {kind: name_fits, from: matched_node, to: this_node}}]
  confidence: mentioned
- rule: fits_class_short
  reads: map
  match:
    node_type: php.class_like
    where: [{id_matches: '^php\.type::(?:.*\\)?(?<short>[^\\]+)$'}]
    follow: [{node: 'md.name::{short}'}]
  emits: [{edge: {kind: name_fits, from: matched_node, to: this_node}}]
  confidence: mentioned
- rule: fits_method_full
  reads: map
  match:
    node_type: php.method
    where: [{id_matches: '^php\.method::(?<full>.+)$'}]
    follow: [{node: 'md.name::{full}'}]
  emits: [{edge: {kind: name_fits, from: matched_node, to: this_node}}]
  confidence: mentioned
- rule: fits_method_short
  reads: map
  match:
    node_type: php.method
    where: [{id_matches: '^php\.method::(?:.*\\)?(?<cls>[^\\:]+)::(?<m>\w+)$'}]
    follow: [{node: 'md.name::{cls}::{m}'}]
  emits: [{edge: {kind: name_fits, from: matched_node, to: this_node}}]
  confidence: mentioned
```

**The link a person reads.** The rule starts at the mention, so the edge sits at the page's
line, not at the code's. A short name that fits two classes gives an edge to each, marked
`ambiguous: yes`.

<!-- example docs: .periplus/packs/invoicing@0.1.0/rules/php_documents.yaml -->
```yaml
edge_kinds:
- kind: documents
  from: md.part
  to: [php.class_like, php.method]
  cause: touch
  description: "the page or section writes the PHP class or method's full or short name as inline code"
edge_attributes:
- {name: as_written, on: [documents], description: the inline-code name as the page writes it}
- {name: ambiguous, on: [documents], description: yes when the name fits more than one class}
rules:
- rule: documents
  reads: map
  match:
    node_type: md.mention
    where: [{id_matches: '^md\.mention::(?<part>[^|]+)\|(?<name>.+)$'}]
    follow: [{node: 'md.name::{name}'}, {edge: name_fits}]
  emits:
  - edge: {kind: documents, from: {template: '{part}', types: [md.section, md.page]}, to: matched_node, attributes: {as_written: {template: '{name}'}}}
  confidence: mentioned
# A short name two classes share: each of its documents edges says so.
- rule: documents_ambiguous
  reads: map
  match:
    node_type: md.mention
    where: [{id_matches: '^md\.mention::(?<part>[^|]+)\|(?<name>[^\\:]+)$'}]
    follow:
    - node: 'md.name::{name}'
    - edge: name_fits
    - id_matches: '^php\.type::(?<cls>.+)$'
    - node: 'md.name::{name}'
    - edge: name_fits
    - id_matches: '^php\.type::(?!{cls}$)'
  emits:
  - edge: {kind: documents, from: {template: '{part}', types: [md.section, md.page]}, to: matched_node, attributes: {ambiguous: {template: 'yes'}}}
  confidence: mentioned
```

## The gate for missing names

A rule that marks a name no join found reads the joins through `unless`. A map rule's `unless`
sees the map as it stood when its pass began, and nothing runs one map rule after another. So
written plainly, the rule runs in pass 1 beside the joins and marks real names as missing. No
message warns of it. On this project the plain rule marked 28 names; the gated rule marks 5.

The gate makes it wait: one rule per shape of a code name writes a self-edge in pass 1, and the
missing-name rule follows that edge, so it fires in pass 2, after every join. This holds only
while every join rule fires in pass 1. A join that needs two passes brings the wrong marks back,
silently: read the map report's "Map rule passes" after any new join.

The shape rules also keep junk out: only a name shaped like a class or method can be marked. A
capitalised word that is no class, such as `JSON`, still is. The table `not_code_names` in the
pack lists those words. Before the table, `JSON` on a new page was marked missing.

<!-- example docs: .periplus/packs/invoicing@0.1.0/rules/php_missing.yaml -->
```yaml
node_types:
- name: docphp.name
  id_namespace: docphp.name
  description: "a PHP-looking name a page writes as inline code that no mapped class or method has"
edge_kinds:
- kind: looks_like_php
  from: md.name
  to: md.name
  cause: none
  description: "the inline-code name has a PHP name's shape; a gate the missing rule reads one pass later"
- kind: names_missing
  from: md.part
  to: docphp.name
  cause: touch
  description: "the page or section writes, as inline code, a PHP-looking name that no mapped class or method has"
rules:
# The gate: one rule per shape of a PHP name. Pass 1, beside the fits rules. A capitalised word
# in the table not_code_names, such as JSON, is not a class name.
- rule: looks_like_method
  reads: map
  match:
    node_type: md.name
    where: [{id_matches: '^md\.name::\w+::\w+$'}]
  emits: [{edge: {kind: looks_like_php, from: this_node, to: this_node}}]
  confidence: mentioned
- rule: looks_like_namespaced
  reads: map
  match:
    node_type: md.name
    where: [{id_matches: '^md\.name::[A-Za-z_]\w*(?:\\\w+)+$'}]
  emits: [{edge: {kind: looks_like_php, from: this_node, to: this_node}}]
  confidence: mentioned
- rule: looks_like_class
  reads: map
  match:
    node_type: md.name
    where: [{id_matches: '^md\.name::(?<word>[A-Z]\w*)$'}, {not_in_table: {table: not_code_names, capture: word}}]
  emits: [{edge: {kind: looks_like_php, from: this_node, to: this_node}}]
  confidence: mentioned
# Pass 2: the gate edge exists only after pass 1, when every name_fits edge exists too.
- rule: missing_name
  reads: map
  match:
    node_type: md.mention
    where: [{id_matches: '^md\.mention::(?<part>[^|]+)\|(?<name>.+)$'}]
    follow: [{node: 'md.name::{name}'}, {edge: looks_like_php}, {node: 'md.doc::{part}'}]
    unless: [[{node: 'md.name::{name}'}, {edge: name_fits}]]
  emits: [{edge: {kind: names_missing, from: matched_node, to: {template: '{name}', type: docphp.name, on_miss: unresolved}}}]
  confidence: mentioned
```

The map report shows the order:

```text
Map rule passes:
  pass 1: ... invoicing fits_class_full fired 6, invoicing fits_class_short fired 3, invoicing fits_method_short fired 10, invoicing looks_like_method fired 11, invoicing looks_like_namespaced fired 6, invoicing looks_like_class fired 3
  pass 2: invoicing documents fired 21, invoicing documents_ambiguous fired 2, invoicing missing_name fired 2
  pass 3: none
  pass 4: ...
```

The last pass runs only `php_basic`'s map rule that marks a call decided at run time.

## The questions, and the commands that answer them

**Which pages name this thing?** `periplus show` lists them under `documents`, each with the
page's line:

```console
$ periplus show 'App\Billing\Invoice::send'
...
Incoming (3):
  ...
  documents:
    md.doc::docs/billing.md#sending  md.section  mapped  docs/billing.md:13  x1  mentioned  invoicing:documents [as_written: Invoice::send]
      | `Invoice::send()` hands the invoice to `Sender::deliver()`. Old invoices can be closed with
```

**Which names match nothing in the code?**

```console
$ periplus find --type docphp.name --limit 0
periplus find: 2 things (2 not mapped or with no location), 0 edges
not main by type: docphp.name 2

docphp.name::Invoice::archive  docphp.name  unresolved  no location
docphp.name::TaxRate  docphp.name  unresolved  no location
$ periplus show 'docphp.name::TaxRate'
...
Incoming (1):
  names_missing:
    md.doc::docs/adr/0001-payment-gateway.md#related  md.section  mapped  docs/adr/0001-payment-gateway.md:19  x1  mentioned  invoicing:missing_name
      | - `TaxRate`
```

**Which pages link to which?** `periplus show` on a page lists its links both ways. To list every
link of a kind, search the words of its description with `--kinds`:

```console
$ periplus show 'md.doc::docs/payments.md'
...
Outgoing (1):
  links_to:
    md.doc::docs/billing.md  md.page  mapped  docs/payments.md:3  x1  declared  invoicing:link_page
Incoming (5):
  links_to:
    md.doc::README.md  md.page  mapped  README.md:7  x1  declared  invoicing:link_page
    md.doc::docs/adr/0001-payment-gateway.md  md.page  mapped  docs/adr/0001-payment-gateway.md:16  x1  declared  invoicing:link_page
  ...
$ periplus find Markdown link --kinds --type md.page --limit 0
periplus find: 0 things, 11 edges
edges by kind: links_to 9, links_to_file 2
```

`periplus neighbors` with several pages as starts is not a list of links: it shows each page
once, at the first start that reaches it. Ask one page at a time.

**Which code does no page name?** No single command lists things with no incoming link of one
kind. Save what the pages name and what the code holds as two map files, then subtract:

```
periplus find --type md.part --ids | periplus neighbors - --touch --kind documents --depth 1 --ids | periplus extract - --out documented.json
periplus find --type php.class_like --type php.method --ids | periplus extract - --out code.json
```

```console
$ periplus minus code.json documented.json --ids
php.method::App\Billing\Customer::email
php.method::App\Billing\Invoice::tax
...
php.type::App\Billing\Customer
php.type::App\Billing\Sender
```

`App\Billing\Sender` is on the list although a page links to its file: see the file-link limit
below.

**What did a code change do to the docs?** The change removed `Invoice::addLine`, renamed the
class `Refund` to `RefundRequest`, and added a page. Keep the old map, map again, and compare:

```console
$ periplus diff map-before.json map-after.json --limit 0
...
  added by kind: names_missing 4, contains 2, documents 2, ...
  removed by kind: documents 4, contains 3, ...
...
edges added:
  names_missing  md.doc::docs/billing.md#adding-lines -> docphp.name::Invoice::addLine
  names_missing  md.doc::docs/payments.md#refunds -> docphp.name::Refund
...
edges removed:
  documents  md.doc::docs/billing.md#adding-lines -> php.method::App\\Billing\\Invoice::addLine
  documents  md.doc::docs/payments.md#refunds -> php.type::App\\Payments\\Refund
```

Each lost `documents` edge sits beside the `names_missing` edge that took its place, so the
change names the sections to rewrite. `periplus find --type docphp.name` then lists every
missing name on the new map.

**Has this section changed since it was described?** A page and a section take a description
like any thing. `periplus stamp` ties it to the section's text, and `periplus stale` lists it
when that text changes. A renamed heading changes the section's id, so its entry shows as gone:

```console
$ periplus stale
1 node entry: 0 fresh, 1 changed, 0 gone, 0 unreadable, 0 not stamped
changed:
  sending  md.section  mapped  docs/billing.md:10
```

## Limits

- **A link to a source file stops at the file.** A map rule cannot read the file a node sits in,
  so no rule joins `md.file::src/Billing/Sender.php` to the class in it. Two ways were tried; the
  engine refused both. A `where` key for the file:
  `Additional properties are not allowed ('file_matches' was unexpected)`. A `follow` step that
  names the file: `the follow step node md.file::{file} names file, which no id_matches captures
  before it`. Run `periplus in` on the link's target to list what the file holds. Where the
  project can choose, write the class name in inline code beside the link.
- **A lowercase method name alone joins nothing.** `email()` without its class could be any
  method, so it gives no link and no mark.
- **The anchor rule is simple.** It lowercases the heading, drops what is not a letter, digit,
  space or hyphen, and puts a hyphen for each space. Not tried: underlined headings, two headings
  with one text, reference-style links and HTML links.
- **The cost is internal nodes.** On this project the rules added 26 nodes and 50 edges to the
  map. They also add one internal node per name and one per section and name, which the written
  map leaves out.
