"""Constants for the ConnectLife integration."""

DOMAIN = "connectlife"

ATTR_DEVICE = "device"
ATTR_DESC = "desc"
ATTR_KEY = "key"

CONF_DEVICES = "devices"
CONF_DEVELOPMENT_MODE = "development_mode"
CONF_DISABLE_BEEP = "disable_beep"
CONF_TEST_SERVER_URL = "test_server_url"

# Token-mode (ConnectLife.RU / TRIR) authentication fields. Required when
# the account is registered against a non-Gigya Russian backend; the
# username/password flow doesn't work for those users.
CONF_REFRESH_TOKEN = "refresh_token"
CONF_SOURCE_ID = "source_id"
CONF_GATEWAY_BASE_URL = "gateway_base_url"

# Set by the orphaned-statistics repair flow once the user clicks Clear or
# Ignore. While unset, every setup runs orphan detection so the repair
# survives missed restarts; once set, detection is skipped permanently for
# this entry.
DATA_STATE_CLASS_MIGRATION_DONE = "state_class_migration_done"

ACTION = "action"
CURRENT_OPERATION = "current_operation"
HVAC_ACTION = "hvac_action"
HVAC_MODE = "hvac_mode"
FAN_MODE = "fan_mode"
IS_ON = "is_on"
IS_AWAY_MODE_ON = "is_away_mode_on"
MODE = "mode"
PRESET = "preset"
PRESETS = "presets"
STATE = "state"
SWING_MODE = "swing_mode"
SWING_HORIZONTAL_MODE = "swing_horizontal_mode"
TARGET_HUMIDITY = "target_humidity"
TARGET_TEMPERATURE = "target_temperature"
TEMPERATURE_UNIT = "temperature_unit"

SW_VERSION_PROPERTY = "oem_host_version"
