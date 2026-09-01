# pyHomevolt

Python library for Homevolt EMS devices.

Get real-time data from your Homevolt Energy Management System, including:

- Voltage, current, and power measurements
- Battery state of charge and temperature
- Grid, solar, and load sensor data
- Schedule information

Control your battery with:

- Immediate battery control (charge, discharge, idle)
- Scheduled battery operations
- Local mode management
- Parameter configuration

## Install

```bash
pip install homevolt
```

## Development

This repository supports a standard `uv` development workflow.

```bash
uv sync --dev
```

That creates a local environment with the package and development tools installed.

Common commands:

```bash
uv run pre-commit run --all-files
uv run ruff check .
uv run mypy homevolt
uv run pytest
```

## Example

```python
import asyncio
import aiohttp
import homevolt


async def main():
    async with aiohttp.ClientSession() as session:
        homevolt_connection = homevolt.Homevolt(
            host="192.168.1.100",
            password="optional_password",
            websession=session,
        )
        await homevolt_connection.update_info()

        print(f"Device ID: {homevolt_connection.unique_id}")
        print(f"Current Power: {homevolt_connection.sensors['Power'].value} W")
        print(f"Battery SOC: {homevolt_connection.sensors['Battery State of Charge'].value * 100}%")

        # Access all sensors
        for sensor_name, sensor in homevolt_connection.sensors.items():
            print(f"{sensor_name}: {sensor.value} ({sensor.type.value})")

        # Access device metadata
        for device_id, metadata in homevolt_connection.device_metadata.items():
            print(f"{device_id}: {metadata.name} ({metadata.model})")

        await homevolt_connection.close_connection()


if __name__ == "__main__":
    asyncio.run(main())
```

## Example with context manager

```python
import asyncio
import aiohttp
import homevolt


async def main():
    async with aiohttp.ClientSession() as session:
        async with homevolt.Homevolt(
            host="192.168.1.100",
            password="optional_password",
            websession=session,
        ) as homevolt_connection:
            await homevolt_connection.update_info()

            print(f"Device ID: {homevolt_connection.unique_id}")
            print(f"Available sensors: {list(homevolt_connection.sensors.keys())}")


if __name__ == "__main__":
    asyncio.run(main())
```

## Battery Control Example

```python
import asyncio
import aiohttp
import homevolt


async def main():
    async with aiohttp.ClientSession() as session:
        async with homevolt.Homevolt(
            host="192.168.1.100",
            password="optional_password",
            websession=session,
        ) as homevolt_connection:
            await homevolt_connection.update_info()

            # Enable local mode to prevent remote schedule overrides
            await homevolt_connection.enable_local_mode()

            # Replace the current schedule with immediate inverter-charge control.
            await homevolt_connection.set_battery_mode("inverter_charge")

            # Refresh once so the new Manual Schedule entry can be updated safely.
            await homevolt_connection.fetch_schedule_data()
            await homevolt_connection.set_battery_parameters(
                max_charge=3000,
                min_soc=20,
                max_soc=90,
            )


if __name__ == "__main__":
    asyncio.run(main())
```

## Battery Control Modes

The following mode strings are available for battery control:

- `idle`: Battery standby (mode 0)
- `inverter_charge`: Charge via the inverter from grid/solar (mode 1)
- `inverter_discharge`: Discharge via the inverter to home/grid (mode 2)
- `frequency_reserve`: Frequency regulation service mode (mode 6)
- `solar_charge`: Charge from solar production only (mode 7)

Other firmware schedule types are intentionally rejected because current firmware
does not create a matching manual schedule for them.

Battery writes require local mode to be enabled first. `set_battery_mode()` uses the
device's `sched_set` command, so it replaces the complete current schedule with one
immediate `Manual Schedule` entry. `set_battery_parameters()` only accepts that
single manual entry and refuses writes that would discard unsupported parameters.

## API Reference

### Homevolt

Main class for connecting to a Homevolt device.

#### `Homevolt(host, password=None, websession=None)`

Initialize a Homevolt connection.

- `host` (str): Hostname or IP address of the Homevolt device
- `password` (str, optional): Password for authentication
- `websession` (aiohttp.ClientSession, optional): HTTP session. If not provided, one will be created.

#### Properties

- `unique_id` (str | None): Device unique identifier
- `sensors` (dict[str, Sensor]): Dictionary of sensor readings
- `device_metadata` (dict[str, DeviceMetadata]): Dictionary of device metadata
- `current_schedule` (dict | None): Current schedule information
- `battery_parameters_writable` (bool): Whether the current manual entry supports partial writes

#### Methods

- `async update_info()`: Fetch and update all device information
- `async fetch_ems_data()`: Fetch EMS data specifically
- `async fetch_schedule_data()`: Fetch schedule data specifically
- `async close_connection()`: Close the connection and clean up resources

#### Battery Control Methods

- `async set_battery_mode(mode)`: Replace the schedule with an immediate control mode
- `async set_battery_parameters(**kwargs)`: Update supported values on one manual entry

**Configuration:**

- `async enable_local_mode()`: Enable local mode (prevents remote overrides)
- `async disable_local_mode()`: Disable local mode (allows remote overrides)

### Data Models

#### Sensor

- `value` (float | str | None): Sensor value
- `type` (SensorType): Type of sensor
- `device_identifier` (str): Device identifier for grouping sensors

#### DeviceMetadata

- `name` (str): Device name
- `model` (str): Device model

#### SensorType

Enumeration of sensor types:

- `VOLTAGE`
- `CURRENT`
- `POWER`
- `ENERGY_INCREASING`
- `ENERGY_TOTAL`
- `FREQUENCY`
- `TEMPERATURE`
- `PERCENTAGE`
- `SIGNAL_STRENGTH`
- `COUNT`
- `TEXT`
- `SCHEDULE_TYPE`

### Exceptions

- `HomevoltError`: Base exception for all Homevolt errors
- `HomevoltConnectionError`: Connection or network errors
- `HomevoltAuthenticationError`: Authentication failures
- `HomevoltDataError`: Data parsing errors

## License

GPL-3.0
