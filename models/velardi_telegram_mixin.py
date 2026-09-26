import requests
import json
import re
import time
import logging
import requests
from collections import defaultdict
from datetime import datetime, date, timezone, timedelta
from dateutil.parser import parse as parse_date 
from dateutil.relativedelta import relativedelta
from odoo import models, api, _
from odoo.exceptions import UserError
from odoo.tools import html_escape
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare
from odoo.tools.safe_eval import safe_eval, wrap_module
from email.utils import parseaddr

# Regex estricta para validar emails
EMAIL_REGEX = re.compile(
    r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?"
    r"(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$"
)

_logger = logging.getLogger(__name__)
wrapped_requests = wrap_module(requests, ['post', 'get', 'put', 'delete', 'head', 'patch', 'options'])
class VelardiTelegramMixin(models.AbstractModel):
    _name = 'velardi.telegram.mixin'
    _description = 'Telegram message sending mixin'

    @api.model
    def _process_incoming_update(self, bot_config,update_data):
        _logger.warning("[Telegram] Update recibido: %s", list(update_data.keys()))

        # Obtener el tipo de evento y su contenido específico
        update_type, payload = self._get_update_type_and_payload(update_data)

        _logger.info(f"\n[Telegram] Tipo de actualización recibida: {update_type}")
        _logger.info(f"\n[Telegram] payload recibido: {payload}")

        # Extraer el chat_id según el tipo de respuesta
        chat_id = False
        if update_type in ['message', 'edited_message']:
            chat_id = str(payload.get('chat', {}).get('id', ''))
            message = update_data.get('message') or update_data.get('edited_message')
        elif update_type == 'callback_query':
            chat_id = str(payload.get('message', {}).get('chat', {}).get('id', ''))
            message =payload.get('message', {})
        elif update_type in ['my_chat_member', 'chat_member']:
            chat_id = str(payload.get('chat', {}).get('id', ''))

        if not chat_id:
            _logger.warning(f"\n[Telegram] Evento {update_type} no contiene un chat_id procesable.")
            return


        from_user = message.get('from', {})
        text = (message.get('text') or '').strip()

        # Guardar notificación si está activo (sin romper el flujo)
        if bot_config.save_notificaction:
            try:
                self._save_notification(update_data, update_type)
            except Exception as e:
                _logger.error("[Telegram] Error guardando notificación: %s", e)

        
        # Obtener o crear el telegram.user SIEMPRE
        telegram_user = self._get_or_create_telegram_user(
            bot_config, from_user, chat_id
        )

        telegram_user.write({'last_interaction': fields.Datetime.now()})

        # 5. Detectar si es comando REAL (offset=0)
        entities = message.get('entities', [])
        is_command = any(
            e.get('type') == 'bot_command' and e.get('offset', -1) == 0
            for e in entities
        )
        has_email = any(e['type'] == 'email' for e in entities)
        has_phone_number = any(e['type'] == 'phone_number' for e in entities)

        _logger.info("\n[Telegram] entities: %s", entities)
        _logger.info("\n[Telegram] has_email: %s", has_email)

        if is_command:
            _logger.info("[Telegram] comando: %s", is_command)
            return self._handle_command(bot_config, telegram_user, chat_id, text, message)
            
        if update_type == 'callback_query':
            return self._handle_callback(bot_config, update_data, telegram_user)

        message = update_data.get('message') or update_data.get('edited_message')
        if not message:
            _logger.warning("[Telegram] Update sin message ni callback. Ignorado.")
            return
        
        if has_email and telegram_user.state == 'awaiting_email':
            return self._process_email(
                bot_config, telegram_user, chat_id, message, text
            )
        if (message.get("contact") and telegram_user.state == 'awaiting_phone')or (has_phone_number  and telegram_user.state == 'awaiting_phone'):
            _logger.warning("[Telegram] Esperanod numeor de relefono.")
            return self._process_phone(
                            bot_config, telegram_user, chat_id, message
                        )
            
        
        return
    
    def _handle_command(self, bot_config, telegram_user, chat_id, text, message):
        """Handle explicit commands (/start, /menu, etc.)."""
        if text == '/start':
            # TODO : REvisar
            # remover el menu
            # url = f"https://api.telegram.org/bot{bot_config.bot_token}/setMyCommands"

            # payload = {
            #     "commands": [],
            #     "scope": {
            #         "type": "chat",
            #         "chat_id": chat_id
            #     }
            # }

            # requests.post(url, json=payload, timeout=0.5)
            self._send_welcome_message(bot_config, chat_id, message)

        elif text == '/menu':
            self._send_welcome_message_menu(
                bot_config, chat_id, '🏠 <b>Main Menu</b>\nChoose an option:'
            )

        elif text == '/replykeyboard':
            self._send_welcome_message_replykeyboard(
                bot_config, chat_id, 'Choose an option from the keyboard:'
            )

        elif text == '/inlinekeyboard':
            self._send_welcome_message_inlinekeyboard(
                bot_config, chat_id, '🏠 <b>Main Menu</b>\nChoose an option:'
            )

        elif text == '/cancel':
            # Send cancellation message before deleting
            bot_config.send_message("❌ Operation cancelled. Your data has been deleted.", chat_id)
            
            # Delete the telegram user record
            if telegram_user:
                telegram_user.unlink()
                _logger.info("[Telegram] User %s deleted via /cancel", chat_id)
            
            # Delete the chat using Telegram API
            import requests
            try:
                url = f"https://api.telegram.org/bot{bot_config.bot_token}/deleteChat"
                response = requests.post(url, json={"chat_id": chat_id}, timeout=10)
                _logger.info("[Telegram] Delete chat response: %s", response.json())
            except Exception as e:
                _logger.warning("[Telegram] Could not delete chat %s: %s", chat_id, e)

        else:
            # Comando personalizado → delegar
            self._process_custom_command(bot_config, chat_id, text)

    def _save_notification(self, update_data, update_type):
            """Save incoming notification to velardi.telegram.notification model."""
            if update_type == 'callback_query':
                message = update_data.get('callback_query', {}).get('message', {})
            elif update_type == 'inline_query':
                message = {}
            elif update_type == 'bot_command':
                message = update_data.get('message', {})
            else:
                message = update_data.get('message', {})

            from_info = message.get('from', {})
            chat_info = message.get('chat', {})
    
            date_timestamp = message.get('date')
            date_notification = False
            if date_timestamp:
                date_notification = datetime.fromtimestamp(date_timestamp)
            
            self.env['velardi.telegram.notification'].sudo().create({
                'message_id': str(message.get('message_id', '')),
                'update_id': update_data.get('update_id', False),
                'from_id': str(from_info.get('id', '')),
                'from_is_bot': from_info.get('is_bot', False),
                'from_first_name': from_info.get('first_name', ''),
                'from_last_name': from_info.get('last_name', ''),
                'from_username': from_info.get('username', ''),
                'from_language_code': from_info.get('language_code', ''),
                'chat_id': str(chat_info.get('id', '')),
                'chat_first_name': chat_info.get('first_name', ''),
                'chat_last_name': chat_info.get('last_name', ''),
                'chat_username': chat_info.get('username', ''),
                'chat_type': chat_info.get('type', ''),
                'text': message.get('text', ''),
                'update_type': update_type,
                'date_notification': date_notification,
                'notification_type': 'incoming',
                'notification_body':update_data
            })

    def _send_welcome_message(self, bot_config, chat_id, message):
        """Send welcome message with inline keyboard."""
        
        first_name = message.get('from', {}).get('first_name', '')
        last_name = message.get('from', {}).get('last_name', '')
        _logger.info(bot_config.welcome_message_type )
        if bot_config.welcome_message_type == 'text':
            text = bot_config.welcome_message
            text = text.replace("{{first_name}}",first_name).replace("{{last_name}}",last_name)

            bot_config.send_message(text, chat_id)
        else:
            welcome_message = bot_config.welcome_message
            welcome_message = welcome_message.replace("{{first_name}}",first_name).replace("{{last_name}}",last_name)
            payload= json.loads(welcome_message)
            bot_config.send_message('', chat_id, payload)     
        
    
    
    def _handle_callback(self, bot_config, update_data, telegram_user):
        update_id = update_data.get("update_id")              # Para logs / idempotencia
        callback = update_data.get("callback_query")  
        callback_id = callback["id"]                          # Para answerCallbackQuery
        message_id = callback["message"]["message_id"]        # Para editar el mensaje
        chat_id = str(callback["message"]["chat"]["id"])
        data = callback["data"]
        
        _logger.info(
            "Evento %s → callback %s, mensaje %s, chat %s, data '%s'",
            update_id, callback_id, message_id, chat_id, data
        )
        
        # 1. Responder al callback (obligatorio)
        requests.post(
            f"https://api.telegram.org/bot{bot_config.bot_token}/answerCallbackQuery",
            json={"callback_query_id": callback_id},
            timeout=10,)

        if data == "start_registration":
            self._start_registration(bot_config, telegram_user, chat_id, message_id)

        
    # TODO: REvisar comportamiento
    def _edit_message(self, bot_config, chat_id, message_id, texto, opciones, force_reply=False, selective=False):
        """Edita el mensaje existente en lugar de enviar uno nuevo."""
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": texto,
            "parse_mode": "HTML",
            "reply_markup": {"inline_keyboard": opciones, "force_reply": force_reply,"selective":selective},
        }
        # requests.post(
        #     f"https://api.telegram.org/bot{bot_config.bot_token}/editMessageText",
        #     json=payload,
        #     timeout=10,
        # )

        requests.post(
                    f"https://api.telegram.org/bot{bot_config.bot_token}/editMessageReplyMarkup",
                    json=payload,
                    timeout=10,
                )
        
    
    def _send_welcome_message_menu(self, bot_config, chat_id, text):
        payload = {
               
                "parse_mode": "HTML",
                "reply_markup": {
                    "inline_keyboard": [
                        [
                            {"text": "📋 View Tasks", "callback_data": "menu_tareas"},
                            {"text": "📊 Reports", "callback_data": "menu_reportes"},
                        ],
                        [
                            {"text": "⚙️ Settings", "callback_data": "menu_config"},
                        ],
                        [
                            {"text": "❌ Close Menu", "callback_data": "menu_cerrar"},
                        ],
                    ]
                },
            }
        bot_config.send_message(text, chat_id, payload)

    def _send_welcome_message_replykeyboard(self, bot_config, chat_id, text):
        payload = {
            "reply_markup": {
                "keyboard": [
                    [{"text": "📋 View Tasks"}, {"text": "📊 Reports"}],
                    [{"text": "⚙️ Settings"}],
                    [{"text": "❌ Cancel"}],
                ],
                "resize_keyboard": True,        # Ajusta el tamaño al contenido
                "one_time_keyboard": True,      # Se oculta tras usarlo
                "input_field_placeholder": "Choose an option...",
            },
        }
        bot_config.send_message(text, chat_id, payload)

    def _send_welcome_message_inlinekeyboard(self, bot_config, chat_id, text):
        payload = {
            "chat_id": chat_id,
            "text": "🏠 <b>Main Menu</b>\nChoose an option:",
            "parse_mode": "HTML",
            "reply_markup": {
                "inline_keyboard": [
                    [
                        {"text": "📋 View Tasks", "callback_data": "ver_tareas"},
                        {"text": "📊 Reports", "callback_data": "ver_reportes"},
                    ],
                    [
                        {"text": "⚙️ Settings", "callback_data": "config"},
                    ],
                    [
                        {"text": "🌐 Open Website", "url": "https://ejemplo.com"},
                    ],
                ]
            },
        }
        bot_config.send_message(text, chat_id, payload)

    def _process_custom_command(self, bot_config, chat_id, text, user=None):
        text=text.replace("/","")
        # user = user or self.env.user
        user = self.env['res.users'].sudo().search([('id', '=', 2)], limit=1)
        if not user:
            user = self.env.ref('base.user_admin')
        user_env = self.env(user=user)
        self_user = self.with_env(user_env)
        
        localdict = {
                'env':user_env,
                'user': user,                   # Usuario actual
                'self': self_user,                            # Tu objeto actual
                'bot_config': bot_config,                # Configuración del bot
                'bot_token': bot_config.bot_token,   # Token del bot de Telegram
                '_logger': _logger,
                'log': self.custom_log,
                # Inyectamos solo las clases necesarias (NO el módulo entero)
                'datetime': datetime,                    # La clase datetime (ej: datetime.now())
                'date': date,                            # La clase date (ej: date.today())
                'relativedelta': relativedelta,                    # dateutil.parser, dateutil.relativedelta, etc.
                'timezone': timezone,                    # Timezone utilities
                'timedelta': timedelta,      
                'dateutil_parser': parse_date,            # La clase timedelta (ej: timedelta(days=7))
                'float_compare': float_compare,          # float_compare(val1, val2, precision_digits=2)
                'UserError': UserError,
                'requests': wrapped_requests,
                'html_escape':html_escape,
            }
        # _logger.info(bot_config)
        menu_cmd = bot_config.command_ids.filtered(lambda c: c.command == text)
      
        if menu_cmd and menu_cmd.code:
            safe_eval(menu_cmd.code, localdict, mode="exec", nocopy=True)
        
    
    def _get_or_create_telegram_user(self, bot_config, from_user, chat_id):
        """
        Busca el telegram.user asociado al chat_id y bot_config.
        Si no existe, lo crea junto con su res.partner.

        :param bot_config: record de telegram.bot.config
        :param from_user: dict con los datos del usuario de Telegram
                        (message['from'] o callback['from'])
        :param chat_id: str con el chat_id de Telegram
        :return: record de telegram.user
        """
        chat_id = str(chat_id)

        # 1. Buscar si ya existe
        telegram_user = self.env['velardi.telegram.user'].sudo().search([
            ('chat_id', '=', chat_id),
            ('config_id', '=', bot_config.id),
        ], limit=1)

        if telegram_user:
            # Actualizar datos que puedan haber cambiado en Telegram
            # (nombre, username, idioma). No toca email, state ni user_id.
            updates = {}
            if from_user.get('first_name') and from_user['first_name'] != telegram_user.first_name:
                updates['first_name'] = from_user['first_name']
            if from_user.get('last_name') and from_user.get('last_name') != telegram_user.last_name:
                updates['last_name'] = from_user['last_name']
            if from_user.get('username') and from_user.get('username') != telegram_user.telegram_username:
                updates['telegram_username'] = from_user['username']
            if from_user.get('language_code') and from_user.get('language_code') != telegram_user.language_code:
                updates['language_code'] = from_user['language_code']

            if updates:
                telegram_user.write(updates)
                _logger.info(
                    "[Telegram] Datos actualizados para chat_id=%s: %s",
                    chat_id, list(updates.keys())
                )

            return telegram_user

        # 2. No existe → crear partner y velardi_telegram_user
        _logger.info(
            "[Telegram] Nuevo usuario detectado. chat_id=%s, bot=%s",
            chat_id, bot_config.name
        )

        partner = self._create_partner_from_telegram(from_user)
        telegram_user = self.env['velardi.telegram.user'].sudo().create({
            'partner_id': partner.id,
            'config_id': bot_config.id,
            'chat_id': chat_id,
            'first_name': from_user.get('first_name', ''),
            'last_name': from_user.get('last_name', ''),
            'telegram_username': from_user.get('username', False),
            'language_code': from_user.get('language_code', False),
            'state': 'new',
            'state_updated': fields.Datetime.now(),
            'last_interaction': fields.Datetime.now(),
        })

        return telegram_user


    def _create_partner_from_telegram(self, from_user):
        """
        Crea un res.partner a partir de los datos de un usuario de Telegram.

        :param from_user: dict con 'first_name', 'last_name', 'username', etc.
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
            # Campo estándar de Odoo 18 para redes sociales / username
            # Si no existe en tu versión, usa un Char personalizado
            vals['complete_name'] = f"Telegram: @{username}"

        return self.env['res.partner'].sudo().create(vals)
    

    def _start_registration(self, bot_config, telegram_user, chat_id, message_id):
        # 1. Quitar solo los botones (el texto queda igual)
        requests.post(
            f"https://api.telegram.org/bot{bot_config.bot_token}/editMessageText",
            json={
                "chat_id": chat_id,
                "message_id": message_id,
            },
            timeout=10,
        )

        # 2. Cambiar estado
        telegram_user.write({
            'state': 'awaiting_email',
            'state_updated': fields.Datetime.now(),
        })


        if bot_config.email_request_message_type == 'text':
            email_text = bot_config.email_request_message or "📧 Please enter your email address.\n\n<i>You can cancel with /cancel</i>"
            result = bot_config.send_message(email_text, chat_id, )
        else:
            email_payload = bot_config.email_request_message or '{"text": "📧 Please enter your email address.\n\n<i>You can cancel with /cancel</i>", "parse_mode": "HTML", "reply_markup": {"force_reply": true, "selective": true, "input_field_placeholder": "your@email.com"}}'
            payload = json.loads(email_payload)
            result = bot_config.send_message('', chat_id, payload)
        
        _logger.info(f"[Telegram] {type(result)}")
        _logger.info(f"[Telegram] {result}")
        if result.get("ok"):
            new_msg_id = str(result["result"]["message_id"])
            _logger.info(f"new_msg_id {new_msg_id}")
            telegram_user.write({'awaiting_message_id': new_msg_id})

    def _send_phone_request_message(self, bot_config, chat_id, telegram_user, message_id):
        """Send phone request message with force_reply."""
        # import requests

        # url = f"https://api.telegram.org/bot{bot_config.bot_token}/editMessageText"
        # requests.post(
        #     url,
        #     json={
        #         "chat_id": chat_id,
        #         "message_id": message_id,
        #     },
        #     timeout=10,
        # )

        telegram_user.write({
            'state': 'awaiting_phone',
            'state_updated': fields.Datetime.now(),
        })

        if bot_config.phone_request_message_type == 'text':
            phone_text = bot_config.phone_request_message or "📱 Please enter your phone number.\n\n<i>You can cancel with /cancel</i>"
            result = bot_config.send_message(phone_text, chat_id)
        else:
            phone_payload = bot_config.phone_request_message or '{"text": "📱 Please enter your phone number.\n\n<i>You can cancel with /cancel</i>", "parse_mode": "HTML", "reply_markup": {"force_reply": true, "selective": true, "input_field_placeholder": "+56912345678"}}'
            payload = json.loads(phone_payload)
            result = bot_config.send_message('', chat_id, payload)

        _logger.info(f"[Telegram] {type(result)}")
        _logger.info(f"[Telegram] {result}")
        if result.get("ok"):
            new_msg_id = str(result["result"]["message_id"])
            _logger.info(f"new_msg_id {new_msg_id}")
            telegram_user.write({'awaiting_message_id': new_msg_id})

    def _extract_bot_command(self, payload):
        """
        Verifica si el payload de un 'message' contiene un bot_command.
        Retorna (True, '/comando', 'argumentos') o (False, None, None).
        """
        text = payload.get('text', '')
        entities = payload.get('entities', [])

        for entity in entities:
            if entity.get('type') == 'bot_command':
                # Extraer el comando exacto (ej: /start) según la posición (offset y length)
                offset = entity.get('offset', 0)
                length = entity.get('length', 0)
                
                command = text[offset:offset + length].lower()
                # Si el comando incluye el username del bot (ej: /start@mi_bot), lo limpiamos
                if '@' in command:
                    command = command.split('@')[0]
                    
                # Extraer posibles argumentos adicionales que el usuario escribió tras el comando
                args = text[offset + length:].strip()
                
                return True, command, args

        return False, None, None

    def _get_update_type_and_payload(self, update_data):
        """
        Identifica el tipo de evento recibido desde Telegram y retorna el tipo y su payload.
        """
        # Lista de tipos de Update conocidos en la API de Telegram
        update_types = [
            'message',
            'edited_message',
            'callback_query',
            'inline_query',
            'chosen_inline_result',
            'poll_answer',
            'poll',
            'my_chat_member',
            'chat_member',
            'chat_join_request',
            'shipping_query',
            'pre_checkout_query',
        ]

        for key in update_types:
            if key in update_data:
                return key, update_data[key]

        return 'unknown', update_data
    
    def _process_email(self, bot_config, telegram_user, chat_id, message, text):
        # 1. Validar que la respuesta sea al mensaje correcto
        reply_to = message.get("reply_to_message")
        expected_msg_id = telegram_user.awaiting_message_id

        if reply_to and expected_msg_id:
            reply_msg_id = str(reply_to.get("message_id", ""))
            if reply_msg_id != str(expected_msg_id):
                bot_config.send_message('⚠️ Please reply directly to the message where I asked for your email.', chat_id)     
                return

        # 2. Extraer el email (tolerante)
        email = self._extract_email(text)
        has_error = False
        if not email:
            has_error = True

        # 3. Validar formato estricto
        if not self._is_valid_email(email):
            has_error = True

        # 4. Verificar duplicado
        existente = self.env['velardi.telegram.user'].sudo().search([
            ('email', '=', email),
            ('config_id', '=', bot_config.id),
            ('id', '!=', telegram_user.id),
        ], limit=1)

        if existente:
            has_error = True

        if has_error:
            if bot_config.error_registration_message_type == 'text':
                error_text = bot_config.error_registration_message
                error_text = error_text.replace("{{first_name}}",telegram_user.first_name).replace("{{last_name}}",telegram_user.last_name)
                bot_config.send_message(error_text, chat_id)
            else:
                error_message = bot_config.error_registration_message
                error_message = error_message.replace("{{first_name}}",telegram_user.first_name).replace("{{last_name}}",telegram_user.last_name)
                payload= json.loads(error_message)
                bot_config.send_message('', chat_id, payload)    
            return

        state_user = 'registered' if not bot_config.enable_phone_registration else 'awaiting_phone'
        # 5. Guardar email y cambiar estado
        telegram_user.write({
            'email': email,
            'state': state_user,
            'state_updated': fields.Datetime.now(),
            'awaiting_message_id': False,
        })

        # 6. Vincular con res.users si existe coincidencia
        odoo_user = self._link_odoo_user_by_email(telegram_user, email)

        if not bot_config.enable_phone_registration:
            if bot_config.welcome_message_type == 'text':
                text = bot_config.successful_registration_message
                text = text.replace("{{first_name}}",telegram_user.first_name).replace("{{last_name}}",telegram_user.last_name).replace("{{email}}",telegram_user.email).replace("{{telegram_username}}",telegram_user.telegram_username)
                if odoo_user:
                    text = f"{text}\n\n<i>👤 Linked to: <b>{odoo_user.name}</b><i>"
                bot_config.send_message(text, chat_id)
            else:
                registration_message = bot_config.successful_registration_message
                registration_message = registration_message.replace("{{first_name}}",telegram_user.first_name).replace("{{last_name}}",telegram_user.last_name).replace("{{email}}",telegram_user.email).replace("{{telegram_username}}",telegram_user.telegram_username)
                payload= json.loads(registration_message)

                if odoo_user:
                    payload['text'] += f"\n\n<i>👤 Linked to: <b>{odoo_user.name}</b></i>"

                bot_config.send_message('', chat_id, payload)    
           
        else:
            self._send_phone_request_message(bot_config, chat_id, telegram_user, 'message_id')

        _logger.info(
            "[Telegram] Usuario chat_id=%s registrado con email=%s (Odoo user: %s)",
            chat_id, email, odoo_user.name if odoo_user else "ninguno"
        )
        return



    def _process_phone(self, bot_config, telegram_user, chat_id, message):
        _logger.info( "[Telegram] Usuario message=%s ", message )
        phone_number = message.get("contact", {}).get("phone_number") or message.get("text")
        _logger.info( "[Telegram] Usuario phone_number=%s ",phone_number )

        phone_number = self._extract_phone(phone_number)
        has_error = False

        if not phone_number:
            has_error = True
        if not self._is_valid_phone(phone_number):
            has_error = True

        if has_error:
            if bot_config.error_registration_message_type == 'text':
                error_text = bot_config.error_registration_message
                error_text = error_text.replace("{{first_name}}",telegram_user.first_name).replace("{{last_name}}",telegram_user.last_name)
                bot_config.send_message(error_text, chat_id)
            else:
                error_message = bot_config.error_registration_message
                error_message = error_message.replace("{{first_name}}",telegram_user.first_name).replace("{{last_name}}",telegram_user.last_name)
                payload= json.loads(error_message)
                bot_config.send_message('', chat_id, payload)    
            return

        #  TODO: 4. Quitar el reply keyboard tras capturar el teléfono{
        #  "chat_id": "TU_CHAT_ID",
        # "text": "✅ ¡Teléfono guardado correctamente!",
        # "reply_markup": {
        #  "remove_keyboard": true
        #  }}
        if phone_number:
            telegram_user.write({
                    'phone_number': phone_number,
                    'state': 'registered',
                    'state_updated': fields.Datetime.now(),
            })
            if bot_config.welcome_message_type == 'text':
                text = bot_config.successful_registration_message
                text = text.replace("{{first_name}}",telegram_user.first_name).replace("{{last_name}}",telegram_user.last_name).replace("{{email}}",telegram_user.email).replace("{{telegram_username}}",telegram_user.telegram_username)
                if telegram_user.email:
                    text = f"{text}\n\n<i>👤 Linked to: <b>{telegram_user.email}</b><i>"
                bot_config.send_message(text, chat_id)
            else:
                registration_message = bot_config.successful_registration_message
                registration_message = registration_message.replace("{{first_name}}",telegram_user.first_name).replace("{{last_name}}",telegram_user.last_name).replace("{{email}}",telegram_user.email).replace("{{telegram_username}}",telegram_user.telegram_username)
                payload= json.loads(registration_message)

                if telegram_user.email:
                    payload['text'] += f"\n\n<i>👤 Linked to: <b>{telegram_user.email}</b></i>"

                bot_config.send_message('', chat_id, payload)    
            _logger.info(
                        "[Telegram] Usuario chat_id=%s registrado con phone_number=%s",
                chat_id, phone_number
            )
    def _extract_email(self, raw_text):
        """
        Extrae un email del texto, tolerante a frases alrededor.
        Retorna el email limpio o None si no encuentra nada.
        """
        if not raw_text:
            return None

        # Limpieza básica
        text = raw_text.strip()

        # parseaddr es muy tolerante: extrae el email aunque venga con nombre
        _, email = parseaddr(text)

        if email:
            return email.strip().strip('.,;:').lower()

        # Fallback: buscar con regex en el texto completo
        match = EMAIL_REGEX.search(text)
        if match:
            return match.group(0).strip().strip('.,;:').lower()

        return None
    def _is_valid_email(self, email):
        """
        Valida estrictamente el formato de un email.
        Verifica longitud, regex y estructura.
        """
        if not email:
            return False

        # Longitud total
        if len(email) > 254:
            return False

        # Regex
        if not EMAIL_REGEX.match(email):
            return False

        # Separar en local y dominio
        try:
            local, domain = email.rsplit('@', 1)
        except ValueError:
            return False

        # Longitud de la parte local (máx 64 según RFC)
        if len(local) > 64:
            return False

        # El dominio debe tener al menos un punto
        if '.' not in domain:
            return False

        # El dominio no puede empezar ni terminar con punto o guion
        if domain.startswith(('.', '-')) or domain.endswith(('.', '-')):
            return False

        return True

    def _extract_phone(self, raw_text):
        """
        Extracts a phone number from text, tolerant to surrounding phrases.
        Returns the clean phone number or None if not found.
        """
        if not raw_text:
            _logger.warning("[Telegram] _extract_phone: empty text provided")
            return None

        text = raw_text.strip()

        # Remove common prefixes that users might add
        for prefix in ['tel:', 'phone:', 'teléfono:', 'telefono:', 'número:', 'numero:']:
            if text.lower().startswith(prefix):
                text = text[len(prefix):].strip()

        # Remove common labels
        for label in ['Mi número es', 'My number is', 'Mi telefono es', 'Mi teléfono es',
                       'Número:', 'Telefono:', 'Teléfono:', 'Phone:', 'Tel:']:
            if text.lower().startswith(label.lower()):
                text = text[len(label):].strip()

        # Remove common separators and decorations
        text = text.replace('-', '').replace(' ', '').replace('(', '').replace(')', '')
        text = text.replace('.', '').replace(',', '').strip()

        # Try to extract with regex - international format
        match = re.search(r'\+?\d{7,15}', text)
        if match:
            phone = match.group(0)
            # Ensure it starts with +
            if not phone.startswith('+'):
                phone = '+' + phone
            return phone

        _logger.warning("[Telegram] _extract_phone: no valid phone found in text '%s'", raw_text[:50])
        return None

    def _is_valid_phone(self, phone):
        """
        Strictly validates a phone number format.
        Checks length, country code, and digit structure.
        """
        if not phone:
            _logger.warning("[Telegram] _is_valid_phone: empty phone number")
            return False

        # Remove all non-digit characters except leading +
        cleaned = re.sub(r'[^\d+]', '', phone)

        # Must start with +
        if not cleaned.startswith('+'):
            _logger.warning("[Telegram] _is_valid_phone: phone '%s' does not start with '+'", phone)
            return False

        # Remove the +
        digits = cleaned[1:]

        # Length check: 7-15 digits (ITU-T E.164 standard)
        if len(digits) < 7 or len(digits) > 15:
            _logger.warning("[Telegram] _is_valid_phone: phone '%s' has invalid length (%d digits)", phone, len(digits))
            return False

        # All remaining characters must be digits
        if not digits.isdigit():
            _logger.warning("[Telegram] _is_valid_phone: phone '%s' contains non-digit characters", phone)
            return False

        return True
    
    def _link_odoo_user_by_email(self, telegram_user, email):
        """
        Busca un res.users con ese email y lo vincula al telegram.user.
        Retorna el res.users encontrado o None.
        """
        odoo_user = self.env['res.users'].sudo().search([
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
    def custom_log(self, message, level='info'):
            self.env['ir.logging'].sudo().create({
                'name': 'Telegram Custom SafeEval Script',
                'type': 'server',
                'dbname': self.env.cr.dbname,
                'level': level,
                'message': message,
                'path': 'safe_eval_code',
                'func': 'execute',
                'line': '1',
            })