from odoo import models, fields

class ResPartner(models.Model):
    _inherit = 'res.partner'

    # Campo para almacenar el ID único del usuario en Telegram
    telegram_chat_id = fields.Char(
        string='Telegram Chat ID', 
        index=True, 
        help='ID de usuario o chat devuelto por la API de Telegram'
    )