from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    # Lets the line view build its address domain from the order's customer
    # (`parent.` can only reach fields present on the parent view).
    delivery_commercial_partner_id = fields.Many2one(
        related="partner_id.commercial_partner_id",
        string="Delivery Customer",
    )

    @api.constrains("partner_id")
    def _check_lines_dest_address(self):
        self.order_line._check_dest_address()
