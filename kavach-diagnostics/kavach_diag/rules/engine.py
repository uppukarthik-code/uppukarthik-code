"""The rule registry and the evaluation loop.

Rules are small functions that look at one asset's snapshot and return zero or
more findings. Each rule is registered under a check family ("radio", "power",
...) and only runs when the asset's profile says that family applies, which is
what keeps a loco unit from being failed for having no interlocking interface.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from importlib import import_module

from .. import faults
from ..config import Settings, profile_for
from ..model import Asset, AssetResult, Finding, Snapshot


@dataclass
class RuleContext:
    asset: Asset
    snapshot: Snapshot
    settings: Settings

    @property
    def thresholds(self):
        return self.settings.thresholds


Rule = Callable[[RuleContext], list[Finding]]

REGISTRY: dict[str, list[Rule]] = {}


def register(family: str) -> Callable[[Rule], Rule]:
    """Register a rule under a check family."""

    def decorator(rule: Rule) -> Rule:
        REGISTRY.setdefault(family, []).append(rule)
        return rule

    return decorator


RULE_MODULES = (
    "radio",
    "rfid",
    "location",
    "signalling",
    "power",
    "onboard",
    "config_rules",
    "security",
)


def _load_rule_modules() -> None:
    """Import the rule modules so their @register decorators run."""
    for module in RULE_MODULES:
        import_module(f".{module}", __package__)


def evaluate(
    asset: Asset,
    snapshot: Snapshot | None,
    settings: Settings | None = None,
    now: datetime | None = None,
) -> AssetResult:
    """Assess one asset and return its result."""
    _load_rule_modules()
    settings = settings or Settings()
    now = now or datetime.now()

    if snapshot is None or snapshot.is_empty:
        empty = snapshot or Snapshot(asset_id=asset.asset_id)
        finding = faults.get("KVCH-SYS-001").to_finding(
            {"asset": asset.asset_id, "register_entry": asset.describe()}
        )
        return AssetResult(asset=asset, snapshot=empty, findings=[finding])

    findings: list[Finding] = []

    stale_after = timedelta(hours=settings.thresholds.snapshot_stale_after_hours)
    if snapshot.recorded_at is not None and now - snapshot.recorded_at > stale_after:
        age_hours = round((now - snapshot.recorded_at).total_seconds() / 3600, 1)
        findings.append(
            faults.get("KVCH-SYS-002").to_finding(
                {
                    "last_record": snapshot.age_note,
                    "age_hours": age_hours,
                    "limit_hours": settings.thresholds.snapshot_stale_after_hours,
                }
            )
        )

    context = RuleContext(asset=asset, snapshot=snapshot, settings=settings)
    families = profile_for(asset.asset_type).checks

    for family in families:
        for rule in REGISTRY.get(family, []):
            findings.extend(rule(context) or [])

    if settings.ignore_codes:
        findings = [f for f in findings if f.fault_code not in settings.ignore_codes]

    if not findings:
        findings.append(
            faults.HEALTHY.to_finding(
                {"checks_applied": ", ".join(families) or "none"}
            )
        )

    return AssetResult(asset=asset, snapshot=snapshot, findings=findings)


def evaluate_all(
    assets: list[Asset],
    snapshots: dict[str, Snapshot],
    settings: Settings | None = None,
    now: datetime | None = None,
) -> list[AssetResult]:
    """Assess a whole register against a set of snapshots."""
    return [
        evaluate(asset, snapshots.get(asset.asset_id), settings, now)
        for asset in assets
    ]
