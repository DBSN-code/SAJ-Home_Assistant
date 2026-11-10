"""Offline regression tests: python -m unittest discover -s tests -v."""
import importlib.util
import json
from pathlib import Path
import time
import unittest
from unittest.mock import AsyncMock, Mock, patch

import aiohttp


spec = importlib.util.spec_from_file_location(
    "saj_api_under_test",
    Path(__file__).resolve().parents[1] / "custom_components/saj_iop/api.py",
)
api_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api_module)
SAJApi = api_module.SAJApi
SAJApiError = api_module.SAJApiError
SAJAuthError = api_module.SAJAuthError


class Response:
    def __init__(self, payload=None, status=200, error=None):
        self.status = status
        self.payload = payload
        self.error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self):
        if self.error:
            raise self.error
        return self.payload


def login_response(**overrides):
    return Response({"errCode": 0, "data": {
        "token": "new-test-token", "tokenHead": "Bearer ", "expiresIn": 3600,
        **overrides,
    }})


def client(*, authenticated=False):
    session = Mock(closed=False)
    session.close = AsyncMock()
    api = SAJApi("cliente@example.com", "Senha-á😀!", session=session)
    if authenticated:
        api._token = "old-test-token"
        api._token_expires_at = time.time() + 3600
    return api, session


class LoginTests(unittest.IsolatedAsyncioTestCase):
    async def test_login_matches_independent_node_crypto_vector(self):
        # Golden vector generated independently with Node crypto AES/MD5/HMAC,
        # following the public SAJ portal signing contract, not Python helpers.
        api, session = client(authenticated=True)
        session.post.return_value = login_response()
        with (
            patch.object(api_module.time, "time", return_value=1794236400),
            patch.object(api_module, "date") as calendar,
            patch.object(api_module.uuid, "uuid4") as nonce,
        ):
            calendar.today.return_value.isoformat.return_value = "2026-11-09"
            nonce.return_value.hex = "0123456789abcdef0123456789abcdef"
            await api.login()
        url = session.post.call_args.args[0]
        request = session.post.call_args.kwargs
        self.assertEqual(url, "https://iop.saj-electric.com/dev-api/api/v2/sys/user/login")
        self.assertEqual(request["headers"]["X-Sign"],
                         "83732b282b0a311be50b120f73af92ece4870342db2b4dd536d8036de3c2a9eb")
        self.assertEqual(json.loads(request["data"])["password"],
                         "bbbff62feac680554f0baf577a9b0422")
        self.assertIsInstance(request["data"], bytes)
        self.assertNotIn("Authorization", request["headers"])
        self.assertNotIn("enablesign", request["headers"])
        self.assertNotIn("signature", json.loads(request["data"]))
        self.assertEqual(request["timeout"].total, 30)

    async def test_token_head_and_string_lifetime(self):
        api, session = client()
        session.post.return_value = login_response(tokenHead="Bearer", expiresIn="3600")
        await api.login()
        self.assertTrue(api.is_authenticated)
        self.assertEqual(api._get_headers()["Authorization"], "Bearer new-test-token")

    async def test_short_lifetime_is_not_immediately_expired(self):
        api, session = client()
        session.post.return_value = login_response(expiresIn=60)
        await api.login()
        self.assertTrue(api.is_authenticated)
        self.assertGreater(api._token_expires_at, time.time() + 45)

    async def test_rejected_login_clears_previous_session(self):
        api, session = client(authenticated=True)
        session.post.return_value = Response({"errCode": 10001, "errMsg": "Invalid login"})
        with self.assertRaises(SAJAuthError):
            await api.login()
        self.assertFalse(api.is_authenticated)
        self.assertEqual(session.post.call_count, 1)

    async def test_missing_token_is_not_success(self):
        for token in (None, "", 123):
            with self.subTest(token=token):
                api, session = client(authenticated=True)
                session.post.return_value = login_response(token=token)
                with self.assertRaises(SAJAuthError):
                    await api.login()
                self.assertFalse(api.is_authenticated)

    async def test_invalid_lifetime_is_not_success(self):
        for expiry in (None, "invalid", 0, -1):
            with self.subTest(expiry=expiry):
                api, session = client()
                session.post.return_value = login_response(expiresIn=expiry)
                with self.assertRaises(SAJAuthError):
                    await api.login()
                self.assertFalse(api.is_authenticated)

    async def test_http_auth_error_is_classified(self):
        api, session = client()
        session.post.return_value = Response(status=401)
        with self.assertRaises(SAJAuthError):
            await api.login()

    async def test_does_not_close_home_assistant_shared_session(self):
        api, session = client()
        await api.close()
        session.close.assert_not_awaited()


