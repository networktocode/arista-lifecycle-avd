#!/usr/bin/env python3
"""Hand AVD each production switch's CloudVision serial, found by Nautobot's tags plus hostname.

One CloudVision tenant serves many Nautobot labs, each with its own `dc1-spine1`, and it keeps
stale records of earlier labs, so a lookup by hostname alone can land on the wrong device.
Nautobot's 03 Promote to Production tags every switch it boots with `nautobot_deployment` (the
deployment's name) and `nautobot_lab` (its lab id). For each structured config, this script finds
the one streaming device that carries both tags and the same hostname, and writes its
`serial_number` into that structured config for this run only. AVD's cv_deploy then matches the
switch by serial. Nothing here is committed.

    python3 cloudvision/serials_from_tags.py --deployment DC1 --lab NTC01 \\
        --structured-configs sites/DC1/intended/structured_configs

Reads `CVAAS_SERVER` and `CVAAS_TOKEN` from the environment. Standard library only.
"""

import argparse
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

DEPLOYMENT_TAG_LABEL = "nautobot_deployment"
LAB_TAG_LABEL = "nautobot_lab"
STREAMING_ACTIVE = "STREAMING_STATUS_ACTIVE"
TAG_ASSIGNMENTS_PATH = "api/resources/tag/v2/TagAssignment/all"
DEVICES_PATH = "api/resources/inventory/v1/Device/all"
SERIAL_LINE = re.compile(r"^serial_number:.*$", re.MULTILINE)
TIMEOUT_SECONDS = 60


def parse_stream(text):
    """The values of a CloudVision `/all` response, one JSON object per line."""
    return [(json.loads(line).get("result") or {}).get("value") or {} for line in text.splitlines() if line.strip()]


def tagged_serials(assignments, deployment, lab):
    """The serials whose mainline device tags carry both this deployment and this lab."""
    labels = {}
    for assignment in assignments:
        key = assignment.get("key") or {}
        if key.get("workspaceId") or key.get("interfaceId") or key.get("elementType") != "ELEMENT_TYPE_DEVICE":
            continue
        if key.get("label") in (DEPLOYMENT_TAG_LABEL, LAB_TAG_LABEL) and key.get("deviceId"):
            labels.setdefault(key["deviceId"], {})[key["label"]] = key.get("value")
    wanted = {DEPLOYMENT_TAG_LABEL: deployment, LAB_TAG_LABEL: lab}
    return {serial for serial, found in labels.items() if all(found.get(k) == v for k, v in wanted.items())}


def match(hostnames, devices, tagged, deployment, lab):
    """`({hostname: serial}, [problem, ...])` for the tagged, streaming device behind each hostname."""
    found, problems = {}, []
    tag_text = f"{DEPLOYMENT_TAG_LABEL}={deployment} and {LAB_TAG_LABEL}={lab}"
    for hostname in hostnames:
        candidates = [
            device
            for device in devices
            if (device.get("key") or {}).get("deviceId") in tagged and device.get("hostname") == hostname
        ]
        streaming = [device for device in candidates if device.get("streamingStatus") == STREAMING_ACTIVE]
        if len(streaming) == 1:
            found[hostname] = streaming[0]["key"]["deviceId"]
        elif len(streaming) > 1:
            serials = ", ".join(sorted(device["key"]["deviceId"] for device in streaming))
            problems.append(f"{hostname}: more than one streaming device is tagged {tag_text} ({serials}).")
        elif candidates:
            serials = ", ".join(sorted(device["key"]["deviceId"] for device in candidates))
            problems.append(f"{hostname}: tagged {tag_text} but not streaming ({serials}).")
        else:
            problems.append(
                f"{hostname}: no device in CloudVision is tagged {tag_text} with this hostname. "
                "03 Promote to Production tags the switches it boots; promote again."
            )
    return found, problems


def write_serial(path, serial):
    """Set the top-level `serial_number` of the structured config at `path`."""
    text = path.read_text(encoding="utf-8")
    line = f'serial_number: "{serial}"'
    if SERIAL_LINE.search(text):
        text = SERIAL_LINE.sub(line, text, count=1)
    else:
        text = text.rstrip("\n") + f"\n{line}\n"
    path.write_text(text, encoding="utf-8")


def fetch(server, token, path):
    """GET one CloudVision `/all` resource."""
    base = server if server.startswith("http") else f"https://{server}"
    request = urllib.request.Request(f"{base.rstrip('/')}/{path}", headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - fixed https URL
        return parse_stream(response.read().decode())


def main(argv=None):
    """Resolve and write every serial, or exit non-zero naming each switch that could not be found."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--deployment", required=True, help="the Nautobot deployment name, for example DC1")
    parser.add_argument("--lab", default="", help="the Nautobot lab id (the NAUTOBOT_LAB_ID repository variable)")
    parser.add_argument("--structured-configs", required=True, type=Path)
    args = parser.parse_args(argv)
    if not args.lab:
        print(
            "NAUTOBOT_LAB_ID is not set on this repository. 03 Promote to Production sets it; promote again.",
            file=sys.stderr,
        )
        return 2
    server, token = os.environ.get("CVAAS_SERVER", ""), os.environ.get("CVAAS_TOKEN", "")
    if not server or not token:
        print("CVAAS_SERVER and CVAAS_TOKEN must be set.", file=sys.stderr)
        return 2
    paths = sorted(args.structured_configs.glob("*.yml"))
    if not paths:
        print(f"No structured configs under {args.structured_configs}.", file=sys.stderr)
        return 2
    tagged = tagged_serials(fetch(server, token, TAG_ASSIGNMENTS_PATH), args.deployment, args.lab)
    found, problems = match(
        [path.stem for path in paths], fetch(server, token, DEVICES_PATH), tagged, args.deployment, args.lab
    )
    if problems:
        print("Could not find every switch in CloudVision:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    for path in paths:
        write_serial(path, found[path.stem])
        print(f"{path.stem}: {found[path.stem]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
