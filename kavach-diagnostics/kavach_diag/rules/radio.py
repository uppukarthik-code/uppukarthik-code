"""Radio sub-system rules.

Ordered so that a hard link failure suppresses the softer signal-quality
findings: telling an engineer that RSSI is low on a link that is down wastes
their time at site.
"""

from __future__ import annotations

from .. import faults
from ..model import Finding, Severity
from .engine import RuleContext, register


def _link_is_down(ctx: RuleContext) -> bool:
    state = ctx.snapshot.upper("radio.link_state")
    if state in ("DOWN", "FAIL", "FAILED"):
        return True
    silence = ctx.snapshot.number("radio.time_since_last_frame_s")
    return silence is not None and silence > ctx.thresholds.radio_silence_max_s


@register("radio")
def radio_link_down(ctx: RuleContext) -> list[Finding]:
    if not _link_is_down(ctx):
        return []
    return [
        faults.get("KVCH-RAD-001").to_finding(
            {
                "link_state": ctx.snapshot.text("radio.link_state", "not reported"),
                "seconds_since_last_frame": ctx.snapshot.text(
                    "radio.time_since_last_frame_s", "not reported"
                ),
                "peer_units_seen": ctx.snapshot.text("radio.peer_units_seen", "-"),
            }
        )
    ]


@register("radio")
def radio_signal_strength(ctx: RuleContext) -> list[Finding]:
    if _link_is_down(ctx):
        return []
    rssi = ctx.snapshot.number("radio.rssi_dbm")
    if rssi is None or rssi >= ctx.thresholds.rssi_marginal_dbm:
        return []

    evidence = {
        "rssi_dbm": rssi,
        "working_limit_dbm": ctx.thresholds.rssi_min_dbm,
        "marginal_below_dbm": ctx.thresholds.rssi_marginal_dbm,
        "snr_db": ctx.snapshot.text("radio.snr_db", "-"),
        "km_post": ctx.asset.km_post or "-",
    }

    # Below the marginal line but still above the working limit is worth
    # attention on the next round of maintenance, not a failure entry.
    if rssi >= ctx.thresholds.rssi_min_dbm:
        overrides = {
            "severity": Severity.MINOR,
            "title": "Marginal radio signal - approaching the working limit",
        }
    else:
        overrides = {}

    return [faults.get("KVCH-RAD-002").to_finding(evidence, **overrides)]


@register("radio")
def radio_vswr(ctx: RuleContext) -> list[Finding]:
    vswr = ctx.snapshot.number("radio.vswr")
    if vswr is None or vswr <= ctx.thresholds.vswr_max:
        return []
    return [
        faults.get("KVCH-RAD-003").to_finding(
            {"vswr": vswr, "limit": ctx.thresholds.vswr_max}
        )
    ]


@register("radio")
def radio_frame_loss(ctx: RuleContext) -> list[Finding]:
    if _link_is_down(ctx):
        return []
    loss = ctx.snapshot.number("radio.packet_loss_pct")
    if loss is None or loss <= ctx.thresholds.packet_loss_max_pct:
        return []
    return [
        faults.get("KVCH-RAD-004").to_finding(
            {
                "frame_loss_pct": loss,
                "limit_pct": ctx.thresholds.packet_loss_max_pct,
                "rssi_dbm": ctx.snapshot.text("radio.rssi_dbm", "-"),
            }
        )
    ]


@register("radio")
def radio_frequency(ctx: RuleContext) -> list[Finding]:
    frequency = ctx.snapshot.number("radio.frequency_mhz")
    if frequency is None:
        return []

    low, high = ctx.thresholds.radio_band_mhz
    assigned = None
    if ctx.asset.assigned_freq_mhz:
        try:
            assigned = float(ctx.asset.assigned_freq_mhz)
        except ValueError:
            assigned = None

    off_band = not (low <= frequency <= high)
    off_assignment = assigned is not None and abs(frequency - assigned) > 0.001
    if not (off_band or off_assignment):
        return []

    return [
        faults.get("KVCH-RAD-005").to_finding(
            {
                "operating_mhz": frequency,
                "assigned_mhz": ctx.asset.assigned_freq_mhz or "not in register",
                "band_mhz": f"{low}-{high}",
                "condition": "outside band" if off_band else "not the assigned channel",
            }
        )
    ]


@register("radio")
def radio_interference(ctx: RuleContext) -> list[Finding]:
    events = ctx.snapshot.integer("radio.interference_events_24h")
    if events is None or events <= ctx.thresholds.interference_events_threshold:
        return []

    rssi = ctx.snapshot.number("radio.rssi_dbm")
    auth_failures = ctx.snapshot.integer("sec.auth_failures_24h", 0) or 0
    loss = ctx.snapshot.number("radio.packet_loss_pct", 0.0) or 0.0

    # Interference is only the likely story when the signal itself is adequate.
    signal_adequate = rssi is None or rssi >= ctx.thresholds.rssi_marginal_dbm
    corruption = auth_failures > 0 or loss > ctx.thresholds.packet_loss_max_pct
    if not (signal_adequate and corruption):
        return []

    return [
        faults.get("KVCH-RAD-006").to_finding(
            {
                "interference_events_24h": events,
                "rssi_dbm": ctx.snapshot.text("radio.rssi_dbm", "-"),
                "frame_loss_pct": loss,
                "auth_failures_24h": auth_failures,
                "km_post": ctx.asset.km_post or "-",
            }
        )
    ]
