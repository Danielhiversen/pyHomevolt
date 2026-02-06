"""Constants for the Homevolt library."""

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

# Device type mappings for sensors
DEVICE_MAP = {
    "grid": "grid",
    "solar": "solar",
    "load": "load",
    "house": "load",
}
