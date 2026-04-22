"""Sensor platform for SAJ IOP Solar integration."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, CONF_PLANT_UID, CONF_PLANT_NAME, RUNNING_STATE_MAP
from .coordinator import SAJDataUpdateCoordinator
from .entity import SAJDeviceEntity, SAJPlantEntity


@dataclass(frozen=True, kw_only=True)
class SAJDeviceSensorDescription(SensorEntityDescription):
    """Sensor description for device-level sensors."""
    value_fn: Callable[[dict, dict, dict], Any]


@dataclass(frozen=True, kw_only=True)
class SAJPlantSensorDescription(SensorEntityDescription):
    """Sensor description for plant-level sensors."""
    value_fn: Callable[[dict], Any]


# =========================================================================
# Device (per-inverter) sensor descriptions
# =========================================================================
DEVICE_SENSORS: tuple[SAJDeviceSensorDescription, ...] = (
    SAJDeviceSensorDescription(
        key="power_now",
        translation_key="power_now",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda ld, dd, sd: sd.get("powerNow", 0),
    ),
    SAJDeviceSensorDescription(
        key="today_energy",
        translation_key="today_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda ld, dd, sd: ld.get("todayEnergy", 0),
    ),
    SAJDeviceSensorDescription(
        key="month_energy",
        translation_key="month_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda ld, dd, sd: ld.get("monthEnergy", 0),
    ),
    SAJDeviceSensorDescription(
        key="year_energy",
        translation_key="year_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda ld, dd, sd: ld.get("yearEnergy", 0),
    ),
    SAJDeviceSensorDescription(
        key="total_energy",
        translation_key="total_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda ld, dd, sd: ld.get("totalEnergy", 0),
    ),
    SAJDeviceSensorDescription(
        key="grid_voltage",
        translation_key="grid_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda ld, dd, sd: _get_grid_value(sd, "gridVolt"),
    ),
    SAJDeviceSensorDescription(
        key="grid_current",
        translation_key="grid_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda ld, dd, sd: _get_grid_value(sd, "gridCurr"),
    ),
    SAJDeviceSensorDescription(
        key="grid_frequency",
        translation_key="grid_frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda ld, dd, sd: _get_grid_value(sd, "gridFreq"),
    ),
    SAJDeviceSensorDescription(
        key="running_state",
        translation_key="running_state",
        device_class=SensorDeviceClass.ENUM,
        options=list(RUNNING_STATE_MAP.values()),
        value_fn=lambda ld, dd, sd: RUNNING_STATE_MAP.get(
            ld.get("runningState", 0), "unknown"
        ),
    ),
    SAJDeviceSensorDescription(
        key="today_income",
        translation_key="today_income",
        icon="mdi:currency-brl",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda ld, dd, sd: _safe_float(sd.get("incomeDay")),
    ),
)


# =========================================================================
# Plant (aggregated) sensor descriptions
# =========================================================================
PLANT_SENSORS: tuple[SAJPlantSensorDescription, ...] = (
    SAJPlantSensorDescription(
        key="plant_power_now",
        translation_key="plant_power_now",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda o: o.get("nowPower", 0),
    ),
    SAJPlantSensorDescription(
        key="plant_today_energy",
        translation_key="plant_today_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda o: o.get("todayEnergy", 0),
    ),
    SAJPlantSensorDescription(
        key="plant_total_energy",
        translation_key="plant_total_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda o: o.get("totalEnergy", 0),
    ),
    SAJPlantSensorDescription(
        key="plant_peak_power",
        translation_key="plant_peak_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda o: o.get("peakPower", 0),
    ),
    SAJPlantSensorDescription(
        key="plant_online_devices",
        translation_key="plant_online_devices",
        icon="mdi:solar-panel",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda o: o.get("onlineDeviceNum", 0),
    ),
    SAJPlantSensorDescription(
        key="plant_total_devices",
        translation_key="plant_total_devices",
        icon="mdi:solar-panel",
        value_fn=lambda o: o.get("totalDeviceNum", 0),
    ),
    SAJPlantSensorDescription(
        key="plant_today_income",
        translation_key="plant_today_income",
        icon="mdi:currency-brl",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda o: o.get("todayIncome", 0),
    ),
    SAJPlantSensorDescription(
        key="plant_total_income",
        translation_key="plant_total_income",
        icon="mdi:currency-brl",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda o: o.get("totalIncome", 0),
    ),
)


def _get_grid_value(stats: dict, key: str) -> float | None:
    """Extract a grid value from the device stats."""
    grid_list = stats.get("gridList", [])
    if grid_list:
        return _safe_float(grid_list[0].get(key))
    return None


def _safe_float(value: Any) -> float | None:
    """Safely convert a value to float."""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SAJ IOP sensors from a config entry."""
    coordinator: SAJDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    plant_uid = entry.data[CONF_PLANT_UID]
    plant_name = entry.data[CONF_PLANT_NAME]

    entities: list[SensorEntity] = []

    # Plant-level sensors
    for description in PLANT_SENSORS:
        entities.append(SAJPlantSensor(coordinator, description, plant_uid, plant_name))

    # Device-level sensors (per inverter)
    if coordinator.data:
        for device_sn in coordinator.data.get("devices", {}):
            for description in DEVICE_SENSORS:
                entities.append(SAJDeviceSensor(coordinator, description, device_sn))

    async_add_entities(entities)


class SAJDeviceSensor(SAJDeviceEntity, SensorEntity):
    """Sensor for a SAJ inverter device."""

    entity_description: SAJDeviceSensorDescription

    def __init__(
        self,
        coordinator: SAJDataUpdateCoordinator,
        description: SAJDeviceSensorDescription,
        device_sn: str,
    ) -> None:
        super().__init__(coordinator, device_sn)
        self.entity_description = description
        self._attr_unique_id = f"{device_sn}_{description.key}"

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(
            self._list_data, self._detail_data, self._stats_data
        )


class SAJPlantSensor(SAJPlantEntity, SensorEntity):
    """Sensor for the SAJ plant."""

    entity_description: SAJPlantSensorDescription

    def __init__(
        self,
        coordinator: SAJDataUpdateCoordinator,
        description: SAJPlantSensorDescription,
        plant_uid: str,
        plant_name: str,
    ) -> None:
        super().__init__(coordinator, plant_uid, plant_name)
        self.entity_description = description
        self._attr_unique_id = f"{plant_uid}_{description.key}"

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self._overview_data)
