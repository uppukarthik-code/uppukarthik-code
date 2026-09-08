# Working in the Indian Railways context

This document explains the choices that make the tool an Indian Railways tool
rather than a generic network monitor with Kavach words pasted on it.

## Where the tool sits

Kavach is a SIL-4 train protection system. Nothing in this repository is part of
that system, and nothing here may be relied on for train working.

```
  Safety system (SIL-4, RDSO approved, OEM supplied)
  ├── Loco Kavach Unit, Stationary Kavach Unit, radio, RFID tags, interfaces
  └── produces logs, data-logger records, remote-monitoring exports
                                │
                                │  export (read only, offline, one way)
                                ▼
  This tool  ──────────────────────────────────────────────────────────
  ├── reads the export
  ├── classifies conditions against a fault library
  └── produces engineering actions and divisional reports
```

The boundary is deliberate and is worth stating to anyone who asks for "a tool
that talks to Kavach":

* The tool **never** opens a session to a Kavach unit, sends it a command, or
  changes its configuration.
* It reads only what the system has already recorded and exported.
* Its output is an aid to first-line diagnosis. It does not replace the
  prescribed maintenance schedule, the OEM handbook, a site check, or the
  judgement of the SSE attending the failure.

Anything that would cross that line - a live poll, a remote restart, an
automatic remediation - needs the OEM, RDSO and the zonal safety organisation
involved, and is out of scope here.

## The asset register

Everything starts from a register that a division already maintains in some
form. The columns are the ones an S&T asset list actually carries:

| Column | Why it is there |
| --- | --- |
| `asset_id`, `asset_type` | The unit and what kind it is: SKU, LKU, TWR, RIU |
| `kavach_id` | The unit identity as programmed and as recorded |
| `zone`, `division`, `section` | How failures are counted and reported upward |
| `station_code`, `station_name`, `km_post`, `line` | Where an engineer is sent |
| `loco_number`, `loco_class`, `shed_code` | The same, for onboard units |
| `oem`, `spec_version` | Mixed-vendor sections behave differently |
| `commissioned_on` | Age of the installation, warranty and CAMC position |
| `sanctioned_sw_version`, `sanctioned_track_db` | What the unit *should* be running |
| `commissioning_checksum` | The configuration baseline to compare against |
| `assigned_freq_mhz` | The channel allotted to that installation |

The last four are what turn a monitoring tool into an audit tool. A unit that
quietly differs from its register entry is usually the first visible sign that
a change went in without paperwork.

## Asset profiles

The section is not uniform, and the report is only useful if it stops reporting
things that were never there. Each unit type is assessed against the check
families that apply to it:

| Type | Checks applied |
| --- | --- |
| SKU - Stationary Kavach Unit | radio, signalling interface, power, config, security, time |
| LKU - Loco Kavach Unit | radio, RFID, location and odometry, onboard, config, security, time |
| TWR - Radio tower / static radio unit | radio, power, security |
| RIU - Remote Interface Unit | signalling interface, power, config, security |

A loco unit is therefore never failed for having no interlocking interface, and
a tower is never failed for having no brake interface.

## Failure handling

Each finding carries three things beyond the diagnosis:

* **Action** - what to do at site, phrased as an engineer would write it in the
  register.
* **Responsibility** - which maintenance unit owns it: S&T Kavach, S&T
  signalling, S&T IPS, the loco shed, the OEM under CAMC, the divisional Kavach
  cell, or the cyber security cell.
* **Escalation** - how far it travels. Three levels are used:
  * record as an observation and review at the fortnightly Kavach review;
  * record in the S&T failure register and advise the Section Controller;
  * treat as a failure affecting train working - advise the Section Controller
    immediately, record in the register, and include in the divisional Kavach
    performance return.

These are working defaults. Every division's JPO and standing instructions
differ, and the escalation text in `kavach_diag/faults.py` is meant to be edited
to match the division the tool is deployed in.

## Conditions that matter here and not elsewhere

A few of the classifications exist because of how Kavach is worked on Indian
Railways rather than because of anything in the radio or the software:

* **Kavach isolated on the loco** (`KVCH-OBU-001`). A loco working an isolated
  unit through a Kavach-fitted section has no train protection. Isolations left
  unreversed after shed attention are a recurring finding and deserve a
  first-class fault code, not a line in a log.
* **Unknown tag identity** (`KVCH-TAG-003`). Track-side tags sit in the
  permanent way and are disturbed by the same works that disturb the track.
  A tag identity that is not in the sanctioned track database is a joint S&T
  and P.Way matter, and can also be a security matter.
* **Track database version mismatch** (`KVCH-CFG-001`). Yard remodelling, speed
  revisions and new tag laying all generate a revised track database. Units
  running different versions over the same section is a real and recurring
  condition after partial updates.
* **Tag read shortfall** (`KVCH-TAG-001`). Reported with the kilometrage, so
  the joint check with the P.Way official goes to the right place rather than
  to "somewhere in the section".
* **IPS supply** (`KVCH-PWR-001` to `004`). Supply is the most common reason a
  station installation goes out of service, so mains state, charger state,
  remaining backup and bus voltage are assessed together rather than as four
  unrelated alarms.

## Reporting

Three outputs, because three different people need it:

* **Text** - a block the attending SSE can read at site or paste into the
  failure register, with the evidence attached.
* **CSV** - one row per finding, with zone, division, section, station, KM and
  loco columns, so the divisional Kavach cell can sort and count.
* **HTML** - one self-contained page grouped by section and by shed, safe to
  circulate after the daily scan.

## A note on limits and thresholds

The thresholds in `kavach_diag/config.py` are working defaults for a first-line
aid. They are **not** taken from, and are no substitute for, the limits in the
applicable RDSO specification, the OEM maintenance handbook, or the division's
own instructions. Before any field use, each limit must be confirmed against
those documents and adjusted with `--thresholds`.
