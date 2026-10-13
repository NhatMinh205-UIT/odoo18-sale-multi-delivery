# sale_multi_delivery

One sale order, several deliveries: each order line has its own `Destination Address`
(from OCA `sale_stock_delivery_address`); confirming the order creates one delivery per address.

This addon only adds the rules OCA lacks:

- the address must belong to the order's customer and not be an invoice/private address (UI domain + server constraint, re-checked when the customer changes);
- the address of an existing line cannot be changed once the order is confirmed (UI readonly + server check).

## Install

Depends on OCA `sale-workflow` branch `18.0`, pinned at commit `e0694c7bd12d1d286b2a8ebe8e8f0130d1290942`
(`sale_stock_delivery_address` 18.0.1.1.1, `sale_procurement_group_by_line` 18.0.1.0.2),
which is provided as the `oca/sale-workflow` Git submodule at the repository root.

Cloning, `--addons-path` setup, installation and running the tests are described in the root `README.md`.

## Demo (Sales and Inventory apps, one-step delivery)

1. Contacts: customer `Acme Corporation` with three child contacts of type Delivery Address (Office A, B, C).
2. Product `Laptop`: Goods, Track Inventory, invoicing policy "Delivered quantities", 10 units in stock.
3. Sales: new quotation for Acme, three Laptop lines (4, 3, 3), each with its own Destination Address.
   The address picker only lists Acme's own addresses.
4. Confirm. The Delivery smart button shows 3 deliveries, each addressed to its office, demand 4 + 3 + 3.
5. Validate one delivery: only that line's delivered quantity changes. Validate a partial quantity and accept the backorder: it keeps the same address.
6. Create Invoice: only delivered quantities are invoiced.
7. After Confirm, the Destination Address of existing lines is read-only.
