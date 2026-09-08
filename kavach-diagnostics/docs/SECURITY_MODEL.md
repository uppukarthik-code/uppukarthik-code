# OT security posture checks

Kavach exchanges safety-related messages over an open transmission medium: a
UHF radio channel that anyone with a receiver can listen to and anyone with a
transmitter can inject into. EN 50159 is written for exactly this case, and it
names the threats a system on such a medium has to defend against.

The Kavach system's own defences against those threats are the OEM's and RDSO's
concern. What a division can do - and what this tool supports - is check that
the defences are actually in the state they are supposed to be in, using
evidence the units already record.

These checks read exported evidence only. Nothing here probes, scans,
authenticates against, or otherwise touches a unit.

## EN 50159 threats and what the tool looks at

| Threat | What it looks like on Kavach | Checks |
| --- | --- | --- |
| Masquerade | A transmitter impersonating a Kavach unit, or an unregistered identity on the channel | `KVCH-SEC-001` authentication failures, `KVCH-SEC-003` unknown peer identities |
| Insertion | A message, or a track-side tag, introduced into the system | `KVCH-TAG-003` unknown tag identity, `KVCH-SEC-003` |
| Corruption | Message contents altered in transit | `KVCH-SEC-001`, correlated with `KVCH-RAD-002` / `RAD-004` so that a bad radio path is not read as an attack |
| Deletion / denial | Messages prevented from arriving | `KVCH-RAD-001` link down, `KVCH-RAD-006` suspected interference |
| Delay / re-sequencing | Stale data acted on as if current | `KVCH-SIG-002` stale aspect telegrams, `KVCH-LOC-003` time reference lost or drifting |
| Repetition | An old valid message replayed | Depends on the unit's own replay protection; the tool surfaces the time-reference and authentication evidence that make replay detectable |

The correlation matters more than any single check. Authentication failures on
a healthy radio link and authentication failures on a link at -101 dBm are
different findings, and the tool reports them differently: the first stays a
security finding, the second is reported as probable corruption in propagation
with the instruction to fix the radio path first. A tool that reported both as
"possible attack" would be ignored within a fortnight.

## IEC 62443 posture checks

The remaining checks are ordinary industrial-control hygiene, mapped to the
foundational requirements:

| Check | Code | Reference |
| --- | --- | --- |
| Maintenance access port left open after attention | `KVCH-SEC-004` | IEC 62443-3-3 SR 1.1 / SR 2.1 - access control |
| OEM default or shared credentials still in use | `KVCH-SEC-005` | IEC 62443-3-3 SR 1.5 - authenticator management |
| Firmware not verified against a signed OEM release | `KVCH-SEC-006` | IEC 62443-3-3 SR 3.4 - software integrity |
| Removable media used on a unit | `KVCH-SEC-007` | IEC 62443-3-3 SR 3.2 - malicious code protection |
| Site configuration differs from the commissioning baseline | `KVCH-CFG-003` | IEC 62443-2-1 - change control |
| Key set past or near expiry | `KVCH-SEC-002` | Key management lifecycle |

`KVCH-CFG-003` is the one worth dwelling on. It does not detect an attack; it
detects that the configuration in the unit is no longer the configuration the
register says was commissioned. Most of the time that is an authorised change
with the paperwork not caught up. The point is that the difference becomes
visible at all, and gets explained rather than discovered later.

## Severity choices

Two conditions are deliberately CRITICAL rather than "housekeeping":

* **Default credentials** (`KVCH-SEC-005`). On a train protection system this
  is not a to-do item for the next visit.
* **Unsigned firmware** (`KVCH-SEC-006`). The unit should not be accepted into
  service until the image is verified against the OEM's signed release.

Both also carry the instruction to check whether the same condition exists on
the rest of the section's units, because it usually does - one commissioning
practice produces one class of finding across every unit commissioned the same
way.

## What this is not

* Not a penetration test, a vulnerability scan or an active assessment.
* Not a compliance certificate against EN 50159 or IEC 62443. Assessment of the
  Kavach system against those standards is the OEM's and RDSO's work.
* Not a substitute for the zonal cyber security cell's own processes. Where a
  finding needs escalation, the tool says so and names the evidence to preserve;
  it does not investigate.
