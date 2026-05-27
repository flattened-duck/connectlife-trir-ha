"""Subclass of ConnectLifeApi for the ConnectLife.RU / TRIR fork.

The upstream library (``connectlife==0.7.2``) authenticates against
Gigya (SAP CDC) and the EU HijuConn gateway. ConnectLife.RU users are
registered against a different Hisense backend (custom Russian login
system) and live on a different gateway cluster
(``clife-ru2-gateway.hijuconn.com``). The Gigya flow rejects them
outright.

However: the Russian gateway accepts the **same EU-signed request
format** on the legacy ``/clife-svc/pu/*`` and ``/device/pu/*``
endpoints (verified empirically — fetching the device list and toggling
``t_power`` on a real appliance both work), and it exposes a
``POST /account/acc/refresh_token`` endpoint that mints fresh access
tokens given a captured refresh token + per-install ``sourceId``.

So we keep the upstream library unchanged and add a thin subclass that:

  1. Skips the Gigya login (``_initial_access_token`` → refresh-token
     flow) so the parent ``_fetch_access_token`` state machine works.
  2. Implements ``_refresh_access_token`` against ``/account/acc/refresh_token``.
  3. Points the gateway URLs at the RU cluster.
  4. Preserves the refresh token through ``_reset_tokens`` — it is the
     only credential available; clearing it would brick the integration.
  5. Notifies the caller through an async callback every time the
     server rotates the refresh token, so it can be persisted.
"""

from __future__ import annotations

import asyncio
import base64
import datetime as dt
import hashlib
import json
import logging
from typing import Any, Awaitable, Callable

import aiohttp

