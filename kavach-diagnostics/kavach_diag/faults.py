"""The Kavach fault library.

Every classification the engine can produce is declared here once, so that the
report, the ``explain`` command and the documentation all read from the same
source. Fault codes are stable and are intended to be quoted in the S&T failure
register entry and in the divisional Kavach performance return.

The ``responsibility`` and ``escalation`` fields carry the Indian Railways
working context: which maintenance unit owns the fix, and how far the failure
travels. They are defaults - each division's JPO / SOP for Kavach differs, so
they are meant to be edited to match the division the tool is deployed in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .model import Finding, Severity


class Subsystem:
    RADIO = "RADIO"
    TAG = "RFID / TRACK-SIDE TAGS"
    LOCATION = "LOCATION & ODOMETRY"
    SIGNALLING = "SIGNALLING INTERFACE"
    POWER = "POWER SUPPLY"
    ONBOARD = "ONBOARD / LOCO"
    CONFIG = "SOFTWARE & TRACK DATABASE"
    SECURITY = "OT SECURITY (EN 50159)"
    SYSTEM = "DATA AVAILABILITY"


# Maintenance units, as an IR division would name them.
class Owner:
    ST_KAVACH = "SSE/JE (S&T) - Kavach"
    ST_SIGNAL = "SSE/JE (S&T) - Signalling (EI/RRI)"
    ST_POWER = "SSE/JE (S&T) - IPS / power supply"
    SHED = "Loco shed (Elec/Mech) with Kavach OEM"
    OEM = "OEM under CAMC"
    DIV_CELL = "Divisional Kavach cell / Sr.DSTE"
    CYBER = "Zonal cyber security cell with Sr.DSTE"


# Escalation phrasing reused across entries.
REGISTER = (
    "Record in the S&T failure register with this fault code and advise the "
    "Section Controller."
)
UNUSUAL = (
    "Treat as a Kavach failure affecting train working: advise Section "
    "Controller immediately, record in the S&T failure register, and include "
    "in the divisional Kavach performance return."
)
MONITOR = "Record as an observation; review at the fortnightly Kavach review."


@dataclass(frozen=True)
class FaultDefinition:
    code: str
    title: str
    subsystem: str
    severity: str
    signature: str
    likely_cause: str
    action: str
    responsibility: str
    escalation: str
    references: tuple[str, ...] = field(default_factory=tuple)

    def to_finding(self, evidence: dict[str, Any] | None = None, **overrides) -> Finding:
        return Finding(
            fault_code=self.code,
            title=overrides.get("title", self.title),
            severity=overrides.get("severity", self.severity),
            likely_cause=overrides.get("likely_cause", self.likely_cause),
            action=overrides.get("action", self.action),
            responsibility=overrides.get("responsibility", self.responsibility),
            escalation=overrides.get("escalation", self.escalation),
            evidence=dict(evidence or {}),
            subsystem=self.subsystem,
        )


def _f(**kwargs) -> FaultDefinition:
    return FaultDefinition(**kwargs)


FAULTS: dict[str, FaultDefinition] = {d.code: d for d in [

    # ------------------------------------------------------------------ OK
    _f(
        code="KVCH-OK-000",
        title="Kavach unit healthy",
        subsystem=Subsystem.SYSTEM,
        severity=Severity.OK,
        signature="All evaluated checks within limits for the asset type.",
        likely_cause="Normal operation.",
        action="No action required.",
        responsibility="-",
        escalation="-",
    ),

    # -------------------------------------------------------- data / system
    _f(
        code="KVCH-SYS-001",
        title="No telemetry available for asset",
        subsystem=Subsystem.SYSTEM,
        severity=Severity.NO_DATA,
        signature="Asset present in the register but absent from the export.",
        likely_cause=(
            "Unit did not report to the remote monitoring / data-logger export, "
            "OFC or backhaul link to the station is down, unit is switched off "
            "for maintenance, or the export was taken before commissioning."
        ),
        action=(
            "Confirm whether the unit is under maintenance block. If not, check "
            "the station backhaul link and the data-logger export path, then "
            "re-run the scan."
        ),
        responsibility=Owner.ST_KAVACH,
        escalation=REGISTER,
    ),
    _f(
        code="KVCH-SYS-002",
        title="Telemetry export is stale",
        subsystem=Subsystem.SYSTEM,
        severity=Severity.WARNING,
        signature="Snapshot timestamp older than the configured staleness limit.",
        likely_cause=(
            "The unit stopped reporting after the last good record, or the "
            "export job has not run recently."
        ),
        action=(
            "Check the last-seen time against the monitoring server. A unit that "
            "has stopped reporting while in service is to be treated as a "
            "communication failure until proved otherwise."
        ),
        responsibility=Owner.ST_KAVACH,
        escalation=REGISTER,
    ),

    # ------------------------------------------------------------- radio
    _f(
        code="KVCH-RAD-001",
        title="Radio link down - no Kavach radio communication",
        subsystem=Subsystem.RADIO,
        severity=Severity.CRITICAL,
        signature="radio.link_state=DOWN, or no frame received within the timeout.",
        likely_cause=(
            "Radio modem unit failure, tower / static radio unit down, antenna "
            "or feeder cable fault, or loss of power to the radio equipment."
        ),
        action=(
            "Check the radio modem unit and tower equipment status, feeder and "
            "antenna connections, and the power supply to the radio rack. "
            "Without radio, the unit cannot pass movement authority - the "
            "section works on Kavach-unavailable conditions."
        ),
        responsibility=Owner.ST_KAVACH,
        escalation=UNUSUAL,
        references=("RDSO Kavach specification - radio sub-system",),
    ),
    _f(
        code="KVCH-RAD-002",
        title="Weak radio signal (RSSI below working limit)",
        subsystem=Subsystem.RADIO,
        severity=Severity.MAJOR,
        signature="radio.rssi_dbm below the configured working threshold.",
        likely_cause=(
            "Antenna misalignment or degradation, water ingress in the feeder, "
            "connector corrosion, reduced transmit power, or a coverage gap in "
            "the section (cutting, tunnel, curve)."
        ),
        action=(
            "Carry out a radio coverage check over the affected block section, "
            "inspect feeder and connectors, and verify transmit power against "
            "the commissioning record. Persistent low RSSI in the same "
            "kilometrage indicates a coverage gap needing a tower / repeater "
            "review, not a unit fault."
        ),
        responsibility=Owner.ST_KAVACH,
        escalation=REGISTER,
    ),
    _f(
        code="KVCH-RAD-003",
        title="High antenna VSWR",
        subsystem=Subsystem.RADIO,
        severity=Severity.MAJOR,
        signature="radio.vswr above the acceptable limit.",
        likely_cause=(
            "Feeder cable damage, wet or corroded connector, damaged antenna, "
            "or a loose N-connector at the tower end."
        ),
        action=(
            "Attend the tower, sweep the feeder, dry and remake connectors, and "
            "re-measure VSWR. Continued transmission into a high VSWR load "
            "damages the radio modem unit."
        ),
        responsibility=Owner.ST_KAVACH,
        escalation=REGISTER,
    ),
    _f(
        code="KVCH-RAD-004",
        title="Radio frame loss above limit",
        subsystem=Subsystem.RADIO,
        severity=Severity.MAJOR,
        signature="radio.packet_loss_pct above the configured limit while the link is up.",
        likely_cause=(
            "Co-channel interference, congestion from too many units on the "
            "channel, marginal coverage, or an external emitter in the band."
        ),
        action=(
            "Record loss against kilometrage and time of day. Check channel "
            "plan and neighbouring installations for frequency reuse conflict, "
            "and carry out a spectrum check if loss is continuous."
        ),
        responsibility=Owner.ST_KAVACH,
        escalation=REGISTER,
    ),
    _f(
        code="KVCH-RAD-005",
        title="Radio operating off the assigned channel",
        subsystem=Subsystem.RADIO,
        severity=Severity.MAJOR,
        signature="radio.frequency_mhz outside the Kavach band or not matching the register.",
        likely_cause=(
            "Incorrect channel configuration after a card replacement, or a "
            "configuration file restored from the wrong site."
        ),
        action=(
            "Verify the configured frequency and channel against the sanctioned "
            "frequency allotment for the section, and restore the correct "
            "site configuration."
        ),
        responsibility=Owner.ST_KAVACH,
        escalation=REGISTER,
    ),
    _f(
        code="KVCH-RAD-006",
        title="Suspected radio interference or jamming",
        subsystem=Subsystem.RADIO,
        severity=Severity.MAJOR,
        signature=(
            "Elevated interference events with authentication failures or frame "
            "loss while RSSI remains adequate."
        ),
        likely_cause=(
            "External emitter in or adjacent to the band, faulty nearby "
            "transmitter, or deliberate interference."
        ),
        action=(
            "Carry out a spectrum survey over the affected kilometrage, note "
            "time of day and repeatability, and preserve the radio logs. "
            "Deliberate interference with a train protection system is a "
            "security incident, not only a maintenance one."
        ),
        responsibility=Owner.CYBER,
        escalation=(
            "Advise Sr.DSTE and the zonal cyber security cell, preserve logs, "
            "and follow the incident reporting route in addition to the S&T "
            "failure register entry."
        ),
        references=("EN 50159 threat: interference / denial of communication",),
    ),

    # -------------------------------------------------------------- RFID
    _f(
        code="KVCH-TAG-001",
        title="RFID tag read failures on the run",
        subsystem=Subsystem.TAG,
        severity=Severity.MAJOR,
        signature="Tags read materially fewer than tags expected for the run.",
        likely_cause=(
            "Missing or displaced track-side tag, tag damaged during track "
            "maintenance (deep screening, tamping, rail renewal), reader "
            "antenna height or alignment out of limit, or reader fault."
        ),
        action=(
            "Extract the tag-miss kilometrage from the onboard log and arrange "
            "a joint site check of those tag locations with the P.Way "
            "official. Verify reader antenna mounting height and alignment on "
            "the loco before condemning the track-side tags."
        ),
        responsibility=Owner.ST_KAVACH,
        escalation=REGISTER,
    ),
    _f(
        code="KVCH-TAG-002",
        title="RFID tag CRC / read errors",
        subsystem=Subsystem.TAG,
        severity=Severity.MINOR,
        signature="rfid.crc_errors above zero.",
        likely_cause=(
            "Degraded tag, metallic obstruction or ballast contamination near "
            "the tag, or marginal reader performance at speed."
        ),
        action=(
            "Identify the affected tag locations, clean and re-secure the tags, "
            "and replace any tag that repeats the error on subsequent runs."
        ),
        responsibility=Owner.ST_KAVACH,
        escalation=MONITOR,
    ),
    _f(
        code="KVCH-TAG-003",
        title="Unknown tag identity read - not in the track database",
        subsystem=Subsystem.TAG,
        severity=Severity.CRITICAL,
        signature="rfid.unknown_tag_ids greater than zero.",
        likely_cause=(
            "Tag laid but not entered in the track database, a tag recovered "
            "from another section and re-used, a tag programmed with the wrong "
            "identity, or an unauthorised tag placed in the track."
        ),
        action=(
            "Do not dismiss as a data entry error until the tag is physically "
            "identified. Locate the tag by kilometrage, read its programmed "
            "identity, and reconcile against the sanctioned track database. An "
            "unaccounted tag in the running line is a safety and security "
            "matter."
        ),
        responsibility=Owner.ST_KAVACH,
        escalation=(
            "Advise Sr.DSTE and the zonal cyber security cell in addition to "
            "the S&T failure register entry; joint check with P.Way."
        ),
        references=("EN 50159 threat: insertion / masquerade of track-side data",),
    ),

    # ---------------------------------------------------------- location
    _f(
        code="KVCH-LOC-001",
        title="Onboard location error beyond tolerance",
        subsystem=Subsystem.LOCATION,
        severity=Severity.CRITICAL,
        signature="loc.error_m beyond the permitted location accuracy.",
        likely_cause=(
            "Accumulated odometry error from wheel slip or slide with a long "
            "gap between tag reads, incorrect wheel diameter entered after tyre "
            "turning, or a failed speed sensor channel."
        ),
        action=(
            "Verify the wheel diameter entered in the loco unit against the "
            "shed record after the last tyre turning, check both speed sensor "
            "channels, and confirm the tag spacing over the affected stretch."
        ),
        responsibility=Owner.SHED,
        escalation=UNUSUAL,
    ),
    _f(
        code="KVCH-LOC-002",
        title="Excessive wheel slip / slide reported by odometry",
        subsystem=Subsystem.LOCATION,
        severity=Severity.MINOR,
        signature="loc.odometer_slip_pct above the configured limit.",
        likely_cause=(
            "Poor adhesion conditions, sanding equipment defective, or a speed "
            "sensor channel degrading."
        ),
        action=(
            "Advise the shed to check the sanding equipment and both speed "
            "sensor channels at the next scheduled attention."
        ),
        responsibility=Owner.SHED,
        escalation=MONITOR,
    ),
    _f(
        code="KVCH-LOC-003",
        title="Time synchronisation lost or drifting",
        subsystem=Subsystem.LOCATION,
        severity=Severity.MAJOR,
        signature="No usable time source, or time.offset_ms beyond limit.",
        likely_cause=(
            "GNSS antenna or receiver fault, antenna cable damaged, or the unit "
            "has fallen back to its internal clock."
        ),
        action=(
            "Check the GNSS antenna, its cable run and the receiver. Kavach "
            "uses the time reference for log correlation and for the validity "
            "of exchanged messages - a drifting clock makes failure analysis "
            "unreliable and can cause messages to be rejected as stale."
        ),
        responsibility=Owner.ST_KAVACH,
        escalation=REGISTER,
    ),
    _f(
        code="KVCH-LOC-004",
        title="GNSS receiver without a valid fix",
        subsystem=Subsystem.LOCATION,
        severity=Severity.MINOR,
        signature="gnss.fix=V, or zero satellites visible.",
        likely_cause=(
            "Antenna obstruction or damage, water ingress in the antenna cable, "
            "or receiver fault. Expected while stabled in a shed or in a tunnel."
        ),
        action=(
            "Check antenna path and mounting. Correlate against location before "
            "raising a fault - no fix inside a shed or tunnel is normal."
        ),
        responsibility=Owner.ST_KAVACH,
        escalation=MONITOR,
    ),

    # ------------------------------------------------- signalling interface
    _f(
        code="KVCH-SIG-001",
        title="Interface to interlocking is down",
        subsystem=Subsystem.SIGNALLING,
        severity=Severity.CRITICAL,
        signature="ei.link_state=DOWN on a stationary unit.",
        likely_cause=(
            "Cable or media converter failure between the Kavach rack and the "
            "EI/RRI, interface card failure, or the interlocking end being "
            "under maintenance."
        ),
        action=(
            "Check the physical interface between the Kavach rack and the "
            "interlocking, the interface cards at both ends, and the media "
            "converters. Without signal aspect data the stationary unit cannot "
            "generate a movement authority."
        ),
        responsibility=Owner.ST_SIGNAL,
        escalation=UNUSUAL,
    ),
    _f(
        code="KVCH-SIG-002",
        title="Stale signal aspect data from interlocking",
        subsystem=Subsystem.SIGNALLING,
        severity=Severity.MAJOR,
        signature="ei.telegram_age_s beyond the configured limit while the link is up.",
        likely_cause=(
            "Interface process stalled at one end, or a partially failed link "
            "carrying no fresh telegrams."
        ),
        action=(
            "Check the interface process at both ends and restart it as per "
            "the OEM procedure under a proper disconnection memo. Data older "
            "than the timeout must not be relied on for aspect display."
        ),
        responsibility=Owner.ST_SIGNAL,
        escalation=UNUSUAL,
    ),
    _f(
        code="KVCH-SIG-003",
        title="Aspect mismatch between Kavach and signal",
        subsystem=Subsystem.SIGNALLING,
        severity=Severity.CRITICAL,
        signature="ei.aspect_mismatch_count greater than zero.",
        likely_cause=(
            "Wrong signal identity or aspect mapping in the Kavach "
            "configuration, an interface wiring error, or a genuine signalling "
            "fault."
        ),
        action=(
            "Stop further reliance on the affected signal's Kavach data and "
            "carry out a joint check of the aspect mapping against the "
            "signalling plan and the interface wiring. Do not adjust the "
            "mapping without the approved correspondence check."
        ),
        responsibility=Owner.ST_SIGNAL,
        escalation=UNUSUAL,
    ),

    # ------------------------------------------------------------- power
    _f(
        code="KVCH-PWR-001",
        title="Mains supply failed - unit on battery",
        subsystem=Subsystem.POWER,
        severity=Severity.MAJOR,
        signature="power.mains_state=FAIL with battery backup remaining.",
        likely_cause=(
            "Grid supply failure at the station, incoming supply MCB tripped, "
            "or IPS input failure."
        ),
        action=(
            "Confirm the DG / alternate supply arrangement and the remaining "
            "battery backup. Restore mains before the backup is exhausted."
        ),
        responsibility=Owner.ST_POWER,
        escalation=REGISTER,
    ),
    _f(
        code="KVCH-PWR-002",
        title="Battery backup below the required reserve",
        subsystem=Subsystem.POWER,
        severity=Severity.CRITICAL,
        signature="power.battery_backup_min below the configured reserve.",
        likely_cause=(
            "Aged battery bank, cells not topped up, charger not charging, or "
            "a prolonged mains failure."
        ),
        action=(
            "Attend the IPS immediately. Arrange alternate supply and replace "
            "or recondition the battery bank. Loss of supply takes the Kavach "
            "installation out of service for the whole station."
        ),
        responsibility=Owner.ST_POWER,
        escalation=UNUSUAL,
    ),
    _f(
        code="KVCH-PWR-003",
        title="IPS charger not charging",
        subsystem=Subsystem.POWER,
        severity=Severity.MAJOR,
        signature="power.charger_state not in a charging / float state.",
        likely_cause=(
            "Charger module failure, input fuse blown, or charger switched off "
            "after maintenance and not restored."
        ),
        action=(
            "Check the charger module, its input supply and fuses, and restore "
            "float charging. Verify the module was not left off after the last "
            "attention."
        ),
        responsibility=Owner.ST_POWER,
        escalation=REGISTER,
    ),
    _f(
        code="KVCH-PWR-004",
        title="DC supply voltage outside working range",
        subsystem=Subsystem.POWER,
        severity=Severity.MAJOR,
        signature="power.dc_volts outside the configured band for the asset.",
        likely_cause=(
            "Battery discharged, a weak cell, loose termination, or a "
            "regulation fault in the IPS."
        ),
        action=(
            "Measure the bank and individual cell voltages, check terminations "
            "for looseness and corrosion, and replace any weak cell."
        ),
        responsibility=Owner.ST_POWER,
        escalation=REGISTER,
    ),

    # ---------------------------------------------------- onboard / loco
    _f(
        code="KVCH-OBU-001",
        title="Kavach isolated on the loco",
        subsystem=Subsystem.ONBOARD,
        severity=Severity.CRITICAL,
        signature="kavach.isolation_state=ISOLATED.",
        likely_cause=(
            "Unit isolated by the Loco Pilot after a failure en route, or left "
            "isolated after shed attention and not restored."
        ),
        action=(
            "Establish when and why the unit was isolated and by whom. A loco "
            "working an isolated Kavach through a Kavach-equipped section has "
            "no train protection - the loco must be attended and the isolation "
            "reversed at the earliest, and the reason recorded."
        ),
        responsibility=Owner.SHED,
        escalation=(
            "Advise Section Controller and the loco shed; record in the S&T "
            "failure register and in the loco's repair book; include in the "
            "divisional Kavach performance return."
        ),
    ),
    _f(
        code="KVCH-OBU-002",
        title="Driver Machine Interface not healthy",
        subsystem=Subsystem.ONBOARD,
        severity=Severity.MAJOR,
        signature="dmi.state not healthy.",
        likely_cause=(
            "DMI display or its cable failed, backlight failure, or the DMI "
            "lost communication with the loco unit."
        ),
        action=(
            "Attend the DMI and its cabling at the next crew-change or shed "
            "attention. Without a DMI the Loco Pilot cannot see the movement "
            "authority or the braking curve."
        ),
        responsibility=Owner.SHED,
        escalation=REGISTER,
    ),
    _f(
        code="KVCH-OBU-003",
        title="Brake interface fault",
        subsystem=Subsystem.ONBOARD,
        severity=Severity.CRITICAL,
        signature="brake.interface_state not healthy, or the last brake test failed.",
        likely_cause=(
            "Brake interface unit or its valve failed, pneumatic connection "
            "leaking, or wiring to the brake interface disturbed."
        ),
        action=(
            "The loco unit cannot apply the brake - hold the loco for shed "
            "attention. Check the brake interface unit, its valve and the "
            "pneumatic and electrical connections, and repeat the brake test."
        ),
        responsibility=Owner.SHED,
        escalation=UNUSUAL,
    ),
    _f(
        code="KVCH-OBU-004",
        title="SoS message recorded",
        subsystem=Subsystem.ONBOARD,
        severity=Severity.INFO,
        signature="sos.messages_24h greater than zero.",
        likely_cause=(
            "SoS raised by a Loco Pilot, or generated during a test or a "
            "demonstration run."
        ),
        action=(
            "Correlate the SoS with the control chart and the loco log to "
            "confirm whether it relates to a real occurrence or a test. Every "
            "SoS should be accounted for."
        ),
        responsibility=Owner.DIV_CELL,
        escalation=MONITOR,
    ),
    _f(
        code="KVCH-OBU-005",
        title="Repeated automatic brake applications",
        subsystem=Subsystem.ONBOARD,
        severity=Severity.MINOR,
        signature="brake.applications_last_24h above the review threshold.",
        likely_cause=(
            "Genuine over-speed or authority-limit interventions, a section "
            "with a speed profile needing review, or an onboard fault causing "
            "spurious interventions."
        ),
        action=(
            "Review the applications against the speed profile and the driving "
            "log with the LI/CLI. Repeated interventions at the same location "
            "point to a track database or speed profile issue rather than "
            "driving."
        ),
        responsibility=Owner.DIV_CELL,
        escalation=MONITOR,
    ),

    # ------------------------------------------------- software / track DB
    _f(
        code="KVCH-CFG-001",
        title="Track database version mismatch",
        subsystem=Subsystem.CONFIG,
        severity=Severity.CRITICAL,
        signature="sw.track_db_version differs from the sanctioned version in the register.",
        likely_cause=(
            "A track database revision was issued after a yard remodelling, "
            "speed revision or new tag laying, and this unit was not updated."
        ),
        action=(
            "Update the unit to the sanctioned track database version under the "
            "approved procedure, with correspondence check and record of the "
            "version loaded. Units running different versions of the track data "
            "over the same section can behave inconsistently."
        ),
        responsibility=Owner.ST_KAVACH,
        escalation=UNUSUAL,
    ),
    _f(
        code="KVCH-CFG-002",
        title="Application software version not as sanctioned",
        subsystem=Subsystem.CONFIG,
        severity=Severity.MAJOR,
        signature="sw.version differs from the version recorded in the register.",
        likely_cause=(
            "Card replaced from stock carrying an older build, or an OEM update "
            "applied to part of the section only."
        ),
        action=(
            "Reconcile with the OEM's release note and the version approved for "
            "the section, and bring the unit to the sanctioned version under a "
            "proper disconnection memo."
        ),
        responsibility=Owner.OEM,
        escalation=REGISTER,
    ),
    _f(
        code="KVCH-CFG-003",
        title="Configuration checksum changed since commissioning",
        subsystem=Subsystem.CONFIG,
        severity=Severity.MAJOR,
        signature="config.checksum differs from the value recorded at commissioning.",
        likely_cause=(
            "An authorised change made without updating the register, or an "
            "unauthorised change to the site configuration."
        ),
        action=(
            "Establish who changed the configuration and under what authority. "
            "If no authorised change is on record, preserve the logs and treat "
            "it as a potential unauthorised modification."
        ),
        responsibility=Owner.CYBER,
        escalation=(
            "Advise Sr.DSTE and the zonal cyber security cell; preserve the "
            "unit's logs before any further work."
        ),
        references=("IEC 62443-2-1: change control on the automation solution",),
    ),

    # ----------------------------------------------------------- security
    _f(
        code="KVCH-SEC-001",
        title="Message authentication failures recorded",
        subsystem=Subsystem.SECURITY,
        severity=Severity.MAJOR,
        signature="sec.auth_failures_24h above the review threshold.",
        likely_cause=(
            "Key mismatch after a unit replacement, a unit running an old key "
            "set, corruption on a marginal radio link, or an attempt to inject "
            "forged messages."
        ),
        action=(
            "Check the key set loaded in the unit against the section's current "
            "key issue, and correlate the failures with radio quality. "
            "Authentication failures on a good radio link are not a "
            "propagation problem."
        ),
        responsibility=Owner.CYBER,
        escalation=(
            "Advise Sr.DSTE and the zonal cyber security cell if failures "
            "persist on a healthy link."
        ),
        references=("EN 50159 threat: masquerade / message corruption",),
    ),
    _f(
        code="KVCH-SEC-002",
        title="Cryptographic key set nearing or past expiry",
        subsystem=Subsystem.SECURITY,
        severity=Severity.MAJOR,
        signature="sec.key_expiry_days at or below the configured notice period.",
        likely_cause="Scheduled key rotation not carried out for this unit.",
        action=(
            "Plan the key rotation for this unit within the notice period, "
            "along with the other units of the section, so that the section "
            "is not left with mixed key sets."
        ),
        responsibility=Owner.CYBER,
        escalation=REGISTER,
    ),
    _f(
        code="KVCH-SEC-003",
        title="Unknown peer units attempting to communicate",
        subsystem=Subsystem.SECURITY,
        severity=Severity.MAJOR,
        signature="sec.unknown_peer_attempts_24h above zero.",
        likely_cause=(
            "A newly commissioned unit not yet added to the register, a unit "
            "from an adjacent section with overlapping coverage, or an "
            "unauthorised transmitter."
        ),
        action=(
            "Identify each unknown unit identity against the register and the "
            "adjacent section's register. Any identity that cannot be "
            "accounted for is to be treated as an intrusion attempt."
        ),
        responsibility=Owner.CYBER,
        escalation=(
            "Advise Sr.DSTE and the zonal cyber security cell with the unit "
            "identities observed."
        ),
        references=("EN 50159 threat: masquerade",),
    ),
    _f(
        code="KVCH-SEC-004",
        title="Maintenance port left open",
        subsystem=Subsystem.SECURITY,
        severity=Severity.MAJOR,
        signature="sec.maint_port_open is true.",
        likely_cause=(
            "Maintenance access enabled during attention and not disabled "
            "afterwards."
        ),
        action=(
            "Disable the maintenance port and confirm the unit's access "
            "settings match the hardened baseline. Maintenance access is to be "
            "opened only for the duration of the work."
        ),
        responsibility=Owner.CYBER,
        escalation=REGISTER,
        references=("IEC 62443-3-3 SR 1.1 / SR 2.1: access control",),
    ),
    _f(
        code="KVCH-SEC-005",
        title="Default or shared credentials in use",
        subsystem=Subsystem.SECURITY,
        severity=Severity.CRITICAL,
        signature="sec.default_credentials is true.",
        likely_cause=(
            "Unit commissioned with OEM default credentials, or credentials "
            "restored to default after a card replacement."
        ),
        action=(
            "Change the credentials to the division's managed set and record "
            "the change. Default credentials on a train protection system are "
            "an immediate finding, not a housekeeping item."
        ),
        responsibility=Owner.CYBER,
        escalation=(
            "Advise Sr.DSTE and the zonal cyber security cell; verify the same "
            "condition across the rest of the section's units."
        ),
        references=("IEC 62443-3-3 SR 1.5: authenticator management",),
    ),
    _f(
        code="KVCH-SEC-006",
        title="Unsigned firmware present",
        subsystem=Subsystem.SECURITY,
        severity=Severity.CRITICAL,
        signature="sec.firmware_signed is false.",
        likely_cause=(
            "Firmware loaded outside the OEM's signed release process, or "
            "signature verification disabled on the unit."
        ),
        action=(
            "Do not accept the unit into service until the firmware is "
            "verified against the OEM's signed release. Preserve the loaded "
            "image for examination."
        ),
        responsibility=Owner.CYBER,
        escalation=(
            "Advise Sr.DSTE, the zonal cyber security cell and the OEM; "
            "preserve the image and the unit logs."
        ),
        references=("IEC 62443-3-3 SR 3.4: software and information integrity",),
    ),
    _f(
        code="KVCH-SEC-007",
        title="Log extraction by removable media",
        subsystem=Subsystem.SECURITY,
        severity=Severity.MINOR,
        signature="sec.usb_events_24h above zero.",
        likely_cause=(
            "Routine log extraction by maintenance staff, or removable media "
            "used on the unit without authority."
        ),
        action=(
            "Reconcile each event with the maintenance record. Removable media "
            "is the usual route by which malware reaches an otherwise isolated "
            "signalling network."
        ),
        responsibility=Owner.CYBER,
        escalation=MONITOR,
        references=("IEC 62443-3-3 SR 3.2: malicious code protection",),
    ),
]}


class UnknownFaultCode(ValueError):
    """Raised when a fault code is not in the library."""


def get(code: str) -> FaultDefinition:
    """Look up a fault definition, raising a helpful error for a bad code."""
    try:
        return FAULTS[code]
    except KeyError:
        raise UnknownFaultCode(
            f"Unknown fault code {code!r}. Run 'kavach-diag faults' to list them."
        ) from None


def by_subsystem() -> dict[str, list[FaultDefinition]]:
    grouped: dict[str, list[FaultDefinition]] = {}
    for definition in FAULTS.values():
        grouped.setdefault(definition.subsystem, []).append(definition)
    for entries in grouped.values():
        entries.sort(key=lambda d: d.code)
    return grouped


HEALTHY = FAULTS["KVCH-OK-000"]
