"""Run with Home Assistant dependencies installed; never touches a live hass."""
import importlib
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import AsyncMock, Mock


@unittest.skipUnless(importlib.util.find_spec("homeassistant"), "Requires Home Assistant runtime")
class HomeAssistantContractTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        package = types.ModuleType("saj_runtime_test")
        package.__path__ = [str(Path(__file__).resolve().parents[1] / "custom_components/saj_iop")]
        sys.modules[package.__name__] = package
        cls.coordinator_module = importlib.import_module("saj_runtime_test.coordinator")
        cls.sensor_module = importlib.import_module("saj_runtime_test.sensor")
        cls.api_module = importlib.import_module("saj_runtime_test.api")

    def coordinator(self):
        coordinator = object.__new__(self.coordinator_module.SAJDataUpdateCoordinator)
        coordinator.plant_uid = "same-plant-id"
        coordinator.api = Mock()
        coordinator.api.get_plant_overview = AsyncMock(return_value={"totalEnergy": 12345.67})
        coordinator.api.get_energy_flow = AsyncMock(return_value={"totalPvPower": 1800})
        coordinator.api.get_device_list = AsyncMock(return_value=[
            {"deviceSn": "device-normal", "runningState": 1, "totalEnergy": 4000},
            {"deviceSn": "device-alarm", "runningState": 2, "totalEnergy": 5000},
            {"deviceSn": "device-offline", "runningState": 3, "totalEnergy": 3345.67},
        ])
        coordinator.api.get_device_info = AsyncMock(return_value={
            "deviceStatisticsData": {"powerNow": 900},
        })
        return coordinator

    async def test_coordinator_preserves_devices_and_maps_live_power(self):
        result = await self.coordinator()._async_update_data()
        self.assertEqual(result["overview"], {"totalEnergy": 12345.67, "nowPower": 1800,
                                              "onlineDeviceNum": 2, "totalDeviceNum": 3})
        self.assertEqual(set(result["devices"]), {"device-normal", "device-alarm", "device-offline"})
        self.assertEqual(result["devices"]["device-offline"]["list_data"]["totalEnergy"], 3345.67)

    async def test_failed_detail_does_not_turn_power_into_zero(self):
        coordinator = self.coordinator()
        coordinator.api.get_device_info.side_effect = self.api_module.SAJApiError("temporary failure")
        result = await coordinator._async_update_data()
        detail = result["devices"]["device-normal"]
        power = next(s for s in self.sensor_module.DEVICE_SENSORS if s.key == "power_now")
        self.assertIsNone(power.value_fn(detail["list_data"], detail["detail_data"], {}))
        energy = next(s for s in self.sensor_module.DEVICE_SENSORS if s.key == "total_energy")
        self.assertEqual(energy.value_fn(detail["list_data"], detail["detail_data"], {}), 4000)

    async def test_missing_plant_values_do_not_reset_energy_statistics(self):
        for description in self.sensor_module.PLANT_SENSORS:
            with self.subTest(sensor=description.key):
                self.assertIsNone(description.value_fn({}))

    async def test_device_and_plant_entity_ids_remain_unchanged(self):
        coordinator = Mock(config_entry=None, hass=Mock(), data={})
        for description in self.sensor_module.DEVICE_SENSORS:
            sensor = self.sensor_module.SAJDeviceSensor(coordinator, description, "existing-device")
            self.assertEqual(sensor.unique_id, f"existing-device_{description.key}")
        for description in self.sensor_module.PLANT_SENSORS:
            sensor = self.sensor_module.SAJPlantSensor(coordinator, description, "existing-plant", "Plant")
            self.assertEqual(sensor.unique_id, f"existing-plant_{description.key}")


if __name__ == "__main__":
    unittest.main()
