# ConnectLife.TRIR for Home Assistant

A personal, unofficial fork of [oyvindwe/connectlife-ha](https://github.com/oyvindwe/connectlife-ha) that adds support for accounts of [ConnectLife.TRIR](https://play.google.com/store/apps/details?id=com.hisense.connectlife.trir), the CIS version of the ConnectLife app.

Upstream can't log these users in (see [bilan/connectlife-api-connector#25](https://github.com/bilan/connectlife-api-connector/issues/25)): their accounts live on a separate Hisense backend that rejects the standard Gigya login.

## What this fork changes

- **Token login.** Authenticates with a refresh token and `sourceId` captured from the mobile app instead of a username and password.
- **CIS gateway.** Requests go to `clife-ru2-gateway.hijuconn.com`, which accepts the same signed request format as the EU gateway.
- **Token rotation.** The server issues a new refresh token on every refresh (access tokens last 24 h, refresh tokens 30 days). The integration saves each new token to its config entry without reloading, so it keeps working as long as Home Assistant runs at least once a month. The phone app keeps working in parallel.
- **Small footprint.** All of it lives in one subclass of the upstream client, [`_trir_api.py`](custom_components/connectlife/_trir_api.py), plus the config flow. Device mappings are unchanged, and the EU username/password login still works.

Tested with two Hisense split air conditioners, AS-18UW4RMSHB01 and AS-07UW4RYRKA01: full control from Home Assistant works, including power, HVAC modes (auto, cool, heat and others), target temperature, fan speed and swing.

## Installation

### HACS
Add this repository (`flattened-duck/connectlife-trir-ha`) as a custom repository of type "Integration" and install it.
See https://hacs.xyz/docs/faq/custom_repositories/

### Download
Download the `connectlife` directory and place it in your `<config>/custom_components/`.

Restart Home Assistant after installing.

## Setup

1. **Capture the tokens.** Install [HTTP Toolkit](https://httptoolkit.com) on your computer and connect your Android phone to it. Log in to the ConnectLife.TRIR app or refresh a screen, then look through the captured requests and responses for `refreshToken` and `sourceId`. Proxy-based tools such as Charles may not see this traffic: the app is built with Flutter, and its networking doesn't go through them.
2. **Add the integration.** Go to Settings → Devices & services → Add integration → ConnectLife. Leave username and password empty and fill in the refresh token and source ID. The gateway URL is optional and defaults to the CIS gateway.

If the refresh token expires, Home Assistant asks you to re-authenticate: capture a fresh token the same way.

Known limitation: if Home Assistant shuts down uncleanly within about a second of a token rotation, the new token can be lost, and you need to capture a fresh one.

Everything below is the upstream documentation, which applies to this fork as well.

## Supported ConnectLife devices

See [DEVICES.md](DEVICES.md) for the full list of supported devices.

### Default device types

Default mapping files are provided for the following device types:

| Device type              | Device type code                                                |
|--------------------------|-----------------------------------------------------------------|
| Portable air conditioner | [006](custom_components/connectlife/data_dictionaries/006.yaml) |
| Dehumidifier             | [007](custom_components/connectlife/data_dictionaries/007.yaml) |
| Window air conditioner   | [008](custom_components/connectlife/data_dictionaries/008.yaml) |
| Air conditioner          | [009](custom_components/connectlife/data_dictionaries/009.yaml) |
| Hood                     | [012](custom_components/connectlife/data_dictionaries/012.yaml) |
| Oven                     | [013](custom_components/connectlife/data_dictionaries/013.yaml) |
| Dishwasher               | [015](custom_components/connectlife/data_dictionaries/015.yaml) |
| Heat pump                | [016](custom_components/connectlife/data_dictionaries/016.yaml) |
| Induction hob            | [020](custom_components/connectlife/data_dictionaries/020.yaml) |
| Oven                     | [023](custom_components/connectlife/data_dictionaries/023.yaml) |
| Washing machine          | [025](custom_components/connectlife/data_dictionaries/025.yaml) |
| Refrigerator             | [026](custom_components/connectlife/data_dictionaries/026.yaml) |
| Washing machine          | [027](custom_components/connectlife/data_dictionaries/027.yaml) |
| Tumble dryer             | [030](custom_components/connectlife/data_dictionaries/030.yaml) |
| Tumble dryer             | [032](custom_components/connectlife/data_dictionaries/032.yaml) |

Any devices of these types will use the default mapping file, but it may not be fully functional until a
feature-specific mapping file is provided.

Any unmapped properties will show up as sensors with names based on their properties. As there are a lot of exposed
properties, all unknown entities are disabled by default. Access the device or entity list to view sensors and enable.

Please contribute PRs with [mapping files](custom_components/connectlife/data_dictionaries) for your devices!

## Disable beeping

Some devices will beep on every configuration change. To disable this, go to the
[ConnectLife integration](https://my.home-assistant.io/redirect/integration/?domain=connectlife)
and click "Configure" → "Configure a device" and select the device you want to disable beeping for. 

## Service to set property values on sensors

Entity service `connectlife.set_value` can be used to set values. Use with caution, as there is **no** validation
if property is writeable or that the value is legal to set.

1. The service can be accessed from [Developer tools - Services](https://my.home-assistant.io/redirect/developer_services/).
2. Search for service name "ConnectLife: Set value"
3. Select entity as target.
4. Enter value
5. Call service.

It is possible to guard against `set_value` by setting `read_only: true` in the data dictionary on the sensor, e.g.
```yaml
  - property: f_status 
    sensor:
      read_only: true
```

## Polling delay

The integration polls the ConnectLife API every 60 seconds to avoid overloading the API and risking being banned. When a command is sent from Home Assistant, only the properties included in that command are updated immediately in the HA UI. Any side effects on other properties (e.g., turning on an AC may also change fan mode or current temperature) will not appear until the next poll. Changes made outside Home Assistant (e.g., from the ConnectLife mobile app or physical device controls) may also take up to 60 seconds to appear.

## Issues

### Climate entities

Please ignore the following warning in the log:
```
Entity None (<class 'custom_components.connectlife.climate.ConnectLifeClimate'>) implements HVACMode(s): auto, off and therefore implicitly supports the turn_on/turn_off methods without setting the proper ClimateEntityFeature. Please report it to the author of the 'connectlife' custom integration
```

Missing features:
- Setting `target_temperature_high`/`target_temperature_low`

### Heat pump entities
 
Missing features:
- Setting state except to off/one defined state
- Setting `target_temperature_high`/`target_temperature_low`

### Updated Terms & Conditions

ConnectLife periodically updates their Terms & Conditions. When this happens, the integration may stop working
with errors like `Account Pending Registration` or `Missing required fields for registration`, or devices may
silently become unavailable.

To resolve this, you need to accept the new Terms & Conditions in the ConnectLife mobile app:

1. Open the ConnectLife mobile app
2. Go to Settings and **change the app language to English**
3. **Force close the app** (not just background it)
4. **Reopen the app** — the Terms & Conditions acceptance screen should appear
5. **Accept the new Terms & Conditions**
6. In Home Assistant, **reload the ConnectLife integration**
7. You can change the app language back afterward — the acceptance persists

The language change is needed because updated Terms & Conditions are often only available in English initially.
The app skips the acceptance prompt if the translated version for your language doesn't exist yet, but the
backend still requires acceptance.

## Credits and license

Based on [connectlife-ha](https://github.com/oyvindwe/connectlife-ha) by Øyvind Matheson Wergeland. Device support, mappings and most of the code come from upstream; if this integration is useful to you, consider [supporting the upstream author](https://www.buymeacoffee.com/oyvindwev).

Issues specific to ConnectLife.TRIR belong in this repository; everything else, in [upstream](https://github.com/oyvindwe/connectlife-ha/issues). For development, see [DEVELOPMENT.md](DEVELOPMENT.md).

Licensed under GPL-3.0, the same as upstream.
