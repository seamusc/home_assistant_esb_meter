"""Config flow for ESB Meter integration."""
from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from .const import CONF_MPRN, DOMAIN
from .coordinator import UpdateFailed, validate_credentials

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): TextSelector(TextSelectorConfig(type=TextSelectorType.EMAIL)),
        vol.Required(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
        vol.Required(CONF_MPRN): str,
    }
)


async def _validate_credentials(hass: HomeAssistant, data: dict) -> None:
    """Attempt a login to ESB to validate credentials. Raises UpdateFailed on failure."""
    await hass.async_add_executor_job(
        validate_credentials, data[CONF_USERNAME], data[CONF_PASSWORD]
    )


class EsbMeterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the UI config flow for ESB Meter."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                await _validate_credentials(self.hass, user_input)
            except UpdateFailed:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(user_input[CONF_MPRN])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"ESB Meter ({user_input[CONF_MPRN]})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
