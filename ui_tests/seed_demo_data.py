# Run through the Odoo shell (see the "UI test" section of the root README):
#   odoo-bin shell -d <db> ... < ui_tests/seed_demo_data.py
# Idempotent: safe to run more than once.
Partner = env["res.partner"]

acme = Partner.search([("name", "=", "Acme Corporation")], limit=1) or Partner.create(
    {"name": "Acme Corporation", "is_company": True}
)
for key in "ABC":
    if not Partner.search([("name", "=", f"Acme - Office {key}"), ("parent_id", "=", acme.id)]):
        Partner.create({"name": f"Acme - Office {key}", "parent_id": acme.id, "type": "delivery"})

other = Partner.search([("name", "=", "Other Corp UI")], limit=1) or Partner.create(
    {"name": "Other Corp UI", "is_company": True}
)
if not other.child_ids:
    Partner.create({"name": "OtherUI - HQ", "parent_id": other.id, "type": "delivery"})

product = env["product.product"].search([("name", "=", "Laptop UI")], limit=1)
if not product:
    product = env["product.product"].create({
        "name": "Laptop UI", "type": "consu", "is_storable": True,
        "list_price": 100, "invoice_policy": "delivery",
    })
    warehouse = env["stock.warehouse"].search([], limit=1)
    env["stock.quant"]._update_available_quantity(product, warehouse.lot_stock_id, 10)

env.cr.commit()
print("Seed data ready: Acme Corporation (3 delivery addresses), Other Corp UI, Laptop UI")
