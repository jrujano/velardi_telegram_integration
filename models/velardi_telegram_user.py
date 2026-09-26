from odoo import models, fields, api
from odoo.exceptions import ValidationError

class VelardiTelegramUser(models.Model):
    _name = 'velardi.telegram.user'
    _description = 'Telegram Linked User'
    user_id = fields.Many2one(
    'res.users',
        string='Odoo User',
        ondelete='set null',
        index=True,
        help='Odoo user whose permissions will be applied when processing messages.',
    )
    partner_id = fields.Many2one('res.partner', string='Contact', ondelete='set null')
    chat_id = fields.Char(string='Telegram Chat ID', required=True, )
    first_name= fields.Char(string='Telegram First Name', required=False, )
    last_name= fields.Char(string='Telegram Last Name', required=False, )
    telegram_username= fields.Char(string='Telegram Username', required=False, )
    language_code= fields.Char(string='Language Code', required=False, )

    config_id = fields.Many2one(
            "velardi.telegram.config", string="Bot Configuration",
            required=True, ondelete="cascade")
    active = fields.Boolean(string='Active', default=True)
    last_interaction = fields.Datetime(string='Last Interaction')

    # NUEVOS CAMPOS
    email = fields.Char(string='Telegram Email')
    phone_number = fields.Char(string='Phone Number')
    state = fields.Selection([
        ('new', 'new'),
        ('idle', 'Idle'),
        ('awaiting_email', 'Awaiting Email'),
        ('email_received', 'Email Received'),
        ('awaiting_phone', 'Awaiting Phone'),
        ('registered', 'Registered'),
    ], string='State', default='idle')
    awaiting_message_id = fields.Char(
        string='Request Message ID',
        help='message_id of the force_reply message we are waiting for'
    )
    state_updated = fields.Datetime(string='Last State Update')

    _sql_constraints = [
        ('unique_chat_id_bot', 'UNIQUE(chat_id, config_id)',
         'Chat ID must be unique per bot.'),
    ]