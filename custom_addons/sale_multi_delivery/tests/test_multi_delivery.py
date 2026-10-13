from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase


@tagged("post_install", "-at_install")
class TestMultiDelivery(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env = cls.env(context=dict(cls.env.context, tracking_disable=True))
        Partner = cls.env["res.partner"]

        cls.warehouse = cls.env["stock.warehouse"].search(
            [("company_id", "=", cls.env.company.id)], limit=1
        )
        cls.warehouse.delivery_steps = "ship_only"

        cls.customer = Partner.create({"name": "Acme Corporation", "is_company": True})
        cls.addr = {
            key: Partner.create(
                {"name": f"Acme - Office {key}", "parent_id": cls.customer.id, "type": "delivery"}
            )
            for key in "ABC"
        }
        cls.invoice_addr = Partner.create(
            {"name": "Acme - Accounting", "parent_id": cls.customer.id, "type": "invoice"}
        )
        cls.other_customer = Partner.create({"name": "Other Corp", "is_company": True})
        cls.other_addr = Partner.create(
            {"name": "Other - HQ", "parent_id": cls.other_customer.id, "type": "delivery"}
        )

        Product = cls.env["product.product"]
        cls.laptop = Product.create(
            {"name": "Laptop", "type": "consu", "is_storable": True, "list_price": 100,
             "invoice_policy": "delivery"}
        )
        cls.mouse = Product.create(
            {"name": "Mouse", "type": "consu", "is_storable": True, "list_price": 10,
             "invoice_policy": "delivery"}
        )
        cls.service = Product.create({"name": "Setup", "type": "service", "list_price": 50})
        quant = cls.env["stock.quant"]
        quant._update_available_quantity(cls.laptop, cls.warehouse.lot_stock_id, 50)
        quant._update_available_quantity(cls.mouse, cls.warehouse.lot_stock_id, 50)

    def _make_order(self, lines, partner=None, user=None, **vals):
        Order = self.env["sale.order"]
        if user:
            Order = Order.with_user(user)
        return Order.create({
            "partner_id": (partner or self.customer).id,
            "warehouse_id": self.warehouse.id,
            **vals,
            "order_line": [
                Command.create({
                    "product_id": product.id,
                    "product_uom_qty": qty,
                    "dest_address_id": address.id if address else False,
                })
                for product, qty, address in lines
            ],
        })

    def _three_address_order(self):
        return self._make_order([
            (self.laptop, 4, self.addr["A"]),
            (self.laptop, 3, self.addr["B"]),
            (self.laptop, 3, self.addr["C"]),
        ])

    def _picking_of(self, order, address):
        return order.picking_ids.filtered(lambda p: p.partner_id == address)

    # --- Delivery splitting ---

    def test_single_line_without_address_keeps_standard_flow(self):
        order = self._make_order([(self.laptop, 5, False)])
        order.action_confirm()
        self.assertEqual(len(order.picking_ids), 1)
        self.assertEqual(order.picking_ids.partner_id, order.partner_shipping_id)
        self.assertEqual(order.picking_ids.move_ids.product_uom_qty, 5)

    def test_three_addresses_make_three_pickings(self):
        order = self._three_address_order()
        order.action_confirm()
        self.assertEqual(len(order.picking_ids), 3)
        self.assertEqual(order.delivery_count, 3)
        for key, qty in (("A", 4), ("B", 3), ("C", 3)):
            picking = self._picking_of(order, self.addr[key])
            self.assertEqual(len(picking), 1, f"one picking for {key}")
            self.assertEqual(picking.move_ids.product_uom_qty, qty)
            self.assertEqual(picking.move_ids.sale_line_id.dest_address_id, self.addr[key])
        self.assertEqual(sum(order.picking_ids.move_ids.mapped("product_uom_qty")), 10)

    def test_same_address_lines_share_a_picking(self):
        order = self._make_order([
            (self.laptop, 2, self.addr["A"]),
            (self.mouse, 1, self.addr["A"]),
            (self.laptop, 1, self.addr["B"]),
        ])
        order.action_confirm()
        self.assertEqual(len(order.picking_ids), 2)
        self.assertEqual(len(self._picking_of(order, self.addr["A"]).move_ids), 2)
        self.assertEqual(len(self._picking_of(order, self.addr["B"]).move_ids), 1)

    def test_blank_address_falls_back_to_header_address(self):
        order = self._make_order(
            [(self.laptop, 2, self.addr["A"]), (self.laptop, 3, False)],
            partner_shipping_id=self.customer.id,
        )
        order.action_confirm()
        self.assertEqual(len(order.picking_ids), 2)
        self.assertEqual(self._picking_of(order, self.customer).move_ids.product_uom_qty, 3)
        self.assertEqual(self._picking_of(order, self.addr["A"]).move_ids.product_uom_qty, 2)

    def test_service_line_creates_no_picking(self):
        order = self._make_order([(self.service, 1, self.addr["A"])])
        order.action_confirm()
        self.assertFalse(order.picking_ids)

    # --- Delivered quantity, backorder, invoice ---

    def test_pickings_are_independent_and_qty_delivered_follows(self):
        order = self._three_address_order()
        order.action_confirm()
        picking_a = self._picking_of(order, self.addr["A"])
        picking_a.move_ids.quantity = 4
        picking_a.button_validate()
        self.assertEqual(picking_a.state, "done")
        self.assertNotEqual(self._picking_of(order, self.addr["B"]).state, "done")
        self.assertNotEqual(self._picking_of(order, self.addr["C"]).state, "done")
        delivered = {line.dest_address_id: line.qty_delivered for line in order.order_line}
        self.assertEqual(delivered[self.addr["A"]], 4)
        self.assertEqual(delivered[self.addr["B"]], 0)
        self.assertEqual(delivered[self.addr["C"]], 0)

    def test_backorder_keeps_destination_address(self):
        order = self._three_address_order()
        order.action_confirm()
        picking_b = self._picking_of(order, self.addr["B"])
        picking_b.move_ids.quantity = 2
        action = picking_b.button_validate()
        self.env["stock.backorder.confirmation"].with_context(**action["context"]).create(
            {"pick_ids": [Command.link(picking_b.id)]}
        ).process()
        backorder = order.picking_ids.filtered(lambda p: p.backorder_id == picking_b)
        self.assertEqual(len(backorder), 1)
        self.assertEqual(backorder.partner_id, self.addr["B"])
        self.assertEqual(backorder.move_ids.product_uom_qty, 1)
        line_b = order.order_line.filtered(lambda l: l.dest_address_id == self.addr["B"])
        self.assertEqual(line_b.qty_delivered, 2)

    def test_invoice_follows_delivered_quantity(self):
        order = self._three_address_order()
        order.action_confirm()
        picking_a = self._picking_of(order, self.addr["A"])
        picking_a.move_ids.quantity = 4
        picking_a.button_validate()
        invoice = order._create_invoices()
        self.assertEqual(invoice.invoice_line_ids.mapped("quantity"), [4.0])
        invoice.action_post()
        self.assertEqual(invoice.state, "posted")

    # --- Address validation (BR-03) ---

    def test_address_of_another_customer_is_rejected_on_create(self):
        with self.assertRaises(ValidationError):
            self._make_order([(self.laptop, 1, self.other_addr)])

    def test_address_of_another_customer_is_rejected_on_write(self):
        order = self._make_order([(self.laptop, 1, self.addr["A"])])
        with self.assertRaises(ValidationError):
            order.order_line.dest_address_id = self.other_addr

    def test_changing_customer_revalidates_existing_addresses(self):
        order = self._make_order([(self.laptop, 1, self.addr["A"])])
        with self.assertRaises(ValidationError):
            order.partner_id = self.other_customer

    def test_invoice_type_address_is_rejected(self):
        with self.assertRaises(ValidationError):
            self._make_order([(self.laptop, 1, self.invoice_addr)])

    def test_customer_itself_and_company_siblings_are_accepted(self):
        contact = self.env["res.partner"].create(
            {"name": "Jane", "parent_id": self.customer.id, "type": "contact"}
        )
        order = self._make_order(
            [(self.laptop, 1, self.customer), (self.laptop, 1, self.addr["A"])],
            partner=contact,
        )
        self.assertEqual(len(order.order_line), 2)

    # --- Lock after confirmation (BR-08) ---

    def test_address_cannot_change_after_confirm(self):
        order = self._three_address_order()
        order.action_confirm()
        line = order.order_line[0]
        with self.assertRaises(UserError):
            line.dest_address_id = self.addr["C"]
        with self.assertRaises(UserError):
            line.dest_address_id = False

    def test_same_value_write_after_confirm_is_allowed(self):
        order = self._three_address_order()
        order.action_confirm()
        line = order.order_line[0]
        line.dest_address_id = line.dest_address_id
        line.write({"dest_address_id": line.dest_address_id.id})

    def test_address_editable_before_confirm(self):
        order = self._three_address_order()
        order.order_line[0].dest_address_id = self.addr["C"]
        self.assertEqual(order.order_line[0].dest_address_id, self.addr["C"])

    def test_new_line_with_address_can_be_added_after_confirm(self):
        order = self._three_address_order()
        order.action_confirm()
        order.write({"order_line": [Command.create({
            "product_id": self.mouse.id,
            "product_uom_qty": 2,
            "dest_address_id": self.addr["A"].id,
        })]})
        self.assertEqual(len(order.order_line), 4)

    # --- Access rights ---

    def test_salesman_can_run_the_whole_flow(self):
        salesman = self.env["res.users"].with_context(no_reset_password=True).create({
            "name": "Sally Salesman",
            "login": "sally_multi_delivery",
            "email": "sally@example.com",
            "groups_id": [Command.set([
                self.env.ref("base.group_user").id,
                self.env.ref("sales_team.group_sale_salesman").id,
            ])],
        })
        order = self._make_order(
            [(self.laptop, 4, self.addr["A"]), (self.laptop, 3, self.addr["B"])],
            user=salesman,
        )
        order.action_confirm()
        self.assertEqual(len(order.picking_ids), 2)
        with self.assertRaises(UserError):
            order.order_line[0].dest_address_id = self.addr["C"]
