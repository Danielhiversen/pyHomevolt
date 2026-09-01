"""Constants for the Homevolt library."""

# Connection settings
DEFAULT_CONNECT_TIMEOUT = 10
DEFAULT_READ_TIMEOUT = 30
RETRY_COUNT = 3
RETRY_BACKOFF_FACTOR = 2.0
RETRY_STATUS_CODES = {502, 503, 504}

# API endpoints
ENDPOINT_EMS = "/ems.json"
ENDPOINT_SCHEDULE = "/schedule.json"
ENDPOINT_CONSOLE = "/console.json"
ENDPOINT_PARAMS = "/params.json"

# Map integer schedule codes to snake_case identifiers
SCHEDULE_TYPE = {
    0: "idle",
    1: "inverter_charge",
    2: "inverter_discharge",
    3: "grid_charge",
    4: "grid_discharge",
    5: "grid_charge_discharge",
    6: "frequency_reserve",
    7: "solar_charge",
    8: "solar_charge_discharge",
    9: "full_solar_export",
}

# Modes confirmed to produce a matching manual schedule on current firmware.
CONTROLLABLE_SCHEDULE_TYPE = {
    mode: option for mode, option in SCHEDULE_TYPE.items() if mode in {0, 1, 2, 6, 7}
}

# Parameters independently verified to round-trip for each controllable mode.
WRITABLE_BATTERY_PARAMETERS = {
    0: frozenset(),
    1: frozenset({"setpoint"}),
    2: frozenset({"setpoint"}),
    6: frozenset({"grid_import_limit", "grid_export_limit"}),
    7: frozenset(),
}

# Device type mappings for sensors
DEVICE_MAP = {
    "grid": "grid",
    "solar": "solar",
    "load": "load",
    "house": "load",
}
