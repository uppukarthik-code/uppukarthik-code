"""Track-side RFID tag rules.

Tag health is where Kavach meets the permanent way: tags are physically in the
track and are disturbed by the same works that disturb the track. The rules
therefore separate "tags not being read" (usually a site condition) from "a tag
identity that should not exist" (a data-integrity and security matter).
"""

from __future__ import annotations

from .. import faults
from ..model import Finding, Severity
from .engine import RuleContext, register


@register("rfid")
def tag_read_shortfall(ctx: RuleContext) -> list[Finding]:
    read = ctx.snapshot.integer("rfid.reads_last_run")
    expected = ctx.snapshot.integer("rfid.expected_tags_last_run")
    if read is None or not expected:
        return []

    ratio = read / expected
    if ratio >= ctx.thresholds.tag_read_min_ratio:
        return []

    missed = expected - read
    evidence = {
        "tags_read": read,
        "tags_expected": expected,
        "missed": missed,
        "read_ratio": round(ratio, 3),
        "minimum_ratio": ctx.thresholds.tag_read_min_ratio,
        "last_tag_km": ctx.snapshot.text("rfid.last_tag_km", "-"),
    }

    # A handful of misses is a maintenance item; losing a quarter of the tags
    # means the unit is running largely on odometry between fixes.
    overrides = {"severity": Severity.CRITICAL} if ratio < 0.75 else {}
    return [faults.get("KVCH-TAG-001").to_finding(evidence, **overrides)]


@register("rfid")
def tag_integrity_errors(ctx: RuleContext) -> list[Finding]:
    errors = ctx.snapshot.integer("rfid.crc_errors")
    if errors is None or errors <= ctx.thresholds.tag_crc_errors_max:
        return []
    return [
        faults.get("KVCH-TAG-002").to_finding(
            {
                "crc_errors": errors,
                "limit": ctx.thresholds.tag_crc_errors_max,
                "last_tag_id": ctx.snapshot.text("rfid.last_tag_id", "-"),
                "last_tag_km": ctx.snapshot.text("rfid.last_tag_km", "-"),
            }
        )
    ]


@register("rfid")
def unknown_tag_identity(ctx: RuleContext) -> list[Finding]:
    unknown = ctx.snapshot.integer("rfid.unknown_tag_ids")
    if not unknown:
        return []
    return [
        faults.get("KVCH-TAG-003").to_finding(
            {
                "unknown_tag_reads": unknown,
                "last_tag_id": ctx.snapshot.text("rfid.last_tag_id", "-"),
                "last_tag_km": ctx.snapshot.text("rfid.last_tag_km", "-"),
                "track_db_version": ctx.snapshot.text("sw.track_db_version", "-"),
            }
        )
    ]
