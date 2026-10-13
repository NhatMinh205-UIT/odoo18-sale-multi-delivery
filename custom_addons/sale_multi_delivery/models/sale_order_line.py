from odoo import api, models
from odoo.exceptions import UserError, ValidationError


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    @api.constrains("dest_address_id", "order_id")
    def _check_dest_address(self):
        for line in self.filtered("dest_address_id"):
            address = line.dest_address_id
            customer = line.order_id.partner_id.commercial_partner_id
            if address.commercial_partner_id != customer or address.type in ("invoice", "private"):
                raise ValidationError(
                    self.env._(
                        "%(address)s is not a valid delivery address of customer %(customer)s.",
                        address=address.display_name,
                        customer=customer.display_name,
                    )
                )

    def write(self, vals):
        if "dest_address_id" in vals:
            new_address_id = vals["dest_address_id"] or False
            for line in self:
                if line.order_id.state == "sale" and (line.dest_address_id.id or False) != new_address_id:
                    raise UserError(
                        self.env._("The destination address cannot be changed after the order is confirmed.")
                    )
        return super().write(vals)
