"""Onboard (loco) rules: isolation, DMI, brake interface, SoS and interventions."""

from __future__ import annotations

from .. import faults
from ..model import Finding
from .engine import RuleContext, register

HEALTHY_STATES = ("OK", "HEALTHY", "NORMAL", "PASS", "AVAILABLE")


@register("onboard")
def kavach_isolated(ctx: RuleContext) -> list[Finding]:
    state = ctx.snapshot.upper("kavach.isolation_state")
    if state in ("", "NORMAL", "IN SERVICE", "ACTIVE"):
        return []
    return [
        faults.get("KVCH-OBU-001").to_finding(
            {
                "isolation_state": ctx.snapshot.text("kavach.isolation_state"),
                "mode": ctx.snapshot.text("kavach.mode", "-"),
                "loco": ctx.asset.location,
                "last_record": ctx.snapshot.age_note,
            }
        )
    ]


@register("onboard")
def dmi_health(ctx: RuleContext) -> list[Finding]:
    state = ctx.snapshot.upper("dmi.state")
    if not state or state in HEALTHY_STATES:
        return []
    return [
        faults.get("KVCH-OBU-002").to_finding(
            {"dmi_state": ctx.snapshot.text("dmi.state"), "loco": ctx.asset.location}
        )
    ]


@register("onboard")
def brake_interface(ctx: RuleContext) -> list[Finding]:
    state = ctx.snapshot.upper("brake.interface_state")
    last_test = ctx.snapshot.upper("brake.last_test_result")

    interface_bad = state not in ("",) and state not in HEALTHY_STATES
    test_failed = last_test not in ("",) and last_test not in HEALTHY_STATES
    if not (interface_bad or test_failed):
        return []

    return [
        faults.get("KVCH-OBU-003").to_finding(
            {
                "brake_interface_state": ctx.snapshot.text(
                    "brake.interface_state", "not reported"
                ),
                "last_brake_test": ctx.snapshot.text(
                    "brake.last_test_result", "not reported"
                ),
                "loco": ctx.asset.location,
            }
        )
    ]


@register("onboard")
def sos_recorded(ctx: RuleContext) -> list[Finding]:
    count = ctx.snapshot.integer("sos.messages_24h")
    if not count:
        return []
    return [
        faults.get("KVCH-OBU-004").to_finding(
            {"sos_messages_24h": count, "loco": ctx.asset.location}
        )
    ]


@register("onboard")
def repeated_brake_applications(ctx: RuleContext) -> list[Finding]:
    count = ctx.snapshot.integer("brake.applications_last_24h")
    if count is None or count <= ctx.thresholds.brake_applications_review:
        return []
    return [
        faults.get("KVCH-OBU-005").to_finding(
            {
                "applications_24h": count,
                "review_threshold": ctx.thresholds.brake_applications_review,
                "loco": ctx.asset.location,
            }
        )
    ]
