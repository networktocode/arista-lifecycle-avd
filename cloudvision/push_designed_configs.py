#!/usr/bin/env python3
"""Run the deploy's change control with every switch in it, adding the switches CloudVision left out.

CloudVision puts a switch in the change control a workspace creates only when that switch's
intended configuration changed in the workspace. It does not compare with what the switch is
running. A production lab that was rebuilt comes back on its boot configuration with the same
serials, so a switch whose intended configuration is the same as at the last deploy (the spines,
when only the leaves changed) is left out and stays on its boot configuration: CloudVision sees
nothing to do.

AVD's cv_deploy submits the workspace and leaves the change control it creates pending, named
`--change-control-name`. This adds every switch of the deployment that change control left out,
with the same per-switch stages and `setConfig` action from the designed configuration that
CloudVision's own stages use, in the same parallel row; then it approves, starts, and waits for the
change control. Every switch takes its intended configuration in that one change control. A switch
that already runs it takes it again, which changes nothing.

When no switch's intended configuration changed, CloudVision creates no change control; then this
creates one that pushes every switch its intended configuration, in case the lab was rebuilt.

    python3 cloudvision/push_designed_configs.py --release v1.1.0 --since 2026-10-16T19:30:25Z \\
        --change-control-name "AVD v1.1.0" --structured-configs sites/DC1/intended/structured_configs

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
NOT_STARTED = ("", "CHANGE_CONTROL_STATUS_UNSPECIFIED")
SET_CONFIG = "setConfig"
DESIGNED_CONFIG = "DesignedConfig"
# What a stage of a change control's configuration holds; the state CloudVision reports adds status and times.
STAGE_FIELDS = ("name", "action", "rows")
SERIAL_LINE = re.compile(r'^serial_number:\s*"?([^"\n]+?)"?\s*$', re.MULTILINE)
TIMEOUT_SECONDS = 60
POLL_SECONDS = 5
CHANGE_CONTROL_TIMEOUT_SECONDS = 600


class PushError(RuntimeError):
    """The change control could not be found, amended, approved, started, or finished."""


class AmendRefused(PushError):
    """CloudVision did not take the switches added to the change control."""


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


def pending_change_control(change_controls, name, since):
    """The newest change control named `name`, changed since `since`, and not started yet; None if there is none."""
    candidates = [
        change_control
        for change_control in change_controls
        if (change_control.get("change") or {}).get("name") == name
        and (change_control.get("change") or {}).get("time")
        and parse_time(change_control["change"]["time"]) >= since
        and change_control.get("status", "") in NOT_STARTED
        and not change_control.get("error")
    ]
    return max(candidates, key=lambda change_control: parse_time(change_control["change"]["time"]), default=None)


def pushed_devices(change_control):
    """The serials a change control's `setConfig` stages push configuration to."""
    devices = set()
    for stage in ((change_control.get("change") or {}).get("stages") or {}).get("values", {}).values():
        action = (stage or {}).get("action") or {}
        if action.get("name") == SET_CONFIG:
            device = ((action.get("args") or {}).get("values") or {}).get("DeviceID")
            if device:
                devices.add(device)
    return devices


def device_stages(hostname, serial, designed_at_ns):
    """`(group stage id, {stage id: stage})` for one switch, shaped and named like CloudVision's own.

    `setConfig` pushes the designed configuration as it stood at `designed_at_ns` (nanoseconds since
    the epoch), so the caller passes the current time to push the latest one.
    """
    group = f"{hostname} ({serial})"
    action = f"{group}_a"
    args = {"DeviceID": serial, "Source": DESIGNED_CONFIG, "Timestamp": str(designed_at_ns)}
    return group, {
        group: {"name": group, "rows": {"values": [{"values": [action]}]}},
        action: {"name": action, "action": {"name": SET_CONFIG, "args": {"values": args}}},
    }


def amended_change(change, serials, designed_at_ns):
    """`change` with a stage for each `{hostname: serial}` added to the first row of its root stage.

    The whole stage map goes back, every stage reduced to what its configuration holds, so the
    result is the same whether CloudVision merges the map or replaces it.
    """
    stages = {
        stage_id: {field: stage[field] for field in STAGE_FIELDS if stage.get(field)}
        for stage_id, stage in ((change.get("stages") or {}).get("values") or {}).items()
    }
    root_id = change["rootStageId"]
    rows = [list(row.get("values") or []) for row in (stages[root_id].get("rows") or {}).get("values") or []] or [[]]
    for hostname, serial in sorted(serials.items()):
        group, new = device_stages(hostname, serial, designed_at_ns)
        stages.update(new)
        rows[0].append(group)
    stages[root_id]["rows"] = {"values": [{"values": row} for row in rows]}
    return {"stages": {"values": stages}}


