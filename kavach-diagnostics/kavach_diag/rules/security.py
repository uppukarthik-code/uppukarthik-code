"""OT security posture rules.

Kavach is a safety-related communication system over an open transmission
medium, so EN 50159 threats - masquerade, replay, insertion, corruption - are
part of its design assumptions rather than an afterthought. These rules read
the evidence a unit already records and turn it into findings an S&T engineer
and a security cell can act on together.

They assess posture from exported evidence only. Nothing here probes, scans or
authenticates against a unit.
"""

from __future__ import annotations

from .. import faults
from ..model import Finding, Severity
from .engine import RuleContext, register


@register("security")
def authentication_failures(ctx: RuleContext) -> list[Finding]:
    failures = ctx.snapshot.integer("sec.auth_failures_24h")
    if failures is None or failures <= ctx.thresholds.auth_failures_threshold:
        return []

    rssi = ctx.snapshot.number("radio.rssi_dbm")
    link_healthy = rssi is None or rssi >= ctx.thresholds.rssi_marginal_dbm

    evidence = {
        "auth_failures_24h": failures,
        "rssi_dbm": ctx.snapshot.text("radio.rssi_dbm", "-"),
        "radio_link_quality": "adequate" if link_healthy else "degraded",
    }
    overrides = {}
    if not link_healthy:
        # On a poor link, corruption is the more likely explanation.
        overrides = {
            "severity": Severity.MINOR,
            "likely_cause": (
                "Authentication failures accompanied by a degraded radio link - "
                "most likely message corruption in propagation rather than "
                "forged messages. Fix the radio path first, then re-assess."
            ),
        }
    return [faults.get("KVCH-SEC-001").to_finding(evidence, **overrides)]


@register("security")
def key_expiry(ctx: RuleContext) -> list[Finding]:
    days = ctx.snapshot.integer("sec.key_expiry_days")
    if days is None or days > ctx.thresholds.key_expiry_notice_days:
        return []

    overrides = {}
    if days <= 0:
        overrides = {
            "severity": Severity.CRITICAL,
            "title": "Cryptographic key set has expired",
        }
    return [
        faults.get("KVCH-SEC-002").to_finding(
            {
                "days_to_expiry": days,
                "notice_period_days": ctx.thresholds.key_expiry_notice_days,
            },
            **overrides,
        )
    ]


@register("security")
def unknown_peers(ctx: RuleContext) -> list[Finding]:
    attempts = ctx.snapshot.integer("sec.unknown_peer_attempts_24h")
    if attempts is None or attempts <= ctx.thresholds.unknown_peer_threshold:
        return []
    return [
        faults.get("KVCH-SEC-003").to_finding(
            {
                "unknown_peer_attempts_24h": attempts,
                "section": ctx.asset.section or "-",
                "km_post": ctx.asset.km_post or "-",
            }
        )
    ]


@register("security")
def maintenance_port(ctx: RuleContext) -> list[Finding]:
    if ctx.snapshot.flag("sec.maint_port_open") is not True:
        return []
    return [
        faults.get("KVCH-SEC-004").to_finding(
            {
                "maintenance_port": "open",
                "last_record": ctx.snapshot.age_note,
                "asset": ctx.asset.describe(),
            }
        )
    ]


@register("security")
def default_credentials(ctx: RuleContext) -> list[Finding]:
    if ctx.snapshot.flag("sec.default_credentials") is not True:
        return []
    return [
        faults.get("KVCH-SEC-005").to_finding(
            {"default_credentials": "in use", "oem": ctx.asset.oem or "-"}
        )
    ]


@register("security")
def firmware_signature(ctx: RuleContext) -> list[Finding]:
    signed = ctx.snapshot.flag("sec.firmware_signed")
    if signed is not False:
        return []
    return [
        faults.get("KVCH-SEC-006").to_finding(
            {
                "firmware_signed": "no",
                "running_version": ctx.snapshot.text("sw.version", "-"),
                "oem": ctx.asset.oem or "-",
            }
        )
    ]


@register("security")
def removable_media(ctx: RuleContext) -> list[Finding]:
    events = ctx.snapshot.integer("sec.usb_events_24h")
    if not events:
        return []
    return [
        faults.get("KVCH-SEC-007").to_finding(
            {"removable_media_events_24h": events, "asset": ctx.asset.asset_id}
        )
    ]
