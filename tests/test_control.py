"""Tests for Homevolt battery control."""

from __future__ import annotations

import asyncio
import types
from collections.abc import Mapping
from typing import Any
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

import homevolt
from homevolt import (
    Homevolt,
    HomevoltCommandOutcomeUnknownError,
    HomevoltCommandVerificationError,
    HomevoltConnectionError,
    HomevoltDataError,
)


def test_command_outcome_unknown_error_is_public() -> None:
    """Expose ambiguous mutation outcomes to library consumers."""
    assert hasattr(homevolt, "HomevoltCommandOutcomeUnknownError")


class FakeResponse:
    """Minimal aiohttp response context manager."""

    def __init__(self, status: int = 200, text: str = "OK") -> None:
        self.status = status
        self._text = text

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object | None,
    ) -> None:
        return None

    def raise_for_status(self) -> None:
        """Raise for non-success responses."""
        if self.status >= 400:
            raise aiohttp.ClientResponseError(
                request_info=types.SimpleNamespace(real_url="http://homevolt.local"),  # type: ignore[arg-type]
                history=(),
                status=self.status,
            )

    async def text(self) -> str:
        """Return the response body."""
        return self._text


class FakeSession:
    """Capture POST requests made by Homevolt."""

    def __init__(self, response: FakeResponse | None = None) -> None:
        self.response = response or FakeResponse()
        self.posts: list[tuple[str, Any, aiohttp.BasicAuth | None, aiohttp.ClientTimeout]] = []

    def post(
        self,
        url: str,
        *,
        data: Any,
        auth: aiohttp.BasicAuth | None,
        timeout: aiohttp.ClientTimeout,
    ) -> FakeResponse:
        """Capture a POST and return its response context manager."""
        self.posts.append((url, data, auth, timeout))
        return self.response


class TimeoutSession(FakeSession):
    """Raise a timeout for every mutation request."""

    def __init__(self) -> None:
        super().__init__()
        self.attempts = 0

    def post(
        self,
        url: str,
        *,
        data: Any,
        auth: aiohttp.BasicAuth | None,
        timeout: aiohttp.ClientTimeout,
    ) -> FakeResponse:
        """Record one ambiguous mutation attempt."""
        self.attempts += 1
        raise TimeoutError


def test_build_sched_set_command_uses_documented_flags() -> None:
    """Build a command using the flags documented by Tibber."""
    client = Homevolt("homevolt.local")

    command = client._build_sched_set_command(
        mode_int=8,
        setpoint=100,
        max_charge=200,
        max_discharge=300,
        min_soc=20,
        max_soc=90,
        grid_import_limit=400,
        grid_export_limit=500,
    )

    assert command == ("sched_set 8 -s 100 -c 200 -d 300 --min 20 --max 90 -l 400 -x 500")


def test_build_sched_set_command_omits_unset_parameters() -> None:
    """Do not invent limits or setpoints that the caller did not provide."""
    client = Homevolt("homevolt.local")

    command = client._build_sched_set_command(
        mode_int=0,
        setpoint=None,
        max_charge=None,
        max_discharge=None,
        min_soc=None,
        max_soc=None,
        grid_import_limit=None,
        grid_export_limit=None,
    )

    assert command == "sched_set 0"


def test_parse_schedule_uses_documented_response_fields() -> None:
    """Parse schedule limits from their documented JSON locations."""
    client = Homevolt("homevolt.local")
    client.unique_id = "1234"

    client._parse_schedule_data(
        {
            "local_mode": True,
            "schedule_id": "Manual Schedule",
            "schedule": [
                {
                    "id": 1,
                    "min": 20,
                    "max": 90,
                    "type": 8,
                    "params": {
                        "setpoint": 100,
                        "max_charge": 200,
                        "max_discharge": 300,
                        "import_limit": 400,
                        "export_limit": 500,
                    },
                }
            ],
        }
    )

    assert client.schedule == {
        "mode": 8,
        "setpoint": 100,
        "max_charge": 200,
        "max_discharge": 300,
        "min_soc": 20,
        "max_soc": 90,
        "grid_import_limit": 400,
        "grid_export_limit": 500,
        "threshold_high": None,
        "threshold_low": None,
        "freq_reg_droop_up": None,
        "freq_reg_droop_down": None,
    }


