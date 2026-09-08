"""Rules for the interface between the Kavach unit and the interlocking."""

from __future__ import annotations

from .. import faults
from ..model import Finding
from .engine import RuleContext, register


def _link_down(ctx: RuleContext) -> bool:
    return ctx.snapshot.upper("ei.link_state") in ("DOWN", "FAIL", "FAILED")


@register("signalling")
def interlocking_link(ctx: RuleContext) -> list[Finding]:
    if not _link_down(ctx):
        return []
    return [
        faults.get("KVCH-SIG-001").to_finding(
            {
                "ei_link_state": ctx.snapshot.text("ei.link_state", "not reported"),
                "interlocking": ctx.snapshot.text("ei.make", "-"),
                "station": ctx.asset.station_code or "-",
            }
        )
    ]


@register("signalling")
def stale_aspect_data(ctx: RuleContext) -> list[Finding]:
    if _link_down(ctx):
        return []  # already reported as a link failure
    age = ctx.snapshot.number("ei.telegram_age_s")
    if age is None or age <= ctx.thresholds.telegram_age_max_s:
        return []
    return [
        faults.get("KVCH-SIG-002").to_finding(
            {
                "telegram_age_s": age,
                "limit_s": ctx.thresholds.telegram_age_max_s,
                "ei_link_state": ctx.snapshot.text("ei.link_state", "-"),
            }
        )
    ]


@register("signalling")
def aspect_mismatch(ctx: RuleContext) -> list[Finding]:
    mismatches = ctx.snapshot.integer("ei.aspect_mismatch_count")
    if not mismatches:
        return []
    return [
        faults.get("KVCH-SIG-003").to_finding(
            {
                "mismatches": mismatches,
                "station": ctx.asset.station_code or "-",
                "interlocking": ctx.snapshot.text("ei.make", "-"),
            }
        )
    ]
