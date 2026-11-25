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