class RequestTests(unittest.IsolatedAsyncioTestCase):
    async def test_v1_renewal_uses_v2_login_then_retries_once(self):
        for code in (10002, 10004, 10007):
            with self.subTest(code=code):
                api, session = client(authenticated=True)
                session.get.side_effect = [
                    Response({"errCode": code}),
                    Response({"errCode": 0, "data": {"list": [{"deviceSn": "unchanged-id"}]}}),
                ]
                session.post.return_value = login_response()
                result = await api.get_device_list("plant-test")
                self.assertEqual(result, [{"deviceSn": "unchanged-id"}])
                self.assertEqual(session.get.call_count, 2)
                self.assertEqual(session.post.call_count, 1)
                self.assertEqual(session.get.call_args.kwargs["headers"]["Authorization"],
                                 "Bearer new-test-token")
                self.assertIn("/api/v2/sys/user/login", session.post.call_args.args[0])

    async def test_v1_http_401_renews_without_parsing_html(self):
        api, session = client(authenticated=True)
        session.get.side_effect = [Response(status=401), Response({"errCode": 0, "data": {}})]
        session.post.return_value = login_response()
        await api.get_device_info("device-test")
        self.assertEqual(session.post.call_count, 1)

    async def test_repeated_expiry_does_not_loop(self):
        api, session = client(authenticated=True)
        session.get.return_value = Response({"errCode": 10002})
        session.post.return_value = login_response()
        with self.assertRaises(SAJApiError):
            await api.get_device_info("device-test")
        self.assertEqual(session.get.call_count, 2)
        self.assertEqual(session.post.call_count, 1)

    async def test_v2_renewal_and_new_headers(self):
        api, session = client(authenticated=True)
        session.post.side_effect = [
            Response({"errCode": 10004}), login_response(),
            Response({"errCode": 0, "data": {"totalPvPower": 1234}}),
        ]
        result = await api.get_energy_flow("plant-test")
        self.assertEqual(result["totalPvPower"], 1234)
        self.assertEqual(session.post.call_count, 3)
        request = session.post.call_args
        self.assertIn("/api/v2/monitor/plantHome/getDeviceEnergyFlowDiagram", request.args[0])
        self.assertEqual(request.kwargs["headers"]["Authorization"], "Bearer new-test-token")
        self.assertEqual(json.loads(request.kwargs["data"])["plantUid"], "plant-test")

    async def test_v2_repeated_expiry_does_not_loop(self):
        api, session = client(authenticated=True)
        session.post.side_effect = [Response({"errCode": 10002}), login_response(),
                                    Response({"errCode": 10002})]
        with self.assertRaises(SAJApiError):
            await api.get_energy_flow("plant-test")
        self.assertEqual(session.post.call_count, 3)

    async def test_non_auth_errors_do_not_attempt_login(self):
        api, session = client(authenticated=True)
        session.get.return_value = Response({"errCode": 10001, "errMsg": "Invalid parameter"})
        with self.assertRaises(SAJApiError):
            await api.get_device_info("device-test")
        session.post.assert_not_called()

    async def test_removed_endpoint_response_is_controlled(self):
        api, session = client(authenticated=True)
        session.post.return_value = Response(error=aiohttp.ContentTypeError(
            Mock(real_url="https://example.invalid"), (), message="text/plain"))
        with self.assertRaisesRegex(SAJApiError, "invalid JSON"):
            await api.get_energy_flow("plant-test")

    async def test_v2_null_data_is_not_zero_energy(self):
        api, session = client(authenticated=True)
        session.post.return_value = Response({"errCode": 0, "data": None})
        with self.assertRaisesRegex(SAJApiError, "Unexpected data format"):
            await api.get_plant_overview("plant-test")

    async def test_http_failure_is_controlled(self):
        api, session = client(authenticated=True)
        session.post.return_value = Response(status=503)
        with self.assertRaisesRegex(SAJApiError, "HTTP 503"):
            await api.get_energy_flow("plant-test")


class PlantMappingTests(unittest.IsolatedAsyncioTestCase):
    async def test_maps_sections_by_type_not_order_and_keeps_units(self):
        api, session = client(authenticated=True)
        session.post.return_value = Response({"errCode": 0, "data": {
            "peakPower": 3100,
            "energyDataList": [
                {"dataType": "LOAD_ENERGY", "energy1Total": 999999},
                {"dataType": "REVENUE", "todayIncome": 10.5, "totalIncome": 8500},
                {"dataType": "PV_ENERGY", "energy1Today": 12.5, "energy1Total": 10000.25},
            ],
        }})
        overview = await api.get_plant_overview("plant-test")
        self.assertEqual(overview, {"peakPower": 3100, "todayIncome": 10.5,
                                   "totalIncome": 8500, "todayEnergy": 12.5,
                                   "totalEnergy": 10000.25})
        self.assertIn("/api/v2/monitor/plantHome/getPlantEnergyStatistics",
                      session.post.call_args.args[0])

    async def test_missing_readings_remain_unknown(self):
        api, session = client(authenticated=True)
        session.post.return_value = Response({"errCode": 0, "data": {"energyDataList": []}})
        self.assertTrue(all(value is None for value in (await api.get_plant_overview("p")).values()))

    async def test_real_zero_readings_remain_zero(self):
        api, session = client(authenticated=True)
        session.post.return_value = Response({"errCode": 0, "data": {
            "peakPower": 0, "energyDataList": [{"dataType": "PV_ENERGY", "energy1Today": 0}],
        }})
        result = await api.get_plant_overview("p")
        self.assertEqual(result["todayEnergy"], 0)
        self.assertEqual(result["peakPower"], 0)
        self.assertIsNone(result["totalEnergy"])

    async def test_malformed_energy_sections_fail_explicitly(self):
        for rows in (None, {}, ["not-an-object"]):
            with self.subTest(rows=rows):
                api, session = client(authenticated=True)
                session.post.return_value = Response({"errCode": 0, "data": {"energyDataList": rows}})
                with self.assertRaises(SAJApiError):
                    await api.get_plant_overview("p")


if __name__ == "__main__":
    unittest.main()
