from . import models
from . import controllers

def _post_init_hook(env):
    """Re-patch AFTER all modules loaded (base_automation may have overwritten us)."""
    env['velardi.telegram.msg.automation']._register_hook()
