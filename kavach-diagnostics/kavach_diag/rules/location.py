"""Location, odometry and time-reference rules."""

from __future__ import annotations

from .. import faults
from ..model import Finding
from .engine import RuleContext, register


@register("location")
def location_error(ctx: RuleContext) -> list[Finding]:
    error = ctx.snapshot.number("loc.error_m")
    if error is None or error <= ctx.thresholds.location_error_max_m:
        return []
    return [
        faults.get("KVCH-LOC-001").to_finding(
            {
                "location_error_m": error,
                "tolerance_m": ctx.thresholds.location_error_max_m,
                "odometer_slip_pct": ctx.snapshot.text("loc.odometer_slip_pct", "-"),
                "last_tag_km": ctx.snapshot.text("rfid.last_tag_km", "-"),
            }
        )
    ]


@register("location")
def odometer_slip(ctx: RuleContext) -> list[Finding]:
    slip = ctx.snapshot.number("loc.odometer_slip_pct")
    if slip is None or slip <= ctx.thresholds.odometer_slip_max_pct:
        return []
    return [
        faults.get("KVCH-LOC-002").to_finding(
            {"odometer_slip_pct": slip, "limit_pct": ctx.thresholds.odometer_slip_max_pct}
        )
    ]


@register("time")
def time_reference(ctx: RuleContext) -> list[Finding]:
    source = ctx.snapshot.upper("time.source")
    offset = ctx.snapshot.number("time.offset_ms")

    lost_source = source in ("", "NONE", "RTC", "FREERUN", "FREE-RUN")
    drifting = offset is not None and abs(offset) > ctx.thresholds.time_offset_max_ms
    if not (lost_source or drifting):
        return []

    return [
        faults.get("KVCH-LOC-003").to_finding(
            {
                "time_source": ctx.snapshot.text("time.source", "not reported"),
                "offset_ms": ctx.snapshot.text("time.offset_ms", "-"),
                "limit_ms": ctx.thresholds.time_offset_max_ms,
                "gnss_fix": ctx.snapshot.text("gnss.fix", "-"),
            }
        )
    ]


@register("time")
def gnss_fix(ctx: RuleContext) -> list[Finding]:
    fix = ctx.snapshot.upper("gnss.fix")
    satellites = ctx.snapshot.integer("gnss.satellites")

    if fix == "A" and (satellites is None or satellites > 0):
        return []
    if fix == "" and satellites is None:
        return []  # unit does not report GNSS at all

    if fix == "V" and satellites == 0:
        cause = (
            "No satellites visible - antenna, feeder or receiver fault, or the "
            "unit is stabled under cover."
        )
    elif fix == "V":
        cause = (
            "Satellites visible but no navigation solution - degraded antenna or "
            "receiver performance."
        )
    else:
        cause = "GNSS status not reported as a valid fix."

    return [
        faults.get("KVCH-LOC-004").to_finding(
            {
                "gnss_fix": ctx.snapshot.text("gnss.fix", "not reported"),
                "satellites": ctx.snapshot.text("gnss.satellites", "-"),
                "time_source": ctx.snapshot.text("time.source", "-"),
            },
            likely_cause=cause,
        )
    ]
