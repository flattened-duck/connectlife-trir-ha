"""The ConnectLife integration."""

from __future__ import annotations

import logging

from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform, CONF_USERNAME, CONF_PASSWORD
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from connectlife.api import ConnectLifeApi, LifeConnectAuthError, LifeConnectError

from .const import (
    CONF_DEVELOPMENT_MODE,
    CONF_GATEWAY_BASE_URL,
    CONF_REFRESH_TOKEN,
    CONF_SOURCE_ID,
    CONF_TEST_SERVER_URL,
    DATA_STATE_CLASS_MIGRATION_DONE,
    DOMAIN,
)
from .coordinator import ConnectLifeCoordinator, ConnectLifeEnergyCoordinator
from .services import async_setup_services

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.HUMIDIFIER,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SELECT,
    Platform.SWITCH,
    Platform.WATER_HEATER,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up ConnectLife."""

    await async_setup_services(hass)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ConnectLife from a config entry."""
    _LOGGER.debug("Setting up ConnectLife")
    _LOGGER.debug("Options: %s", entry.options)
    hass.data.setdefault(DOMAIN, {})
    test_server_url = (
        entry.options.get(CONF_TEST_SERVER_URL)
       if entry.options.get(CONF_DEVELOPMENT_MODE)
        else None
    )

    refresh_token = entry.data.get(CONF_REFRESH_TOKEN)
    if refresh_token:
        # Token-mode auth: the server rotates the refresh token on every
        # successful refresh, so we must persist the new value back into
        # the config entry — otherwise the integration breaks on the next
        # token expiry (24h).
        #
        # Caveat: `async_update_entry` writes are debounced (~1s). An
        # unclean HA shutdown inside that window after a rotation loses
        # the new token and renders the entry unrecoverable — the user
        # must capture a fresh token. Rare but documented.
        async def _persist_rotated_refresh_token(new_token: str) -> None:
            new_data = {**entry.data, CONF_REFRESH_TOKEN: new_token}
            # update_listener (below) is wired to suppress reloads when
            # only the refresh_token changed, so this is safe to do
            # mid-refresh.
            hass.config_entries.async_update_entry(entry, data=new_data)

        api = ConnectLifeApi(
            test_server=test_server_url,
            refresh_token=refresh_token,
            source_id=entry.data[CONF_SOURCE_ID],
            gateway_base_url=entry.data.get(CONF_GATEWAY_BASE_URL) or None,
            refresh_token_callback=_persist_rotated_refresh_token,
        )
    else:
        api = ConnectLifeApi(entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD], test_server_url)  # type: ignore[arg-type]
    try:
        await api.login()
    except LifeConnectAuthError as ex:
        raise ConfigEntryAuthFailed from ex
    except LifeConnectError as ex:
        raise ConfigEntryNotReady from ex
    coordinator = ConnectLifeCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()
    energy_coordinator = ConnectLifeEnergyCoordinator(hass, api, coordinator)
    await energy_coordinator.async_config_entry_first_refresh()
    hass.data[DOMAIN][entry.entry_id] = coordinator
    hass.data[DOMAIN][f"{entry.entry_id}_energy"] = energy_coordinator

    # Remember the last-known entry data so update_listener can tell
    # whether a triggered update is a meaningful config change or just
    # the periodic refresh-token rotation.
    hass.data[DOMAIN][f"{entry.entry_id}_last_data"] = dict(entry.data)
    entry.async_on_unload(entry.add_update_listener(update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    await coordinator.cleanup_removed_entities()
    if not entry.data.get(DATA_STATE_CLASS_MIGRATION_DONE):
        await coordinator.update_orphaned_statistics_issue()

    return True

async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options/data update."""
    # Token-mode rotates `refresh_token` in entry.data every ~24h; reloading
    # the whole integration each time would tear down the coordinator
    # mid-poll. Compare the new entry data against the last-known snapshot
    # and skip the reload if only the refresh_token changed.
    snapshot_key = f"{entry.entry_id}_last_data"
    last_data = hass.data.get(DOMAIN, {}).get(snapshot_key)
    new_data = dict(entry.data)
    hass.data.setdefault(DOMAIN, {})[snapshot_key] = new_data
    if last_data is not None:
        changed = {
            k
            for k in {*last_data, *new_data}
            if last_data.get(k) != new_data.get(k)
        }
        if changed and changed <= {CONF_REFRESH_TOKEN}:
            _LOGGER.debug("Refresh token rotated; skipping reload")
            return
    _LOGGER.debug(f"Reloading ConnectLife")
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    _LOGGER.debug(f"Unloading ConnectLife")

    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)
        hass.data[DOMAIN].pop(f"{entry.entry_id}_energy", None)
        hass.data[DOMAIN].pop(f"{entry.entry_id}_last_data", None)

    return unload_ok