def test_parse_schedule_populates_control_state_without_ems_data() -> None:
    """Schedule control state must not depend on an earlier EMS fetch."""
    client = Homevolt("homevolt.local")

    client._parse_schedule_data(
        {
            "local_mode": True,
            "schedule_id": "Manual Schedule",
            "schedule": [
                {
                    "type": 5,
                    "params": {
                        "setpoint": 100,
                        "max_charge": 200,
                        "import_limit": 400,
                    },
                }
            ],
        }
    )

    assert client.schedule["mode"] == 5
    assert client.schedule["setpoint"] == 100
    assert client.schedule["max_charge"] == 200
    assert client.schedule["grid_import_limit"] == 400


def test_parse_schedule_normalizes_numeric_grid_limits() -> None:
    """Public grid-limit accessors must return integers for numeric JSON values."""
    client = Homevolt("homevolt.local")

    client._parse_schedule_data(
        {
            "schedule": [
                {
                    "type": 5,
                    "params": {"import_limit": "400", "export_limit": 500.0},
                }
            ]
        }
    )

    assert client.schedule_grid_import_limit == 400
    assert client.schedule_grid_export_limit == 500
    assert isinstance(client.schedule_grid_import_limit, int)
    assert isinstance(client.schedule_grid_export_limit, int)


@pytest.mark.parametrize(
    ("import_limit", "export_limit"),
    [("unknown", []), (True, False), (500.5, 600.5)],
)
def test_parse_schedule_discards_invalid_grid_limits(
    import_limit: Any,
    export_limit: Any,
) -> None:
    """Unexpected grid-limit formats must not escape through typed accessors."""
    client = Homevolt("homevolt.local")

    client._parse_schedule_data(
        {
            "schedule": [
                {
                    "type": 5,
                    "params": {
                        "import_limit": import_limit,
                        "export_limit": export_limit,
                    },
                }
            ]
        }
    )

    assert client.schedule_grid_import_limit is None
    assert client.schedule_grid_export_limit is None


def test_parse_schedule_normalizes_numeric_control_values() -> None:
    """Numeric device values must satisfy the integer schedule accessor contract."""
    client = Homevolt("homevolt.local")
    client.unique_id = "1234"

    client._parse_schedule_data(
        {
            "schedule": [
                {
                    "type": "5",
                    "min": "20",
                    "max": 90.0,
                    "params": {
                        "setpoint": "100",
                        "max_charge": 200.0,
                        "max_discharge": "300",
                    },
                }
            ]
        }
    )

    assert client.schedule_mode == 5
    assert client.schedule_setpoint == 100
    assert client.schedule_max_charge == 200
    assert client.schedule_max_discharge == 300
    assert client.schedule_min_soc == 20
    assert client.schedule_max_soc == 90
    assert client.sensors["Schedule Type"].value == "grid_charge_discharge"


def test_parse_schedule_discards_invalid_control_values() -> None:
    """Malformed device values must not escape through integer accessors."""
    client = Homevolt("homevolt.local")
    client.unique_id = "1234"

    client._parse_schedule_data(
        {
            "schedule": [
                {
                    "type": True,
                    "min": [],
                    "max": {},
                    "params": {
                        "setpoint": False,
                        "max_charge": 200.5,
                        "max_discharge": "unknown",
                    },
                }
            ]
        }
    )

    assert client.schedule_mode is None
    assert client.schedule_setpoint is None
    assert client.schedule_max_charge is None
    assert client.schedule_max_discharge is None
    assert client.schedule_min_soc is None
    assert client.schedule_max_soc is None
    assert client.sensors["Schedule Type"].value is None


def test_set_battery_parameters_requires_local_mode() -> None:
    """A parameter write must not silently take persistent local control."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {"local_mode": False, "schedule": []}
    client.schedule.update({"mode": 5, "setpoint": 0})
    client.enable_local_mode = AsyncMock()
    client._post_console_command = AsyncMock()

    with pytest.raises(HomevoltDataError, match="Local mode"):
        asyncio.run(client.set_battery_parameters(max_charge=1000))

    client.enable_local_mode.assert_not_awaited()
    client._post_console_command.assert_not_awaited()


def test_set_battery_parameters_requires_one_manual_entry() -> None:
    """Do not replace a multi-entry schedule from an individual number write."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {
        "local_mode": True,
        "schedule_id": "Manual Schedule",
        "schedule": [{}, {}],
    }
    client.schedule.update({"mode": 5, "setpoint": 0})
    client._post_console_command = AsyncMock()

    with pytest.raises(HomevoltDataError, match="exactly one Manual Schedule entry"):
        asyncio.run(client.set_battery_parameters(max_charge=1000))

    client._post_console_command.assert_not_awaited()


