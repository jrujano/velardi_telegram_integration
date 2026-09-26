# -*- coding: utf-8 -*-
from odoo import fields, models


class ServerAction(models.Model):
    _inherit = "ir.actions.server"

    usage = fields.Selection(
        selection_add=[('velardi_telegram_integration', 'Telegram Automation')],
        ondelete={'velardi_telegram_integration': 'cascade'},
    )

    velardi_telegram_automation_id = fields.Many2one(
        "velardi.telegram.msg.automation",
        string="Telegram Automation Rule",
        ondelete="cascade",
    )
