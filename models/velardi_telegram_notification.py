# -*- coding: utf-8 -*-
from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools.translate import _
from odoo import _, api, exceptions, fields, models
import json 
class VelardiTelegramNotification(models.Model):
    _name = "velardi.telegram.notification"
    _description = "Telegram Notification"
    _order = "create_date desc"

    chat_id = fields.Char(
                    string='Telegram Chat ID', 
                    index=True, 
                    help='ID de usuario o chat devuelto por la API de Telegram'
            )

    from_id = fields.Char(
            string='From Telegram Chat ID', 
            index=True, 
            help='ID de usuario o chat devuelto por la API de Telegram'
    )
    update_id = fields.Char(
                string='update_id Telegram', 
           
        )
    message_id = fields.Char(
                string='message_id Telegram Chat ID', 
              
        )
    from_is_bot = fields.Boolean(
        string="Simulation Mode", default=True,
        help="When on, messages are not actually sent - useful for testing.")
    
    from_first_name = fields.Char("From First Name")
    from_last_name = fields.Char("From Last Name")
    from_username = fields.Char("From Username")
    from_language_code = fields.Char("From language Code")
    
    chat_first_name = fields.Char("Chat First Name")
    chat_last_name = fields.Char("Chat Last Name")
    chat_username = fields.Char("Chat Username")
    chat_type = fields.Char("Chat type")
    text = fields.Text('Text send')
    update_type = fields.Char(
             required=False
           )
    date_notification = fields.Datetime(
        string='Última Interacción Telegram',
        help='Fecha y hora del último mensaje o acción recibida desde Telegram'
    )
    notification_type = fields.Selection(
        selection=[('outgoing', "outgoing"), ('incoming', "incoming")],
        default='outgoing',
    )
    notification_body = fields.Text(readonly=True)
       # Nuevo campo calculado para la visualización formateada
    notification_body_formatted = fields.Text(
        string="Cuerpo de la Notificación (Formateado)",
        compute='_compute_notification_body_formatted',
        store=False, # No es necesario almacenar este campo en la base de datos
        readonly=True,
        help="Representación formateada del JSON del cuerpo de la notificación."
    )
    notification_answered_option = fields.Char(
        string='Answered Option',
        help='Telegram interaction option that was answered by the user.'
    )

    date_notification_answered_option = fields.Datetime(
        string='Telegram Interaction Answer Time',
        help='Date and time when the user answered the Telegram interaction.'
    )

    answered_chat_id = fields.Char(
        string='Telegram Chat ID',
        help='User or chat ID returned by the Telegram API.'
    )

    @api.depends('notification_body')
    def _compute_notification_body_formatted(self):
        for record in self:
            if record.notification_body:
                try:
                    json_object = json.loads(record.notification_body)

                    record.notification_body_formatted = json.dumps(json_object, indent=4, ensure_ascii=False)
                except (json.JSONDecodeError, TypeError, ValueError):
                    # Si notification_body no es un JSON válido, o hay otro error
                    record.notification_body_formatted = "Error: Contenido no es un JSON válido o está corrupto."
            else:
                record.notification_body_formatted = False # O una cadena vacía si prefieres