def test_set_battery_parameters_preserves_compatible_grid_limit() -> None:
    """Changing one grid limit retains the other verified mode-six limit."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {
        "local_mode": True,
        "schedule_id": "Manual Schedule",
        "schedule": [
            {
                "type": 6,
                "params": {
                    "import_limit": 400,
                    "export_limit": 500,
                    "offline": False,
                },
            }
        ],
    }
    client.schedule.update(
        {
            "mode": 6,
            "grid_import_limit": 400,
            "grid_export_limit": 500,
        }
    )
    client._post_console_command = AsyncMock(return_value="Command executed successfully")

    async def read_updated_schedule() -> None:
        client._parse_schedule_data(
            {
                "local_mode": True,
                "schedule_id": "Manual Schedule",
                "schedule": [
                    {
                        "type": 6,
                        "params": {
                            "import_limit": 450,
                            "export_limit": 500,
                            "offline": False,
                        },
                    }
                ],
            }
        )

    client.fetch_schedule_data = AsyncMock(side_effect=read_updated_schedule)

    asyncio.run(client.set_battery_parameters(grid_import_limit=450))

    client._post_console_command.assert_awaited_once_with("sched_set 6 -l 450 -x 500")
    assert client.schedule["grid_import_limit"] == 450
    assert client.schedule["grid_export_limit"] == 500


def test_set_battery_parameters_uses_manual_entry_mode_when_cache_is_empty() -> None:
    """A parameter write must use the validated manual entry's mode, never idle."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {
        "local_mode": True,
        "schedule_id": "Manual Schedule",
        "schedule": [{"type": 1, "params": {"setpoint": 100}}],
    }
    client.schedule.update({"mode": None, "setpoint": 100})
    client._post_console_command = AsyncMock(return_value="Command executed successfully")

    async def read_updated_schedule() -> None:
        client._parse_schedule_data(
            {
                "local_mode": True,
                "schedule_id": "Manual Schedule",
                "schedule": [{"type": 1, "params": {"setpoint": 250}}],
            }
        )

    client.fetch_schedule_data = AsyncMock(side_effect=read_updated_schedule)

    asyncio.run(client.set_battery_parameters(setpoint=250))

    client._post_console_command.assert_awaited_once_with("sched_set 1 -s 250")
    assert client.schedule["mode"] == 1


@pytest.mark.parametrize(
    "schedule_entry",
    [
        {"params": {"setpoint": 100}},
        {"type": None, "params": {"setpoint": 100}},
        {"type": "invalid", "params": {"setpoint": 100}},
        {"type": True, "params": {"setpoint": 100}},
        {"type": 5.5, "params": {"setpoint": 100}},
        {"type": 10, "params": {"setpoint": 100}},
    ],
)
def test_set_battery_parameters_rejects_invalid_manual_entry_mode(
    schedule_entry: dict[str, Any],
) -> None:
    """Malformed device mode data must raise a controlled library error."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {
        "local_mode": True,
        "schedule_id": "Manual Schedule",
        "schedule": [schedule_entry],
    }
    client._post_console_command = AsyncMock()

    with pytest.raises(HomevoltDataError, match="mode"):
        asyncio.run(client.set_battery_parameters(max_charge=250))

    client._post_console_command.assert_not_awaited()


def test_set_battery_parameters_requires_manual_schedule() -> None:
    """Do not turn a single cloud schedule into an immediate manual command."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {
        "local_mode": True,
        "schedule_id": "cloud-schedule-id",
        "schedule": [{"type": 5, "params": {"setpoint": 100}}],
    }
    client.schedule.update({"mode": 5, "setpoint": 100})
    client._post_console_command = AsyncMock()

    assert not client.battery_parameters_writable

    with pytest.raises(HomevoltDataError, match="Manual Schedule"):
        asyncio.run(client.set_battery_parameters(max_charge=250))

    client._post_console_command.assert_not_awaited()


