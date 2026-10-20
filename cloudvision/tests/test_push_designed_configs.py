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
PENDING = "CHANGE_CONTROL_STATUS_UNSPECIFIED"
SINCE = datetime(2026, 10, 16, 19, 30, 25, tzinfo=timezone.utc)
SHOWN = "2026-10-16T19:31:00.100000000Z"
AMENDED = "2026-10-16T19:31:05.200000000Z"


def _workspace_change_control(
    devices, name="AVD v1.1.0", time=SHOWN, status=PENDING, error=None, cc_id="Workspace-ws-1"
):
    """A change control shaped like the ones a workspace creates: a group stage per switch, all in one row."""
    stages, groups = {}, []
    for hostname, serial in devices.items():
        group = f"{hostname} ({serial})"
        groups.append(group)
        stages[group] = {
            "name": group,
            "rows": {"values": [{"values": [f"{group}_a"]}]},
            "status": "STAGE_STATUS_UNSPECIFIED",
        }
        stages[f"{group}_a"] = {
            "name": f"{group}_a",
            "action": {"name": "setConfig", "args": {"values": {"DeviceID": serial, "Source": "DesignedConfig"}}},
            "rows": {},
            "status": "STAGE_STATUS_UNSPECIFIED",
        }
    stages["root"] = {"name": "root", "rows": {"values": [{"values": groups}]}}
    change_control = {
        "key": {"id": cc_id},
        "change": {"name": name, "time": time, "rootStageId": "root", "stages": {"values": stages}},
        "status": status,
    }
    if error:
        change_control["error"] = error
    return change_control


class FakeCloudVision:
    """Records every write and answers reads of one change control from `states`, the last one repeating."""

    def __init__(self, change_controls=(), states=None, refuse_amend=False):
        self._change_controls = list(change_controls)
        self._states = list(states or [{"change": {"time": AMENDED}, "status": COMPLETED}])
        self._refuse_amend = refuse_amend
        self.writes = []

    def change_controls(self):
        return self._change_controls

    def change_control(self, change_control_id):
        return self._states.pop(0) if len(self._states) > 1 else self._states[0]

    def set(self, path, body):
        if (
            self._refuse_amend
            and str((body.get("key") or {}).get("id", "")).startswith("Workspace-")
            and "change" in body
        ):
            raise push_designed_configs.PushError("CloudVision POST ChangeControlConfig failed with 400: locked")
        self.writes.append((path, body))


def _ticks():
    ticks = count(0, push_designed_configs.POLL_SECONDS)
    return {"sleep": lambda _s: None, "clock": lambda: next(ticks), "now_ns": lambda: 7}


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


class PendingChangeControlTest(unittest.TestCase):
    def test_the_newest_not_started_change_control_with_the_name_since_the_release(self):
        newest = _workspace_change_control({"dc1-leaf1": "LEAF1"}, time="2026-10-16T19:32:00Z", cc_id="newest")
        change_controls = [
            _workspace_change_control({"dc1-leaf1": "LEAF1"}, cc_id="older"),
            newest,
            _workspace_change_control({"dc1-leaf1": "LEAF1"}, name="AVD v1.0.0", time="2026-10-16T19:33:00Z"),
            _workspace_change_control({"dc1-leaf1": "LEAF1"}, time="2026-10-16T19:34:00Z", status=COMPLETED),
            _workspace_change_control({"dc1-leaf1": "LEAF1"}, time="2026-10-16T19:35:00Z", error="build failed"),
            _workspace_change_control({"dc1-leaf1": "LEAF1"}, time="2026-10-16T19:18:28Z", cc_id="before release"),
        ]
        self.assertIs(push_designed_configs.pending_change_control(change_controls, "AVD v1.1.0", SINCE), newest)

    def test_none_when_cloudvision_created_none(self):
        self.assertIsNone(push_designed_configs.pending_change_control([], "AVD v1.1.0", SINCE))


class PushedDevicesTest(unittest.TestCase):
    def test_the_serials_of_its_set_config_actions(self):
        change_control = _workspace_change_control({"dc1-leaf1": "LEAF1", "dc1-leaf2": "LEAF2"})
        change_control["change"]["stages"]["values"]["upgrade"] = {
            "action": {"name": "upgradeImage", "args": {"values": {"DeviceID": "SPINE1"}}}
        }
        self.assertEqual(push_designed_configs.pushed_devices(change_control), {"LEAF1", "LEAF2"})


