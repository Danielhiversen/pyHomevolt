"""Constants for the Homevolt library."""

# API endpoints
ENDPOINT_EMS = "/ems.json"
ENDPOINT_SCHEDULE = "/schedule.json"

SCHEDULE_TYPE = {
    0: "Idle",
    1: "Charge Setpoint",
    2: "Discharge Setpoint",
    3: "Charge Grid Setpoint",
    4: "Discharge Grid Setpoint",
    5: "Charge/Discharge Grid Setpoint",
}

# Device type mappings for sensors
DEVICE_MAP = {
    "grid": "grid",
    "solar": "solar",
    "load": "load",
    "house": "load",
}