def test_set_battery_parameters_rejects_idle_mode() -> None:
    """Do not report success for parameters that firmware ignores in idle mode."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {
        "local_mode": True,
        "schedule_id": "Manual Schedule",
        "schedule": [{"type": 0, "params": {"offline": False}}],
    }
    client._post_console_command = AsyncMock()

    assert not client.battery_parameters_writable

    with pytest.raises(HomevoltDataError, match="ignored in idle mode"):
        asyncio.run(client.set_battery_parameters(max_charge=250))

    client._post_console_command.assert_not_awaited()


@pytest.mark.parametrize("mode", [None, "invalid", True, 5.5, 10, "0"])
def test_battery_parameters_writable_rejects_invalid_or_idle_modes(mode: Any) -> None:
    """Only a known, non-idle manual entry can accept parameter writes."""
    client = Homevolt("homevolt.local")
    client.current_schedule = {
        "local_mode": True,
        "schedule_id": "Manual Schedule",
        "schedule": [{"type": mode, "params": {"setpoint": 100}}],
    }

    assert not client.battery_parameters_writable


def test_battery_parameters_writable_accepts_numeric_string_mode() -> None:
    """A valid device mode uses the same coercion as parsed schedule data."""
    client = Homevolt("homevolt.local")
    client.current_schedule = {
        "local_mode": True,
        "schedule_id": "Manual Schedule",
        "schedule": [{"type": "1", "params": {"setpoint": 100}}],
    }

    assert client.battery_parameters_writable


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        (0, frozenset()),
        (1, frozenset({"setpoint"})),
        (2, frozenset({"setpoint"})),
        (6, frozenset({"grid_import_limit", "grid_export_limit"})),
        (7, frozenset()),
    ],
)
def test_writable_battery_parameters_are_mode_specific(
    mode: int,
    expected: frozenset[str],
) -> None:
    """Advertise only parameters independently verified for the active mode."""
    client = Homevolt("homevolt.local")
    client.current_schedule = {
        "local_mode": True,
        "schedule_id": "Manual Schedule",
        "schedule": [{"type": mode, "params": {"offline": False}}],
    }

    assert client.writable_battery_parameters == expected
    assert client.battery_parameters_writable is bool(expected)


def test_set_battery_parameters_rejects_unsupported_existing_parameters() -> None:
    """Do not silently drop mode-specific parameters from a manual entry."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {
        "local_mode": True,
        "schedule_id": "Manual Schedule",
        "schedule": [
            {
                "type": 6,
                "params": {"setpoint": 100, "fcr_n_power": 500},
            }
        ],
    }
    client.schedule.update({"mode": 6, "setpoint": 100})
    client._post_console_command = AsyncMock()

    assert not client.battery_parameters_writable

    with pytest.raises(HomevoltDataError, match="fcr_n_power"):
        asyncio.run(client.set_battery_parameters(grid_import_limit=250))

    client._post_console_command.assert_not_awaited()


def test_set_battery_parameters_rejects_parameter_not_writable_for_mode() -> None:
    """Reject a field whose independent firmware behavior is not verified."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {
        "local_mode": True,
        "schedule_id": "Manual Schedule",
        "schedule": [{"type": 1, "params": {"setpoint": 500, "offline": False}}],
    }
    client.schedule.update({"mode": 1, "setpoint": 500})
    client._post_console_command = AsyncMock()

    with pytest.raises(HomevoltDataError, match="max_charge.*mode 1"):
        asyncio.run(client.set_battery_parameters(max_charge=1000))

    client._post_console_command.assert_not_awaited()


def test_set_battery_parameters_sends_only_mode_compatible_fields() -> None:
    """Do not carry stale fields into an independently writable setpoint command."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {
        "local_mode": True,
        "schedule_id": "Manual Schedule",
        "schedule": [{"type": 1, "params": {"setpoint": 500, "offline": False}}],
    }
    client.schedule.update(
        {
            "mode": 1,
            "setpoint": 500,
            "max_charge": 2000,
            "max_discharge": 3000,
            "min_soc": 20,
            "max_soc": 90,
            "grid_import_limit": 4000,
            "grid_export_limit": 5000,
        }
    )
    client._post_console_command = AsyncMock(return_value="Command executed successfully")

    async def read_updated_schedule() -> None:
        client._parse_schedule_data(
            {
                "local_mode": True,
                "schedule_id": "Manual Schedule",
                "schedule": [
                    {
                        "type": 1,
                        "params": {"setpoint": 600, "offline": False},
                    }
                ],
            }
        )

    client.fetch_schedule_data = AsyncMock(side_effect=read_updated_schedule)

    asyncio.run(client.set_battery_parameters(setpoint=600))

    client._post_console_command.assert_awaited_once_with("sched_set 1 -s 600")
    client.fetch_schedule_data.assert_awaited_once()
    assert client.schedule["setpoint"] == 600
    assert client.schedule["max_charge"] is None


