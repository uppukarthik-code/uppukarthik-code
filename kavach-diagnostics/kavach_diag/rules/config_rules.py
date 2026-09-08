"""Software, track database and configuration rules.

These compare what the unit reports against what the asset register says was
sanctioned. A unit that quietly differs from its register entry is the usual
first sign that a change went in without paperwork.
"""

from __future__ import annotations

from .. import faults
from ..model import Finding
from .engine import RuleContext, register


@register("config")
def track_database_version(ctx: RuleContext) -> list[Finding]:
    sanctioned = ctx.asset.sanctioned_track_db.strip()
    running = ctx.snapshot.text("sw.track_db_version")
    if not sanctioned or not running or sanctioned == running:
        return []
    return [
        faults.get("KVCH-CFG-001").to_finding(
            {
                "loaded_version": running,
                "sanctioned_version": sanctioned,
                "section": ctx.asset.section or "-",
            }
        )
    ]


@register("config")
def software_version(ctx: RuleContext) -> list[Finding]:
    sanctioned = ctx.asset.sanctioned_sw_version.strip()
    running = ctx.snapshot.text("sw.version")
    if not sanctioned or not running or sanctioned == running:
        return []
    return [
        faults.get("KVCH-CFG-002").to_finding(
            {
                "running_version": running,
                "sanctioned_version": sanctioned,
                "oem": ctx.asset.oem or "-",
            }
        )
    ]


@register("config")
def configuration_checksum(ctx: RuleContext) -> list[Finding]:
    baseline = ctx.asset.commissioning_checksum.strip()
    current = ctx.snapshot.text("config.checksum")
    if not baseline or not current or baseline.lower() == current.lower():
        return []
    return [
        faults.get("KVCH-CFG-003").to_finding(
            {
                "current_checksum": current,
                "commissioning_checksum": baseline,
                "commissioned_on": ctx.asset.commissioned_on or "-",
            }
        )
    ]
