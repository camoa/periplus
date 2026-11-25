# Rule composition

Small rules, each finding one thing, can together find how an application is put together. This
page builds one such link step by step: from a route in a routes file to the JavaScript function
that handles it, across two file formats and two rutters. The example is in
[`examples/rule-composition`](../examples/rule-composition), so you can run each command below.

Read [Writing a rutter](rutter-author-guide.md) for the rule format itself.

## The tree

An invoicing app keeps its routes in a plain text file. Each line gives a method, a path and the
name of the function that handles it. The file does not say which script holds the function.

```text config/app.routes
POST   /invoices           createInvoice
GET    /invoices/:id       showInvoice
POST   /invoices/:id/send  sendInvoice
DELETE /invoices/:id       removeInvoice
```

```js src/invoices.js
function createInvoice(req) {
  return save({ customer: req.body.customer, lines: req.body.lines });
}

function showInvoice(req) {
  return load(req.params.id);
}

function sendInvoice(req) {
  const invoice = load(req.params.id);
  return deliver(invoice);
}

function save(invoice) { /* write to the database */ }
function load(id) { /* read from the database */ }
function deliver(invoice) { /* email the invoice */ }
```

The project pins the bundled `js_basic` rutter and its own rutter, `invoice_routes`:

```yaml .periplus/settings.yml
periplus_version: 0
packs:
  - js_basic@0.0.2
  - invoice_routes@0.1.0
```

```yaml .periplus/packs/invoice_routes@0.1.0/pack.yaml
pack: invoice_routes
version: 0.1.0
depends: [js_basic]
folders:
  routes: ./config
files:
  types:
    routes:
      endings: [routes]
      reader: text
```

`depends: [js_basic]` lets this rutter name `js.function`, a type `js_basic` declares.

With `js_basic` alone, `periplus types` counts one `js.file`, six `js.function` nodes and four
`js_calls` edges.

## Rule 1: the routes

`rules/routes.yaml` finds each route. It knows nothing of handlers.

```yaml .periplus/packs/invoice_routes@0.1.0/rules/routes.yaml
node_types:
- name: inv.route
  id_namespace: inv.route
  description: "an HTTP route the routes file declares, named by its method and path"
rules:
- rule: route
  reads: file
  in: [routes]
  match: {file: app, filetype: routes, text: '(?m)^(?<verb>[A-Z]+)[ \t]+(?<path>\S+)'}
  id: {template: '{verb} {path}'}
  emits: [{node: {type: inv.route}}]
  confidence: declared
```

`periplus find --type inv.route` now lists four routes, each at its line:

```text
inv.route::DELETE /invoices/:id  inv.route  mapped  config/app.routes:4
inv.route::GET /invoices/:id  inv.route  mapped  config/app.routes:2
inv.route::POST /invoices  inv.route  mapped  config/app.routes:1
inv.route::POST /invoices/:id/send  inv.route  mapped  config/app.routes:3
```

## Rule 2: the name each route gives its handler

`rules/handler_names.yaml` reads the same lines and keeps the third column as written. It does
not look for the function, because a file rule reads one file and cannot see the script.

```yaml .periplus/packs/invoice_routes@0.1.0/rules/handler_names.yaml
node_types:
- name: inv.handler_name
  id_namespace: inv.handler_name
  description: "the name a route gives the function that handles it, as the routes file writes it"
edge_kinds:
- kind: names_handler
  from: inv.route
  to: inv.handler_name
  cause: touch
  description: "the routes file names this function as the route's handler"
rules:
- rule: handler_name
  reads: file
  in: [routes]
  match: {file: app, filetype: routes, text: '(?m)^(?<verb>[A-Z]+)[ \t]+(?<path>\S+)[ \t]+(?<fn>\w+)'}
  id: {template: '{verb} {path}'}
  emits: [{edge: {kind: names_handler, from: this_node, to: {template: '{fn}', type: inv.handler_name}}}]
  confidence: declared
```

`periplus types` now adds `inv.handler_name 4` and `names_handler 4`. Each name is a
`referenced` node: the code names it, and no rule has said what it is yet.

## Rule 3: the route meets its function

`rules/handled_by.yaml` is a map rule, `reads: map`. It runs after every file rule, over the map
they made. It starts at each function `js_basic` found, takes the function's name from its id,
steps to the handler name of that text, and walks back to each route that names it.

```yaml .periplus/packs/invoice_routes@0.1.0/rules/handled_by.yaml
edge_kinds:
- kind: handled_by
  from: inv.route
  to: js.function
  realizes: to
  description: "the route runs that function: a script declares a function of the name the routes file gives"
rules:
- rule: route_handler
  reads: map
  match:
    node_type: js.function
    where:
    - id_matches: '^js\.function::.+:(?<fn>\w+)$'
    follow:
    - node: 'inv.handler_name::{fn}'
    - incoming_edge: names_handler
  emits:
  - edge: {kind: handled_by, from: matched_node, to: this_node}
  confidence: inferred
```