def test_set_battery_parameters_rejects_readback_mismatch() -> None:
    """Do not report success when firmware keeps the previous parameter value."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {
        "local_mode": True,
        "schedule_id": "Manual Schedule",
        "schedule": [{"type": 1, "params": {"setpoint": 500, "offline": False}}],
    }
    client.schedule.update({"mode": 1, "setpoint": 500})
    client._post_console_command = AsyncMock(return_value="Command executed successfully")

    async def read_unchanged_schedule() -> None:
        client._parse_schedule_data(
            {
                "local_mode": True,
                "schedule_id": "Manual Schedule",
                "schedule": [
                    {
                        "type": 1,
                        "params": {"setpoint": 500, "offline": False},
                    }
                ],
            }
        )

    client.fetch_schedule_data = AsyncMock(side_effect=read_unchanged_schedule)

    with pytest.raises(
        HomevoltCommandVerificationError,
        match="setpoint.*500.*requested 600",
    ):
        asyncio.run(client.set_battery_parameters(setpoint=600))


@pytest.mark.parametrize(
    ("mode", "parameters"),
    [
        (1, {"setpoint": -1}),
        (6, {"grid_import_limit": -1}),
        (6, {"grid_export_limit": -1}),
    ],
)
def test_set_battery_parameters_rejects_invalid_limits(
    mode: int,
    parameters: dict[str, int],
) -> None:
    """Reject unsafe limits before sending a console command."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {
        "local_mode": True,
        "schedule_id": "Manual Schedule",
        "schedule": [{"type": mode, "params": {"setpoint": 100}}],
    }
    client.schedule.update({"mode": mode, "setpoint": 100})
    client._post_console_command = AsyncMock()

    with pytest.raises(HomevoltDataError, match="invalid"):
        asyncio.run(client.set_battery_parameters(**parameters))

    client._post_console_command.assert_not_awaited()


@pytest.mark.parametrize(
    ("mode", "parameter", "value"),
    [
        (1, "setpoint", 200.5),
        (1, "setpoint", True),
        (1, "setpoint", "invalid"),
        (6, "grid_import_limit", 400.5),
        (6, "grid_export_limit", "invalid"),
    ],
)
def test_set_battery_parameters_rejects_non_integer_caller_values(
    mode: int,
    parameter: str,
    value: Any,
) -> None:
    """Caller values must be whole numbers and reject booleans or other types."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {
        "local_mode": True,
        "schedule_id": "Manual Schedule",
        "schedule": [{"type": mode, "params": {"setpoint": 100}}],
    }
    client.schedule.update({"mode": mode, "setpoint": 100})
    client._post_console_command = AsyncMock()

    with pytest.raises(HomevoltDataError, match=f"{parameter} is invalid"):
        asyncio.run(client.set_battery_parameters(**{parameter: value}))

    client._post_console_command.assert_not_awaited()


def test_set_battery_parameters_accepts_integral_float() -> None:
    """Whole-number floats remain valid and produce integer command arguments."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {
        "local_mode": True,
        "schedule_id": "Manual Schedule",
        "schedule": [{"type": 1, "params": {"setpoint": 100}}],
    }
    client.schedule.update({"mode": 1, "setpoint": 100})
    client._post_console_command = AsyncMock(return_value="Command executed successfully")

    async def read_updated_schedule() -> None:
        client._parse_schedule_data(
            {
                "local_mode": True,
                "schedule_id": "Manual Schedule",
                "schedule": [{"type": 1, "params": {"setpoint": 250}}],
            }
        )

    client.fetch_schedule_data = AsyncMock(side_effect=read_updated_schedule)

    asyncio.run(client.set_battery_parameters(setpoint=250.0))

    client._post_console_command.assert_awaited_once_with("sched_set 1 -s 250")


