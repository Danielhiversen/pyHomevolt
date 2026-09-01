"""Tests for parsing HomeVolt EMS data."""

from homevolt.homevolt import _sum_phase_power


def test_sum_phase_power_ignores_unavailable_phase_values() -> None:
    """Unavailable phase readings should not make the full update fail."""
    assert _sum_phase_power([{"power": 120}, {"power": None}, {}, {"power": -20}]) == 100