# These imports reach into the upstream library's module — they are not
# part of its public API. If a future upstream version renames them this
# subclass will need to follow. The constants haven't changed since the
# HijuConn migration so the risk is low.
from connectlife.api import (
    GATEWAY_APP_ID,
    GATEWAY_APP_SECRET,
    GATEWAY_LANGUAGE_ID,
    GATEWAY_RANDSTR_CHECK_FAILED,
    GATEWAY_TIMEZONE,
    GATEWAY_USER_AGENT,
    GATEWAY_VERSION,
    ConnectLifeApi,
    LifeConnectAuthError,
    LifeConnectError,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_TRIR_GATEWAY_BASE_URL = "https://clife-ru2-gateway.hijuconn.com"


class TRIRConnectLifeApi(ConnectLifeApi):
    """ConnectLife API client for the Russian / TRIR fork."""

    def __init__(
        self,
        refresh_token: str,
        source_id: str,
        *,
        gateway_base_url: str | None = None,
        refresh_token_callback: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        if not refresh_token:
            raise ValueError("refresh_token is required for TRIR auth")
        if not source_id:
            raise ValueError("source_id is required for TRIR auth")

        # The parent's __init__ stores username/password but we never use
        # the Gigya path. Passing placeholder strings keeps the parent
        # happy and never touches the wire.
        super().__init__("__trir__", "__trir__")

        base = (gateway_base_url or DEFAULT_TRIR_GATEWAY_BASE_URL).rstrip("/")
        self.gateway_device_list_url = f"{base}/clife-svc/pu/get_device_status_list"
        self.gateway_update_url = f"{base}/device/pu/property/set"
        self.gateway_energy_url = f"{base}/clife-svc/pu/air_duct_energy"
        self._trir_refresh_url = f"{base}/account/acc/refresh_token"

        self._refresh_token = refresh_token
        self._source_id = source_id
        self._refresh_token_callback = refresh_token_callback

        # Serializes the auth/refresh decision so two concurrent gateway
        # calls don't race each other into the refresh endpoint — the
        # loser of such a race would discard a now-rotated token and the
        # whole integration would break on the next 24h cycle.
        self._auth_lock = asyncio.Lock()

    # -- Auth: override Gigya path -----------------------------------------

    async def _fetch_access_token(self) -> None:
        # Re-implement the parent state machine to (a) serialize via a
        # lock, (b) raise a clear error when the refresh token expires
        # since we have no Gigya fallback, and (c) avoid the parent's
        # _reset_tokens path which would wipe the refresh token.
        async with self._auth_lock:
            now = dt.datetime.now()
            if self._access_token is not None and self._expires is not None and self._expires >= now:
                return
            if self._refresh_token_expires is not None and self._refresh_token_expires <= now:
                raise LifeConnectAuthError(
                    "Refresh token expired; reconfigure with a freshly captured token",
                    endpoint=self._trir_refresh_url,
                )
            await self._do_refresh()

    async def _initial_access_token(self) -> None:  # pragma: no cover
        # The parent's login() calls _reset_tokens + _fetch_access_token,
        # which now go through _do_refresh via our overridden
        # _fetch_access_token. This method exists only because the parent
        # references it in retry helpers — keep it as a synonym.
        await self._fetch_access_token()

    async def _refresh_access_token(self) -> None:  # pragma: no cover
        # Same reason as above: the parent's gateway invalid-token retry
        # path calls login() which routes here. We funnel through the
        # locked _fetch_access_token to keep token state consistent.
        await self._fetch_access_token()

    def _reset_tokens(self) -> None:
        # Preserve the refresh token — it is the only credential we have
        # and the parent's login() unconditionally calls this.
        self._access_token = None
        self._expires = None

    # -- The actual refresh request ----------------------------------------

    async def _do_refresh(self) -> None:
        """Exchange the stored refresh token for a fresh access token.

        The refresh endpoint demands the same EU-style signed envelope as
        the rest of the gateway, but it must NOT carry an ``accessToken``
        field (we don't have one yet, and the server validates by field
        set as well as by signature). The parent's
        ``_gateway_request_data`` always includes ``accessToken``, so we
        build the signed payload here and reuse the parent's
        ``_sign_gateway_request`` static helper for the signing itself.
        """
        if not self._refresh_token:
            raise LifeConnectAuthError(
                "Cannot refresh: no refresh_token stored",
                endpoint=self._trir_refresh_url,
            )

        timestamp = str(int(dt.datetime.now().timestamp() * 1000))
        request_data: dict[str, Any] = {
            "appId": GATEWAY_APP_ID,
            "appSecret": GATEWAY_APP_SECRET,
            "languageId": GATEWAY_LANGUAGE_ID,
            "randStr": hashlib.md5(timestamp.encode()).hexdigest(),
            "timeStamp": timestamp,
            "timezone": GATEWAY_TIMEZONE,
            "version": GATEWAY_VERSION,
            "refreshToken": self._refresh_token,
            "sourceId": self._source_id,
        }
        request_data["sign"] = ConnectLifeApi._sign_gateway_request(request_data)

        async with aiohttp.ClientSession(timeout=self.request_timeout) as session:
            async with session.post(
                self._trir_refresh_url,
                json=request_data,
                headers={"User-Agent": GATEWAY_USER_AGENT},
            ) as response:
                text = await response.text()
                if response.status != 200:
                    raise LifeConnectAuthError(
                        f"Refresh failed: HTTP {response.status}",
                        status=response.status,
                        endpoint=self._trir_refresh_url,
                    )
                try:
                    body = json.loads(text)
                except json.JSONDecodeError as err:
                    raise LifeConnectError(
                        f"Non-JSON response from refresh: {text[:200]}",
                        endpoint=self._trir_refresh_url,
                    ) from err

        gateway_response = body.get("response") if isinstance(body, dict) else None
        if not isinstance(gateway_response, dict):
            raise LifeConnectError(
                "Refresh response missing 'response' field",
                endpoint=self._trir_refresh_url,
            )
        if gateway_response.get("resultCode") not in (0, "0"):
            error_code = gateway_response.get("errorCode")
            error_desc = gateway_response.get("errorDesc") or "Unknown error"
            # randStr collision is benign — the server caches recently-seen
            # randomness for replay protection. Retrying with a fresh
            # timestamp/randStr almost always works.
            if error_code == GATEWAY_RANDSTR_CHECK_FAILED:
                _LOGGER.warning("Refresh randStr collision; retrying once")
                await asyncio.sleep(0.1)
                await self._do_refresh()
                return
            raise LifeConnectAuthError(
                f"Refresh rejected: code={error_code} desc='{error_desc}'",
                endpoint=self._trir_refresh_url,
            )

        access_token = gateway_response.get("accessToken")
        if not access_token:
            raise LifeConnectAuthError(
                "Refresh response missing accessToken",
                endpoint=self._trir_refresh_url,
            )
        self._access_token = access_token

        # NOTE: unlike the EU OAuth response (which uses epoch-ms for the
        # refresh-token expiry), the Russian gateway returns BOTH
        # ``accessTokenExpiredTime`` and ``refreshTokenExpiredTime`` as
        # durations in seconds. Observed: 86400 (24h) and 2592000 (30d).
        expires_in = _parse_positive_int(
            gateway_response.get("accessTokenExpiredTime"), default=60
        )
        # Renew 90 s before expiration to absorb clock skew.
        self._expires = dt.datetime.now() + dt.timedelta(
            seconds=max(expires_in - 90, 0)
        )

        new_refresh = gateway_response.get("refreshToken")
        if new_refresh and new_refresh != self._refresh_token:
            self._refresh_token = new_refresh
            if self._refresh_token_callback is not None:
                try:
                    await self._refresh_token_callback(new_refresh)
                except Exception:
                    _LOGGER.exception(
                        "refresh_token_callback raised; the new refresh "
                        "token may not be persisted"
                    )
        rt_expires_in = _parse_positive_int(
            gateway_response.get("refreshTokenExpiredTime"), default=None
        )
        if rt_expires_in is not None:
            self._refresh_token_expires = dt.datetime.now() + dt.timedelta(
                seconds=rt_expires_in
            )


def _parse_positive_int(value: Any, *, default: int | None) -> int | None:
    """Return a positive int parsed from ``value``, otherwise ``default``."""
    # Reject booleans explicitly (bool is an int subtype in Python and would
    # otherwise coerce to 0 or 1).
    if isinstance(value, bool):
        return default
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return n if n > 0 else default