def test_battery_writes_are_serialized() -> None:
    """Concurrent entity writes must not overlap their read-modify-write cycles."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {
        "local_mode": True,
        "schedule_id": "Manual Schedule",
        "schedule": [{"type": 1, "params": {"setpoint": 100}}],
    }
    client.schedule.update({"mode": 1, "setpoint": 100})
    active_writes = 0
    peak_writes = 0

    async def capture_write(command: str) -> str:
        nonlocal active_writes, peak_writes
        active_writes += 1
        peak_writes = max(peak_writes, active_writes)
        await asyncio.sleep(0)
        setpoint = int(command.rsplit(" ", 1)[1])
        client._parse_schedule_data(
            {
                "local_mode": True,
                "schedule_id": "Manual Schedule",
                "schedule": [{"type": 1, "params": {"setpoint": setpoint}}],
            }
        )
        active_writes -= 1
        return "Command executed successfully"

    client._post_console_command = AsyncMock(side_effect=capture_write)
    client.fetch_schedule_data = AsyncMock()

    async def write_concurrently() -> None:
        await asyncio.gather(
            client.set_battery_parameters(setpoint=250),
            client.set_battery_parameters(setpoint=350),
        )

    asyncio.run(write_concurrently())

    assert peak_writes == 1
    assert client.schedule["setpoint"] == 350


def test_set_battery_mode_uses_observed_readback_state() -> None:
    """A successful write publishes only the schedule returned by the device."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {"local_mode": True, "schedule": [{}]}
    client.schedule.update({"mode": 5, "setpoint": 100, "max_charge": 200})
    client._post_console_command = AsyncMock(return_value="Command executed successfully")

    async def read_normalized_schedule() -> None:
        client._parse_schedule_data(
            {
                "local_mode": True,
                "schedule_id": "Manual Schedule",
                "schedule": [
                    {
                        "type": 7,
                        "max": 95,
                        "params": {"offline": False},
                    }
                ],
            }
        )

    client.fetch_schedule_data = AsyncMock(side_effect=read_normalized_schedule)

    asyncio.run(client.set_battery_mode("solar_charge"))

    client.fetch_schedule_data.assert_awaited_once()
    assert client.schedule["mode"] == 7
    assert client.schedule["setpoint"] is None
    assert client.schedule["max_charge"] is None
    assert client.schedule["max_soc"] == 95


def test_set_battery_mode_rejects_normalized_mismatched_mode() -> None:
    """Do not report success when firmware normalizes the request to idle."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {"local_mode": True, "schedule": [{}]}
    client._post_console_command = AsyncMock(return_value="Command executed successfully")

    async def read_idle_schedule() -> None:
        client._parse_schedule_data(
            {
                "local_mode": True,
                "schedule_id": "Manual Schedule",
                "schedule": [{"type": 0, "params": {"offline": False}}],
            }
        )

    client.fetch_schedule_data = AsyncMock(side_effect=read_idle_schedule)

    with pytest.raises(
        HomevoltCommandVerificationError,
        match="reported mode 0 after requesting 7",
    ):
        asyncio.run(client.set_battery_mode("solar_charge"))

    assert client.schedule["mode"] == 0


def test_set_battery_mode_reports_unknown_outcome_when_readback_fails() -> None:
    """Distinguish an accepted command with unavailable confirmation."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {"local_mode": True, "schedule": [{}]}
    client._post_console_command = AsyncMock(return_value="Command executed successfully")
    client.fetch_schedule_data = AsyncMock(
        side_effect=HomevoltConnectionError("read-back unavailable")
    )

    with pytest.raises(
        HomevoltCommandOutcomeUnknownError,
        match="read-back unavailable",
    ):
        asyncio.run(client.set_battery_mode("idle"))


def test_set_battery_mode_reconciles_timeout_with_device_state() -> None:
    """Treat an ambiguous timeout as success only when read-back matches."""
    session = TimeoutSession()
    client = Homevolt("homevolt.local", websession=session)  # type: ignore[arg-type]
    client.current_schedule = {"local_mode": True, "schedule": [{}]}

    async def read_applied_schedule() -> None:
        client._parse_schedule_data(
            {
                "local_mode": True,
                "schedule_id": "Manual Schedule",
                "schedule": [{"type": 1, "params": {"offline": False}}],
            }
        )

    client.fetch_schedule_data = AsyncMock(side_effect=read_applied_schedule)

    asyncio.run(client.set_battery_mode("inverter_charge"))

    assert session.attempts == 1
    client.fetch_schedule_data.assert_awaited_once()
    assert client.schedule["mode"] == 1