def change_control_config(change_control_id, release, serials, designed_at_ns):
    """A new change control that pushes each `{hostname: serial}` its intended configuration, all at once."""
    stages = {}
    groups = []
    for hostname, serial in sorted(serials.items()):
        group, new = device_stages(hostname, serial, designed_at_ns)
        stages.update(new)
        groups.append(group)
    stages["root"] = {"name": f"Push the intended configuration ({release})", "rows": {"values": [{"values": groups}]}}
    return {
        "key": {"id": change_control_id},
        "change": {
            "name": f"AVD {release}: push the intended configuration",
            "notes": (
                "No switch's intended configuration changed, so CloudVision created no change control. "
                "This pushes it to every switch in case the lab was rebuilt."
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


def wait_for_version(cloudvision, change_control_id, after, deadline, sleep, clock):
    """The change control's state once CloudVision shows a version (its change time) other than `after`."""
    state = cloudvision.change_control(change_control_id)
    while not (state.get("change") or {}).get("time") or state["change"]["time"] == after:
        if clock() >= deadline:
            raise PushError(f"Change control {change_control_id} never showed its new version in CloudVision.")
        sleep(POLL_SECONDS)
        state = cloudvision.change_control(change_control_id)
    return state


def approve_start_and_wait(cloudvision, change_control_id, state, deadline, sleep, clock):
    """Approve the version `state` shows, start the change control, and wait for it to finish."""
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
        CHANGE_CONTROL_CONFIG_PATH,
        {"key": {"id": change_control_id}, "start": {"value": True, "notes": "Started by AVD"}},
    )
    while True:
        state = cloudvision.change_control(change_control_id)
        if state.get("error"):
            raise PushError(f"Change control {change_control_id} failed: {state['error']}")
        if state.get("status") == COMPLETED:
            return
        if clock() >= deadline:
            raise PushError(
                f"Change control {change_control_id} did not finish within {CHANGE_CONTROL_TIMEOUT_SECONDS // 60} "
                f"minutes (status {state.get('status')})."
            )
        sleep(POLL_SECONDS)


def complete(cloudvision, change_control, serials, sleep=time.sleep, clock=time.monotonic, now_ns=time.time_ns):
    """Add `serials` to the pending `change_control` (when there are any), then approve, start, and wait for it."""
    change_control_id = change_control["key"]["id"]
    deadline = clock() + CHANGE_CONTROL_TIMEOUT_SECONDS
    state = change_control
    if serials:
        try:
            cloudvision.set(
                CHANGE_CONTROL_CONFIG_PATH,
                {
                    "key": {"id": change_control_id},
                    "change": amended_change(change_control["change"], serials, now_ns()),
                },
            )
            state = wait_for_version(
                cloudvision, change_control_id, change_control["change"]["time"], deadline, sleep, clock
            )
        except PushError as exc:
            raise AmendRefused(str(exc)) from exc
    approve_start_and_wait(cloudvision, change_control_id, state, deadline, sleep, clock)


def push(cloudvision, release, serials, sleep=time.sleep, clock=time.monotonic, now_ns=time.time_ns):
    """Create, approve, and start one change control pushing `serials`, then wait for it to finish."""
    change_control_id = f"avd-push-{uuid.uuid4().hex[:12]}"
    deadline = clock() + CHANGE_CONTROL_TIMEOUT_SECONDS
    cloudvision.set(CHANGE_CONTROL_CONFIG_PATH, change_control_config(change_control_id, release, serials, now_ns()))
    state = wait_for_version(cloudvision, change_control_id, None, deadline, sleep, clock)
    approve_start_and_wait(cloudvision, change_control_id, state, deadline, sleep, clock)
    return change_control_id


def main(argv=None):
    """Run the deploy's change control with every switch in it, or exit non-zero saying why it could not."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--release", required=True, help="the release tag, for example v1.1.0")
    parser.add_argument("--since", required=True, help="when the release was published (RFC 3339)")
    parser.add_argument("--change-control-name", required=True, help="the name cv_deploy gave the change control")
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
        deploy = pending_change_control(cloudvision.change_controls(), args.change_control_name, parse_time(args.since))
        if deploy is None:
            print(
                f"CloudVision created no change control named {args.change_control_name!r}: no switch's intended "
                "configuration changed. Pushing it to every switch in case the lab was rebuilt."
            )
            change_control_id = push(cloudvision, args.release, serials)
            print(
                f"Change control {change_control_id} pushed the intended configuration to {', '.join(sorted(serials))}."
            )
            return 0
        included = pushed_devices(deploy)
        left_out = {hostname: serial for hostname, serial in serials.items() if serial not in included}
        if left_out:
            them = "it" if len(left_out) == 1 else "them"
            print(f"Change control {args.change_control_name!r} left out {', '.join(sorted(left_out))}; adding {them}.")
        try:
            complete(cloudvision, deploy, left_out)
        except AmendRefused as exc:
            # A refused addition leaves the change control at the version first shown, so that version is approved.
            print(f"CloudVision did not take them ({exc}); running the change control as it is, then pushing them.")
            complete(cloudvision, deploy, {})
            change_control_id = push(cloudvision, args.release, left_out)
            pushed = ", ".join(sorted(left_out))
            print(f"Change control {change_control_id} pushed the intended configuration to {pushed}.")
            return 0
    except PushError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    switches = ", ".join(sorted(serials))
    print(f"Change control {args.change_control_name!r} pushed the intended configuration to {switches}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
