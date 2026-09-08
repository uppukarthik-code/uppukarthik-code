"""Reporting: per-asset text, divisional CSV and an HTML health report.

The reports are shaped for how the output actually gets used - a text block an
SSE can paste into the failure register, a CSV the divisional Kavach cell can
sort, and one HTML page that can be circulated after the daily scan.
"""

from __future__ import annotations

import csv
import html
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from .model import AssetResult, Severity

LINE = "-" * 68
DOUBLE = "=" * 68

SEVERITY_COLOURS = {
    Severity.CRITICAL: "#b3261e",
    Severity.MAJOR: "#c2410c",
    Severity.MINOR: "#a16207",
    Severity.WARNING: "#6b7280",
    Severity.NO_DATA: "#4b5563",
    Severity.INFO: "#1d4ed8",
    Severity.OK: "#15803d",
}


# --------------------------------------------------------------- text report


def render_asset_report(result: AssetResult) -> str:
    asset = result.asset
    lines: list[str] = []
    lines.append(DOUBLE)
    lines.append(f"KAVACH DIAGNOSTIC REPORT - {asset.asset_id}")
    lines.append(DOUBLE)
    lines.append("")

    lines.append("ASSET")
    lines.append(LINE)
    rows = [
        ("Unit type", asset.asset_type),
        ("Kavach ID", asset.kavach_id or "-"),
        ("Location", asset.location),
        ("Zone / Division", f"{asset.zone or '-'} / {asset.division or '-'}"),
        ("Section", asset.section or "-"),
        ("OEM / Spec", f"{asset.oem or '-'} / {asset.spec_version or '-'}"),
        ("Telemetry as at", result.snapshot.age_note),
        ("Telemetry source", result.snapshot.source or "-"),
    ]
    for label, value in rows:
        lines.append(f"{label:<22}: {value}")
    lines.append("")

    lines.append("ASSESSMENT")
    lines.append(LINE)
    lines.append(f"{'Overall':<22}: {result.severity}")
    lines.append(f"{'Diagnosis':<22}: {result.diagnosis}")
    lines.append("")

    for index, finding in enumerate(result.by_severity(), start=1):
        lines.append(f"[{index}] {finding.severity} - {finding.fault_code}")
        lines.append(f"    {finding.title}")
        lines.append(f"    Subsystem     : {finding.subsystem}")
        lines.append(f"    Evidence      : {finding.evidence_text}")
        lines.append(f"    Likely cause  : {finding.likely_cause}")
        lines.append(f"    Action        : {finding.action}")
        if finding.responsibility and finding.responsibility != "-":
            lines.append(f"    Responsibility: {finding.responsibility}")
        if finding.escalation and finding.escalation != "-":
            lines.append(f"    Escalation    : {finding.escalation}")
        lines.append("")

    return "\n".join(lines)


def render_summary(results: list[AssetResult]) -> str:
    counts = Counter(result.severity for result in results)
    lines = [DOUBLE, "SCAN SUMMARY", DOUBLE, ""]
    lines.append(f"{'Assets assessed':<22}: {len(results)}")
    for severity in Severity.ORDER:
        if counts.get(severity):
            lines.append(f"{severity:<22}: {counts[severity]}")
    lines.append("")

    attention = [
        r
        for r in results
        if Severity.rank(r.severity) <= Severity.rank(Severity.MAJOR)
    ]
    if attention:
        lines.append("REQUIRING ATTENTION")
        lines.append(LINE)
        for result in sorted(attention, key=lambda r: Severity.rank(r.severity)):
            head = result.headline
            code = head.fault_code if head else "-"
            lines.append(
                f"{result.severity:<9} {result.asset.asset_id:<12} {code:<13} "
                f"{result.diagnosis}"
            )
        lines.append("")
    else:
        lines.append("No critical or major conditions in this scan.")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------- CSV report

CSV_COLUMNS = [
    "asset_id",
    "asset_type",
    "kavach_id",
    "zone",
    "division",
    "section",
    "station_code",
    "km_post",
    "loco_number",
    "shed_code",
    "overall_severity",
    "fault_code",
    "severity",
    "subsystem",
    "diagnosis",
    "likely_cause",
    "recommended_action",
    "responsibility",
    "escalation",
    "evidence",
    "telemetry_as_at",
]


