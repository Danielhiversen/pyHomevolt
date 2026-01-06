"""Constants for the Homevolt library."""

# API endpoints
ENDPOINT_EMS = "/ems.json"
ENDPOINT_SCHEDULE = "/schedule.json"
ENDPOINT_CONSOLE = "/console.json"
ENDPOINT_PARAMS = "/params.json"

SCHEDULE_TYPE = {
    0: "Idle",
    1: "Inverter Charge",
    2: "Inverter Discharge",
    3: "Grid Charge",
    4: "Grid Discharge",
    5: "Grid Charge/Discharge",
    6: "Frequency Reserve",
    7: "Solar Charge",
    8: "Solar Charge/Discharge",
    9: "Full Solar Export",
}

# Device type mappings for sensors
DEVICE_MAP = {
    "grid": "grid",
    "solar": "solar",
    "load": "load",
    "house": "load",
}
