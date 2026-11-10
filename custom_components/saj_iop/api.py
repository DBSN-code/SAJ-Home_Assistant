"""
SAJ IOP API Client
==================
Async Python client for the SAJ Electric IOP monitoring portal.
Uses v2 login/plant endpoints and the compatible v1 device endpoints.

Supports:
- Authentication (login with AES-ECB encrypted password + JWT token)
- Request signing (SHA1-based signature mechanism)
- Plant data retrieval
- Device (micro inverter) data retrieval
- Energy statistics
"""

import hashlib
import hmac
import json
import logging
import string
import random
import time
import uuid
from datetime import date
from typing import Any

import aiohttp
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

_LOGGER = logging.getLogger(__name__)

# Constants
DEFAULT_BASE_URL = "https://iop.saj-electric.com"
API_PATH = "/dev-api/api/v1"
API_V2_PATH = "/dev-api/api/v2"
# Public portal client secret, not an account credential.
V2_CLIENT_SECRET = "b389a704-31f1-463d-8db7-435b18d1311d"
AUTH_EXPIRED_CODES = {401, 10002, 10004, 10007}
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=30)
APP_PROJECT_NAME = "elekeeper"
CLIENT_ID = "esolar-monitor-admin"
SIGNATURE_KEY = "ktoKRLgQPjvNyUZO8lVc9kU1Bsip6XIe"
AES_KEY_HEX = "ec1840a7c53cf0709eb784be480379b6"
AES_KEY = bytes.fromhex(AES_KEY_HEX)

# Keys excluded from signature computation
SIGN_EXCLUDED_KEYS = {"signature", "signParams"}


class SAJApiError(Exception):
    """Base exception for SAJ API errors."""

    def __init__(self, message: str, err_code: int = -1):
        super().__init__(message)
        self.err_code = err_code


class SAJAuthError(SAJApiError):
    """Authentication error."""


