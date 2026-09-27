from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class VelardiTelegramGroup(models.Model):
    _name = 'velardi.telegram.group'
    _description = 'Telegram User Group'
    _order = 'create_date desc'

    name = fields.Char(string='Group Name', required=True)
    description = fields.Text(string='Description')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('cancelled', 'Cancelled'),
    ], string='State', default='draft', required=True)
    chat_id = fields.Char(string='Telegram Chat ID')
    bot_config_id = fields.Many2one(
        'velardi.telegram.config',
        string='Bot Configuration',
        required=True,
        ondelete='cascade',
    )
    
    user_ids = fields.Many2many(
        comodel_name='velardi.telegram.user',
        relation='velardi_group_user_rel',
        column1='group_id',
        column2='user_id',
        string="Users"
    )

    user_count = fields.Integer(
        string='User Count',
        compute='_compute_user_count',
    )
    active = fields.Boolean(string='Active', default=True)

    @api.depends('user_ids')
    def _compute_user_count(self):
        for record in self:
            record.user_count = len(record.user_ids)

    def action_activate(self):
        self.write({'state': 'active'})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def action_draft(self):
        self.write({'state': 'draft'})

    def action_open_users(self):
        self.ensure_one()
        return {
            'name': _('Users'),
            'type': 'ir.actions.act_window',
            'res_model': 'velardi.telegram.user',
            'view_mode': 'list',
            'limit': 99999999,
            'views': [[False, 'list'], [False, 'form']]
        }

