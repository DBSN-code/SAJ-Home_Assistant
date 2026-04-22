"""
SAJ IOP API Client
==================
Async Python client for the SAJ Electric IOP monitoring portal.
Communicates directly with the REST API at iop.saj-electric.com.

Supports:
- Authentication (login with AES-ECB encrypted password + JWT token)
- Request signing (SHA1-based signature mechanism)
- Plant data retrieval
- Device (micro inverter) data retrieval
- Energy statistics
"""

import hashlib
import logging
import string
import random
import time
from datetime import date
from typing import Any

import aiohttp
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

_LOGGER = logging.getLogger(__name__)

# Constants
DEFAULT_BASE_URL = "https://iop.saj-electric.com"
API_PATH = "/dev-api/api/v1"
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

    async def login(self) -> dict[str, Any]:
        """
        Authenticate with the SAJ portal.
        
        Returns the login response data including token info.
        Raises SAJAuthError on failure.
        """
        session = await self._ensure_session()
        
        encrypted_password = self._encrypt_password(self._password)

        login_params = {
            "lang": "en",
            "password": encrypted_password,
            "rememberMe": "true",
            "username": self._username,
            "loginType": "1",
        }

        # Build signed params for login (POST: sign only common params)
        signed_params = self._build_signed_params(login_params, is_post=True)

        headers = self._get_headers(authenticated=False)
        headers["Content-Type"] = "application/x-www-form-urlencoded;charset=UTF-8"

        _LOGGER.debug("Logging in to SAJ portal as %s", self._username)

        async with session.post(
            f"{self._base_url}{API_PATH}/sys/login",
            data=signed_params,
            headers=headers,
        ) as resp:
            result = await resp.json()
            err_code = result.get("errCode", -1)

            if err_code != 0:
                raise SAJAuthError(
                    f"Login failed: {result.get('errMsg', 'Unknown error')}",
                    err_code=err_code,
                )

            data = result.get("data", {})
            self._token = data.get("token")
            self._token_head = data.get("tokenHead", "Bearer ")
            expires_in = data.get("expiresIn", 259199)
            self._token_expires_at = time.time() + expires_in - 300  # 5min buffer

            _LOGGER.info("Successfully logged in to SAJ portal")
            return data

    async def _ensure_authenticated(self):
        """Ensure we have a valid authentication token."""
        if not self.is_authenticated:
            await self.login()

    async def _api_get(
        self, path: str, extra_params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Make an authenticated GET request to the API."""
        await self._ensure_authenticated()
        session = await self._ensure_session()

        params = self._build_signed_params(extra_params)
        headers = self._get_headers(authenticated=True)

        url = f"{self._base_url}{API_PATH}/{path}"
        _LOGGER.debug("GET %s", url)

        async with session.get(url, params=params, headers=headers) as resp:
            result = await resp.json()
            err_code = result.get("errCode", -1)

            if err_code == 401 or err_code == 10001:
                # Token expired, re-authenticate
                _LOGGER.warning("Token expired, re-authenticating...")
                self._token = None
                await self.login()
                # Retry the request
                params = self._build_signed_params(extra_params)
                headers = self._get_headers(authenticated=True)
                async with session.get(url, params=params, headers=headers) as retry_resp:
                    result = await retry_resp.json()
                    err_code = result.get("errCode", -1)

            if err_code != 0:
                raise SAJApiError(
                    f"API error on {path}: {result.get('errMsg', 'Unknown')}",
                    err_code=err_code,
                )

            return result.get("data", {})

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
        """Get aggregated overview data for a plant."""
        return await self._api_get("monitor/home/getPlantGridOverviewInfo", {
            "plantUid": plant_uid,
        })

    async def get_plant_statistics(self, plant_uid: str) -> dict[str, Any]:
        """Get plant statistics data."""
        return await self._api_get("monitor/home/getPlantStatisticsData", {
            "plantUid": plant_uid,
        })

    async def get_energy_flow(self, plant_uid: str) -> dict[str, Any]:
        """Get real-time energy flow data for a plant."""
        return await self._api_get("monitor/home/getDeviceEneryFlowData", {
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
