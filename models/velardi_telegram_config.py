# -*- coding: utf-8 -*-
import requests
import logging
import json 
from odoo import fields, models
from odoo.exceptions import UserError
from odoo.tools.translate import _
from odoo import _, api, exceptions, fields, models
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot%s/sendMessage"

DEFAULT_JSON_CODE = """{
                    "text": "🏠 Main Menu\nChoose an option:",
                    "parse_mode": "HTML",
                    "reply_markup": {
                        "inline_keyboard": [
                        [
                            {
                            "text": "📋 View Task",
                            "callback_data": "menu_tasks"
                            },
                            {
                            "text": "📊 Reports",
                            "callback_data": "menu_reports"
                            }
                        ],
                        [
                            {
                            "text": "⚙️ Settings",
                            "callback_data": "menu_settings"
                            }
                        ],
                        [
                            {
                            "text": "❌ Close menu",
                            "callback_data": "menu_close"
                            }
                        ]
                        ]
                    }
                    }"""

class VelardiTelegramConfig(models.Model):
    _name = "velardi.telegram.config"
    _description = "Telegram Configuration"
    _order = "create_date desc"


    name = fields.Char(required=True)
    bot_token = fields.Char(
        string="Bot Token", required=True,
        help="Token from @BotFather, e.g. 123456:ABC-DEF...")
    default_chat_id = fields.Char(
        string="Default Chat ID",
        help="Chat, group or channel ID messages are sent to by default.")
    simulation = fields.Boolean(
        string="Simulation Mode", default=True,
        help="When on, messages are not actually sent - useful for testing.")
    active = fields.Boolean(default=True)
    webhook_path = fields.Char(
        string="Webhook Base URL",
        default=lambda self: self.env['ir.config_parameter'].sudo().get_param('web.base.url'),
        help="URL base para el webhook de Telegram")
    webhook_url = fields.Char(
        string="Registered Webhook URL",
        readonly=True,
        help="URL completa del webhook registrado en Telegram")
    save_notificaction = fields.Boolean("Save notificactions",default=False)
    last_status = fields.Char(string="Last Status", readonly=True)
    welcome_message =fields.Char(
        string="Welcome message",
        default="👋 Welcome! How can I help you today?",
        help=f"Content of the welcome message. If the type is 'JSON Payload', it must be valid JSON. eg:{DEFAULT_JSON_CODE}")
    welcome_message_type = fields.Selection(
            [("text", "Text"), ("payload", "Payload")],string="Welcome Message Type", default='text', required=True)

    enable_email_registration = fields.Boolean(default=False, help="Indicate whether it asks the user to register their email.")
    enable_phone_registration = fields.Boolean(default=False, help="Indicate whether it asks the user to register their phone number.")
    
    
    successful_registration_message = fields.Char(
        string="Registration Success Message",
        default="✅ Registration completed successfully. Welcome!",
        help=f"Message sent after a user completes registration successfully. If the type is 'Payload', it must be valid JSON.")
    successful_registration_message_type = fields.Selection(
            [("text", "Text"), ("payload", "Payload")], string="Registration Message Type", default='text', required=True)

    error_registration_message = fields.Char(
        string="Registration Error Message",
        default="❌ An error occurred during registration. Please try again.",
        help=f"Message sent when a registration attempt fails. If the type is 'Payload', it must be valid JSON.")
    error_registration_message_type = fields.Selection(
            [("text", "Text"), ("payload", "Payload")], string="Error Message Type", default='text', required=True)

    email_request_message = fields.Char(
        string="Email Request Message",
        default="📧 Please enter your email address.\n\n<i>You can cancel with /cancel</i>",
        help="Message sent when requesting the user's email. If the type is 'Payload', it must be valid JSON.")
    email_request_message_type = fields.Selection(
            [("text", "Text"), ("payload", "Payload")], string="Email Request Message Type", default='text', required=True)

    phone_request_message = fields.Char(
        string="Phone Request Message",
        default="📱 Please enter your phone number.\n\n<i>You can cancel with /cancel</i>",
        help="Message sent when requesting the user's phone number. If the type is 'Payload', it must be valid JSON.")
    phone_request_message_type = fields.Selection(
            [("text", "Text"), ("payload", "Payload")], string="Phone Request Message Type", default='text', required=True)
    
    command_ids = fields.One2many(
        'velardi.telegram.command', 'bot_config_id',
        string='Comandos'
    )

    @api.constrains('welcome_message_type', 'welcome_message')
    def _check_welcome_message_json(self):
        for record in self:
            if record.welcome_message_type == 'payload':
                if not record.welcome_message:
                    raise ValidationError("Welcome message cannot be empty when type is 'Payload JSON'.")
                raw = record.welcome_message.strip().strip('\ufeff')
                try:
                    json.loads(raw)
                except json.JSONDecodeError as e:
                    raise ValidationError(
                        "Welcome message must be valid JSON.\n"
                        "Error: %s" % e
                    )

    @api.constrains('successful_registration_message_type', 'successful_registration_message')
    def _check_successful_registration_message_json(self):
        for record in self:
            if record.successful_registration_message_type == 'payload':
                if not record.successful_registration_message:
                    raise ValidationError("Successful registration message cannot be empty when type is 'Payload JSON'.")
                raw = record.successful_registration_message.strip().strip('\ufeff')
                try:
                    json.loads(raw)
                except json.JSONDecodeError as e:
                    raise ValidationError(
                        "Successful registration message must be valid JSON.\n"
                        "Error: %s" % e
                    )

    @api.constrains('error_registration_message_type', 'error_registration_message')
    def _check_error_registration_message_json(self):
        for record in self:
            if record.error_registration_message_type == 'payload':
                if not record.error_registration_message:
                    raise ValidationError("Error message cannot be empty when type is 'Payload JSON'.")
                raw = record.error_registration_message.strip().strip('\ufeff')
                try:
                    json.loads(raw)
                except json.JSONDecodeError as e:
                    raise ValidationError(
                        "Error message must be valid JSON.\n"
                        "Error: %s" % e
                    )

    @api.constrains('email_request_message_type', 'email_request_message')
    def _check_email_request_message_json(self):
        for record in self:
            if record.email_request_message_type == 'payload':
                if not record.email_request_message:
                    raise ValidationError("Email request message cannot be empty when type is 'Payload JSON'.")
                raw = record.email_request_message.strip().strip('\ufeff')
                try:
                    json.loads(raw)
                except json.JSONDecodeError as e:
                    raise ValidationError(
                        "Email request message must be valid JSON.\n"
                        "Error: %s" % e
                    )

    @api.constrains('phone_request_message_type', 'phone_request_message')
    def _check_phone_request_message_json(self):
        for record in self:
            if record.phone_request_message_type == 'payload':
                if not record.phone_request_message:
                    raise ValidationError("Phone request message cannot be empty when type is 'Payload JSON'.")
                raw = record.phone_request_message.strip().strip('\ufeff')
                try:
                    json.loads(raw)
                except json.JSONDecodeError as e:
                    raise ValidationError(
                        "Phone request message must be valid JSON.\n"
                        "Error: %s" % e
                    )
                
    def send_message(self, text=None, chat_id=None, payload=None):
        """Send a message through this bot. Returns the Telegram API response
        (or a simulated payload when Simulation Mode is on).
        
        Args:
            text: Message text (used as default if payload not provided)
            chat_id: Chat ID (used as default if payload not provided)
            payload: Complete Telegram API payload (overrides text and chat_id)
        """
        self.ensure_one()
        
        if payload:
            final_payload = payload.copy()
            final_payload.setdefault('chat_id', chat_id or self.default_chat_id)
            final_payload.setdefault('text', text or '')
        else:
            chat = chat_id or self.default_chat_id
            if not chat:
                raise UserError(_("No Telegram chat ID set for bot '%s'.") % self.name)
            final_payload = {
                "chat_id": chat,
                "text": text or '',
                "parse_mode": "HTML",
            }
        
        if not final_payload.get('chat_id'):
            raise UserError(_("No Telegram chat ID set for bot '%s'.") % self.name)
        
        msg_text = final_payload.get('text', '')
        msg_chat = final_payload.get('chat_id', '')
        
        if self.simulation:
            self.last_status = _("Simulated")
            return {"ok": True, "simulated": True, "text": msg_text, "chat_id": msg_chat}
        try:
            _logger.info("[Telegram] final_payload: %s", final_payload)
            response = requests.post(
                TELEGRAM_API % self.bot_token,
                json=final_payload,
                timeout=5
            )
            res_data = response.json() if response.content else {}
            if response.status_code == 200 and res_data.get("ok"):
                message_id = res_data.get("result", {}).get("message_id")
                _logger.info("[Telegram] Message sent OK. Message ID: %s", message_id)
                if self.save_notificaction:
                    result_msg = res_data.get("result", {})
                    from_info = result_msg.get("from", {})
                    chat_info = result_msg.get("chat", {})
                    message = result_msg.get("message", {})
                    self.env['velardi.telegram.notification'].create({
                        'update_id': str(result_msg.get("update_id", "")),
                        'message_id': str(result_msg.get("message_id", "")),
                        'from_id': str(from_info.get("id", "")),
                        'from_id': str(from_info.get("id", "")),
                        'from_is_bot': from_info.get("is_bot", ""),
                        'from_first_name': from_info.get("first_name", ""),
                        'from_last_name': from_info.get("last_name", ""),
                        'from_username': from_info.get("username", ""),
                        'from_language_code': from_info.get("language_code", ""),
                        'chat_id': str(chat_info.get("id", "")),
                        'chat_first_name': chat_info.get("first_name", ""),
                        'chat_last_name': chat_info.get("last_name", ""),
                        'chat_username': chat_info.get("username", ""),
                        'chat_type': chat_info.get("type", ""),
                        'text': msg_text,
                        'date_notification': fields.Datetime.now(),
                        'notification_type': 'outgoing',
                        'notification_body':final_payload
                    })
            else:
                error_desc = res_data.get("description", response.text)
                error_code = res_data.get("error_code", response.status_code)
                _logger.error("[Telegram] Error (%s): %s", error_code, error_desc)
        except Exception as exc:
            self.last_status = _("Error: %s") % exc
            raise UserError(_("Could not reach Telegram: %s") % exc)
        if not res_data.get("ok"):
            self.last_status = _("Error: %s") % res_data.get("description")
            raise UserError(_("Telegram error: %s") % res_data.get("description"))
        self.last_status = _("Sent")
        return res_data

    def action_send_test(self):
        self.ensure_one()
        self.send_message(_("Test alert from Odoo (%s).") % self.name)
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {"title": _("Telegram"),
                       "message": _("Test message sent (status: %s).") % self.last_status,
                       "type": "success", "sticky": False},
        }


    def action_register_webhook(self):
            """Registra la URL del webhook en Telegram."""
            self.ensure_one()
            base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url')
            if base_url != self.webhook_path:
                webhook_endpoint = self.webhook_path
            else:
                webhook_endpoint = f'{base_url}/telegram/webhook/{self.id}'

            
            url = f'https://api.telegram.org/bot{self.bot_token}/setWebhook'
            payload = {'url': webhook_endpoint}
            _logger.info('Registro de url : %s', url)
            _logger.info('Registro de webhook_endpoint url : %s', webhook_endpoint)

            try:
                response = requests.post(url, json=payload, timeout=10)
                response.raise_for_status()
                data = response.json()
                if data.get('ok'):
                    self.webhook_url = webhook_endpoint
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {
                            'title': _('Webhook Registrado'),
                            'message': _('La URL del webhook se ha registrado correctamente.'),
                            'type': 'success',
                        }
                    }
                else:
                    raise UserError(_('Error al registrar webhook: %s') % data.get('description'))
            except requests.exceptions.RequestException as e:
                raise UserError(_('Error de conexión: %s') % str(e))