def test_set_battery_mode_does_not_carry_parameters_between_modes() -> None:
    """A mode change must not send stale or incompatible schedule parameters."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {"local_mode": True, "schedule": [{}]}
    client.schedule.update(
        {
            "mode": 5,
            "setpoint": 100,
            "max_charge": 200,
            "max_discharge": 300,
            "min_soc": 20,
            "max_soc": 90,
            "grid_import_limit": 400,
            "grid_export_limit": 500,
        }
    )
    client._post_console_command = AsyncMock(return_value="Command executed successfully")

    async def read_solar_schedule() -> None:
        client._parse_schedule_data(
            {
                "local_mode": True,
                "schedule_id": "Manual Schedule",
                "schedule": [{"type": 7, "params": {"offline": False}}],
            }
        )

    client.fetch_schedule_data = AsyncMock(side_effect=read_solar_schedule)

    asyncio.run(client.set_battery_mode("solar_charge"))

    client._post_console_command.assert_awaited_once_with("sched_set 7")


def test_set_idle_clears_preserved_parameters() -> None:
    """Idle mode sends no ignored parameters and clears their cached values."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {"local_mode": True, "schedule": [{}]}
    client.schedule.update(
        {
            "mode": 5,
            "setpoint": 100,
            "max_charge": 200,
            "max_discharge": 300,
            "min_soc": 20,
            "max_soc": 90,
            "grid_import_limit": 400,
            "grid_export_limit": 500,
        }
    )
    client._post_console_command = AsyncMock(return_value="Command executed successfully")

    async def read_idle_schedule() -> None:
        client._parse_schedule_data(
            {
                "local_mode": True,
                "schedule_id": "Manual Schedule",
                "schedule": [{"type": 0, "params": {"offline": False}}],
            }
        )

    client.fetch_schedule_data = AsyncMock(side_effect=read_idle_schedule)

    asyncio.run(client.set_battery_mode("idle"))

    client._post_console_command.assert_awaited_once_with("sched_set 0")
    assert client.schedule == {
        "mode": 0,
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


def test_set_battery_mode_rejects_firmware_unsupported_mode() -> None:
    """Do not send modes that current firmware silently turns into idle."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {"local_mode": True, "schedule": [{}]}
    client._post_console_command = AsyncMock()

    with pytest.raises(HomevoltDataError, match="Invalid mode"):
        asyncio.run(client.set_battery_mode("grid_charge"))

    client._post_console_command.assert_not_awaited()


def test_set_battery_mode_requires_local_mode() -> None:
    """A mode change must not silently enable local control."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {"local_mode": False, "schedule": [{}]}
    client._post_console_command = AsyncMock()

    with pytest.raises(HomevoltDataError, match="Local mode"):
        asyncio.run(client.set_battery_mode("idle"))

    client._post_console_command.assert_not_awaited()


def test_console_command_uses_urlencoded_form_data() -> None:
    """POST console commands using the documented form payload."""
    session = FakeSession()
    client = Homevolt("homevolt.local", "secret", session)  # type: ignore[arg-type]

    asyncio.run(client._post_console_command("sched_set 1 -s 1000"))

    assert len(session.posts) == 1
    url, data, auth, timeout = session.posts[0]
    assert url == "http://homevolt.local/console.json"
    assert isinstance(data, Mapping)
    assert data == {"cmd": "sched_set 1 -s 1000"}
    assert auth == aiohttp.BasicAuth("admin", "secret")
    assert timeout is client._timeout


def test_console_command_returns_device_response() -> None:
    """Return the console body so command acceptance can be evaluated."""
    session = FakeSession(FakeResponse(text="Command executed successfully"))
    client = Homevolt("homevolt.local", websession=session)  # type: ignore[arg-type]

    response = asyncio.run(client._post_console_command("sched_set 0"))

    assert response == "Command executed successfully"


def test_console_command_rejects_error_response() -> None:
    """Raise when the console reports rejection despite an HTTP 200 response."""
    session = FakeSession(FakeResponse(text="Error: invalid arguments"))
    client = Homevolt("homevolt.local", websession=session)  # type: ignore[arg-type]

    with pytest.raises(HomevoltDataError, match="invalid arguments"):
        asyncio.run(client._post_console_command("sched_set 1 -c 250"))


def test_console_command_failure_is_not_described_as_mode_change() -> None:
    """Shared console transport errors must describe parameter writes accurately."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client._post = AsyncMock(side_effect=HomevoltConnectionError("offline"))

    with pytest.raises(
        HomevoltConnectionError,
        match="^Failed to send console command: offline$",
    ):
        asyncio.run(client._post_console_command("sched_set 1 -c 250"))


def test_console_mutation_is_not_blindly_retried_after_timeout() -> None:
    """Do not resend a command whose first outcome is unknown."""
    session = TimeoutSession()
    client = Homevolt("homevolt.local", websession=session)  # type: ignore[arg-type]

    with (
        patch("homevolt.homevolt.asyncio.sleep", new_callable=AsyncMock),
        pytest.raises(HomevoltConnectionError),
    ):
        asyncio.run(client._post_console_command("sched_set 1 -s 500"))

    assert session.attempts == 1


def test_http_error_is_wrapped_with_response_context() -> None:
    """HTTP response failures must retain status and URL in the library error."""
    session = FakeSession(FakeResponse(status=400))
    client = Homevolt("homevolt.local", websession=session)  # type: ignore[arg-type]

    with pytest.raises(HomevoltConnectionError, match=r"400.*homevolt\.local"):
        asyncio.run(client._post_console_command("sched_set 1 -c 250"))


def test_local_mode_write_remains_non_persistent() -> None:
    """Keep the released local-mode write semantics."""
    session = FakeSession()
    client = Homevolt("homevolt.local", "secret", session)  # type: ignore[arg-type]
    client.current_schedule = {"local_mode": False}

    async def read_enabled_local_mode() -> None:
        client._parse_schedule_data(
            {
                "local_mode": True,
                "schedule_id": "Manual Schedule",
                "schedule": [{"type": 0, "params": {"offline": False}}],
            }
        )

    client.fetch_schedule_data = AsyncMock(side_effect=read_enabled_local_mode)

    asyncio.run(client.enable_local_mode())

    assert len(session.posts) == 1
    url, data, auth, timeout = session.posts[0]
    assert url == "http://homevolt.local/params.json"
    assert data == {"k": "settings_local", "v": "true", "store": "0"}
    assert auth == aiohttp.BasicAuth("admin", "secret")
    assert timeout is client._timeout
    assert client.local_mode_enabled


def test_local_mode_uses_observed_readback_state() -> None:
    """Publish local mode only after the device reports the requested value."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {"local_mode": False, "schedule": []}
    client._post = AsyncMock(return_value="OK")

    async def read_enabled_local_mode() -> None:
        client._parse_schedule_data(
            {
                "local_mode": True,
                "schedule_id": "Manual Schedule",
                "schedule": [{"type": 0, "params": {"offline": False}}],
            }
        )

    client.fetch_schedule_data = AsyncMock(side_effect=read_enabled_local_mode)

    asyncio.run(client.enable_local_mode())

    client.fetch_schedule_data.assert_awaited_once()
    assert client.local_mode_enabled


def test_local_mode_preserves_unknown_mutation_outcome() -> None:
    """Expose an ambiguous local-mode write through the specific public error."""
    session = TimeoutSession()
    client = Homevolt("homevolt.local", websession=session)  # type: ignore[arg-type]
    client.current_schedule = {"local_mode": False, "schedule": []}

    with pytest.raises(HomevoltCommandOutcomeUnknownError, match="Mutation outcome is unknown"):
        asyncio.run(client.enable_local_mode())

    assert session.attempts == 1


def test_local_mode_rejects_readback_mismatch() -> None:
    """Do not report success when local mode remains unchanged."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {"local_mode": False, "schedule": []}
    client._post = AsyncMock(return_value="OK")

    async def read_disabled_local_mode() -> None:
        client._parse_schedule_data(
            {
                "local_mode": False,
                "schedule_id": "Partner Schedule",
                "schedule": [],
            }
        )

    client.fetch_schedule_data = AsyncMock(side_effect=read_disabled_local_mode)

    with pytest.raises(
        HomevoltCommandVerificationError,
        match="local mode False.*requested True",
    ):
        asyncio.run(client.enable_local_mode())
