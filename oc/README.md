# Operational Compliance rules

Loaded into Nautobot by the Operational Compliance app's Git datasources:
`nautobot_operational_compliance.validation_rules` reads `oc/rules/*.yml` and `oc/rule-groups/*.yml`;
`nautobot_operational_compliance.command_parsers` reads `parsers/<network_driver>/<command>.textfsm`.

| Group | File | Purpose |
| --- | --- | --- |
| DC1 Change Window | `dc1_change_window.yml` | Pre/post comparison (exact_match / tolerance) around a production change. |
| AVD Validation | `avd_validation.yml` | One-sided checks (parameter_match / operator / regex) mirroring the ANTA tests AVD generates for DC1 (pyavd 6.3.0 `AVD_TEST_INDEX`). Run on a single snapshot. |

## Changes to `dc1_change_window.yml` on this branch

`Interface Health` used `jmespath: "*.{is_up: is_up, is_enabled: is_enabled}"`. The app stores NAPALM output
wrapped under the getter name (`{"get_interfaces": {...}}`), so `*` selected the whole interface table and the
projection produced nulls: the rule passed vacuously (verified: a shut Port-Channel did not flip it). The path
is now `get_interfaces.$*$.[is_up, is_enabled]`, anchored per interface so the diff names the interface.

`Route Count` used `jmespath: "totalRoutes"`. On EOS 4.30 `show ip route summary | json` nests the counter
under `vrfs.default.totalRoutes`, and jdiff's tolerance check needs an anchored list, so the path is now
`[{routes: {total: vrfs.default.totalRoutes}}]`. Without this the rule extracted nothing and passed vacuously.

`Interface Health` and `BGP Session State` now compare **dictionaries keyed by interface / VRF+neighbour** (NAPALM
`get_interfaces` with `mtu, speed, last_flapped, description, mac_address` excluded; `show ip bgp summary vrf all | json`
with the counters excluded) instead of anchored lists. jdiff pairs anchored list items by name only when both lists have
the same length; when an interface or neighbour appears or disappears between the snapshots it falls back to positional
pairing and the diff compares unrelated interfaces (`index_element[0]: Ethernet49/1 -> Ethernet1`). With dictionaries the
diff reads `Ethernet49/1.is_up true -> false`, `Loopback77: new`, `Vlan1188: missing`. What is compared is unchanged:
admin/oper state per interface, and peer state + received prefixes per neighbour.

## ANTA tests not mirrored

EnvironmentCooling, EnvironmentPower, EnvironmentSystemCooling, Temperature, TransceiversManufacturers,
TransceiversTemperature, Inventory (no hardware on cEOS); InterfaceUtilization, StormControlDrops,
Maintenance, LoggingErrors (skipped by the playbooks too); OSPF*, AVTSpecificPath, SpecificPath,
SpecificIPSecConn, Reachability (not generated for this design).

## Deviations from ANTA, and known lab behaviour

- `Memory Free` asserts an absolute free-memory floor (2 GB) instead of ANTA's 75 % utilisation: JMESPath has no arithmetic.
- The lab has one dual-homed LACP host (`dc1-host1`), so the leafs' server-facing Ethernet1 / Port-Channel1 are up and checked by `Interfaces Status` and `Port-Channels Healthy`.
- `VXLAN Config Sanity` ignores the `Flood List` items (a single MLAG pair has no remote VTEP) and `Peer VLAN-VNI`
  (cEOS-lab reports it not identical on the MLAG secondary although both peers show identical mappings).
- `MLAG Status Active`, `MLAG Interfaces`, `MLAG Config Sanity`, `VXLAN Config Sanity` also run on the spines, which
  report MLAG/VXLAN as disabled/empty and pass.
- Expected FAIL on the healthy NTC lab: `NTP Synchronised` on every device (no NTP reachability; the twin playbook skips
  `VerifyNTP` for the same reason). `MLAG Interfaces` passes since the lab gained a real LACP host (their twin skips
  `VerifyMlagInterfaces` because its host image has no LACP).

## Rule audit (2026-09-04)

`jobs/avd_demo/tests/audit_rules.py` in the nautobot-3.1 project evaluates every rule against captured output and flags
jdiff/JMESPath pitfalls: positional list comparison (two-sided rules), fallbacks (`||`) that let a rule pass when the
command output loses the key it reads, empty extractions that pass, numeric strings. Outcome:

- All pre/post rules compare **dictionaries keyed by name** (interface, VRF/neighbour, MLAG field), never anchored lists,
  because jdiff pairs list items by position when the lists differ in length.
- One-sided rules are **anchored per object** (`dict.$*$.[field]`) or built as a single named item, and no longer use `||`
  fallbacks on the key they read: a changed or missing key raises during evaluation (an UNKNOWN result) instead of passing.
- Known accepted residual: `MLAG Status Active` accepts `null` for the negotiation/peer-link/local-interface fields because
  spines report exactly that; a leaf whose `show mlag | json` lost those keys would therefore pass. `MLAG State` (pre/post)
  and `MLAG Interfaces` cover the same failure modes without that gap.
- `Route Count` uses jdiff tolerance, which is a **percentage** with a strict bound (a 10 % change fails, 9 % passes).
- Devices without port-channels have nothing for `Port-Channels Healthy` to check and pass by construction.

## Tests

`jobs/avd_demo/tests/test_rules_offline.py` in the nautobot-3.1 project evaluates every rule with jdiff against
captured cEOS output (healthy -> PASS) and a mutated copy (-> FAIL). The authoritative check is a Nautobot
`Take Snapshot` run with both groups against the lab, because the app's collection path (nornir dispatcher,
parser selection) is what actually feeds jdiff.
