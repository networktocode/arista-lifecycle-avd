#!/usr/bin/env python3
"""Push the intended configuration to every switch that the deploy's change control left out.

CloudVision puts a switch in the change control a workspace creates only when that switch's
intended configuration changed in the workspace. It does not compare with what the switch is
running. A production lab that was rebuilt comes back on its boot configuration with the same
serials, so a switch whose intended configuration is the same as at the last deploy (the spines,
when only the leaves changed) stays on its boot configuration: CloudVision sees nothing to do.

This runs after AVD's cv_deploy. Every switch in the deployment that no completed change control
since the release was published pushed configuration to gets one more change control that pushes
its intended configuration, with the same `setConfig` action from the designed configuration that
CloudVision's own change controls use. A switch that already runs that configuration takes it
again, which changes nothing.

    python3 cloudvision/push_designed_configs.py --release v1.1.0 --since 2026-10-16T19:30:25Z \\
        --structured-configs sites/DC1/intended/structured_configs

Run it after serials_from_tags.py, which writes each switch's `serial_number` into its structured
config for the run. Reads `CVAAS_SERVER` and `CVAAS_TOKEN` from the environment. Standard library
only.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path

CHANGE_CONTROLS_PATH = "api/resources/changecontrol/v1/ChangeControl/all"
CHANGE_CONTROL_PATH = "api/resources/changecontrol/v1/ChangeControl"
CHANGE_CONTROL_CONFIG_PATH = "api/resources/changecontrol/v1/ChangeControlConfig"
APPROVE_CONFIG_PATH = "api/resources/changecontrol/v1/ApproveConfig"
COMPLETED = "CHANGE_CONTROL_STATUS_COMPLETED"
SET_CONFIG = "setConfig"
DESIGNED_CONFIG = "DesignedConfig"
SERIAL_LINE = re.compile(r'^serial_number:\s*"?([^"\n]+?)"?\s*$', re.MULTILINE)
TIMEOUT_SECONDS = 60
POLL_SECONDS = 5
CHANGE_CONTROL_TIMEOUT_SECONDS = 600


class PushError(RuntimeError):
    """The push change control could not be created, approved, started, or finished."""


def parse_stream(text):
    """The values of a CloudVision `/all` response, one JSON object per line."""
    return [(json.loads(line).get("result") or {}).get("value") or {} for line in text.splitlines() if line.strip()]


def parse_time(text):
    """A CloudVision RFC 3339 timestamp, nanoseconds and all, as an aware datetime."""
    return datetime.fromisoformat(re.sub(r"(\.\d{6})\d+", r"\1", text).replace("Z", "+00:00"))


def deployment_serials(paths):
    """`({hostname: serial}, [path without a serial, ...])` from the structured configs."""
    serials, missing = {}, []
    for path in paths:
        found = SERIAL_LINE.search(path.read_text(encoding="utf-8"))
        if found:
            serials[path.stem] = found.group(1)
        else:
            missing.append(path)
    return serials, missing


def pushed_since(change_controls, since):
    """The serials that a change control completed without error pushed configuration to since `since`."""
    pushed = set()
    for change_control in change_controls:
        change = change_control.get("change") or {}
        if change_control.get("status") != COMPLETED or change_control.get("error") or not change.get("time"):
            continue
        if parse_time(change["time"]) < since:
            continue
        for stage in ((change.get("stages") or {}).get("values") or {}).values():
            action = (stage or {}).get("action") or {}
            if action.get("name") == SET_CONFIG:
                device = ((action.get("args") or {}).get("values") or {}).get("DeviceID")
                if device:
                    pushed.add(device)
    return pushed


def change_control_config(change_control_id, release, serials, designed_at_ns):
    """A change control that pushes each `{hostname: serial}` its intended configuration, all at once.

    `setConfig` pushes the designed configuration as it stood at `designed_at_ns` (nanoseconds since
    the epoch), so the caller passes the current time to push the latest one.
    """
    args = {"Source": DESIGNED_CONFIG, "Timestamp": str(designed_at_ns)}
    stages = {
        f"push {hostname}": {
            "name": f"{hostname} ({serial})",
            "action": {"name": SET_CONFIG, "args": {"values": {"DeviceID": serial, **args}}},
        }
        for hostname, serial in sorted(serials.items())
    }
    stages["root"] = {
        "name": f"Push the intended configuration ({release})",
        "rows": {"values": [{"values": sorted(stage_id for stage_id in stages)}]},
    }
    return {
        "key": {"id": change_control_id},
        "change": {
            "name": f"AVD {release}: push the intended configuration to switches the deploy left unchanged",
            "notes": (
                "The deploy's change control only covers switches whose intended configuration changed. "
                "These switches' did not, so this pushes it to them in case they were rebuilt."
            ),
            "rootStageId": "root",
            "stages": {"values": stages},
        },
    }


class CloudVision:
    """The few change control calls this needs, over HTTPS with a service token."""

    def __init__(self, server, token):
        """Talk to the CloudVision at `server` with bearer `token`."""
        base = server if server.startswith("http") else f"https://{server}"
        self.base = base.rstrip("/")
        self.headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _open(self, method, path, params=None, body=None):
        url = f"{self.base}/{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(url, data=data, method=method, headers=self.headers)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310 - fixed https URL
                return response.read().decode()
        except urllib.error.HTTPError as exc:
            raise PushError(f"CloudVision {method} {path} failed with {exc.code}: {exc.read().decode()[:300]}") from exc

    def change_controls(self):
        """Every change control CloudVision holds."""
        return parse_stream(self._open("GET", CHANGE_CONTROLS_PATH))

    def change_control(self, change_control_id):
        """One change control's state, or an empty dict while CloudVision has not built it yet."""
        try:
            text = self._open("GET", CHANGE_CONTROL_PATH, params={"key.id": change_control_id})
        except PushError as exc:
            if "failed with 404" in str(exc):
                return {}
            raise
        return json.loads(text).get("value") or {}

    def set(self, path, body):
        """Create or update one config resource."""
        self._open("POST", path, body=body)


