import logging
from odoo import models, fields, _

_logger = logging.getLogger(__name__)


class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Campo para almacenar el ID único del usuario en Telegram
    telegram_chat_id = fields.Char(
        string='Telegram Chat ID',
        index=True,
        help='ID de usuario o chat devuelto por la API de Telegram'
    )

    def _create_partner_from_telegram(self, from_user, chat_id=False):
        """
        Crea un res.partner a partir de los datos de un usuario de Telegram.

        :param from_user: dict con 'first_name', 'last_name', 'username', etc.
        :param chat_id: str con el chat_id de Telegram
        :return: record de res.partner
        """
        first_name = (from_user.get('first_name') or '').strip()
        last_name = (from_user.get('last_name') or '').strip()
        username = from_user.get('username')

        # Construir nombre completo
        if first_name or last_name:
            full_name = f"{first_name} {last_name}".strip()
        elif username:
            full_name = f"@{username}"
        else:
            full_name = f"Telegram {from_user.get('id', 'Desconocido')}"

        vals = {
            'name': full_name,
            'is_company': False,
        }

        if username:
            vals['complete_name'] = f"Telegram: @{username}"

        if chat_id:
            vals['telegram_chat_id'] = str(chat_id)

        return self.sudo().create(vals)