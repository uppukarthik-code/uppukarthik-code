"""Telemetry collectors.

A collector turns some export produced by the monitoring side of a Kavach
installation into ``Snapshot`` objects. Collectors are deliberately one-way and
offline: the diagnostic tool reads what the system has already recorded and
never opens a session to a unit.
"""

from .base import METRICS, Collector, canonical_metric
from .file_collector import FileCollector, load_snapshots
from .simulator import SimulatedCollector, write_simulated_telemetry

__all__ = [
    "METRICS",
    "Collector",
    "canonical_metric",
    "FileCollector",
    "load_snapshots",
    "SimulatedCollector",
    "write_simulated_telemetry",
]
