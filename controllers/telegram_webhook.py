from odoo import http, _
from odoo.http import request
from datetime import datetime
import json
import logging

_logger = logging.getLogger(__name__)

class TelegramWebhookController(http.Controller):

    @http.route('/telegram/webhook/<int:bot_id>', type='json', auth='none', csrf=False, methods=['POST'])
    def telegram_webhook(self, bot_id, **kwargs):
        """Recibe actualizaciones de Telegram."""
        try:
            bot_config = request.env['velardi.telegram.config'].sudo().browse(bot_id)
            if not bot_config.exists() or not bot_config.active:
                _logger.warning('Webhook recibido para bot inexistente o inactivo: %s', bot_id)
                return {'ok': False}

            update_data = request.get_json_data()
            _logger.info('Actualización de Telegram recibida: %s', update_data)

            
            request.env['velardi.telegram.mixin'].sudo()._process_incoming_update(bot_config, update_data)

            return {'ok': True}
        except Exception as e:
            _logger.error('Error procesando webhook de Telegram: %s', str(e), exc_info=True)
            return {'ok': False}

    