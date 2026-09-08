"""Command line interface for the Kavach diagnostic tool."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from . import __version__, faults, report
from .collectors import METRICS, FileCollector, SimulatedCollector
from .collectors.file_collector import parse_timestamp
from .collectors.simulator import SCENARIOS, write_simulated_telemetry
from .config import ASSET_PROFILES, Settings, Thresholds
from .inventory import InventoryError, load_inventory, summarise
from .model import Severity
from .rules import evaluate_all

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_ERROR = 2


def _as_of(value: str | None, flag: str) -> datetime | None:
    """Parse a user supplied 'as at' time, so a run can be reproduced."""
    if not value:
        return None
    parsed = parse_timestamp(value)
    if parsed is None:
        raise ValueError(f"{flag}: could not read {value!r} as a date/time")
    return parsed


def _settings(args: argparse.Namespace) -> Settings:
    thresholds = Thresholds.load(getattr(args, "thresholds", None))
    ignore = tuple(
        code.strip().upper()
        for code in (getattr(args, "ignore", "") or "").split(",")
        if code.strip()
    )
    return Settings(thresholds=thresholds, ignore_codes=ignore)


# ------------------------------------------------------------------ commands


def cmd_scan(args: argparse.Namespace) -> int:
    assets = load_inventory(args.inventory)
    if args.asset:
        wanted = {a.strip() for a in args.asset.split(",") if a.strip()}
        assets = [a for a in assets if a.asset_id in wanted]
        if not assets:
            print(f"No asset in the register matches {args.asset!r}", file=sys.stderr)
            return EXIT_ERROR

    now = _as_of(args.now, "--now")

    if args.simulate:
        collector = SimulatedCollector(scenario=args.simulate, seed=args.seed, now=now)
    elif args.telemetry:
        collector = FileCollector(args.telemetry)
    else:
        print(
            "Supply --telemetry <file|dir> with exported data, or --simulate "
            f"<{'|'.join(SCENARIOS)}> to run against generated data.",
            file=sys.stderr,
        )
        return EXIT_ERROR

    snapshots = collector.collect(assets)
    results = evaluate_all(assets, snapshots, _settings(args), now=now)

    formats = {f.strip().lower() for f in args.format.split(",")}
    if "all" in formats:
        formats = {"text", "csv", "html"}

    if "text" in formats:
        if args.detail:
            for result in results:
                print(report.render_asset_report(result))
        print(report.render_summary(results))

    out_dir = Path(args.out)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    written: list[Path] = []

    if "csv" in formats:
        written.append(report.write_csv(results, out_dir / f"kavach-scan-{stamp}.csv"))
    if "html" in formats:
        first = results[0].asset if results else None
        context = {
            "Zone": first.zone if first else "",
            "Division": first.division if first else "",
            "Source": collector.name,
        }
        written.append(
            report.write_html(
                results,
                out_dir / f"kavach-health-{stamp}.html",
                title="Kavach Health Report",
                context=context,
            )
        )

    for path in written:
        print(f"Written: {path}")

    worst = Severity.worst(r.severity for r in results)
    return EXIT_FINDINGS if Severity.rank(worst) <= Severity.rank(Severity.MAJOR) else EXIT_OK


def cmd_explain(args: argparse.Namespace) -> int:
    definition = faults.get(args.code.upper())
    print(f"{definition.code} - {definition.title}")
    print(report.LINE)
    print(f"Subsystem      : {definition.subsystem}")
    print(f"Default severity: {definition.severity}")
    print(f"Signature      : {definition.signature}")
    print(f"Likely cause   : {definition.likely_cause}")
    print(f"Action         : {definition.action}")
    print(f"Responsibility : {definition.responsibility}")
    print(f"Escalation     : {definition.escalation}")
    if definition.references:
        print(f"References     : {'; '.join(definition.references)}")
    return EXIT_OK


def cmd_faults(args: argparse.Namespace) -> int:
    for subsystem, definitions in sorted(faults.by_subsystem().items()):
        print(f"\n{subsystem}")
        print(report.LINE)
        for definition in definitions:
            print(f"  {definition.code:<14} {definition.severity:<9} {definition.title}")
    print()
    return EXIT_OK


def cmd_metrics(args: argparse.Namespace) -> int:
    print("Canonical telemetry vocabulary")
    print(report.LINE)
    for name, description in METRICS.items():
        print(f"  {name:<34} {description}")
    print()
    print("Asset profiles (which check families run per unit type)")
    print(report.LINE)
    for asset_type, profile in ASSET_PROFILES.items():
        print(f"  {asset_type:<5} {', '.join(profile.checks)}")
        print(f"        {profile.description}")
    return EXIT_OK


def cmd_simulate(args: argparse.Namespace) -> int:
    assets = load_inventory(args.inventory)
    path = write_simulated_telemetry(
        assets,
        args.out,
        scenario=args.scenario,
        seed=args.seed,
        now=_as_of(args.as_of, "--as-of"),
    )
    counts = summarise(assets)
    breakdown = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
    print(f"Simulated '{args.scenario}' telemetry for {len(assets)} assets ({breakdown})")
    print(f"Written: {path}")
    return EXIT_OK


# -------------------------------------------------------------------- parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kavach-diag",
        description=(
            "Offline health and fault classification for Indian Railways Kavach "
            "installations. Reads exported telemetry only; never connects to a "
            "Kavach unit."
        ),
    )
    parser.add_argument("--version", action="version", version=f"kavach-diag {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="assess a register against exported telemetry")
    scan.add_argument("--inventory", required=True, help="asset register CSV")
    scan.add_argument("--telemetry", help="exported telemetry file or directory")
    scan.add_argument(
        "--simulate",
        choices=SCENARIOS,
        help="generate telemetry instead of reading it (for demonstration/testing)",
    )
    scan.add_argument("--seed", type=int, default=20250908, help="simulator seed")
    scan.add_argument("--out", default="reports", help="output directory (default: reports)")
    scan.add_argument(
        "--format",
        default="text",
        help="comma separated: text, csv, html, all (default: text)",
    )
    scan.add_argument("--detail", action="store_true", help="print a report per asset")
    scan.add_argument("--asset", help="limit the scan to these asset ids (comma separated)")
    scan.add_argument("--thresholds", help="JSON file overriding the default thresholds")
    scan.add_argument("--ignore", help="fault codes to suppress (comma separated)")
    scan.add_argument(
        "--now",
        help=(
            "treat this date/time as 'now' when judging telemetry age, e.g. "
            "'2026-09-08 06:00' - use it to reproduce a past scan"
        ),
    )
    scan.set_defaults(func=cmd_scan)

    explain = sub.add_parser("explain", help="show one fault definition in full")
    explain.add_argument("code", help="fault code, e.g. KVCH-RAD-002")
    explain.set_defaults(func=cmd_explain)

    listing = sub.add_parser("faults", help="list the fault library")
    listing.set_defaults(func=cmd_faults)

    metrics = sub.add_parser("metrics", help="list the telemetry vocabulary and profiles")
    metrics.set_defaults(func=cmd_metrics)

    simulate = sub.add_parser("simulate", help="write simulated telemetry to a CSV")
    simulate.add_argument("--inventory", required=True, help="asset register CSV")
    simulate.add_argument("--out", required=True, help="telemetry CSV to write")
    simulate.add_argument("--scenario", choices=SCENARIOS, default="mixed")
    simulate.add_argument("--seed", type=int, default=20250908)
    simulate.add_argument(
        "--as-of", dest="as_of", help="timestamp the generated readings against this time"
    )
    simulate.set_defaults(func=cmd_simulate)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (InventoryError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_ERROR
    except FileNotFoundError as error:
        print(f"error: {error}", file=sys.stderr)
        return EXIT_ERROR
    except BrokenPipeError:
        # Output was piped into something that closed early, e.g. 'head'.
        return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
