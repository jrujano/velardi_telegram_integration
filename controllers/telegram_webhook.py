from odoo import http, _
from odoo.http import request
from datetime import datetime
import json
import logging

from odoo.http import request, Response

_logger = logging.getLogger(__name__)

class TelegramWebhookController(http.Controller):
    
    @http.route('/velardi/telegram/webhook/<int:bot_id>', type='http', auth='none', csrf=False, methods=['POST'])
    def telegram_webhook(self, bot_id, **kwargs):
        """
            Recibe las notificaciones Push de la API de Telegram.
        """
        try:
            
            # 1. Leer el cuerpo de la petición POST enviada por Telegram
            raw_data = request.httprequest.data.decode('utf-8')
            if not raw_data:
                return Response("Empty payload", status=400)
        except Exception as e:
            _logger.error(f"[Telegram Webhook] Error procesando update para bot {bot_id}: {str(e)}")
            # Siempre se debe responder 200 a Telegram para evitar desbordamiento de pending_update_count
            return Response("OK", status=200)
        """Recibe actualizaciones de Telegram."""
        try:
            bot_config = request.env['velardi.telegram.config'].sudo().browse(bot_id)
            if not bot_config.exists() or not bot_config.active:
                _logger.warning('Webhook recibido para bot inexistente o inactivo: %s', bot_id)
                return Response("OK", status=200)

            update_data = request.get_json_data()
            _logger.info('Actualización de Telegram recibida: %s', update_data)

            
            request.env['velardi.telegram.mixin'].sudo()._process_incoming_update(bot_config, update_data)

            return Response("OK", status=200)
        except Exception as e:
            _logger.error('Error procesando webhook de Telegram: %s', str(e), exc_info=True)
            return Response("OK", status=200)

    