class AmendedChangeTest(unittest.TestCase):
    def test_left_out_switches_join_the_first_row_beside_cloudvisions_own_stages(self):
        change = _workspace_change_control({"dc1-leaf1": "LEAF1"})["change"]
        amended = push_designed_configs.amended_change(change, {"dc1-spine2": "SPINE2", "dc1-spine1": "SPINE1"}, 9)
        stages = amended["stages"]["values"]
        self.assertEqual(
            stages["root"],
            {
                "name": "root",
                "rows": {"values": [{"values": ["dc1-leaf1 (LEAF1)", "dc1-spine1 (SPINE1)", "dc1-spine2 (SPINE2)"]}]},
            },
        )
        self.assertEqual(
            stages["dc1-spine1 (SPINE1)"],
            {"name": "dc1-spine1 (SPINE1)", "rows": {"values": [{"values": ["dc1-spine1 (SPINE1)_a"]}]}},
        )
        self.assertEqual(
            stages["dc1-spine1 (SPINE1)_a"]["action"],
            {
                "name": "setConfig",
                "args": {"values": {"DeviceID": "SPINE1", "Source": "DesignedConfig", "Timestamp": "9"}},
            },
        )

    def test_the_whole_stage_map_goes_back_without_the_state_cloudvision_reports(self):
        change = _workspace_change_control({"dc1-leaf1": "LEAF1"})["change"]
        stages = push_designed_configs.amended_change(change, {"dc1-spine1": "SPINE1"}, 9)["stages"]["values"]
        self.assertEqual(
            stages["dc1-leaf1 (LEAF1)_a"],
            {
                "name": "dc1-leaf1 (LEAF1)_a",
                "action": {"name": "setConfig", "args": {"values": {"DeviceID": "LEAF1", "Source": "DesignedConfig"}}},
            },
        )
        self.assertEqual(len(stages), 5)


class ChangeControlConfigTest(unittest.TestCase):
    def test_a_new_change_control_pushes_every_switch_in_one_parallel_row(self):
        body = push_designed_configs.change_control_config(
            "avd-push-1", "v1.1.0", {"dc1-spine2": "SPINE2", "dc1-spine1": "SPINE1"}, 1792185600123456789
        )
        stages = body["change"]["stages"]["values"]
        self.assertEqual(body["key"], {"id": "avd-push-1"})
        self.assertEqual(
            stages[body["change"]["rootStageId"]]["rows"]["values"],
            [{"values": ["dc1-spine1 (SPINE1)", "dc1-spine2 (SPINE2)"]}],
        )
        self.assertEqual(
            stages["dc1-spine1 (SPINE1)_a"]["action"]["args"]["values"],
            {"DeviceID": "SPINE1", "Source": "DesignedConfig", "Timestamp": "1792185600123456789"},
        )


class CompleteTest(unittest.TestCase):
    def test_amends_then_approves_the_amended_version_starts_and_waits(self):
        deploy = _workspace_change_control({"dc1-leaf1": "LEAF1"})
        cloudvision = FakeCloudVision(
            states=[
                {"change": {"time": SHOWN}, "status": PENDING},
                {"change": {"time": AMENDED}, "status": PENDING},
                {"change": {"time": AMENDED}, "status": "CHANGE_CONTROL_STATUS_RUNNING"},
                {"change": {"time": AMENDED}, "status": COMPLETED},
            ]
        )
        push_designed_configs.complete(cloudvision, deploy, {"dc1-spine1": "SPINE1"}, **_ticks())
        (amend_path, amend), (approve_path, approval), (_, start) = cloudvision.writes
        self.assertEqual(amend_path, push_designed_configs.CHANGE_CONTROL_CONFIG_PATH)
        self.assertEqual(amend["key"], {"id": "Workspace-ws-1"})
        self.assertIn("dc1-spine1 (SPINE1)", amend["change"]["stages"]["values"])
        self.assertEqual(approve_path, push_designed_configs.APPROVE_CONFIG_PATH)
        self.assertEqual(approval["version"], AMENDED)
        self.assertEqual(start, {"key": {"id": "Workspace-ws-1"}, "start": {"value": True, "notes": "Started by AVD"}})

    def test_with_nothing_left_out_it_approves_the_version_it_found(self):
        deploy = _workspace_change_control({"dc1-leaf1": "LEAF1"})
        cloudvision = FakeCloudVision()
        push_designed_configs.complete(cloudvision, deploy, {}, **_ticks())
        self.assertEqual([path for path, _ in cloudvision.writes][0], push_designed_configs.APPROVE_CONFIG_PATH)
        self.assertEqual(cloudvision.writes[0][1]["version"], SHOWN)

    def test_an_amendment_cloudvision_never_shows_times_out(self):
        deploy = _workspace_change_control({"dc1-leaf1": "LEAF1"})
        cloudvision = FakeCloudVision(states=[{"change": {"time": SHOWN}, "status": PENDING}])
        with self.assertRaises(push_designed_configs.PushError) as raised:
            push_designed_configs.complete(cloudvision, deploy, {"dc1-spine1": "SPINE1"}, **_ticks())
        self.assertIn("never showed its new version", str(raised.exception))
        self.assertEqual(len(cloudvision.writes), 1)


