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
TELEGRAM_API_PHOTO = "https://api.telegram.org/bot%s/sendPhoto"

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
    @api.onchange('enable_email_registration')
    def _onchange_enable_email_registration(self):
        """
        Si campo_a cambia a False, campo_b también debe cambiar a False.
        """
        if not self.enable_email_registration:  
            self.enable_phone_registration = False 
            
    def _save_outgoing_notification(self, res_data, msg_text, payload):
        _logger.info("""Save outgoing notification if save_notificaction is enabled.""")
        if not self.save_notificaction:
            return
        result_msg = res_data.get("result", {})
        from_info = result_msg.get("from", {})
        chat_info = result_msg.get("chat", {})
        self.env['velardi.telegram.notification'].create({
            'update_id': str(result_msg.get("update_id", "")),
            'message_id': str(result_msg.get("message_id", "")),
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
            'notification_body': payload,
        })

    def send_message(self, text=None, chat_id=None, payload=None):
        """Send a message through this bot. Returns the Telegram API response
        (or a simulated payload when Simulation Mode is on).
        
        Args:
            text: Message text (used as default if payload not provided)
            chat_id: Chat ID (used as default if payload not provided)
            payload: Complete Telegram API payload (overrides text and chat_id)
        """
        self.ensure_one()
        _logger.info("\n[Telegram]== send_message",)
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
        _logger.warning("\n[Telegram]== msg_text = %s", msg_text)
        if self.simulation:
            self.last_status = _("Simulated")
            return True
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
                self._save_outgoing_notification(res_data, msg_text, final_payload)
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
        return str(res_data.get("result", {}).get("message_id", ""))

    def send_photo(self, photo, chat_id=None, caption=None, payload=None):
        """Send a photo through this bot. Returns the message_id on success.
        
        Args:
            photo: File ID, URL, or local file path of the photo
            chat_id: Chat ID (defaults to self.default_chat_id)
            caption: Optional caption text for the photo
            payload: Extra fields (reply_markup, parse_mode, etc.)
        """
        self.ensure_one()

        chat = chat_id or self.default_chat_id
        if not chat:
            raise UserError(_("No Telegram chat ID set for bot '%s'.") % self.name)

        if self.simulation:
            self.last_status = _("Simulated")
            return True

        body = dict(payload) if payload else {}
        body.setdefault('chat_id', chat)
        body['photo'] = photo
        if caption:
            body['caption'] = caption
            body.setdefault('parse_mode', 'HTML')

        is_url = photo.startswith(('http://', 'https://'))

        try:
            _logger.info("[Telegram] send_photo chat_id=%s photo=%s", chat, photo)
            if is_url:
                response = requests.post(
                    TELEGRAM_API_PHOTO % self.bot_token,
                    json=body,
                    timeout=10
                )
            else:
                files = {'photo': open(photo, 'rb')}
                response = requests.post(
                    TELEGRAM_API_PHOTO % self.bot_token,
                    data=body,
                    files=files,
                    timeout=10
                )
                files['photo'].close()

            res_data = response.json() if response.content else {}
            if response.status_code == 200 and res_data.get("ok"):
                message_id = res_data.get("result", {}).get("message_id")
                _logger.info("[Telegram] Photo sent OK. Message ID: %s", message_id)
                self._save_outgoing_notification(res_data, caption or '', body)
                self.last_status = _("Sent")
                return str(message_id) if message_id else ""
            else:
                error_desc = res_data.get("description", response.text)
                error_code = res_data.get("error_code", response.status_code)
                _logger.error("[Telegram] sendPhoto Error (%s): %s", error_code, error_desc)
                self.last_status = _("Error: %s") % error_desc
                raise UserError(_("Telegram error: %s") % error_desc)
        except UserError:
            raise
        except Exception as exc:
            self.last_status = _("Error: %s") % exc
            raise UserError(_("Could not reach Telegram: %s") % exc)

    def lock_inline_keyboard(self, chat_id, message_id,
                            original_caption=None, result_text=None,
                            parse_mode=None, is_media=True,  reply_markup=None):
        """Lock inline keyboard on a message, keeping original content
        and appending result text. Removes the keyboard by not sending
        reply_markup.

        Args:
            chat_id: Telegram chat ID
            message_id: Message ID to edit
            original_caption: Original caption to preserve (for media)
            result_text: Text to append as result
            parse_mode: Parse mode (HTML, Markdown, etc.)
            is_media: True for editMessageCaption, False for editMessageText
        """
        self.ensure_one()
        KEEP_MARKUP = object()
        url = f"https://api.telegram.org/bot{self.bot_token}"

        if result_text:
            base = original_caption or ''
            new_content = f"{base}\n\n{result_text}" if base else result_text

            if is_media:
                payload = {
                    'chat_id': chat_id,
                    'message_id': message_id,
                    'caption': new_content,
                }
                if reply_markup is not None:
                    # Reemplazar el teclado por el que se pasa
                    payload['reply_markup'] = reply_markup
                if parse_mode:
                    payload['parse_mode'] = parse_mode
                response = requests.post(f"{url}/editMessageCaption", json=payload, timeout=10)
            else:
                payload = {
                    'chat_id': chat_id,
                    'message_id': message_id,
                    'text': new_content,
                }
                if reply_markup is not None:
                    # Reemplazar el teclado por el que se pasa
                    payload['reply_markup'] = reply_markup
                if parse_mode:
                    payload['parse_mode'] = parse_mode
                response = requests.post(f"{url}/editMessageText", json=payload, timeout=10)
        else:
            payload = {
                'chat_id': chat_id,
                'message_id': message_id,
            }
            if reply_markup is not None:
                # Reemplazar el teclado por el que se pasa
                payload['reply_markup'] = reply_markup
            response = requests.post(f"{url}/editMessageReplyMarkup", json=payload, timeout=10)

        res_data = response.json() if response.content else {}
        if not res_data.get("ok"):
            _logger.error("[Telegram] lock_inline_keyboard error: %s", res_data.get("description"))
        return res_data

    def answer_callback_query(self, callback_query_id):
        """Answer a callback query from inline keyboard."""
        self.ensure_one()
        response = requests.post(
            f"https://api.telegram.org/bot{self.bot_token}/answerCallbackQuery",
            json={"callback_query_id": callback_query_id},
            timeout=10,
        )
        res_data = response.json() if response.content else {}
        if not res_data.get("ok"):
            _logger.error("[Telegram] answerCallbackQuery error: %s", res_data.get("description"))
        return res_data

    def edit_message_text(self, chat_id, message_id, text, parse_mode=None,
                          reply_markup=None):
        """Edit a text message."""
        self.ensure_one()
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup:
            payload["reply_markup"] = reply_markup
        response = requests.post(
            f"https://api.telegram.org/bot{self.bot_token}/editMessageText",
            json=payload,
            timeout=10,
        )
        res_data = response.json() if response.content else {}
        if not res_data.get("ok"):
            _logger.error("[Telegram] editMessageText error: %s", res_data.get("description"))
        return res_data

    def edit_message_reply_markup(self, chat_id, message_id, reply_markup=None):
        """Edit the reply markup of a message."""
        self.ensure_one()
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        response = requests.post(
            f"https://api.telegram.org/bot{self.bot_token}/editMessageReplyMarkup",
            json=payload,
            timeout=10,
        )
        res_data = response.json() if response.content else {}
        if not res_data.get("ok"):
            _logger.error("[Telegram] editMessageReplyMarkup error: %s", res_data.get("description"))
        return res_data

    def set_my_commands(self, commands):
        """Set the bot's commands list.
        Args:
            commands: list of dicts [{"command": "start", "description": "..."}]
        """
        self.ensure_one()
        response = requests.post(
            f"https://api.telegram.org/bot{self.bot_token}/setMyCommands",
            json={"commands": commands},
            timeout=10,
        )
        res_data = response.json() if response.content else {}
        if not res_data.get("ok"):
            _logger.error("[Telegram] setMyCommands error: %s", res_data.get("description"))
        return res_data

    def delete_my_commands(self):
        """Delete all bot commands."""
        self.ensure_one()
        response = requests.post(
            f"https://api.telegram.org/bot{self.bot_token}/deleteMyCommands",
            json={},
            timeout=10,
        )
        res_data = response.json() if response.content else {}
        if not res_data.get("ok"):
            _logger.error("[Telegram] deleteMyCommands error: %s", res_data.get("description"))
        return res_data

    def get_my_commands(self):
        """Get the bot's current commands list."""
        self.ensure_one()
        response = requests.get(
            f"https://api.telegram.org/bot{self.bot_token}/getMyCommands",
            timeout=10,
        )
        response.raise_for_status()
        return response.json().get("result", [])

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
                webhook_endpoint = f'{self.webhook_path}/{self.id}'
            else:
                webhook_endpoint = f'{base_url}/telegram/webhook/{self.id}'

            
            url = f'https://api.telegram.org/bot{self.bot_token}/setWebhook'
            payload = {'url': webhook_endpoint}
            _logger.info(f"[Telegram] payload {payload}")
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