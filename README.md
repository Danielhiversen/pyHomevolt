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
pip install pyHomevolt
```

## Example

```python
import asyncio
import aiohttp
import homevolt


async def main():
    async with aiohttp.ClientSession() as session:
        homevolt_connection = homevolt.Homevolt(
            ip_address="192.168.1.100",
            password="optional_password",
            websession=session,
        )
        await homevolt_connection.update_info()

        device = homevolt_connection.get_device()
        print(f"Device ID: {device.device_id}")
        print(f"Current Power: {device.sensors['Power'].value} W")
        print(f"Battery SOC: {device.sensors['Battery State of Charge'].value * 100}%")

        # Access all sensors
        for sensor_name, sensor in device.sensors.items():
            print(f"{sensor_name}: {sensor.value} ({sensor.type.value})")

        # Access device metadata
        for device_id, metadata in device.device_metadata.items():
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
            ip_address="192.168.1.100",
            password="optional_password",
            websession=session,
        ) as homevolt_connection:
            await homevolt_connection.update_info()

            device = homevolt_connection.get_device()
            await device.update_info()  # Refresh data

            print(f"Device ID: {device.device_id}")
            print(f"Available sensors: {list(device.sensors.keys())}")


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
            ip_address="192.168.1.100",
            password="optional_password",
            websession=session,
        ) as homevolt_connection:
            await homevolt_connection.update_info()
            device = homevolt_connection.get_device()

            # Enable local mode to prevent remote schedule overrides
            await device.enable_local_mode()

            # Charge battery immediately (up to 3000W, stop at 90% SOC)
            await device.charge_battery(max_power=3000, max_soc=90)

            # Or use the full control method
            await device.set_battery_mode(
                mode=1,  # Inverter Charge
                max_charge=3000,
                max_soc=90,
            )

            # Schedule night charging (11 PM - 7 AM)
            from datetime import datetime, timedelta
            tonight = datetime.now().replace(hour=23, minute=0, second=0)
            tomorrow = (tonight + timedelta(days=1)).replace(hour=7, minute=0, second=0)

            await device.add_schedule(
                mode=1,  # Inverter Charge
                from_time=tonight.isoformat(),
                to_time=tomorrow.isoformat(),
                max_charge=3000,
                max_soc=80,
            )

            # Set battery to idle
            await device.set_battery_idle()

            # Discharge during peak hours
            await device.discharge_battery(max_power=2500, min_soc=30)


if __name__ == "__main__":
    asyncio.run(main())
```

## Battery Control Modes

The following modes are available for battery control:

- `0`: Idle - Battery standby (no charge/discharge)
- `1`: Inverter Charge - Charge battery via inverter from grid/solar
- `2`: Inverter Discharge - Discharge battery via inverter to home/grid
- `3`: Grid Charge - Charge from grid with power setpoint
- `4`: Grid Discharge - Discharge to grid with power setpoint
- `5`: Grid Charge/Discharge - Bidirectional grid control
- `6`: Frequency Reserve - Frequency regulation service mode
- `7`: Solar Charge - Charge from solar production only
- `8`: Solar Charge/Discharge - Solar-based grid management
- `9`: Full Solar Export - Export all solar production

## API Reference

### Homevolt

Main class for connecting to a Homevolt device.

#### `Homevolt(ip_address, password=None, websession=None)`

Initialize a Homevolt connection.

- `ip_address` (str): IP address of the Homevolt device
- `password` (str, optional): Password for authentication
- `websession` (aiohttp.ClientSession, optional): HTTP session. If not provided, one will be created.

#### Methods

- `async update_info()`: Fetch and update device information
- `get_device()`: Get the Device object
- `async close_connection()`: Close the connection and clean up resources

### Device

Represents a Homevolt EMS device.

#### Properties

- `device_id` (str): Device identifier
- `sensors` (dict[str, Sensor]): Dictionary of sensor readings
- `device_metadata` (dict[str, DeviceMetadata]): Dictionary of device metadata
- `current_schedule` (dict): Current schedule information

#### Methods

- `async update_info()`: Fetch latest EMS and schedule data
- `async fetch_ems_data()`: Fetch EMS data specifically
- `async fetch_schedule_data()`: Fetch schedule data specifically

#### Battery Control Methods

**Immediate Control:**
- `async set_battery_mode(mode, **kwargs)`: Set immediate battery control mode
- `async charge_battery(**kwargs)`: Charge battery using inverter
- `async discharge_battery(**kwargs)`: Discharge battery using inverter
- `async set_battery_idle(**kwargs)`: Set battery to idle mode
- `async charge_from_grid(**kwargs)`: Charge from grid with power setpoint
- `async discharge_to_grid(**kwargs)`: Discharge to grid with power setpoint
- `async charge_from_solar(**kwargs)`: Charge from solar only

**Scheduled Control:**
- `async add_schedule(mode, **kwargs)`: Add a scheduled battery control entry
- `async delete_schedule(schedule_id)`: Delete a schedule by ID
- `async clear_all_schedules()`: Clear all schedules

**Configuration:**
- `async enable_local_mode()`: Enable local mode (prevents remote overrides)
- `async disable_local_mode()`: Disable local mode (allows remote overrides)
- `async set_parameter(key, value)`: Set a device parameter
- `async get_parameter(key)`: Get a device parameter value

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

