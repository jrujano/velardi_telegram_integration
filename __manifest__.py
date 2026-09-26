# -*- coding: utf-8 -*-
{
    "name": "Velardi Telegram Integration",
    "version": "18.0.1.8.0",
    "category": "Discuss",
    "summary": "Integration with Telegram Bot API",
    "description": """
        Integration module with Telegram Bot API
        =========================================

        This module provides integration with Telegram Bot API to:
        - Send notifications and alerts from Odoo to Telegram
        - Manage bot credentials and chat configuration
        - Test connectivity with simulation mode
    """,
    "author": "Velardi",
    "website": "https://www.velardi.cl",
    "depends": [
        "base",
        "web",
        "base_automation",
    ],
    "external_dependencies": {
        "python": [
            "requests",
        ],
    },
    "data": [
        "security/security.xml",
        "security/ir.model.access.csv",
        "views/velardi_telegram_config_views.xml",
        "views/velardi_telegram_msg_automation_views.xml",
        "views/velardi_telegram_notification_views.xml",
        "views/velardi_telegram_user_views.xml",
        "views/velardi_telegram_command.xml",
        "views/menu_views.xml",
    ],
    "installable": True,
    "auto_install": False,
    "application": True,
    "license": "LGPL-3",
    "post_init_hook": "_post_init_hook",
    "languages": [
        ("es_ES", "Spanish (Spain)"),
    ],
}
