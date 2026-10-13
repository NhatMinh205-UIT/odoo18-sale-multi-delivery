# sale_multi_delivery

One sale order, several deliveries: each order line has its own `Destination Address`
(from OCA `sale_stock_delivery_address`); confirming the order creates one delivery per address.

This addon only adds the rules OCA lacks:

- the address must belong to the order's customer and not be an invoice/private address (UI domain + server constraint, re-checked when the customer changes);
- the address of an existing line cannot be changed once the order is confirmed (UI readonly + server check).

## Install

OCA `sale-workflow` branch `18.0`, pinned at commit `e0694c7bd12d1d286b2a8ebe8e8f0130d1290942`
(`sale_stock_delivery_address` 18.0.1.1.1, `sale_procurement_group_by_line` 18.0.1.0.2).

```bash
cd /home/pc/odoo-dev/odoo
../odoo-venv/bin/python3 odoo-bin \
  --addons-path="addons,odoo/addons,/home/pc/odoo-dev/oca/sale-workflow,/home/pc/odoo-dev/multi-delivery/custom_addons" \
  -d multi_delivery_poc --db_host=/var/run/postgresql --db_port=5433 --db_user=pc \
  -i sale_multi_delivery
```

Run the tests by adding `--test-enable --test-tags /sale_multi_delivery --stop-after-init`.

## Demo (Sales and Inventory apps, one-step delivery)

1. Contacts: customer `Acme Corporation` with three child contacts of type Delivery Address (Office A, B, C).
2. Product `Laptop`: Goods, Track Inventory, invoicing policy "Delivered quantities", 10 units in stock.
3. Sales: new quotation for Acme, three Laptop lines (4, 3, 3), each with its own Destination Address.
   The address picker only lists Acme's own addresses.
4. Confirm. The Delivery smart button shows 3 deliveries, each addressed to its office, demand 4 + 3 + 3.
5. Validate one delivery: only that line's delivered quantity changes. Validate a partial quantity and accept the backorder: it keeps the same address.
6. Create Invoice: only delivered quantities are invoiced.
7. After Confirm, the Destination Address of existing lines is read-only.
