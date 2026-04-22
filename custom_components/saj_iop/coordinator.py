"""DataUpdateCoordinator for SAJ IOP Solar."""
from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import SAJApi, SAJApiError, SAJAuthError
from .const import DOMAIN, CONF_PLANT_UID, DEFAULT_SCAN_INTERVAL

_LOGGER = logging.getLogger(__name__)


class SAJDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to fetch data from SAJ IOP API."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.plant_uid: str = entry.data[CONF_PLANT_UID]
        scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

        session = async_get_clientsession(hass)
        self.api = SAJApi(
            username=entry.data[CONF_USERNAME],
            password=entry.data[CONF_PASSWORD],
            session=session,
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
            config_entry=entry,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from SAJ API."""
        try:
            # Fetch plant overview
            overview = await self.api.get_plant_overview(self.plant_uid)

            # Fetch energy flow
            energy_flow = await self.api.get_energy_flow(self.plant_uid)

            # Fetch device list with basic data
            devices = await self.api.get_device_list(self.plant_uid)

            # Fetch detailed info for each device
            device_details: dict[str, dict[str, Any]] = {}
            for device in devices:
                sn = device.get("deviceSn", "")
                if sn:
                    try:
                        detail = await self.api.get_device_info(sn)
                        device_details[sn] = {
                            "list_data": device,
                            "detail_data": detail,
                        }
                    except SAJApiError as err:
                        _LOGGER.warning(
                            "Failed to get details for device %s: %s", sn, err
                        )
                        device_details[sn] = {
                            "list_data": device,
                            "detail_data": {},
                        }

            return {
                "overview": overview,
                "energy_flow": energy_flow,
                "devices": device_details,
            }

        except SAJAuthError as err:
            raise UpdateFailed(f"Authentication failed: {err}") from err
        except SAJApiError as err:
            raise UpdateFailed(f"Error communicating with SAJ API: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}") from err
