#!/usr/bin/env python3
"""Offline tests for cloudvision/push_designed_configs.py.

Standard library only, so this runs on a bare CI runner:

    python3 cloudvision/tests/test_push_designed_configs.py
"""

import importlib.util
import os
import tempfile
import unittest
from datetime import datetime, timezone
from itertools import count
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("push_designed_configs", HERE.parent / "push_designed_configs.py")
push_designed_configs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(push_designed_configs)

COMPLETED = push_designed_configs.COMPLETED
SINCE = datetime(2026, 10, 16, 19, 30, 25, tzinfo=timezone.utc)


def _change_control(serials, time="2026-10-16T19:30:41.913479123Z", status=COMPLETED, error=None, action="setConfig"):
    stages = {
        f"stage {serial}": {"action": {"name": action, "args": {"values": {"DeviceID": serial}}}} for serial in serials
    }
    stages["root"] = {"rows": {"values": [{"values": list(stages)}]}}
    change_control = {"change": {"time": time, "stages": {"values": stages}}, "status": status}
    if error:
        change_control["error"] = error
    return change_control


class FakeCloudVision:
    """Records every write. With `warm_up` the change control appears after one poll and finishes after
    another, as on a real CloudVision; without it, it is finished from the first read.
    """

    def __init__(self, change_controls=(), final=None, warm_up=True):
        self._change_controls = list(change_controls)
        self._final = final or {"status": COMPLETED}
        self._warm_up = warm_up
        self.writes = []
        self.reads = 0

    def change_controls(self):
        return self._change_controls

    def change_control(self, change_control_id):
        self.reads += 1
        if self._warm_up and self.reads == 1:
            return {}
        if self._warm_up and self.reads == 2:
            return {"change": {"time": "2026-10-16T21:40:00.123456789Z"}, "status": "CHANGE_CONTROL_STATUS_UNSPECIFIED"}
        return {"change": {"time": "2026-10-16T21:40:00.123456789Z"}, **self._final}

    def set(self, path, body):
        self.writes.append((path, body))


class ParseTimeTest(unittest.TestCase):
    def test_keeps_microseconds_of_a_nanosecond_timestamp(self):
        parsed = push_designed_configs.parse_time("2026-10-16T19:30:41.913479123Z")
        self.assertEqual(parsed, datetime(2026, 10, 16, 19, 30, 41, 913479, tzinfo=timezone.utc))

    def test_reads_a_timestamp_without_a_fraction(self):
        self.assertEqual(push_designed_configs.parse_time("2026-10-16T19:30:25Z"), SINCE)


class DeploymentSerialsTest(unittest.TestCase):
    def test_reads_quoted_and_bare_serials_and_names_files_without_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "dc1-spine1.yml").write_text('hostname: dc1-spine1\nserial_number: "CLAB-NTC02-DC1SPINE1"\n')
            (root / "dc1-leaf1.yml").write_text("hostname: dc1-leaf1\nserial_number: CLAB-NTC02-DC1LEAF1\n")
            (root / "dc1-leaf2.yml").write_text("hostname: dc1-leaf2\n")
            serials, missing = push_designed_configs.deployment_serials(sorted(root.glob("*.yml")))
        self.assertEqual(serials, {"dc1-spine1": "CLAB-NTC02-DC1SPINE1", "dc1-leaf1": "CLAB-NTC02-DC1LEAF1"})
        self.assertEqual([path.name for path in missing], ["dc1-leaf2.yml"])


class PushedSinceTest(unittest.TestCase):
    def test_counts_only_completed_error_free_set_config_changes_since_the_release(self):
        change_controls = [
            _change_control(["LEAF1", "LEAF2"]),
            _change_control(["SPINE1"], time="2026-10-16T19:18:28Z"),
            _change_control(["SPINE2"], status="CHANGE_CONTROL_STATUS_RUNNING"),
            _change_control(["LEAF3"], error="push failed"),
            _change_control(["LEAF4"], action="upgradeImage"),
        ]
        self.assertEqual(push_designed_configs.pushed_since(change_controls, SINCE), {"LEAF1", "LEAF2"})


class ChangeControlConfigTest(unittest.TestCase):
    def test_one_parallel_stage_per_switch_pushing_its_designed_config(self):
        body = push_designed_configs.change_control_config(
            "avd-push-1", "v1.1.0", {"dc1-spine2": "SPINE2", "dc1-spine1": "SPINE1"}, 1792185600123456789
        )
        stages = body["change"]["stages"]["values"]
        self.assertEqual(body["key"], {"id": "avd-push-1"})
        self.assertEqual(
            stages[body["change"]["rootStageId"]]["rows"]["values"],
            [{"values": ["push dc1-spine1", "push dc1-spine2"]}],
        )
        self.assertEqual(
            stages["push dc1-spine1"]["action"],
            {
                "name": "setConfig",
                "args": {
                    "values": {"DeviceID": "SPINE1", "Source": "DesignedConfig", "Timestamp": "1792185600123456789"}
                },
            },
        )