def write_csv(results: list[AssetResult], path: str | Path) -> Path:
    """One row per finding, so the file can be sorted and filtered by fault."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for result in results:
            asset = result.asset
            for finding in result.by_severity():
                writer.writerow([
                    asset.asset_id,
                    asset.asset_type,
                    asset.kavach_id,
                    asset.zone,
                    asset.division,
                    asset.section,
                    asset.station_code,
                    asset.km_post,
                    asset.loco_number,
                    asset.shed_code,
                    result.severity,
                    finding.fault_code,
                    finding.severity,
                    finding.subsystem,
                    finding.title,
                    finding.likely_cause,
                    finding.action,
                    finding.responsibility,
                    finding.escalation,
                    finding.evidence_text,
                    result.snapshot.age_note,
                ])
    return path


# --------------------------------------------------------------- HTML report

_HTML_STYLE = """
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body { margin: 0; padding: 24px; font: 14px/1.5 system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
       background: #f6f7f9; color: #16191d; }
h1 { margin: 0 0 4px; font-size: 22px; }
h2 { margin: 28px 0 10px; font-size: 16px; text-transform: uppercase; letter-spacing: .06em;
     color: #4b5563; }
.sub { color: #6b7280; margin: 0 0 20px; }
.cards { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 8px; }
.card { flex: 1 1 120px; background: #fff; border: 1px solid #e5e7eb; border-radius: 10px;
        padding: 12px 14px; }
.card .n { font-size: 26px; font-weight: 650; line-height: 1.1; }
.card .l { font-size: 11px; letter-spacing: .08em; text-transform: uppercase; color: #6b7280; }
.wrap { overflow-x: auto; background: #fff; border: 1px solid #e5e7eb; border-radius: 10px; }
table { border-collapse: collapse; width: 100%; min-width: 900px; }
th, td { text-align: left; padding: 9px 12px; border-bottom: 1px solid #eef0f3;
         vertical-align: top; }
th { background: #f9fafb; font-size: 11px; letter-spacing: .06em; text-transform: uppercase;
     color: #4b5563; position: sticky; top: 0; }
tr:last-child td { border-bottom: none; }
.pill { display: inline-block; padding: 2px 9px; border-radius: 999px; color: #fff;
        font-size: 11px; font-weight: 650; letter-spacing: .04em; white-space: nowrap; }
.code { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
.ev { color: #6b7280; font-size: 12px; }
footer { margin-top: 28px; color: #6b7280; font-size: 12px; }
@media (prefers-color-scheme: dark) {
  body { background: #101317; color: #e6e8ea; }
  .card, .wrap { background: #171b20; border-color: #2a2f36; }
  th { background: #1c2127; color: #9aa3ad; }
  th, td { border-color: #242a31; }
  .sub, .card .l, .ev, footer { color: #9aa3ad; }
}
"""


def _pill(severity: str) -> str:
    colour = SEVERITY_COLOURS.get(severity, "#6b7280")
    return f'<span class="pill" style="background:{colour}">{html.escape(severity)}</span>'


def write_html(
    results: list[AssetResult],
    path: str | Path,
    title: str = "Kavach Fleet Health Report",
    context: dict[str, str] | None = None,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    counts = Counter(result.severity for result in results)
    generated = datetime.now().strftime("%d-%m-%Y %H:%M")

    context_bits = [f"{k}: {v}" for k, v in (context or {}).items() if v]
    subtitle = " &nbsp;|&nbsp; ".join(
        html.escape(bit) for bit in ([f"Generated {generated}"] + context_bits)
    )

    cards = [
        f'<div class="card"><div class="n">{len(results)}</div>'
        f'<div class="l">Assets</div></div>'
    ]
    for severity in Severity.ORDER:
        if not counts.get(severity):
            continue
        colour = SEVERITY_COLOURS.get(severity, "#6b7280")
        cards.append(
            f'<div class="card"><div class="n" style="color:{colour}">'
            f'{counts[severity]}</div><div class="l">{html.escape(severity)}</div></div>'
        )

    grouped: dict[str, list[AssetResult]] = defaultdict(list)
    for result in results:
        grouped[result.asset.group].append(result)

    sections: list[str] = []
    for group in sorted(grouped):
        rows: list[str] = []
        ordered = sorted(
            grouped[group],
            key=lambda r: (Severity.rank(r.severity), r.asset.asset_id),
        )
        for result in ordered:
            findings = result.by_severity()
            span = len(findings)
            for index, finding in enumerate(findings):
                cells = []
                if index == 0:
                    cells.append(
                        f'<td rowspan="{span}"><strong>'
                        f"{html.escape(result.asset.asset_id)}</strong><br>"
                        f'<span class="ev">{html.escape(result.asset.asset_type)} &middot; '
                        f'{html.escape(result.asset.location)}</span></td>'
                    )
                cells.append(f"<td>{_pill(finding.severity)}</td>")
                cells.append(
                    f'<td class="code">{html.escape(finding.fault_code)}</td>'
                )
                cells.append(
                    f"<td>{html.escape(finding.title)}<br>"
                    f'<span class="ev">{html.escape(finding.evidence_text)}</span></td>'
                )
                cells.append(f"<td>{html.escape(finding.action)}</td>")
                cells.append(
                    f'<td class="ev">{html.escape(finding.responsibility or "-")}</td>'
                )
                rows.append("<tr>" + "".join(cells) + "</tr>")

        sections.append(
            f"<h2>{html.escape(group)}</h2>"
            '<div class="wrap"><table><thead><tr>'
            "<th>Asset</th><th>Severity</th><th>Code</th><th>Finding &amp; evidence</th>"
            "<th>Recommended action</th><th>Responsibility</th>"
            "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
        )

    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<style>{_HTML_STYLE}</style></head>
<body>
<h1>{html.escape(title)}</h1>
<p class="sub">{subtitle}</p>
<div class="cards">{''.join(cards)}</div>
{''.join(sections)}
<footer>
Produced by kavach-diag from exported telemetry. Findings are a first-line
engineering aid and do not replace the prescribed maintenance schedule, the
OEM handbook or a site check.
</footer>
</body></html>
"""
    path.write_text(document, encoding="utf-8")
    return path
