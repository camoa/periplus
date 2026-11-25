# Rule composition example

An invoicing app whose routes file names JavaScript handlers, and a rutter of four small rules
that links each route to its handler. [Rule composition](../../docs/rule-composition.md) walks
through it. Run these in this folder:

```
periplus validate invoice_routes
periplus map
periplus path 'inv.route::POST /invoices/:id/send' 'js.function::src/invoices.js:deliver'
```
