# Odoo 18 Multi-Delivery

One `sale.order` creating several `stock.picking`, each delivered to a different customer address chosen per order line.

Built on Odoo 18 core and two OCA addons; this repo only contains the thin addon `sale_multi_delivery`.

| Part | Source |
|---|---|
| Split deliveries by line address | OCA `sale-workflow` 18.0: `sale_stock_delivery_address`, `sale_procurement_group_by_line`, pinned at commit `e0694c7bd12d1d286b2a8ebe8e8f0130d1290942` |
| Address must belong to the customer, address locked after Confirm | `custom_addons/sale_multi_delivery` (this repo) |

## Layout

- `custom_addons/sale_multi_delivery`: the addon, with install and demo steps in its own README.
- `ui_tests/ui_test_multi_delivery.py`: Playwright test driving the real Odoo UI (needs a running server on port 8171, database `multi_delivery_poc`).

## Verified results

- Addon tests: 18 passed, 0 failed.
- OCA addon tests: 12 passed, 0 failed.
- Core `sale_stock` tests with OCA and this addon installed: 134 passed, 0 failed.
- Playwright UI test: 16 passed, 0 failed.

## Known points to confirm

- A line left blank and a line that explicitly picks the same address as the order header produce two separate deliveries to the same recipient (OCA behaviour).
- New lines with an address can still be added after Confirm; only changing an existing line's address is blocked.
- The Purchase side of the chain was studied in the Odoo source but not exercised.
