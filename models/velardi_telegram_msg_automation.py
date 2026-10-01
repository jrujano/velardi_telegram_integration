# -*- coding: utf-8 -*-
import re
import time
import logging
import requests
from collections import defaultdict
from datetime import datetime, date, timezone, timedelta
from dateutil.parser import parse as parse_date 
from dateutil.relativedelta import relativedelta
from odoo.tools import html_escape
from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare
from odoo.tools.safe_eval import safe_eval, wrap_module
_logger = logging.getLogger(__name__)

CREATE_TRIGGERS = ("create",)
WRITE_TRIGGERS = ("write",)
UNLINK_TRIGGERS = ("unlink",)
CREATE_WRITE_SET = set(CREATE_TRIGGERS + WRITE_TRIGGERS)

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

wrapped_requests = wrap_module(requests, ['post', 'get', 'put', 'delete', 'head', 'patch', 'options'])
_registering = False


class VelardiTelegramMsgAutomation(models.Model):

    _name = "velardi.telegram.msg.automation"
    _description = "Telegram Message Automation"
    _order = "create_date desc"

    name = fields.Char(required=True)
    config_id = fields.Many2one(
        "velardi.telegram.config", string="Bot Configuration",
        required=True, ondelete="cascade")
    model_id = fields.Many2one(
        "ir.model", string="Source Model", required=True,
        ondelete="cascade")
    model_name = fields.Char(
        related="model_id.model", string="Model Technical Name",
        readonly=True, store=True)
    trigger = fields.Selection(
        [("create", "On Create"), ("write", "On Write"),
         ("unlink", "On Unlink")],
        string="Trigger", required=True, default="create")
    filter_domain = fields.Text(
        string="Filter Domain",
        help="Odoo domain, e.g. [('state','=','sale')]")
    message_template = fields.Text(
        string="Message Template",
        help="Use ${field_name} for dynamic values.")
    chat_id = fields.Char(string="Chat ID Override")
    active = fields.Boolean(default=True)
    last_run = fields.Datetime(string="Last Run", readonly=True)
    run_count = fields.Integer(string="Run Count", readonly=True, default=0)
    type = fields.Selection([
            ('template', 'Template'),
            ('code', 'Code')
        ], default='template')

    
    code = fields.Text(string='Python Code', groups='base.group_system',
                    default=DEFAULT_PYTHON_CODE,
                    help="Write Python code that the action will execute. Some variables are "
                        "available for use; help about python expression is given in the help tab.")



    # ------------------------------------------------------------------
    # ORM lifecycle
    # ------------------------------------------------------------------
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        _logger.info("[Telegram] Rule(s) created: %s", records.ids)
        self._update_registry()
        return records

    def write(self, vals):
        result = super().write(vals)
        _logger.info("[Telegram] Rule(s) updated: %s, fields: %s",
                      self.ids, list(vals.keys()))
        self._update_registry()
        return result

    def unlink(self):
        _logger.info("[Telegram] Rule(s) deleted: %s", self.ids)
        result = super().unlink()
        self._update_registry()
        return result

    def _update_registry(self):
        if self.env.registry.ready and not self.env.context.get('import_file'):
            self._register_hook()

    # ------------------------------------------------------------------
    # Hook registration
    # ------------------------------------------------------------------
    @api.model
    def _register_hook(self):
        global _registering
        if _registering:
            return
        _registering = True
        try:
            self._do_register_hook()
        finally:
            _registering = False

    def _do_register_hook(self):
        _logger.info("[Telegram] ========== _register_hook START ==========")

        def make_create():
            @api.model_create_multi
            def create(self, vals_list, **kw):
                _logger.info("[Telegram] >>> CREATE intercepted on %s, %d record(s)", self._name, len(vals_list))
                if self.env.context.get('__telegram_done'):
                    return create._tg_origin(self, vals_list, **kw)
                try:
                    self = self.with_context(__telegram_done=True)
                    automations = self.env['velardi.telegram.msg.automation'].sudo()._get_actions(self, CREATE_TRIGGERS)
                    _logger.info("[Telegram] _get_actions returned %d rule(s)", len(automations))
                    if not automations:
                        return create._tg_origin(self, vals_list, **kw)
                    records = create._tg_origin(self.with_env(automations.env), vals_list, **kw)
                    for automation in automations.with_context(old_values=None):
                        automation._process(automation._filter_post(records))
                    return records.with_env(self.env)
                except Exception:
                    _logger.exception("[Telegram] Error in patched create")
                    return create._tg_origin(self, vals_list, **kw)
            return create

        def make_write():
            def write(self, vals, **kw):
                if self.env.context.get('__telegram_done'):
                    return write._tg_origin(self, vals, **kw)
                try:
                    self = self.with_context(__telegram_done=True)
                    automations = self.env['velardi.telegram.msg.automation'].sudo()._get_actions(self, WRITE_TRIGGERS)
                    if not (automations and self):
                        return write._tg_origin(self, vals, **kw)
                    old_values = {}
                    for record in self:
                        old_values[record.id] = {
                            f: record[f] for f in vals.keys()
                            if f in record._fields
                        }
                    result = write._tg_origin(self.with_env(automations.env), vals, **kw)
                    for automation in automations.with_context(old_values=old_values):
                        automation._process(automation._filter_post(self))
                    return self.with_env(self.env)
                except Exception:
                    _logger.exception("[Telegram] Error in patched write")
                    return write._tg_origin(self, vals, **kw)
            return write

        def make_unlink():
            def unlink(self, **kw):
                if self.env.context.get('__telegram_done'):
                    return unlink._tg_origin(self, **kw)
                try:
                    self = self.with_context(__telegram_done=True)
                    automations = self.env['velardi.telegram.msg.automation'].sudo()._get_actions(self, UNLINK_TRIGGERS)
                    if not automations:
                        return unlink._tg_origin(self, **kw)
                    for automation in automations:
                        automation._process(automation._filter_post(self))
                    return unlink._tg_origin(self.with_env(automations.env), **kw)
                except Exception:
                    _logger.exception("[Telegram] Error in patched unlink")
                    return unlink._tg_origin(self, **kw)
            return unlink

        def patch(model, name, method):
            ModelClass = model.env.registry[model._name]
            current = getattr(ModelClass, name, None)
            method._tg_origin = current
            setattr(ModelClass, name, method)
            _logger.info("[Telegram] PATCHED %s.%s (origin=%s)", model._name, name,
                          getattr(current, '__name__', current))

        rules = self.with_context({}).search([])
        _logger.info("[Telegram] Found %d total rule(s)", len(rules))

        for rule in rules:
            Model = self.env.get(rule.model_name)
            if Model is None:
                _logger.warning("[Telegram] Model '%s' not found, skipping rule '%s'",
                                rule.model_name, rule.name)
                continue

            _logger.info("[Telegram] Processing rule '%s': model=%s, trigger=%s, active=%s",
                          rule.name, rule.model_name, rule.trigger, rule.active)

            if rule.trigger in CREATE_WRITE_SET:
                if rule.trigger in CREATE_TRIGGERS:
                    patch(Model, 'create', make_create())
                if rule.trigger in WRITE_TRIGGERS:
                    patch(Model, 'write', make_write())

            elif rule.trigger in ('on_unlink', 'unlink'):
                patch(Model, 'unlink', make_unlink())

        _logger.info("[Telegram] ========== _register_hook END ==========")

    @api.model
    def _unregister_hook(self):
        pass

    # ------------------------------------------------------------------
    # Runtime lookup - matches base_automation pattern exactly
    # ------------------------------------------------------------------
    def _get_actions(self, records, triggers):
        if not hasattr(records, '_name'):
            return self.browse()
        domain = [
            ('model_name', '=', records._name),
            ('trigger', 'in', triggers),
            ('active', '=', True),
        ]
        result = self.with_context(active_test=True).sudo().search(domain)
        _logger.info("[Telegram] _get_actions: model=%s, triggers=%s, found=%d: %s",
                      records._name, triggers, len(result), result.mapped('name'))
        return result

    def _filter_post(self, records):
        self.ensure_one()
        if not self.filter_domain or not records:
            _logger.info("[Telegram] _filter_post: rule='%s', no domain or no records, returning all (%d)",
                         self.name, len(records) if records else 0)
            return records
        try:
            domain = safe_eval(self.filter_domain)
            _logger.info("[Telegram] _filter_post: rule='%s', domain=%s, input=%d records",
                         self.name, domain, len(records))
            filtered = records.filtered_domain(domain)
            _logger.info("[Telegram] _filter_post: rule='%s', filtered=%d records",
                         self.name, len(filtered))
            return filtered
        except Exception:
            _logger.warning("[Telegram] Invalid domain for '%s': %s", self.name, self.filter_domain)
            return records

    def _process(self, records):
        self.ensure_one()
        if not records:
            return
        _logger.info("[Telegram] _process: rule='%s', records=%s", self.name, records.ids)
        try:
            self._execute(records)
        except Exception:
            _logger.exception("[Telegram] Error in rule '%s'", self.name)

    def _execute(self, records):
        self.ensure_one()
        done_key = "__telegram_automation_done"
        done = self.env.context.get(done_key, set())
        key = (self.id, tuple(sorted(records.ids)))
        if key in done:
            return
        done = done | {key}

        for record in records.with_context(**{done_key: done}):
            try:
                _logger.info(f"type: {self.type}")
                if self.type=='template':
                    message = self._render_message(record)
                else:
                    localdict = {
                            'env':self.env,
                            'user': self.env.user,                   # Usuario actual
                            'self': self,                            # Tu objeto actual
                            'records': records,
                            'record': records[0] if records else None,
                            'config': self.config_id,                # Configuración del bot
                            'bot_token': self.config_id.bot_token,   # Token del bot de Telegram
                            '_logger': _logger,
                            'log': self.custom_log,
                            # --- Inyectar funciones Built-in de Python requeridas ---
                            'getattr': getattr,
                            'hasattr': hasattr,
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
                    code_to_execute = f"""
                        {self.code}
                        """
                    message = safe_eval(self.code, localdict, mode="exec", nocopy=True)
                
                if message:
                    _logger.info("[Telegram] Sending for %s(%s): %s",
                                                  record._name, record.id, message[:200] if message else "EMPTY")
                    self.config_id.send_message(message, chat_id=self.chat_id or None)
                    _logger.info("[Telegram] Sent OK for %s(%s)", record._name, record.id)
            except Exception as exc:
                _logger.error("[Telegram] Failed for %s(%s): %s", record._name, record.id, exc)

        try:
            self.env.cr.execute(
                "UPDATE velardi_telegram_msg_automation "
                "SET last_run = %s, run_count = run_count + %s WHERE id = %s",
                (fields.Datetime.now(), len(records), self.id))
        except Exception:
            pass

    def _render_message(self, record):
        self.ensure_one()
        template = (self.message_template or "").replace('\r\n', '\n').replace('\r', '\n')

        def _resolve_field(obj, field_path):
            try:
                value = obj
                for part in field_path.split("."):
                    if value is None or value is False:
                        return None
                    value = getattr(value, part, None)
                return value
            except Exception:
                return None

        def _format_value(value):
            if value is None or value is False:
                return ""
            if hasattr(value, "name") and not isinstance(value, str):
                return value.name
            if isinstance(value, float):
                return f"{value:,.2f}"
            return str(value)

        def _replace_field(match):
            field_path = match.group(1)
            value = _resolve_field(record, field_path)
            return _format_value(value)

        def _process_loops(text):
            loop_pattern = re.compile(
                r"\{%\s*for\s+(\w+)\s+in\s+([\w.]+)\s*%\}(.*?)\{%\s*endfor\s*%\}",
                re.DOTALL,
            )

            def _replace_loop(match):
                loop_var = match.group(1)
                collection_path = match.group(2)
                body = match.group(3).strip()

                collection = _resolve_field(record, collection_path)
                if not collection:
                    return ""

                parts = []
                for item in collection:
                    def _replace_in_loop(m, _item=item):
                        inner_path = m.group(1)
                        if inner_path.startswith(loop_var + "."):
                            sub_path = inner_path[len(loop_var) + 1:]
                            value = _resolve_field(_item, sub_path)
                            return _format_value(value)
                        value = _resolve_field(record, inner_path)
                        return _format_value(value)

                    rendered = re.sub(r"\$\{([^}]+)\}", _replace_in_loop, body)
                    rendered = re.sub(r"\n\s*\n", "\n", rendered).strip()
                    if rendered:
                        parts.append(rendered)

                return "\n".join(parts)

            prev = None
            while prev != text:
                prev = text
                text = loop_pattern.sub(_replace_loop, text)
            return text

        result = _process_loops(template)
        result = re.sub(r"\$\{([^}]+)\}", _replace_field, result)
        result = re.sub(r"\n{3,}", "\n\n", result)
        return result.strip()

    def action_test(self):
        self.ensure_one()
        model = self.env[self.model_name]
        record = model.search([], limit=1)
        if not record:
            raise UserError(
                _("No records found in model '%s' to test.") % self.model_name)
        _logger.info(self.type)

        if  self.type=='template':
            message = self._render_message(record)
        else:
            message ="""
            ----- Message -----
            Type:code
            """
        self.config_id.send_message(message, chat_id=self.chat_id or None)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Telegram Automation"),
                "message": _("Test sent using record '%s'.") % record.display_name,
                "type": "success",
                "sticky": False,
            },
        }

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