The link rests on a name that matches, not on an import, so the rule says `inferred`. The map
report lists the rule under Map rule passes, in pass 1. `periplus show
'inv.route::POST /invoices/:id/send'` lists the new edge, with the file and line of the function:

```text
Outgoing (2):
  handled_by:
    js.function::src/invoices.js:sendInvoice  js.function  mapped  src/invoices.js:9  x1  inferred  invoice_routes:route_handler
      | function sendInvoice(req) {
```

No script declares `removeInvoice`, so the rule fired three times, not four. The `DELETE` route
keeps its `names_handler` edge to a `referenced` name, and gets no `handled_by` edge. The map
does not guess a target.

## Rule 4: the function learns its route

`rules/route_on_handler.yaml` reads the edge rule 3 made, so it fires one pass later. It writes
the route on each handler, under a declared attribute with a mark.

```yaml .periplus/packs/invoice_routes@0.1.0/rules/route_on_handler.yaml
attributes:
- name: route
  on: [js.function]
  description: The route that runs this function.
  mark: route handler
rules:
- rule: route_on_handler
  reads: map
  match:
    node_type: inv.route
    where:
    - id_matches: '^inv\.route::(?<route>.+)$'
    follow:
    - edge: handled_by
  emits:
  - attribute: {name: route, template: '{route}', target: matched_node}
  confidence: inferred
```

```text
Map rule passes:
  pass 1: invoice_routes route_handler fired 3
  pass 2: invoice_routes route_on_handler fired 3
  pass 3: none
```

`periplus find --mark 'route handler'` lists the three handlers:

```text
js.function::src/invoices.js:createInvoice  js.function  mapped  src/invoices.js:1  [route handler]
js.function::src/invoices.js:sendInvoice  js.function  mapped  src/invoices.js:9  [route handler]
js.function::src/invoices.js:showInvoice  js.function  mapped  src/invoices.js:5  [route handler]
```

## The whole chain

`periplus path` now walks from a line of the routes file into the JavaScript calls. The first
hop comes from `invoice_routes`, the second from `js_basic`:

```text
$ periplus path 'inv.route::POST /invoices/:id/send' 'js.function::src/invoices.js:deliver'
1 shortest chain
  chain 1:
    inv.route::POST /invoices/:id/send --handled_by--> js.function::src/invoices.js:sendInvoice  [route handler]  src/invoices.js:9
      | function sendInvoice(req) {
    js.function::src/invoices.js:sendInvoice  [route handler] --js_calls--> js.function::src/invoices.js:deliver  src/invoices.js:11
      | return deliver(invoice);
```

No rule knows the whole. The route rule knows one file format. `js_basic` knows JavaScript and
nothing of routes. The map rule knows only how to join what the two found. Each rule file can be
read, changed or removed alone, and the map report shows what each one added. A rutter builds on
the types another rutter declares: `invoice_routes` names `js.function` and copies none of the
rules of `js_basic`.

## One thing, many ways to write it

Code says the same thing in several ways, and the ways change as a framework grows. Small rules
handle this well: each way of writing is one rule, and every rule ends at the same thing in the
map.

Drupal hooks show it. A module can implement a hook in more than one way:

- a function named after the module and the hook, the older way;
- a method that carries a `#[Hook]` attribute, the newer way;
- a class that carries the attribute;
- a function kept as a shim, marked `#[LegacyHook]`, that calls the class.

The Drupal rutter has one small rule for each. Other small rules find the call that runs the hook
and the function that documents it in an `api.php` file. All of them end at one hook. So "who
implements this hook" has one answer, whichever way each module wrote it.

When a framework adds a way of writing, you add one rule file. No other rule changes, and
`periplus diff` on the two maps shows what the new rule added.

## What a map rule can and cannot read

From [Map rules](rutter-author-guide-map-rules.md):

- A map rule runs after every file rule. The engine runs map rules in passes until a pass adds
  nothing. Each pass reads the map as it stood when the pass began.
- It reads the nodes the rules found, the edges the file rules made, and the edges map rules made
  between those. An end a map rule composed is never read, so the passes end.
- A node a map rule makes is read only when a file rule found the same id. A node that is only
  referenced is never a start for `node_type`.
- It emits edges whose ends are `this_node`, `matched_node` or one template end, or one node, or
  declared attributes. Beside a node it emits only `resolution: runtime`.
- What a fire makes sits at each location of the node it matched, or, after a `place: edge`
  step, at each location of the edge that step walked.
- No `follow` step reads a node attribute. `edge_attribute` reads only values file rules wrote.
- An `unless` or `unless_matched` chain sees the map as it stood when the pass began, so an edge a
  later pass makes does not take back what the rule already made.
