"""Kavach Diagnostics - an offline health and fault-classification tool for
Indian Railways Kavach (Train Collision Avoidance System) installations.

The package is read-only with respect to the signalling system: it consumes
exported telemetry and data-logger records and produces classifications,
engineering actions and divisional reports. It never connects to, commands or
configures a Kavach unit.
"""

__version__ = "0.1.0"

from .model import Asset, AssetResult, AssetType, Finding, Severity, Snapshot

__all__ = [
    "Asset",
    "AssetResult",
    "AssetType",
    "Finding",
    "Severity",
    "Snapshot",
    "__version__",
]
