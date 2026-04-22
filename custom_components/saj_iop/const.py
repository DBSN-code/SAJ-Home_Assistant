"""Constants for the SAJ IOP Solar integration."""

DOMAIN = "saj_iop"

# Configuration keys
CONF_PLANT_UID = "plant_uid"
CONF_PLANT_NAME = "plant_name"

# Defaults
DEFAULT_SCAN_INTERVAL = 300  # 5 minutes
MIN_SCAN_INTERVAL = 60  # 1 minute

# Running states
RUNNING_STATE_MAP = {
    0: "unknown",
    1: "normal",
    2: "alarm",
    3: "offline",
}