class PushTest(unittest.TestCase):
    def _push(self, cloudvision):
        return push_designed_configs.push(cloudvision, "v1.1.0", {"dc1-spine1": "SPINE1"}, **_ticks())

    def test_creates_approves_the_version_it_was_shown_starts_and_waits(self):
        cloudvision = FakeCloudVision(
            states=[{}, {"change": {"time": SHOWN}}, {"change": {"time": SHOWN}, "status": COMPLETED}]
        )
        change_control_id = self._push(cloudvision)
        created, approval, start = (body for _, body in cloudvision.writes)
        self.assertEqual(created["key"]["id"], change_control_id)
        self.assertEqual(approval["version"], SHOWN)
        self.assertEqual(start, {"key": {"id": change_control_id}, "start": {"value": True, "notes": "Started by AVD"}})

    def test_a_change_control_that_reports_an_error_fails(self):
        with self.assertRaises(push_designed_configs.PushError) as raised:
            self._push(
                FakeCloudVision(
                    states=[{"change": {"time": SHOWN}, "status": COMPLETED, "error": "device unreachable"}]
                )
            )
        self.assertIn("device unreachable", str(raised.exception))

    def test_a_change_control_that_never_finishes_times_out(self):
        with self.assertRaises(push_designed_configs.PushError) as raised:
            self._push(FakeCloudVision(states=[{"change": {"time": SHOWN}, "status": "CHANGE_CONTROL_STATUS_RUNNING"}]))
        self.assertIn("did not finish", str(raised.exception))


class MainTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "dc1-spine1.yml").write_text('serial_number: "SPINE1"\n')
        (self.root / "dc1-leaf1.yml").write_text('serial_number: "LEAF1"\n')
        self.args = [
            "--release", "v1.1.0",
            "--since", "2026-10-16T19:30:25Z",
            "--change-control-name", "AVD v1.1.0",
            "--structured-configs", str(self.root),
        ]  # fmt: skip

    def _main(self, cloudvision):
        env = {"CVAAS_SERVER": "www.cv-prod.example", "CVAAS_TOKEN": "t0ken"}
        with (
            mock.patch.dict(os.environ, env),
            mock.patch.object(push_designed_configs, "CloudVision", return_value=cloudvision),
            mock.patch.object(push_designed_configs.time, "sleep"),
        ):
            return push_designed_configs.main(self.args)

    def test_adds_the_switches_the_deploy_left_out_to_its_change_control(self):
        deploy = _workspace_change_control({"dc1-leaf1": "LEAF1"})
        cloudvision = FakeCloudVision(change_controls=[deploy])
        self.assertEqual(self._main(cloudvision), 0)
        amend = cloudvision.writes[0][1]
        self.assertEqual(amend["key"], {"id": "Workspace-ws-1"})
        added = push_designed_configs.pushed_devices({"change": amend["change"]})
        self.assertEqual(added, {"LEAF1", "SPINE1"})

    def test_runs_the_change_control_unchanged_when_it_covers_every_switch(self):
        deploy = _workspace_change_control({"dc1-leaf1": "LEAF1", "dc1-spine1": "SPINE1"})
        cloudvision = FakeCloudVision(change_controls=[deploy])
        self.assertEqual(self._main(cloudvision), 0)
        self.assertEqual(
            [path for path, _ in cloudvision.writes],
            [push_designed_configs.APPROVE_CONFIG_PATH, push_designed_configs.CHANGE_CONTROL_CONFIG_PATH],
        )

    def test_pushes_every_switch_when_cloudvision_created_no_change_control(self):
        cloudvision = FakeCloudVision(states=[{"change": {"time": SHOWN}, "status": COMPLETED}])
        self.assertEqual(self._main(cloudvision), 0)
        created = cloudvision.writes[0][1]
        self.assertTrue(created["key"]["id"].startswith("avd-push-"))
        self.assertEqual(push_designed_configs.pushed_devices(created), {"LEAF1", "SPINE1"})

    def test_when_cloudvision_refuses_the_addition_it_runs_the_deploy_then_pushes_the_rest(self):
        deploy = _workspace_change_control({"dc1-leaf1": "LEAF1"})
        cloudvision = FakeCloudVision(change_controls=[deploy], refuse_amend=True)
        self.assertEqual(self._main(cloudvision), 0)
        approval, start, created, *_ = (body for _, body in cloudvision.writes)
        self.assertEqual(approval["key"], {"id": "Workspace-ws-1"})
        self.assertEqual(start["key"], {"id": "Workspace-ws-1"})
        self.assertTrue(created["key"]["id"].startswith("avd-push-"))
        self.assertEqual(push_designed_configs.pushed_devices(created), {"SPINE1"})

    def test_a_failed_change_control_exits_non_zero(self):
        deploy = _workspace_change_control({"dc1-leaf1": "LEAF1", "dc1-spine1": "SPINE1"})
        cloudvision = FakeCloudVision(change_controls=[deploy], states=[{"change": {"time": SHOWN}, "error": "boom"}])
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
