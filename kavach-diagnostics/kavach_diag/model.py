"""Core data model for the Kavach diagnostic platform.

The model deliberately separates three things:

* ``Asset``      - what the Indian Railways installation register says exists.
* ``Snapshot``   - what an exported telemetry / data-logger record says the
                   asset was doing at a point in time.
* ``Finding``    - what the diagnostic engine concluded, with the evidence
                   that supports the conclusion.

Nothing in this module talks to a Kavach unit. Snapshots always arrive from an
offline export (see ``kavach_diag.collectors``), which keeps the tool outside
the safety envelope of the SIL-4 system it reports on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


class Severity:
    """Severity ladder, ordered worst-first for sorting and roll-up."""

    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    WARNING = "WARNING"
    INFO = "INFO"
    OK = "OK"
    NO_DATA = "NO_DATA"

    ORDER = [CRITICAL, MAJOR, MINOR, WARNING, NO_DATA, INFO, OK]

    @classmethod
    def rank(cls, severity: str) -> int:
        try:
            return cls.ORDER.index(severity)
        except ValueError:
            return len(cls.ORDER)

    @classmethod
    def worst(cls, severities) -> str:
        severities = list(severities)
        if not severities:
            return cls.OK
        return min(severities, key=cls.rank)


class AssetType:
    """Kavach sub-system types as named in RDSO/IR usage."""

    SKU = "SKU"          # Stationary Kavach Unit (station / IB / LC)
    LKU = "LKU"          # Loco Kavach Unit (onboard)
    TWR = "TWR"          # Radio infrastructure: tower with static radio units
    RIU = "RIU"          # Remote Interface Unit (interfaces to signalling)

    ALL = [SKU, LKU, TWR, RIU]

    LABELS = {
        SKU: "Stationary Kavach Unit",
        LKU: "Loco Kavach Unit",
        TWR: "Kavach Radio Tower / Static Radio Unit",
        RIU: "Remote Interface Unit",
    }


@dataclass
class Asset:
    """One Kavach installation as recorded in the divisional asset register."""

    asset_id: str
    asset_type: str
    kavach_id: str = ""
    oem: str = ""
    spec_version: str = ""
    zone: str = ""
    division: str = ""
    section: str = ""
    station_code: str = ""
    station_name: str = ""
    km_post: str = ""
    line: str = ""
    loco_number: str = ""
    loco_class: str = ""
    shed_code: str = ""
    commissioned_on: str = ""
    # Sanctioned values from the register, compared against what the unit reports.
    sanctioned_sw_version: str = ""
    sanctioned_track_db: str = ""
    commissioning_checksum: str = ""
    assigned_freq_mhz: str = ""
    notes: str = ""

    def __post_init__(self) -> None:
        self.asset_type = (self.asset_type or "").strip().upper()

    @property
    def is_onboard(self) -> bool:
        return self.asset_type == AssetType.LKU

    @property
    def is_stationary(self) -> bool:
        return self.asset_type in (AssetType.SKU, AssetType.TWR, AssetType.RIU)

    @property
    def location(self) -> str:
        """Human location string in the form an IR engineer would use."""
        if self.is_onboard:
            bits = [b for b in (self.loco_class, self.loco_number) if b]
            loco = " ".join(bits) or self.asset_id
            return f"{loco} ({self.shed_code})" if self.shed_code else loco
        bits = []
        if self.station_code:
            name = self.station_name or ""
            bits.append(f"{self.station_code}{' - ' + name if name else ''}")
        if self.km_post:
            bits.append(f"KM {self.km_post}")
        if self.line:
            bits.append(self.line)
        return " / ".join(bits) or self.asset_id

    @property
    def group(self) -> str:
        """Grouping key used by the divisional report."""
        if self.is_onboard:
            return f"{self.shed_code or 'UNKNOWN SHED'} (locos)"
        return self.section or self.division or "UNGROUPED"

    def describe(self) -> str:
        label = AssetType.LABELS.get(self.asset_type, self.asset_type)
        return f"{self.asset_id} - {label} - {self.location}"


@dataclass
class Snapshot:
    """A normalised set of metric readings exported for one asset."""

    asset_id: str
    recorded_at: datetime | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    source: str = ""

    def has(self, metric: str) -> bool:
        return metric in self.metrics and self.metrics[metric] not in ("", None)

    def get(self, metric: str, default: Any = None) -> Any:
        value = self.metrics.get(metric, default)
        if value in ("", None):
            return default
        return value

    def text(self, metric: str, default: str = "") -> str:
        value = self.get(metric, default)
        return str(value).strip()

    def upper(self, metric: str, default: str = "") -> str:
        return self.text(metric, default).upper()

    def number(self, metric: str, default: float | None = None) -> float | None:
        """Return a metric as a float, or ``default`` when absent/unparsable."""
        raw = self.get(metric)
        if raw is None:
            return default
        try:
            return float(str(raw).strip())
        except (TypeError, ValueError):
            return default

    def integer(self, metric: str, default: int | None = None) -> int | None:
        value = self.number(metric)
        if value is None:
            return default
        return int(value)

    def flag(self, metric: str, default: bool | None = None) -> bool | None:
        """Interpret a metric as a boolean using the vocabularies seen in exports."""
        raw = self.get(metric)
        if raw is None:
            return default
        if isinstance(raw, bool):
            return raw
        token = str(raw).strip().upper()
        if token in ("1", "TRUE", "YES", "Y", "OK", "PRESENT", "ON", "UP", "HEALTHY"):
            return True
        if token in ("0", "FALSE", "NO", "N", "ABSENT", "OFF", "DOWN", "FAIL", "FAILED"):
            return False
        return default

    @property
    def is_empty(self) -> bool:
        return not self.metrics

    @property
    def age_note(self) -> str:
        if self.recorded_at is None:
            return "timestamp not supplied"
        return self.recorded_at.strftime("%d-%m-%Y %H:%M IST")


@dataclass
class Finding:
    """One classified condition, with the evidence that produced it."""

    fault_code: str
    title: str
    severity: str
    likely_cause: str
    action: str
    responsibility: str = ""
    escalation: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    subsystem: str = ""

    @property
    def evidence_text(self) -> str:
        if not self.evidence:
            return "-"
        return "; ".join(f"{k}={v}" for k, v in self.evidence.items())


@dataclass
class AssetResult:
    """The complete diagnostic outcome for one asset."""

    asset: Asset
    snapshot: Snapshot
    findings: list[Finding] = field(default_factory=list)

    @property
    def severity(self) -> str:
        return Severity.worst(f.severity for f in self.findings)

    @property
    def headline(self) -> Finding | None:
        if not self.findings:
            return None
        return sorted(self.findings, key=lambda f: Severity.rank(f.severity))[0]

    @property
    def diagnosis(self) -> str:
        head = self.headline
        return head.title if head else "No assessment produced"

    def by_severity(self) -> list[Finding]:
        return sorted(self.findings, key=lambda f: Severity.rank(f.severity))

    def counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for finding in self.findings:
            counts[finding.severity] = counts.get(finding.severity, 0) + 1
        return counts
