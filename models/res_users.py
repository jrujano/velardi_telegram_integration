import logging
from odoo import models, api, _

_logger = logging.getLogger(__name__)


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _link_odoo_user_by_email(self, telegram_user, email):
        """
        Busca un res.users con ese email y lo vincula al telegram.user.
        Retorna el res.users encontrado o None.
        """
        odoo_user = self.sudo().search([
            ('email', '=', email),
            ('active', '=', True),
        ], limit=1)

        if odoo_user:
            telegram_user.write({'user_id': odoo_user.id})
            _logger.info(
                "[Telegram] Vinculado chat_id=%s con res.users=%s (ID %s)",
                telegram_user.chat_id, odoo_user.name, odoo_user.id
            )
        else:
            _logger.info(
                "[Telegram] No se encontró res.users con email=%s. Sin vincular.",
                email
            )

        return odoo_user
