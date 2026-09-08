"""Power supply rules.

Supply is the single most common reason a station Kavach installation goes out
of service, so mains state, charger state, remaining backup and bus voltage are
assessed together rather than as independent alarms.
"""

from __future__ import annotations

from .. import faults
from ..model import Finding
from .engine import RuleContext, register

CHARGING_STATES = ("FLOAT", "BOOST", "CHARGING", "OK", "NORMAL")


@register("power")
def mains_supply(ctx: RuleContext) -> list[Finding]:
    state = ctx.snapshot.upper("power.mains_state")
    if state in ("", "OK", "ON", "HEALTHY", "NORMAL"):
        return []
    return [
        faults.get("KVCH-PWR-001").to_finding(
            {
                "mains_state": ctx.snapshot.text("power.mains_state"),
                "battery_backup_min": ctx.snapshot.text(
                    "power.battery_backup_min", "not reported"
                ),
                "station": ctx.asset.station_code or ctx.asset.location,
            }
        )
    ]


@register("power")
def battery_reserve(ctx: RuleContext) -> list[Finding]:
    backup = ctx.snapshot.number("power.battery_backup_min")
    if backup is None or backup >= ctx.thresholds.battery_backup_min_minutes:
        return []
    return [
        faults.get("KVCH-PWR-002").to_finding(
            {
                "battery_backup_min": backup,
                "required_min": ctx.thresholds.battery_backup_min_minutes,
                "mains_state": ctx.snapshot.text("power.mains_state", "-"),
                "charger_state": ctx.snapshot.text("power.charger_state", "-"),
            }
        )
    ]


@register("power")
def charger_state(ctx: RuleContext) -> list[Finding]:
    state = ctx.snapshot.upper("power.charger_state")
    if not state or state in CHARGING_STATES:
        return []
    return [
        faults.get("KVCH-PWR-003").to_finding(
            {
                "charger_state": ctx.snapshot.text("power.charger_state"),
                "dc_volts": ctx.snapshot.text("power.dc_volts", "-"),
                "mains_state": ctx.snapshot.text("power.mains_state", "-"),
            }
        )
    ]


@register("power")
def dc_bus_voltage(ctx: RuleContext) -> list[Finding]:
    volts = ctx.snapshot.number("power.dc_volts")
    if volts is None:
        return []
    low, high = ctx.settings.dc_range_for(ctx.asset.asset_type)
    if low <= volts <= high:
        return []
    return [
        faults.get("KVCH-PWR-004").to_finding(
            {
                "dc_volts": volts,
                "working_range_v": f"{low}-{high}",
                "condition": "below range" if volts < low else "above range",
                "charger_state": ctx.snapshot.text("power.charger_state", "-"),
            }
        )
    ]
