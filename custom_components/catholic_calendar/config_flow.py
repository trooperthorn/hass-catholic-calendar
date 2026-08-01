"""Config flow for Catholic Calendar."""
import voluptuous as vol
from homeassistant import config_entries
from .const import DOMAIN

class CatholicCalendarConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Catholic Calendar."""
    
    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        # Only allow a single instance of the calendar
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            # Create the integration entry in the UI
            return self.async_create_entry(title="Catholic Calendar", data=user_input)

        # Show a simple submit button (no complex config required)
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))
