# pyHomevolt

Python library for Homevolt EMS devices.

Get real-time data from your Homevolt Energy Management System, including:
- Voltage, current, and power measurements
- Battery state of charge and temperature
- Grid, solar, and load sensor data
- Schedule information

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

- `HomevoltException`: Base exception for all Homevolt errors
- `HomevoltConnectionError`: Connection or network errors
- `HomevoltAuthenticationError`: Authentication failures
- `HomevoltDataError`: Data parsing errors

## License

GPL-3.0

