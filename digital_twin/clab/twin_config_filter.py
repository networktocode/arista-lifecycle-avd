#!/usr/bin/env python3
"""Make an AVD intended configuration safe to push at the containerlab twin.

``playbooks/deploy_twin_eapi.yml`` pushes the twin-mode intended configs with
``arista.eos.eos_config`` and ``replace: config``. That module opens a
configuration session, runs ``rollback clean-config``, loads the file, and
commits, so whatever the file does not say is removed from the device. The
intended configs describe *production's* management plane:

    interface Management1        static 192.168.0.x, VRF MGMT
    management api http-commands eAPI enabled in VRF MGMT only
    ip route vrf MGMT 0.0.0.0/0 192.168.0.1
    username cvpadmin ...        and no `admin` user

The twin is a plain containerlab lab. Its nodes come up on the twin's own
management bridge with a dynamically assigned address on Management1 in the
DEFAULT VRF, eAPI listening in the default VRF, and containerlab's default
``admin``/``admin`` credentials. Committing production's management plane onto
the twin would therefore cut the eAPI session that is doing the committing and
delete the account it authenticated with, in the same commit.

So the configuration is filtered before it is pushed: the management-plane
stanzas are dropped and a small reachability tail is appended that keeps the
session alive on the twin's own addressing and credentials. Everything else -
BGP, VLANs, VRFs, Ethernet interfaces, MLAG, route maps - is passed through
byte for byte, because that is what the pull request is validating.

What is removed, and why each one is a management-plane stanza:

* ``interface Management<n>`` - production's static address in VRF MGMT. Left
  in, it moves the twin's management interface into VRF MGMT and renumbers it.
* ``management api http-commands`` - production enables eAPI in VRF MGMT only,
  which turns off the default-VRF listener the runner is connected to.
* ``management ssh`` - same reasoning, if a rendering ever emits it.
* ``ip route ... 192.168.0.1`` - production's management default route, whose
  next hop does not exist on the twin's bridge.
* ``ntp local-interface ...`` - names the management interface that is gone.
* ``username admin ...`` - never present in an intended config; removed so the
  tail's own ``admin`` account cannot be duplicated when this runs twice.
* ``daemon TerminAttr`` - streams to CloudVision with an onboarding token the
  twin never has (nothing binds ``/tmp/cv-onboarding-token`` into a twin
  node), so on the twin the agent can only restart in a loop for the life of
  the lab. Removing it loses nothing the pull request validates.

What is deliberately KEPT is ``vrf instance MGMT``. It is referenced from
stanzas that are not management-plane and must be validated as rendered -
``mlag configuration``'s ``peer-address heartbeat ... vrf MGMT``, plus
``ip name-server vrf MGMT``, ``no ip routing vrf MGMT`` and ``ntp server vrf
MGMT`` - so deleting the VRF instance would make the replace fail on those
lines. An MGMT VRF with no interface in it cannot carry a session, so it has
no bearing on twin reachability.

Filtering is idempotent by construction: every stanza the tail adds is also a
stanza the filter removes, so filtering an already filtered configuration
returns the same bytes.

Usage:

    twin_config_filter.py <intended.cfg> <filtered.cfg>
    twin_config_filter.py --management-address 192.168.1.12/24 in.cfg out.cfg

With ``--management-address`` the tail also re-creates ``interface Management1``
with that address in the default VRF, which is what the deploy playbook passes
from the twin inventory's ``ansible_host``. Without it the tail only restores
the credentials and the eAPI listener, which is enough when the device keeps
its management address some other way.

Standard library only, so it runs in the AVD universal image and on a bare CI
runner.
"""

from __future__ import annotations

import argparse
import sys

# The management default gateway production renders into `ip route vrf MGMT`.
# It does not exist on the twin's management bridge.
PRODUCTION_MGMT_GATEWAY = "192.168.0.1"

# The management interface the twin's eAPI session arrives on, per the cEOS
# interface mapping the containerlab host installs.
TWIN_MGMT_INTERFACE = "Management1"

