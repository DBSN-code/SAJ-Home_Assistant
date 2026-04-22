"""Config flow for SAJ IOP Solar integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, CONF_SCAN_INTERVAL
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SAJApi, SAJAuthError, SAJApiError
from .const import DOMAIN, CONF_PLANT_UID, CONF_PLANT_NAME, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class SAJIOPConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for SAJ IOP Solar."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._api: SAJApi | None = None
        self._username: str = ""
        self._password: str = ""
        self._plants: list[dict] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step — login credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._username = user_input[CONF_USERNAME]
            self._password = user_input[CONF_PASSWORD]

            session = async_get_clientsession(self.hass)
            self._api = SAJApi(
                username=self._username,
                password=self._password,
                session=session,
            )

            try:
                await self._api.login()
                self._plants = await self._api.get_plant_list()

                if not self._plants:
                    errors["base"] = "no_plants"
                elif len(self._plants) == 1:
                    # Only one plant, skip selection
                    plant = self._plants[0]
                    return await self._create_entry(plant)
                else:
                    # Multiple plants, let user choose
                    return await self.async_step_plant()

            except SAJAuthError:
                errors["base"] = "invalid_auth"
            except SAJApiError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during SAJ login")
                errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_plant(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle plant selection when user has multiple plants."""
        if user_input is not None:
            plant_uid = user_input[CONF_PLANT_UID]
            plant = next(
                (p for p in self._plants if p.get("plantUid") == plant_uid),
                self._plants[0],
            )
            return await self._create_entry(plant)

        # Build plant selection options
        plant_options = {
            p["plantUid"]: f"{p.get('plantName', 'Plant')} ({p.get('systemPower', '?')} kW)"
            for p in self._plants
        }

        return self.async_show_form(
            step_id="plant",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PLANT_UID): vol.In(plant_options),
                }
            ),
        )

    async def _create_entry(self, plant: dict) -> ConfigFlowResult:
        """Create the config entry for the selected plant."""
        plant_uid = plant.get("plantUid", "")
        plant_name = plant.get("plantName", "SAJ Solar")

        # Ensure unique entry per plant
        await self.async_set_unique_id(plant_uid)
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=plant_name,
            data={
                CONF_USERNAME: self._username,
                CONF_PASSWORD: self._password,
                CONF_PLANT_UID: plant_uid,
                CONF_PLANT_NAME: plant_name,
                CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
            },
        )
