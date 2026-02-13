"""Main Homevolt class for connecting to EMS devices."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import (
    ENDPOINT_CONSOLE,
    ENDPOINT_EMS,
    ENDPOINT_PARAMS,
    ENDPOINT_SCHEDULE,
    SCHEDULE_TYPE,
)
from .exceptions import (
    HomevoltAuthenticationError,
    HomevoltConnectionError,
    HomevoltDataError,
)
from .models import DeviceMetadata, Sensor

_LOGGER = logging.getLogger(__name__)


class Homevolt:
    """Main class for interacting with Homevolt EMS devices."""

    def __init__(
        self,
        host: str,
        password: str | None = None,
        websession: aiohttp.ClientSession | None = None,
    ) -> None:
        """Initialize the Homevolt connection.

        Args:
            host: Hostname or IP address of the Homevolt device
            password: Optional password for authentication
            websession: Optional aiohttp ClientSession. If not provided, one will be created.
        """
        if not host.startswith("http"):
            host = f"http://{host}"
        self.base_url = host
        self._password = password
        self._websession = websession
        self._own_session = websession is None
        self._auth = aiohttp.BasicAuth("admin", password) if password else None

        self.unique_id: str | None = None
        self.sensors: dict[str, Sensor] = {}
        self.device_metadata: dict[str, DeviceMetadata] = {}
        self.current_schedule: dict[str, Any] | None = None

        self.schedule: dict[str, int | None] = {
            "mode": None,
            "setpoint": None,
            "max_charge": None,
            "max_discharge": None,
            "min_soc": None,
            "max_soc": None,
            "grid_import_limit": None,
            "grid_export_limit": None,
            "threshold_high": None,
            "threshold_low": None,
            "freq_reg_droop_up": None,
            "freq_reg_droop_down": None,
        }

    @property
    def schedule_mode(self) -> int:
        """Get current schedule mode (0-9)."""
        return self.schedule["mode"] if self.schedule["mode"] is not None else 0

    @property
    def local_mode_enabled(self) -> bool:
        """Check if local mode is enabled."""
        if self.current_schedule is None:
            return False
        return self.current_schedule.get("local_mode", False)

    @property
    def schedule_setpoint(self) -> int | None:
        """Get current schedule power setpoint."""
        return self.schedule["setpoint"]

    @property
    def schedule_max_charge(self) -> int | None:
        """Get current schedule max charge power."""
        return self.schedule["max_charge"]

    @property
    def schedule_max_discharge(self) -> int | None:
        """Get current schedule max discharge power."""
        return self.schedule["max_discharge"]

    @property
    def schedule_min_soc(self) -> int | None:
        """Get current schedule minimum state of charge."""
        return self.schedule["min_soc"]

    @property
    def schedule_max_soc(self) -> int | None:
        """Get current schedule maximum state of charge."""
        return self.schedule["max_soc"]

    @property
    def schedule_grid_import_limit(self) -> int | None:
        """Get current grid import limit."""
        return self.schedule["grid_import_limit"]

    @property
    def schedule_grid_export_limit(self) -> int | None:
        """Get current grid export limit."""
        return self.schedule["grid_export_limit"]

    async def update_info(self) -> None:
        """Fetch and update all device information."""
        await self._ensure_session()
        await self.fetch_ems_data()
        await self.fetch_schedule_data()

    async def close_connection(self) -> None:
        """Close the connection and clean up resources."""
        if self._own_session and self._websession:
            await self._websession.close()
            self._websession = None

    async def _ensure_session(self) -> None:
        """Ensure a websession exists."""
        if self._websession is None:
            self._websession = aiohttp.ClientSession()
            self._own_session = True

    async def __aenter__(self) -> Homevolt:
        """Async context manager entry."""
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close_connection()

    async def fetch_ems_data(self) -> None:
        """Fetch EMS data from the device."""
        await self._ensure_session()
        assert self._websession is not None
        url = f"{self.base_url}{ENDPOINT_EMS}"
        try:
            async with self._websession.get(url, auth=self._auth) as response:
                if response.status == 401:
                    raise HomevoltAuthenticationError("Authentication failed")
                response.raise_for_status()
                ems_data = await response.json()
        except HomevoltAuthenticationError:
            raise
        except HomevoltConnectionError:
            raise
        except aiohttp.ClientError as err:
            raise HomevoltConnectionError(f"Failed to connect to device: {err}") from err
        except Exception as err:
            raise HomevoltDataError(f"Failed to parse EMS data: {err}") from err
        _LOGGER.debug("EMS Data: %s", ems_data)
        self._parse_ems_data(ems_data)

    async def fetch_schedule_data(self) -> None:
        """Fetch schedule data from the device."""
        await self._ensure_session()
        assert self._websession is not None
        url = f"{self.base_url}{ENDPOINT_SCHEDULE}"
        try:
            async with self._websession.get(url, auth=self._auth) as response:
                if response.status == 401:
                    raise HomevoltAuthenticationError("Authentication failed")
                response.raise_for_status()
                schedule_data = await response.json()
        except HomevoltAuthenticationError:
            raise
        except HomevoltConnectionError:
            raise
        except aiohttp.ClientError as err:
            raise HomevoltConnectionError(f"Failed to connect to device: {err}") from err
        except Exception as err:
            raise HomevoltDataError(f"Failed to parse schedule data: {err}") from err

        _LOGGER.debug("Schedule Data: %s", schedule_data)
        self._parse_schedule_data(schedule_data)

    async def set_battery_mode(
        self,
        mode: str | None = None,
        setpoint: int | float | None = None,
        max_charge: int | float | None = None,
        max_discharge: int | float | None = None,
        min_soc: int | float | None = None,
        max_soc: int | float | None = None,
        grid_import_limit: int | float | None = None,
        grid_export_limit: int | float | None = None,
    ) -> None:
        """Set battery operational mode and parameters.

        Merges provided parameters with current state to prevent resetting values.

        Args:
            mode: Operational mode string (e.g., 'idle', 'inverter_charge'). If None, auto-detects from parameters.
            setpoint: Power setpoint (W)
            max_charge: Max charging power (W)
            max_discharge: Max discharging power (W)
            min_soc: Minimum state of charge (%)
            max_soc: Maximum state of charge (%)
            grid_import_limit: Optional grid import limit (W)
            grid_export_limit: Optional grid export limit (W)
        """
        await self._ensure_session()
        assert self._websession is not None

        if not self.local_mode_enabled:
            await self.enable_local_mode()

        mode_int: int | None = None
        if mode is not None:
            # Create reverse mapping for validation
            valid_modes = {v: k for k, v in SCHEDULE_TYPE.items()}
            if mode not in valid_modes:
                raise ValueError(
                    f"Invalid mode '{mode}'. Must be one of: {', '.join(valid_modes.keys())}"
                )
            mode_int = valid_modes[mode]

        setpoint_val = int(
            setpoint
            if setpoint is not None
            else (self.schedule["setpoint"] if self.schedule["setpoint"] is not None else 0)
        )
        max_charge_val = int(
            max_charge
            if max_charge is not None
            else (self.schedule["max_charge"] if self.schedule["max_charge"] is not None else 0)
        )
        max_discharge_val = int(
            max_discharge
            if max_discharge is not None
            else (
                self.schedule["max_discharge"] if self.schedule["max_discharge"] is not None else 0
            )
        )
        min_soc_val = int(
            min_soc
            if min_soc is not None
            else (self.schedule["min_soc"] if self.schedule["min_soc"] is not None else 0)
        )
        max_soc_val = int(
            max_soc
            if max_soc is not None
            else (self.schedule["max_soc"] if self.schedule["max_soc"] is not None else 100)
        )

        grid_import_limit_val = (
            int(grid_import_limit)
            if grid_import_limit is not None
            else self.schedule["grid_import_limit"]
        )
        grid_export_limit_val = (
            int(grid_export_limit)
            if grid_export_limit is not None
            else self.schedule["grid_export_limit"]
        )

        if mode_int == 0:  # Idle
            setpoint_val = None
            max_charge_val = None
            max_discharge_val = None
            min_soc_val = None
            max_soc_val = None
        elif mode_int == 1:  # Inverter Charge
            setpoint_val = None
            max_discharge_val = None
        elif mode_int == 2:  # Inverter Discharge
            setpoint_val = None
            max_charge_val = None
        elif mode_int in (3, 4, 5):  # Grid Charge/Discharge modes
            max_charge_val = None
            max_discharge_val = None
            min_soc_val = None
            max_soc_val = None
        elif mode_int == 7:  # Solar Charge
            setpoint_val = None
            max_discharge_val = None
        elif mode_int == 8:  # Solar Charge/Discharge
            min_soc_val = None
            max_soc_val = None
        elif mode_int == 9:  # Full Solar Export
            setpoint_val = None
            max_charge_val = None
            max_discharge_val = None
            min_soc_val = None
            max_soc_val = None
        elif mode_int is None:
            # Auto-detect mode based on provided parameters
            # Check original input parameters (not the merged values)
            if setpoint is not None and max_charge is not None and max_discharge is not None:
                mode_int = 8  # Solar Charge/Discharge
            elif setpoint is not None:
                mode_int = 3  # Grid Charge (default grid mode with setpoint)
            elif max_charge is not None and max_discharge is None:
                mode_int = 1  # Inverter Charge
            elif max_discharge is not None and max_charge is None:
                mode_int = 2  # Inverter Discharge
            else:
                # Fall back to current mode or default to idle
                mode_int = self.schedule["mode"] if self.schedule["mode"] is not None else 0

        cmd_parts = [f"sched_set -m {mode_int}"]

        if setpoint_val is not None:
            cmd_parts.append(f"-s {setpoint_val}")
        if max_charge_val is not None:
            cmd_parts.append(f"-c {max_charge_val}")
        if max_discharge_val is not None:
            cmd_parts.append(f"-d {max_discharge_val}")
        if min_soc_val is not None:
            cmd_parts.append(f"-n {min_soc_val}")
        if max_soc_val is not None:
            cmd_parts.append(f"-x {max_soc_val}")
        if grid_import_limit_val is not None:
            cmd_parts.append(f"-i {int(grid_import_limit_val)}")
        if grid_export_limit_val is not None:
            cmd_parts.append(f"-e {int(grid_export_limit_val)}")

        command = " ".join(cmd_parts)
        _LOGGER.debug("Sending battery mode command: %s", command)

        url = f"{self.base_url}{ENDPOINT_CONSOLE}"
        data = {"command": command}

        try:
            async with self._websession.post(url, json=data, auth=self._auth) as response:
                if response.status == 401:
                    raise HomevoltAuthenticationError("Authentication failed")
                response.raise_for_status()
                _LOGGER.debug("Battery mode set successfully")
        except HomevoltAuthenticationError:
            raise
        except aiohttp.ClientError as err:
            raise HomevoltConnectionError(f"Failed to set battery mode: {err}") from err

        self.schedule["mode"] = mode_int
        self.schedule["setpoint"] = setpoint_val
        self.schedule["max_charge"] = max_charge_val
        self.schedule["max_discharge"] = max_discharge_val
        self.schedule["min_soc"] = min_soc_val
        self.schedule["max_soc"] = max_soc_val
        self.schedule["grid_import_limit"] = grid_import_limit_val
        self.schedule["grid_export_limit"] = grid_export_limit_val

    async def enable_local_mode(self) -> None:
        """Enable local mode for battery control."""
        await self._set_local_mode(1)

    async def disable_local_mode(self) -> None:
        """Disable local mode for battery control."""
        await self._set_local_mode(0)

    async def _set_local_mode(self, value: int) -> None:
        """Set local mode parameter.

        Args:
            value: 1 to enable, 0 to disable
        """
        await self._ensure_session()
        assert self._websession is not None

        url = f"{self.base_url}{ENDPOINT_PARAMS}"
        data = {"settings_local": value}

        try:
            async with self._websession.post(url, json=data, auth=self._auth) as response:
                if response.status == 401:
                    raise HomevoltAuthenticationError("Authentication failed")
                response.raise_for_status()
                _LOGGER.debug("Local mode set to %s", value)
        except HomevoltAuthenticationError:
            raise
        except aiohttp.ClientError as err:
            raise HomevoltConnectionError(f"Failed to set local mode: {err}") from err

    def _parse_ems_data(self, ems_data: dict[str, Any]) -> None:
        """Parse EMS JSON response."""
        if not ems_data.get("ems") or not ems_data["ems"]:
            raise HomevoltDataError("No EMS data found in response")

        device_id = str(ems_data["ems"][0]["ecu_id"])
        self.unique_id = device_id
        ems_device_id = f"ems_{device_id}"

        self.device_metadata = {
            ems_device_id: DeviceMetadata(name=f"EMS {device_id}", model="EMS"),
        }

        self.sensors = {}

        ems = ems_data["ems"][0]
        self.sensors.update(
            {
                "L1 Voltage": Sensor(
                    value=ems["ems_voltage"]["l1"] / 10,
                    type="l1_voltage",
                    device_identifier=ems_device_id,
                ),
                "L2 Voltage": Sensor(
                    value=ems["ems_voltage"]["l2"] / 10,
                    type="l2_voltage",
                    device_identifier=ems_device_id,
                ),
                "L3 Voltage": Sensor(
                    value=ems["ems_voltage"]["l3"] / 10,
                    type="l3_voltage",
                    device_identifier=ems_device_id,
                ),
                "L1_L2 Voltage": Sensor(
                    value=ems["ems_voltage"]["l1_l2"] / 10,
                    type="l1_l2_voltage",
                    device_identifier=ems_device_id,
                ),
                "L2_L3 Voltage": Sensor(
                    value=ems["ems_voltage"]["l2_l3"] / 10,
                    type="l2_l3_voltage",
                    device_identifier=ems_device_id,
                ),
                "L3_L1 Voltage": Sensor(
                    value=ems["ems_voltage"]["l3_l1"] / 10,
                    type="l3_l1_voltage",
                    device_identifier=ems_device_id,
                ),
                "L1 Current": Sensor(
                    value=ems["ems_current"]["l1"],
                    type="l1_current",
                    device_identifier=ems_device_id,
                ),
                "L2 Current": Sensor(
                    value=ems["ems_current"]["l2"],
                    type="l2_current",
                    device_identifier=ems_device_id,
                ),
                "L3 Current": Sensor(
                    value=ems["ems_current"]["l3"],
                    type="l3_current",
                    device_identifier=ems_device_id,
                ),
                "System Temperature": Sensor(
                    value=ems["ems_data"]["sys_temp"] / 10.0,
                    type="system_temperature",
                    device_identifier=ems_device_id,
                ),
                "Energy imported": Sensor(
                    value=ems["ems_aggregate"]["imported_kwh"],
                    type="energy_imported",
                    device_identifier=ems_device_id,
                ),
                "Energy exported": Sensor(
                    value=ems["ems_aggregate"]["exported_kwh"],
                    type="energy_exported",
                    device_identifier=ems_device_id,
                ),
                "Available Charging Power": Sensor(
                    value=ems["ems_prediction"]["avail_ch_pwr"],
                    type="available_charging_power",
                    device_identifier=ems_device_id,
                ),
                "Available Discharge Power": Sensor(
                    value=ems["ems_prediction"]["avail_di_pwr"],
                    type="available_discharge_power",
                    device_identifier=ems_device_id,
                ),
                "Available Charging Energy": Sensor(
                    value=ems["ems_prediction"]["avail_ch_energy"],
                    type="available_charging_energy",
                    device_identifier=ems_device_id,
                ),
                "Available Discharge Energy": Sensor(
                    value=ems["ems_prediction"]["avail_di_energy"],
                    type="available_discharge_energy",
                    device_identifier=ems_device_id,
                ),
                "Power": Sensor(
                    value=ems["ems_data"]["power"],
                    type="power",
                    device_identifier=ems_device_id,
                ),
                "Frequency": Sensor(
                    value=ems["ems_data"]["frequency"],
                    type="frequency",
                    device_identifier=ems_device_id,
                ),
                "State of Charge": Sensor(
                    value=ems["ems_data"]["soc_avg"] / 100,
                    type="state_of_charge",
                    device_identifier=ems_device_id,
                ),
            }
        )

        for bat_id, battery in enumerate(ems.get("bms_data", [])):
            battery_device_id = f"battery_{bat_id}"
            self.device_metadata[battery_device_id] = DeviceMetadata(
                name=f"Battery blade {bat_id}",
                model="Battery blade",
            )
            if "soc" in battery:
                self.sensors[f"Homevolt battery {bat_id}"] = Sensor(
                    value=battery["soc"] / 100,
                    type="state_of_charge",
                    device_identifier=battery_device_id,
                )
            if "tmin" in battery:
                self.sensors[f"Homevolt battery {bat_id} tmin"] = Sensor(
                    value=battery["tmin"] / 10,
                    type="tmin",
                    device_identifier=battery_device_id,
                )
            if "tmax" in battery:
                self.sensors[f"Homevolt battery {bat_id} tmax"] = Sensor(
                    value=battery["tmax"] / 10,
                    type="tmax",
                    device_identifier=battery_device_id,
                )
            if "cycle_count" in battery:
                self.sensors[f"Homevolt battery {bat_id} charge cycles"] = Sensor(
                    value=battery["cycle_count"],
                    type="charge_cycles",
                    device_identifier=battery_device_id,
                )
            if "voltage" in battery:
                self.sensors[f"Homevolt battery {bat_id} voltage"] = Sensor(
                    value=battery["voltage"] / 100,
                    type="voltage",
                    device_identifier=battery_device_id,
                )
            if "current" in battery:
                self.sensors[f"Homevolt battery {bat_id} current"] = Sensor(
                    value=battery["current"],
                    type="current",
                    device_identifier=battery_device_id,
                )
            if "power" in battery:
                self.sensors[f"Homevolt battery {bat_id} power"] = Sensor(
                    value=battery["power"],
                    type="power",
                    device_identifier=battery_device_id,
                )
            if "soh" in battery:
                self.sensors[f"Homevolt battery {bat_id} soh"] = Sensor(
                    value=battery["soh"] / 100,
                    type="soh",
                    device_identifier=battery_device_id,
                )

        for sensor in ems_data.get("sensors", []):
            if not sensor.get("available"):
                continue

            if sensor_type := sensor.get("sensor_type"):
                if sensor_type == "ems":
                    continue
                function = sensor.get("function", "")

            elif sensor_type := sensor.get("type"):
                function = ""
            else:
                continue

            sensor_device_id = sensor.get("euid")

            if not sensor_device_id:
                continue
            self.device_metadata[sensor_device_id] = DeviceMetadata(
                name=f"{str(sensor_type).title()} {function.title()} Sensor".replace(
                    "  ", " "
                ).replace("_", " "),
                model=sensor_type,
            )

            total_power = sum(phase["power"] for phase in sensor.get("phase", []))

            self.sensors[f"Power {sensor_type}"] = Sensor(
                value=total_power,
                type="power",
                device_identifier=sensor_device_id,
            )
            self.sensors[f"Energy imported {sensor_type}"] = Sensor(
                value=sensor.get("energy_imported", 0),
                type="energy_imported",
                device_identifier=sensor_device_id,
            )
            self.sensors[f"Energy exported {sensor_type}"] = Sensor(
                value=sensor.get("energy_exported", 0),
                type="energy_exported",
                device_identifier=sensor_device_id,
            )
            self.sensors[f"RSSI {sensor_type}"] = Sensor(
                value=sensor.get("rssi"),
                type="rssi",
                device_identifier=sensor_device_id,
            )
            self.sensors[f"Average RSSI {sensor_type}"] = Sensor(
                value=sensor.get("average_rssi"),
                type="average_rssi",
                device_identifier=sensor_device_id,
            )

            for phase_name, phase in zip(["L1", "L2", "L3"], sensor.get("phase", [])):
                phase_lower = phase_name.lower()
                self.sensors[f"{phase_name} Voltage {sensor_type}"] = Sensor(
                    value=phase.get("voltage"),
                    type=f"{phase_lower}_voltage",
                    device_identifier=sensor_device_id,
                )
                self.sensors[f"{phase_name} Current {sensor_type}"] = Sensor(
                    value=phase.get("amp"),
                    type=f"{phase_lower}_current",
                    device_identifier=sensor_device_id,
                )
                self.sensors[f"{phase_name} Power {sensor_type}"] = Sensor(
                    value=phase.get("power"),
                    type=f"{phase_lower}_power",
                    device_identifier=sensor_device_id,
                )

    def _parse_schedule_data(self, schedule_data: dict[str, Any]) -> None:
        """Parse schedule JSON response and track battery control state."""
        self.current_schedule = schedule_data

        if not self.unique_id:
            return

        ems_device_id = f"ems_{self.unique_id}"

        self.sensors["Schedule id"] = Sensor(
            value=schedule_data.get("schedule_id"),
            type="schedule_id",
            device_identifier=ems_device_id,
        )

        schedule = (
            schedule_data.get("schedule", [{}])[0]
            if schedule_data.get("schedule")
            else {"type": -1, "params": {}}
        )

        params = schedule.get("params", {})

        # Track current battery control state
        self.schedule["mode"] = schedule.get("type")
        self.schedule["setpoint"] = params.get("setpoint")
        self.schedule["max_charge"] = schedule.get("max_charge")
        self.schedule["max_discharge"] = schedule.get("max_discharge")
        self.schedule["min_soc"] = params.get("min_soc") or params.get("min")
        self.schedule["max_soc"] = params.get("max_soc") or params.get("max")
        self.schedule["grid_import_limit"] = params.get("grid_import_limit")
        self.schedule["grid_export_limit"] = params.get("grid_export_limit")
        self.schedule["threshold_high"] = params.get("threshold_high")
        self.schedule["threshold_low"] = params.get("threshold_low")
        self.schedule["freq_reg_droop_up"] = params.get("freq_reg_droop_up")
        self.schedule["freq_reg_droop_down"] = params.get("freq_reg_droop_down")

        self.sensors["Schedule Type"] = Sensor(
            value=SCHEDULE_TYPE.get(schedule.get("type", -1)),
            type="schedule_type",
            device_identifier=ems_device_id,
        )
        self.sensors["Schedule Power Setpoint"] = Sensor(
            value=self.schedule["setpoint"],
            type="schedule_power_setpoint",
            device_identifier=ems_device_id,
        )
        self.sensors["Schedule Max Power"] = Sensor(
            value=self.schedule["max_charge"],
            type="schedule_max_power",
            device_identifier=ems_device_id,
        )
        self.sensors["Schedule Max Discharge"] = Sensor(
            value=self.schedule["max_discharge"],
            type="schedule_max_discharge",
            device_identifier=ems_device_id,
        )