# Top-level stanzas dropped whole, with everything indented under them.
REMOVED_BLOCK_PREFIXES = (
    "daemon TerminAttr",
    "interface Management",
    "management api http-commands",
    "management ssh",
)

# Top-level single lines dropped.
REMOVED_LINE_PREFIXES = (
    "ntp local-interface",
    "username admin ",
)

TAIL_CREDENTIALS = ("username admin privilege 15 role network-admin secret 0 admin",)

TAIL_EAPI = (
    "management api http-commands",
    "   protocol https",
    "   no shutdown",
    "   vrf default",
    "      no shutdown",
)


def _is_removed_line(line: str) -> bool:
    """True for a top-level line that is dropped on its own."""
    if line.startswith(REMOVED_LINE_PREFIXES):
        return True
    return line.startswith("ip route") and PRODUCTION_MGMT_GATEWAY in line.split()


def _management_tail(management_address: str | None, delimited: bool) -> list[str]:
    """The reachability tail, in the order it is appended.

    ``delimited`` says whether the configuration already ends with a ``!``, in
    which case the tail does not open with one of its own.
    """
    tail = [] if delimited else ["!"]
    tail.extend(TAIL_CREDENTIALS)
    tail.append("!")
    if management_address:
        tail.extend(
            [
                "interface {0}".format(TWIN_MGMT_INTERFACE),
                "   description TWIN_MANAGEMENT",
                "   no shutdown",
                "   ip address {0}".format(management_address),
                "!",
            ]
        )
    tail.extend(TAIL_EAPI)
    tail.append("!")
    return tail


def filter_config(text: str, management_address: str | None = None) -> str:
    """Return ``text`` with the management plane replaced by the twin's own.

    Pure: no I/O, no globals mutated. ``management_address`` is rendered as
    given (``A.B.C.D/LEN``) onto the twin's management interface; when it is
    None the interface stanza is left out of the tail.
    """
    lines = text.splitlines()

    kept: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        top_level = bool(line) and not line.startswith((" ", "\t"))

        if top_level and line.startswith(REMOVED_BLOCK_PREFIXES):
            index += 1
            while index < len(lines) and lines[index].startswith((" ", "\t")):
                index += 1
            index = _skip_one_delimiter(lines, index)
            continue

        if top_level and _is_removed_line(line):
            index += 1
            index = _skip_one_delimiter(lines, index)
            continue

        kept.append(line)
        index += 1

    # `end` closes the configuration, so the tail goes in front of it and the
    # filtered file keeps the shape of the file it came from.
    trailing: list[str] = []
    while kept and (kept[-1].strip() == "" or kept[-1].strip() == "end"):
        trailing.insert(0, kept.pop())

    kept.extend(_management_tail(management_address, delimited=bool(kept) and kept[-1].strip() == "!"))
    kept.extend(trailing)
    return "\n".join(kept) + "\n"


def _skip_one_delimiter(lines: list[str], index: int) -> int:
    """Consume the single ``!`` that delimited a stanza that was just removed.

    Without this, removing a stanza leaves the ``!`` above it and the ``!``
    below it back to back. Only one delimiter is consumed, so a stanza that was
    not followed by one is left alone.
    """
    if index < len(lines) and lines[index].strip() == "!":
        return index + 1
    return index


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Filter an AVD intended configuration so it can be replaced onto the digital twin.",
    )
    parser.add_argument("source", help="the intended configuration to read")
    parser.add_argument("destination", help="the filtered configuration to write")
    parser.add_argument(
        "--management-address",
        default=None,
        help=(
            "the twin node's own management address as A.B.C.D/LEN; rendered onto "
            "{0} in the default VRF so the eAPI session survives the replace".format(TWIN_MGMT_INTERFACE)
        ),
    )
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    try:
        with open(args.source, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        print("error: cannot read {0}: {1}".format(args.source, exc), file=sys.stderr)
        return 1

    try:
        with open(args.destination, "w", encoding="utf-8") as handle:
            handle.write(filter_config(text, args.management_address))
    except OSError as exc:
        print("error: cannot write {0}: {1}".format(args.destination, exc), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
