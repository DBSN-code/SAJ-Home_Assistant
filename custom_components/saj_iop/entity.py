"""Base entity for SAJ IOP Solar integration."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import SAJDataUpdateCoordinator


class SAJEntity(CoordinatorEntity[SAJDataUpdateCoordinator]):
    """Base class for SAJ IOP entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SAJDataUpdateCoordinator, device_sn: str | None = None) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._device_sn = device_sn

    @property
    def _device_data(self) -> dict:
        if self._device_sn and self.coordinator.data:
            return self.coordinator.data.get("devices", {}).get(self._device_sn, {})
        return {}

    @property
    def _list_data(self) -> dict:
        return self._device_data.get("list_data", {})

    @property
    def _detail_data(self) -> dict:
        return self._device_data.get("detail_data", {})

    @property
    def _stats_data(self) -> dict:
        return self._detail_data.get("deviceStatisticsData", {})

    @property
    def _overview_data(self) -> dict:
        if self.coordinator.data:
            return self.coordinator.data.get("overview", {})
        return {}


class SAJDeviceEntity(SAJEntity):
    """Entity for a specific SAJ inverter."""

    def __init__(self, coordinator: SAJDataUpdateCoordinator, device_sn: str) -> None:
        super().__init__(coordinator, device_sn)

    @property
    def device_info(self) -> DeviceInfo:
        ld = self._list_data
        dd = self._detail_data
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_sn)},
            name=ld.get("aliases", self._device_sn),
            manufacturer="SAJ Electric",
            model=ld.get("deviceModel", "Unknown"),
            serial_number=self._device_sn,
            sw_version=dd.get("masterMCUFw"),
        )


class SAJPlantEntity(SAJEntity):
    """Entity for the SAJ plant (solar installation)."""

    def __init__(self, coordinator: SAJDataUpdateCoordinator, plant_uid: str, plant_name: str) -> None:
        super().__init__(coordinator)
        self._plant_uid = plant_uid
        self._plant_name = plant_name

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._plant_uid)},
            name=self._plant_name,
            manufacturer="SAJ Electric",
            model="Solar Plant",
        )
