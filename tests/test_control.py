"""Tests for Homevolt battery control."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any
from unittest.mock import AsyncMock

import aiohttp
import pytest

from homevolt import Homevolt, HomevoltConnectionError, HomevoltDataError


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
                request_info=None,  # type: ignore[arg-type]
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


def test_set_battery_parameters_preserves_other_values() -> None:
    """Changing one parameter retains the rest of the manual entry."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {
        "local_mode": True,
        "schedule_id": "Manual Schedule",
        "schedule": [{"type": 5, "params": {"setpoint": 100, "offline": False}}],
    }
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
    client._post_console_command = AsyncMock()

    assert client.battery_parameters_writable

    asyncio.run(client.set_battery_parameters(max_charge=250))

    client._post_console_command.assert_awaited_once_with(
        "sched_set 5 -s 100 -c 250 -d 300 --min 20 --max 90 -l 400 -x 500"
    )
    assert client.schedule["max_charge"] == 250


def test_set_battery_parameters_coerces_preserved_grid_limits() -> None:
    """Parsed grid limits must remain integer command arguments when preserved."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {
        "local_mode": True,
        "schedule_id": "Manual Schedule",
        "schedule": [{"type": 5, "params": {"setpoint": 100}}],
    }
    client.schedule.update(
        {
            "mode": 5,
            "setpoint": 100,
            "max_charge": 200,
            "grid_import_limit": 400.0,
            "grid_export_limit": "500",
        }
    )
    client._post_console_command = AsyncMock()

    asyncio.run(client.set_battery_parameters(max_charge=250))

    client._post_console_command.assert_awaited_once_with("sched_set 5 -s 100 -c 250 -l 400 -x 500")
    assert client.schedule["grid_import_limit"] == 400
    assert client.schedule["grid_export_limit"] == 500


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
        asyncio.run(client.set_battery_parameters(max_charge=250))

    client._post_console_command.assert_not_awaited()


@pytest.mark.parametrize(
    "parameters",
    [
        {"max_charge": -1},
        {"max_discharge": -1},
        {"min_soc": -1},
        {"max_soc": 101},
        {"grid_import_limit": -1},
        {"grid_export_limit": -1},
    ],
)
def test_set_battery_parameters_rejects_invalid_limits(
    parameters: dict[str, int],
) -> None:
    """Reject unsafe limits before sending a console command."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {
        "local_mode": True,
        "schedule_id": "Manual Schedule",
        "schedule": [{"type": 5, "params": {"setpoint": 100}}],
    }
    client.schedule.update({"mode": 5, "setpoint": 100, "min_soc": 20, "max_soc": 90})
    client._post_console_command = AsyncMock()

    with pytest.raises(HomevoltDataError, match="invalid"):
        asyncio.run(client.set_battery_parameters(**parameters))

    client._post_console_command.assert_not_awaited()


def test_set_battery_parameters_rejects_inverted_soc_range() -> None:
    """Minimum state of charge cannot exceed the maximum."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {
        "local_mode": True,
        "schedule_id": "Manual Schedule",
        "schedule": [{"type": 5, "params": {"setpoint": 100}}],
    }
    client.schedule.update({"mode": 5, "setpoint": 100, "min_soc": 20, "max_soc": 90})
    client._post_console_command = AsyncMock()

    with pytest.raises(HomevoltDataError, match="Minimum state of charge"):
        asyncio.run(client.set_battery_parameters(min_soc=95))

    client._post_console_command.assert_not_awaited()


def test_battery_writes_are_serialized() -> None:
    """Concurrent entity writes must not overlap their read-modify-write cycles."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {
        "local_mode": True,
        "schedule_id": "Manual Schedule",
        "schedule": [{"type": 5, "params": {"setpoint": 100}}],
    }
    client.schedule.update(
        {
            "mode": 5,
            "setpoint": 100,
            "max_charge": 200,
            "max_discharge": 300,
        }
    )
    active_writes = 0
    peak_writes = 0

    async def capture_write(command: str) -> None:
        nonlocal active_writes, peak_writes
        active_writes += 1
        peak_writes = max(peak_writes, active_writes)
        await asyncio.sleep(0)
        active_writes -= 1

    client._post_console_command = AsyncMock(side_effect=capture_write)

    async def write_concurrently() -> None:
        await asyncio.gather(
            client.set_battery_parameters(max_charge=250),
            client.set_battery_parameters(max_discharge=350),
        )

    asyncio.run(write_concurrently())

    assert peak_writes == 1
    assert client.schedule["max_charge"] == 250
    assert client.schedule["max_discharge"] == 350


def test_set_battery_mode_preserves_known_parameters() -> None:
    """Changing mode preserves the currently reported control parameters."""
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
    client._post_console_command = AsyncMock()

    asyncio.run(client.set_battery_mode("solar_charge"))

    client._post_console_command.assert_awaited_once_with(
        "sched_set 7 -s 100 -c 200 -d 300 --min 20 --max 90 -l 400 -x 500"
    )


def test_set_idle_does_not_invent_a_setpoint() -> None:
    """Idle mode works without an arbitrary power setpoint."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client.current_schedule = {"local_mode": True, "schedule": [{}]}
    client._post_console_command = AsyncMock()

    asyncio.run(client.set_battery_mode("idle"))

    client._post_console_command.assert_awaited_once_with("sched_set 0")


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


def test_console_command_failure_is_not_described_as_mode_change() -> None:
    """Shared console transport errors must describe parameter writes accurately."""
    client = Homevolt("homevolt.local", websession=FakeSession())  # type: ignore[arg-type]
    client._post = AsyncMock(side_effect=HomevoltConnectionError("offline"))

    with pytest.raises(
        HomevoltConnectionError,
        match="^Failed to send console command: offline$",
    ):
        asyncio.run(client._post_console_command("sched_set 1 -c 250"))


def test_local_mode_write_remains_non_persistent() -> None:
    """Keep the released local-mode write semantics."""
    session = FakeSession()
    client = Homevolt("homevolt.local", "secret", session)  # type: ignore[arg-type]
    client.current_schedule = {"local_mode": False}

    asyncio.run(client.enable_local_mode())

    assert len(session.posts) == 1
    url, data, auth, timeout = session.posts[0]
    assert url == "http://homevolt.local/params.json"
    assert data == {"k": "settings_local", "v": "true", "store": "0"}
    assert auth == aiohttp.BasicAuth("admin", "secret")
    assert timeout is client._timeout
    assert client.local_mode_enabled