class SAJApi:
    """Async client for the SAJ IOP REST API."""

    def __init__(
        self,
        username: str,
        password: str,
        base_url: str = DEFAULT_BASE_URL,
        session: aiohttp.ClientSession | None = None,
    ):
        self._username = username
        self._password = password
        self._base_url = base_url.rstrip("/")
        self._session = session
        self._own_session = session is None
        self._token: str | None = None
        self._token_head: str = "Bearer "
        self._token_expires_at: float = 0

    # =========================================================================
    # Crypto helpers
    # =========================================================================

    @staticmethod
    def _encrypt_password(password: str) -> str:
        """Encrypt password using AES-ECB with PKCS7 padding."""
        cipher = AES.new(AES_KEY, AES.MODE_ECB)
        padded = pad(password.encode("utf-8"), AES.block_size)
        encrypted = cipher.encrypt(padded)
        return encrypted.hex()

    @staticmethod
    def _generate_random(length: int = 32) -> str:
        """Generate random alphanumeric string for request signing."""
        chars = string.ascii_letters + string.digits
        return "".join(random.choice(chars) for _ in range(length))

    @staticmethod
    def _compute_signature(params: dict[str, Any]) -> str:
        """
        Compute signature for API request parameters.
        
        Algorithm (reverse-engineered from SAJ portal JavaScript):
        1. Take all params except 'signature' and 'signParams'
        2. Remove keys with empty/null values
        3. Build "key=value" pairs
        4. Sort pairs by ASCII char code (lexicographic)
        5. Join with "&"
        6. Append "&key=<SIGNATURE_KEY>"
        7. MD5 hash the string
        8. SHA1 hash the MD5 result
        9. Uppercase
        """
        pairs = []
        for key, value in params.items():
            if key in SIGN_EXCLUDED_KEYS:
                continue
            if value is None or (isinstance(value, str) and value == ""):
                continue
            pairs.append(f"{key}={value}")

        # Sort by char code (standard ASCII lexicographic sort on full pair string)
        pairs.sort(key=lambda s: [ord(c) for c in s])

        sign_string = "&".join(pairs) + f"&key={SIGNATURE_KEY}"

        # Double hash: MD5 then SHA1
        md5_hash = hashlib.md5(sign_string.encode("utf-8")).hexdigest()
        sha1_hash = hashlib.sha1(md5_hash.encode("utf-8")).hexdigest().upper()
        return sha1_hash

    def _build_common_params(self) -> dict[str, Any]:
        """Build the common parameters included in every request."""
        return {
            "appProjectName": APP_PROJECT_NAME,
            "clientDate": date.today().strftime("%Y-%m-%d"),
            "lang": "en",
            "timeStamp": str(int(time.time() * 1000)),
            "random": self._generate_random(32),
            "clientId": CLIENT_ID,
        }

    def _build_signed_params(
        self,
        extra_params: dict[str, Any] | None = None,
        is_post: bool = False,
    ) -> dict[str, Any]:
        """
        Build request parameters with common fields and signature.
        
        For GET requests: signature covers ALL params (extra + common).
        For POST requests: signature covers ONLY common params.
        The extra params are still sent but not signed.
        """
        common = self._build_common_params()

        if is_post:
            # POST: sign only common params, then merge extra params into final
            sign_params = dict(common)
            signature = self._compute_signature(sign_params)
            sign_param_names = [k for k in sign_params.keys() if k not in SIGN_EXCLUDED_KEYS]

            # Build final params: extra data + common + signing metadata
            final: dict[str, Any] = {}
            if extra_params:
                final.update(extra_params)
            final.update(common)
            final["signParams"] = ",".join(sign_param_names)
            final["signature"] = signature
            return final
        else:
            # GET: sign ALL params together (extra + common)
            all_params: dict[str, Any] = {}
            if extra_params:
                all_params.update(extra_params)
            all_params.update(common)

            signature = self._compute_signature(all_params)
            sign_param_names = [k for k in all_params.keys() if k not in SIGN_EXCLUDED_KEYS]
            all_params["signParams"] = ",".join(sign_param_names)
            all_params["signature"] = signature
            return all_params

    # =========================================================================
    # Session management
    # =========================================================================

    async def _ensure_session(self) -> aiohttp.ClientSession:
        """Ensure an aiohttp session exists."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
            self._own_session = True
        return self._session

    async def close(self):
        """Close the session if we own it."""
        if self._own_session and self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    def _get_headers(self, authenticated: bool = True) -> dict[str, str]:
        """Build HTTP headers for requests."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Content-Language": "zh_CN",
            "enablesign": "false",
        }
        if authenticated and self._token:
            headers["Authorization"] = f"{self._token_head}{self._token}"
        return headers

    @property
    def is_authenticated(self) -> bool:
        """Check if we have a valid token."""
        return self._token is not None and time.time() < self._token_expires_at

    # =========================================================================
    # API methods
    # =========================================================================

    def _build_v2_request(
        self, params: dict[str, Any], *, authenticated: bool = True
    ) -> tuple[dict[str, str], str]:
        """Match the portal v2 JSON body and X-Sign HMAC-SHA256 protocol.

        Sign the MD5 of the exact serialized body plus sorted X-* metadata.
        Timestamp and trace ID are appended as timestamp/nonce, not included
        among the sorted headers. The legacy v1 signing remains for reads.
        """
        timestamp = str(int(time.time() * 1000))
        client_date = date.today().isoformat()
        headers = self._get_headers(authenticated=authenticated)
        headers.pop("enablesign", None)
        headers.update({
            "Content-Type": "application/json;charset=utf-8",
            "lang": "en",
            "X-App-Project-Name": APP_PROJECT_NAME,
            "X-Client-Date": client_date,
            "X-Lang": "en",
            "X-Timestamp": timestamp,
            "X-Client-Code": "organization",
            "X-Theme-Color": "light",
            "X-Trace-Id": uuid.uuid4().hex[:16],
        })
        body = json.dumps({
            **params,
            "appProjectName": APP_PROJECT_NAME,
            "clientDate": client_date,
            "lang": "en",
            "timeStamp": int(timestamp),
            "clientId": CLIENT_ID,
            "clientCode": "organization",
            "themeColor": "light",
        }, ensure_ascii=False, separators=(",", ":"))
        sign_params = {
            key.lower()[2:]: value
            for key, value in headers.items()
            if key.lower().startswith("x-")
            and key.lower() not in {"x-timestamp", "x-trace-id"}
        }
        sign_params["body"] = hashlib.md5(body.encode("utf-8")).hexdigest()
        sign_string = "&".join(f"{key}={sign_params[key]}" for key in sorted(sign_params))
        sign_string += f"&nonce={headers['X-Trace-Id']}&timestamp={timestamp}"
        headers["X-Sign"] = hmac.new(
            V2_CLIENT_SECRET.encode("utf-8"),
            sign_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return headers, body

    async def login(self) -> dict[str, Any]:
        """
        Authenticate with the SAJ portal.
        
        Returns the login response data including token info.
        Raises SAJAuthError on failure.
        """
        session = await self._ensure_session()
        
        self._token = None
        self._token_expires_at = 0
        headers, body = self._build_v2_request({
            "username": self._username,
            "password": self._encrypt_password(self._password),
            "rememberMe": True,
            "loginType": 1,
        }, authenticated=False)

        _LOGGER.debug("Logging in to SAJ portal")

        async with session.post(
            f"{self._base_url}{API_V2_PATH}/sys/user/login",
            data=body.encode("utf-8"),
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        ) as resp:
            if resp.status in (401, 403):
                raise SAJAuthError("SAJ login was rejected", err_code=resp.status)
            result = await self._read_response(resp)
            err_code = result.get("errCode", -1)

            if err_code != 0:
                raise SAJAuthError(
                    f"Login failed: {result.get('errMsg', 'Unknown error')}",
                    err_code=err_code,
                )

            data = result.get("data")
            if not isinstance(data, dict) or not isinstance(data.get("token"), str) or not data["token"]:
                raise SAJAuthError("Login response did not include a valid token")
            try:
                expires_in = int(data["expiresIn"])
            except (KeyError, TypeError, ValueError) as err:
                raise SAJAuthError("Login response did not include a valid token lifetime") from err
            if expires_in <= 0:
                raise SAJAuthError("Login response token lifetime must be positive")
            token_head = data.get("tokenHead") or "Bearer"
            if not isinstance(token_head, str):
                raise SAJAuthError("Login response did not include a valid token type")
            self._token = data["token"]
            self._token_head = token_head.strip() + " "
            # Reserve at most 10% for short-lived tokens, capped at five minutes.
            self._token_expires_at = time.time() + expires_in - min(300, expires_in * 0.1)

            _LOGGER.info("Successfully logged in to SAJ portal")
            return data

    async def _ensure_authenticated(self):
        """Ensure we have a valid authentication token."""
        if not self.is_authenticated:
            await self.login()

    @staticmethod
    async def _read_response(resp: aiohttp.ClientResponse) -> dict[str, Any]:
        """Reject removed endpoints/invalid responses without logging secrets."""
        if resp.status >= 400:
            raise SAJApiError(f"SAJ returned HTTP {resp.status}", err_code=resp.status)
        try:
            result = await resp.json()
        except (aiohttp.ContentTypeError, ValueError) as err:
            raise SAJApiError("SAJ returned an invalid JSON response") from err
        if not isinstance(result, dict):
            raise SAJApiError("SAJ returned an unexpected response format")
        return result

    async def _api_get(
        self, path: str, extra_params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make an authenticated GET request to the API."""
        await self._ensure_authenticated()
        session = await self._ensure_session()

        url = f"{self._base_url}{API_PATH}/{path}"
        _LOGGER.debug("GET %s", url)
        for attempt in range(2):
            async with session.get(
                url, params=self._build_signed_params(extra_params),
                headers=self._get_headers(), timeout=REQUEST_TIMEOUT,
            ) as resp:
                result = {"errCode": 401} if resp.status == 401 else await self._read_response(resp)
            err_code = result.get("errCode", -1)
            if err_code in AUTH_EXPIRED_CODES and attempt == 0:
                _LOGGER.warning("Token expired, re-authenticating...")
                self._token = None
                await self.login()
                continue
            if err_code != 0:
                raise SAJApiError(
                    f"API error on {path}: {result.get('errMsg', 'Unknown')}",
                    err_code=err_code,
                )
            return result.get("data", {})

    async def _api_v2_post(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """Read a v2 endpoint and renew an expired session at most once."""
        await self._ensure_authenticated()
        session = await self._ensure_session()
        for attempt in range(2):
            headers, body = self._build_v2_request(params)
            async with session.post(
                f"{self._base_url}{API_V2_PATH}/{path}", data=body.encode("utf-8"),
                headers=headers, timeout=REQUEST_TIMEOUT,
            ) as resp:
                result = {"errCode": 401} if resp.status == 401 else await self._read_response(resp)
            err_code = result.get("errCode", -1)
            if err_code in AUTH_EXPIRED_CODES and attempt == 0:
                self._token = None
                await self.login()
                continue
            if err_code != 0:
                raise SAJApiError(
                    f"API error on {path}: {result.get('errMsg', 'Unknown')}",
                    err_code=err_code,
                )
            data = result.get("data")
            if not isinstance(data, dict):
                raise SAJApiError(f"Unexpected data format on {path}")
            return data

    async def _api_post(
        self, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make an authenticated POST request to the API."""
        await self._ensure_authenticated()
        session = await self._ensure_session()

        # For POST, signature covers only common params
        params = self._build_signed_params(body, is_post=True)
        headers = self._get_headers(authenticated=True)
        headers["Content-Type"] = "application/x-www-form-urlencoded;charset=UTF-8"

        url = f"{self._base_url}{API_PATH}/{path}"
        _LOGGER.debug("POST %s", url)

        async with session.post(url, data=params, headers=headers) as resp:
            result = await resp.json()
            err_code = result.get("errCode", -1)

            if err_code != 0:
                raise SAJApiError(
                    f"API error on {path}: {result.get('errMsg', 'Unknown')}",
                    err_code=err_code,
                )

            return result.get("data", {})

    # =========================================================================
    # Plant endpoints
    # =========================================================================

    async def get_plant_list(self) -> list[dict[str, Any]]:
        """Get list of all plants (solar installations)."""
        data = await self._api_get("monitor/plant/getPlantList", {
            "searchOfficeIdArr": "1",
            "pageNo": "1",
            "pageSize": "100",
        })
        return data.get("list", []) if isinstance(data, dict) else data

    async def get_plant_overview(self, plant_uid: str) -> dict[str, Any]:
        """Map v2 energy statistics to the existing sensor keys (kWh, W)."""
        data = await self.get_plant_statistics(plant_uid)
        rows = data.get("energyDataList", [])
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise SAJApiError("Unexpected plant energy statistics format")
        sections = {row.get("dataType"): row for row in rows}
        energy = sections.get("PV_ENERGY", {})
        revenue = sections.get("REVENUE", {})
        return {
            "todayEnergy": energy.get("energy1Today"),
            "totalEnergy": energy.get("energy1Total"),
            "peakPower": data.get("peakPower"),
            "todayIncome": revenue.get("todayIncome"),
            "totalIncome": revenue.get("totalIncome"),
        }

    async def get_plant_statistics(self, plant_uid: str) -> dict[str, Any]:
        """Get plant statistics data."""
        return await self._api_v2_post("monitor/plantHome/getPlantEnergyStatistics", {
            "plantUid": plant_uid,
        })

    async def get_energy_flow(self, plant_uid: str) -> dict[str, Any]:
        """Get real-time energy flow data for a plant."""
        return await self._api_v2_post("monitor/plantHome/getDeviceEnergyFlowDiagram", {
            "plantUid": plant_uid,
        })

    # =========================================================================
    # Device endpoints
    # =========================================================================

    async def get_device_list(self, plant_uid: str) -> list[dict[str, Any]]:
        """Get list of all devices (inverters) for a plant."""
        data = await self._api_get("monitor/device/getDeviceList", {
            "plantUid": plant_uid,
            "pageNo": "1",
            "pageSize": "100",
        })
        return data.get("list", []) if isinstance(data, dict) else data

    async def get_device_info(self, device_sn: str) -> dict[str, Any]:
        """Get detailed info for a specific device including real-time data."""
        return await self._api_get("monitor/device/getOneDeviceInfo", {
            "deviceSn": device_sn,
        })

    async def get_device_base_info(self, device_sn: str) -> dict[str, Any]:
        """Get base/static info for a device (model, firmware, etc.)."""
        return await self._api_get("monitor/device/baseDeviceInfo", {
            "deviceSn": device_sn,
        })

    # =========================================================================
    # Weather
    # =========================================================================

    async def get_current_weather(self, plant_uid: str) -> dict[str, Any]:
        """Get current weather at plant location."""
        return await self._api_get("monitor/weather/getCurrentWeather", {
            "plantUid": plant_uid,
            "forecastType": "1",
        })
