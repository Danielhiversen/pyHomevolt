"""Main Homevolt class for connecting to EMS devices."""

from __future__ import annotations

import asyncio
import logging
import types
from typing import Any

import aiohttp

from .const import (
    DEFAULT_CONNECT_TIMEOUT,
    DEFAULT_READ_TIMEOUT,
    ENDPOINT_EMS,
    ENDPOINT_PARAMS,
    ENDPOINT_SCHEDULE,
    RETRY_BACKOFF_FACTOR,
    RETRY_COUNT,
    RETRY_STATUS_CODES,
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
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        read_timeout: float = DEFAULT_READ_TIMEOUT,
    ) -> None:
        """Initialize the Homevolt connection.

        Args:
            host: Hostname or IP address of the Homevolt device
            password: Optional password for authentication
            websession: Optional aiohttp ClientSession. If not provided, one will be created.
            connect_timeout: Seconds to wait for establishing a connection.
            read_timeout: Seconds to wait for reading response data.
        """
        if not host.startswith("http"):
            host = f"http://{host}"
        self.base_url = host
        self._password = password
        self._websession = websession
        self._own_session = websession is None
        self._auth = aiohttp.BasicAuth("admin", password) if password else None
        self._timeout = aiohttp.ClientTimeout(
            total=connect_timeout + read_timeout,
            connect=connect_timeout,
            sock_read=read_timeout,
        )

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
        return bool(self.current_schedule.get("local_mode", False))

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

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: types.TracebackType | None,
    ) -> None:
        """Async context manager exit."""
        await self.close_connection()

    async def _get_json(self, url: str) -> Any:
        """GET a URL with retries and return the parsed JSON body.

        Retries on timeouts, client errors, and transient HTTP status codes
        (502/503/504) with exponential backoff. Never retries 401.
        """
        await self._ensure_session()
        assert self._websession is not None
        last_err: Exception | None = None
        for attempt in range(RETRY_COUNT + 1):
            try:
                async with self._websession.get(
                    url, auth=self._auth, timeout=self._timeout
                ) as response:
                    if response.status == 401:
                        raise HomevoltAuthenticationError("Authentication failed")
                    response.raise_for_status()
                    try:
                        return await response.json()
                    except (aiohttp.ContentTypeError, ValueError) as err:
                        raise HomevoltDataError(f"Failed to parse data: {err}") from err
            except HomevoltAuthenticationError:
                raise
            except HomevoltDataError:
                raise
            except (TimeoutError, aiohttp.ClientError) as err:
                if (
                    isinstance(err, aiohttp.ClientResponseError)
                    and err.status not in RETRY_STATUS_CODES
                ):
                    raise HomevoltConnectionError(f"Failed to connect to device: {err}") from err
                last_err = err
                if attempt < RETRY_COUNT:
                    delay = RETRY_BACKOFF_FACTOR * (2**attempt)
                    _LOGGER.debug(
                        "Request to %s failed (%s), retrying in %.1fs (attempt %d/%d)",
                        url,
                        err,
                        delay,
                        attempt + 1,
                        RETRY_COUNT,
                    )
                    await asyncio.sleep(delay)
        raise HomevoltConnectionError(f"Failed to connect to device: {last_err}") from last_err

    async def _post(self, url: str, data: dict[str, str]) -> None:
        """POST data to a URL with retries.

        Retries on timeouts, client errors, and transient HTTP status codes
        (502/503/504) with exponential backoff. Never retries 401.
        """
        await self._ensure_session()
        assert self._websession is not None
        last_err: Exception | None = None
        for attempt in range(RETRY_COUNT + 1):
            try:
                async with self._websession.post(
                    url, data=data, auth=self._auth, timeout=self._timeout
                ) as response:
                    if response.status == 401:
                        raise HomevoltAuthenticationError("Authentication failed")
                    response.raise_for_status()
                    return
            except HomevoltAuthenticationError:
                raise
            except (TimeoutError, aiohttp.ClientError) as err:
                if (
                    isinstance(err, aiohttp.ClientResponseError)
                    and err.status not in RETRY_STATUS_CODES
                ):
                    raise HomevoltConnectionError(f"Failed to connect to device: {err}") from err
                last_err = err
                if attempt < RETRY_COUNT:
                    delay = RETRY_BACKOFF_FACTOR * (2**attempt)
                    _LOGGER.debug(
                        "Request to %s failed (%s), retrying in %.1fs (attempt %d/%d)",
                        url,
                        err,
                        delay,
                        attempt + 1,
                        RETRY_COUNT,
                    )
                    await asyncio.sleep(delay)
        raise HomevoltConnectionError(f"Failed to connect to device: {last_err}") from last_err

    async def fetch_ems_data(self) -> None:
        """Fetch EMS data from the device."""
        url = f"{self.base_url}{ENDPOINT_EMS}"
        ems_data = await self._get_json(url)
        _LOGGER.debug("EMS Data: %s", ems_data)
        self._parse_ems_data(ems_data)

    async def fetch_schedule_data(self) -> None:
        """Fetch schedule data from the device."""
        url = f"{self.base_url}{ENDPOINT_SCHEDULE}"
        schedule_data = await self._get_json(url)
        _LOGGER.debug("Schedule Data: %s", schedule_data)
        self._parse_schedule_data(schedule_data)

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
        data = {
            "k": "settings_local",
            "v": "true" if value else "false",
            "store": "0",
        }

        try:
            await self._post(url, data)
        except HomevoltConnectionError as err:
            raise HomevoltConnectionError(f"Failed to set local mode: {err}") from err
        _LOGGER.debug("Local mode set to %s", value)

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