class PushTest(unittest.TestCase):
    def _push(self, cloudvision):
        ticks = count(0, push_designed_configs.POLL_SECONDS)
        return push_designed_configs.push(
            cloudvision,
            "v1.1.0",
            {"dc1-spine1": "SPINE1"},
            sleep=lambda _s: None,
            clock=lambda: next(ticks),
            now_ns=lambda: 7,
        )

    def test_creates_approves_the_version_it_was_shown_starts_and_waits(self):
        cloudvision = FakeCloudVision()
        change_control_id = self._push(cloudvision)
        paths = [path for path, _ in cloudvision.writes]
        self.assertEqual(
            paths,
            [
                push_designed_configs.CHANGE_CONTROL_CONFIG_PATH,
                push_designed_configs.APPROVE_CONFIG_PATH,
                push_designed_configs.CHANGE_CONTROL_CONFIG_PATH,
            ],
        )
        created, approval, start = (body for _, body in cloudvision.writes)
        self.assertEqual(created["key"]["id"], change_control_id)
        self.assertEqual(approval["version"], "2026-10-16T21:40:00.123456789Z")
        self.assertEqual(start, {"key": {"id": change_control_id}, "start": {"value": True, "notes": "Started by AVD"}})

    def test_a_change_control_that_reports_an_error_fails(self):
        with self.assertRaises(push_designed_configs.PushError) as raised:
            self._push(FakeCloudVision(final={"status": COMPLETED, "error": "device unreachable"}))
        self.assertIn("device unreachable", str(raised.exception))

    def test_a_change_control_that_never_finishes_times_out(self):
        with self.assertRaises(push_designed_configs.PushError) as raised:
            self._push(FakeCloudVision(final={"status": "CHANGE_CONTROL_STATUS_RUNNING"}))
        self.assertIn("did not finish", str(raised.exception))


class MainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "dc1-spine1.yml").write_text('serial_number: "SPINE1"\n')
        (self.root / "dc1-leaf1.yml").write_text('serial_number: "LEAF1"\n')
        self.args = ["--release", "v1.1.0", "--since", "2026-10-16T19:30:25Z", "--structured-configs", str(self.root)]

    def _main(self, cloudvision):
        env = {"CVAAS_SERVER": "www.cv-prod.example", "CVAAS_TOKEN": "t0ken"}
        with (
            mock.patch.dict(os.environ, env),
            mock.patch.object(push_designed_configs, "CloudVision", return_value=cloudvision),
        ):
            return push_designed_configs.main(self.args)

    def test_pushes_only_the_switches_the_deploy_left_out(self):
        cloudvision = FakeCloudVision(change_controls=[_change_control(["LEAF1"])], warm_up=False)
        self.assertEqual(self._main(cloudvision), 0)
        created = cloudvision.writes[0][1]
        devices = [
            stage["action"]["args"]["values"]["DeviceID"]
            for stage in created["change"]["stages"]["values"].values()
            if "action" in stage
        ]
        self.assertEqual(devices, ["SPINE1"])

    def test_pushes_nothing_when_the_deploy_covered_every_switch(self):
        cloudvision = FakeCloudVision(change_controls=[_change_control(["LEAF1", "SPINE1"])], warm_up=False)
        self.assertEqual(self._main(cloudvision), 0)
        self.assertEqual(cloudvision.writes, [])

    def test_a_failed_push_exits_non_zero(self):
        cloudvision = FakeCloudVision(final={"status": COMPLETED, "error": "boom"}, warm_up=False)
        self.assertEqual(self._main(cloudvision), 1)

    def test_without_credentials_nothing_is_called(self):
        with mock.patch.dict(os.environ, {"CVAAS_SERVER": "", "CVAAS_TOKEN": ""}):
            self.assertEqual(push_designed_configs.main(self.args), 2)

    def test_a_switch_without_a_serial_stops_before_calling_cloudvision(self):
        (self.root / "dc1-leaf2.yml").write_text("hostname: dc1-leaf2\n")
        with (
            mock.patch.dict(os.environ, {"CVAAS_SERVER": "s", "CVAAS_TOKEN": "t"}),
            mock.patch.object(push_designed_configs, "CloudVision", side_effect=AssertionError("called CloudVision")),
        ):
            self.assertEqual(push_designed_configs.main(self.args), 2)


if __name__ == "__main__":
    unittest.main()