def push(cloudvision, release, serials, sleep=time.sleep, clock=time.monotonic, now_ns=time.time_ns):
    """Create, approve, and start one change control pushing `serials`, then wait for it to finish."""
    change_control_id = f"avd-push-{uuid.uuid4().hex[:12]}"
    cloudvision.set(CHANGE_CONTROL_CONFIG_PATH, change_control_config(change_control_id, release, serials, now_ns()))
    deadline = clock() + CHANGE_CONTROL_TIMEOUT_SECONDS
    state = cloudvision.change_control(change_control_id)
    while not (state.get("change") or {}).get("time"):
        if clock() >= deadline:
            raise PushError(f"Change control {change_control_id} never appeared in CloudVision.")
        sleep(POLL_SECONDS)
        state = cloudvision.change_control(change_control_id)
    # CloudVision approves exactly the version of the change it was shown: the change's last update time.
    cloudvision.set(
        APPROVE_CONFIG_PATH,
        {
            "key": {"id": change_control_id},
            "approve": {"value": True, "notes": "Approved by AVD"},
            "version": state["change"]["time"],
        },
    )
    cloudvision.set(
        CHANGE_CONTROL_CONFIG_PATH, {"key": {"id": change_control_id}, "start": {"value": True, "notes": "Started by AVD"}}
    )
    while True:
        state = cloudvision.change_control(change_control_id)
        if state.get("error"):
            raise PushError(f"Change control {change_control_id} failed: {state['error']}")
        if state.get("status") == COMPLETED:
            return change_control_id
        if clock() >= deadline:
            raise PushError(
                f"Change control {change_control_id} did not finish within {CHANGE_CONTROL_TIMEOUT_SECONDS // 60} "
                f"minutes (status {state.get('status')})."
            )
        sleep(POLL_SECONDS)


def main(argv=None):
    """Push every switch the deploy left out, or exit non-zero saying why it could not."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--release", required=True, help="the release tag, for example v1.1.0")
    parser.add_argument("--since", required=True, help="when the release was published (RFC 3339)")
    parser.add_argument("--structured-configs", required=True, type=Path)
    args = parser.parse_args(argv)
    server, token = os.environ.get("CVAAS_SERVER", ""), os.environ.get("CVAAS_TOKEN", "")
    if not server or not token:
        print("CVAAS_SERVER and CVAAS_TOKEN must be set.", file=sys.stderr)
        return 2
    serials, missing = deployment_serials(sorted(args.structured_configs.glob("*.yml")))
    if missing or not serials:
        names = ", ".join(path.stem for path in missing) or f"anything under {args.structured_configs}"
        print(f"No serial_number for {names}; run serials_from_tags.py first.", file=sys.stderr)
        return 2
    cloudvision = CloudVision(server, token)
    try:
        pushed = pushed_since(cloudvision.change_controls(), parse_time(args.since))
        left_out = {hostname: serial for hostname, serial in serials.items() if serial not in pushed}
        if not left_out:
            print("The deploy's change control pushed every switch; nothing else to push.")
            return 0
        print(f"The deploy's change control left out {', '.join(sorted(left_out))}; pushing their intended configuration.")
        change_control_id = push(cloudvision, args.release, left_out)
    except PushError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"Change control {change_control_id} pushed the intended configuration to {', '.join(sorted(left_out))}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
