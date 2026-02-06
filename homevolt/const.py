"""Constants for the Homevolt library."""

# API endpoints
ENDPOINT_EMS = "/ems.json"
ENDPOINT_SCHEDULE = "/schedule.json"
ENDPOINT_CONSOLE = "/console.json"
ENDPOINT_PARAMS = "/params.json"

SCHEDULE_TYPE = {
    "frequency_reserve": "Frequency reserve",
    "full_solar_export": "Full solar export",
    "grid_charge": "Grid charge",
    "grid_charge_discharge": "Grid charge/discharge",
    "grid_discharge": "Grid discharge",
    "idle": "Idle",
    "inverter_charge": "Inverter charge",
    "inverter_discharge": "Inverter discharge",
    "solar_charge": "Solar charge",
    "solar_charge_discharge": "Solar charge/discharge",
}

# Device type mappings for sensors
DEVICE_MAP = {
    "grid": "grid",
    "solar": "solar",
    "load": "load",
    "house": "load",
}
