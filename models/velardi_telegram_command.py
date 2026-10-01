# -*- coding: utf-8 -*-
import logging
from odoo.exceptions import UserError
from odoo import _, api, fields, models


DEFAULT_PYTHON_CODE = """# Available variables:
#  - env: Odoo environment (self.env)
#  - user: Current logged-in user (self.env.user)
#  - self: Current automation record (velardi.telegram.msg.automation)
#  - config: Bot configuration record (velardi.telegram.config)
#  - bot_token: Telegram bot token (from config_id.bot_token)
#  - record: First record of the recordset being processed
#  - records: Full recordset of records being processed
#  - _logger: Logger instance for debug messages (_logger.info, _logger.error, etc.)
#  - log: Custom logging function (log(message))
#  - time: Python time module (time.time(), time.sleep(), time.strftime(), etc.)
#  - datetime: Python datetime class (datetime.now(), datetime.strptime, etc.)
#  - date: Python date class (date.today(), etc.)
#  - relativedelta: dateutil.relativedelta (relativedelta(months=3), etc.)
#  - dateutil_parser: dateutil.parser.parse (parse_date("2026-01-01"), etc.)
#  - timezone: Timezone utilities
#  - timedelta: Python timedelta class (timedelta(days=7), etc.)
#  - float_compare: Compare floats with precision (float_compare(val1, val2, precision_digits=2))
#  - UserError: Exception class for raising user-facing warning messages
#  - requests: HTTP requests library (requests.get, requests.post, etc.)
#
# Example:
# message = f"New order {record.name} from {record.partner_id.name}"
# config.send_message(message)\n\n\n\n"""

_logger = logging.getLogger(__name__)

class VelardiTelegramCommand(models.Model):
    _name = "velardi.telegram.command"
    _description = "Telegram Command"
    _order = "create_date desc"
    command = fields.Char(string="Command", required=True, help="Command name without the '/'")
    type_code = fields.Selection(
        [('command', 'Command'), ('callback', 'Callback')],
        string="Type", default='command', required=True,
        help="Command: triggered by /command. Callback: triggered by inline keyboard button.")
    description = fields.Char(required=True, help="Indicate which action or code the bot executes.")
    bot_config_id = fields.Many2one(
            "velardi.telegram.config", string="Bot Configuration",
            required=True, ondelete="cascade")
    active = fields.Boolean(default=True)
    active_bot = fields.Boolean(string="Register in BOT", default=False)
    code = fields.Text(string='Python Code', groups='base.group_system',
                        default=DEFAULT_PYTHON_CODE,
                        help="Write Python code that the action will execute. Some variables are "
                            "available for use; help about python expression is given in the help tab.")

    _sql_constraints = [
        ('unique_command_bot', 'UNIQUE(command, bot_config_id)',
         'El comando debe ser único por bot.'),
    ]
    def action_register_commands(self):
        """Registra un command en Telegram-Bot."""
        self.ensure_one()

        cmd_name = self.command.replace("/", "").strip().lower()

        # 1. Leer los comandos actuales directamente de Telegram
        try:
            actuales = self.bot_config_id.get_my_commands()
            _logger.info("Comandos actuales en Telegram: %s", actuales)
        except Exception as e:
            _logger.error("[Telegram] Error获取 comandos: %s", e)
            raise UserError(_("Error fetching commands from Telegram: %s") % e)

        # 2. Evitar duplicados
        actuales = [c for c in actuales if c["command"] != cmd_name]
        actuales.append({"command": cmd_name, "description": self.description})

        # 3. Telegram limita a 100 comandos
        if len(actuales) > 100:
            raise UserError(_("Telegram allows a maximum of 100 commands."))

        _logger.info("[Telegram] Enviando comandos: %s", actuales)

        # 4. Enviar la lista completa
        try:
            res_data = self.bot_config_id.set_my_commands(actuales)
            if not res_data.get("ok"):
                error_desc = res_data.get("description", "Unknown error")
                _logger.error("[Telegram] setMyCommands error: %s", error_desc)
                raise UserError(_("Telegram error: %s") % error_desc)
        except UserError:
            raise
        except Exception as e:
            _logger.error("[Telegram] Error registrando comando: %s", e)
            raise UserError(_("Error registering command: %s") % e)

        _logger.info("[Telegram] Comando '%s' registrado exitosamente.", cmd_name)
        self.active_bot = True

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Telegram Commands'),
                'message': _("Command '/%s' registered successfully.") % cmd_name,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }

    def action_remove_command(self):
        """Elimina un comando preservando los demás."""
        self.ensure_one()
        command = self.command

        actuales = self.bot_config_id.get_my_commands()
        _logger.warning(command)
        _logger.info(actuales)
        # Filtrar el que queremos eliminar
        nuevos = [c for c in actuales if c["command"] != command]

        if len(nuevos) == len(actuales):
            _logger.warning("El comando '%s' no existe en Telegram.", command)
            self.active_bot = False
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Telegram Commands'),
                    'message': _("Command '%s' was not found in Telegram.") % self.command,
                    'type': 'warning',
                    'sticky': False,
                    'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
                },
            }

        if nuevos:
            self.bot_config_id.set_my_commands(nuevos)
        else:
            # Si ya no queda ninguno, borrar todos
            self.bot_config_id.delete_my_commands()
        self.active_bot = False

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Telegram Commands'),
                'message': _("Command '%s' unregistered successfully.") % self.command,
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.client', 'tag': 'soft_reload'},
            },
        }