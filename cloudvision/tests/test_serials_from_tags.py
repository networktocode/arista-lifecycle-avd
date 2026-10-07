#!/usr/bin/env python3
"""Offline tests for cloudvision/serials_from_tags.py.

Standard library only, so this runs on a bare CI runner:

    python3 cloudvision/tests/test_serials_from_tags.py
"""

import importlib.util
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("serials_from_tags", HERE.parent / "serials_from_tags.py")
serials_from_tags = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(serials_from_tags)

DEPLOYMENT = serials_from_tags.DEPLOYMENT_TAG_LABEL
LAB = serials_from_tags.LAB_TAG_LABEL
ACTIVE = serials_from_tags.STREAMING_ACTIVE


def _assignment(serial, label, value, workspace="", interface=""):
    key = {
        "workspaceId": workspace,
        "elementType": "ELEMENT_TYPE_DEVICE",
        "label": label,
        "value": value,
        "deviceId": serial,
    }
    if interface:
        key["interfaceId"] = interface
    return {"key": key}


def _tagged(serial, deployment="DC1", lab="NTC01"):
    return [_assignment(serial, DEPLOYMENT, deployment), _assignment(serial, LAB, lab)]


def _device(serial, hostname, status=ACTIVE):
    return {"key": {"deviceId": serial}, "hostname": hostname, "streamingStatus": status}


class ParseStreamTest(unittest.TestCase):
    def test_unwraps_each_line(self):
        text = '{"result": {"value": {"a": 1}}}\n\n{"result": {"value": {"b": 2}}}\n'
        self.assertEqual(serials_from_tags.parse_stream(text), [{"a": 1}, {"b": 2}])


class TaggedSerialsTest(unittest.TestCase):
    def test_needs_both_tags_matching(self):
        assignments = (
            _tagged("MINE")
            + _tagged("OTHER-LAB", lab="TEAM02")
            + [_assignment("HALF", DEPLOYMENT, "DC1")]
            + [
                _assignment("WS", DEPLOYMENT, "DC1", workspace="ws-1"),
                _assignment("WS", LAB, "NTC01", workspace="ws-1"),
            ]
            + [
                _assignment("IF", DEPLOYMENT, "DC1", interface="Ethernet1"),
                _assignment("IF", LAB, "NTC01", interface="Ethernet1"),
            ]
        )
        self.assertEqual(serials_from_tags.tagged_serials(assignments, "DC1", "NTC01"), {"MINE"})


class MatchTest(unittest.TestCase):
    def _match(self, devices, tagged):
        return serials_from_tags.match(["dc1-spine1"], devices, tagged, "DC1", "NTC01")

    def test_the_tagged_streaming_device_wins_over_stale_and_foreign_ones(self):
        devices = [
            _device("CLABDC1SPINE1", "dc1-spine1", status="STREAMING_STATUS_INACTIVE"),
            _device("CLAB-TEAM02-DC1SPINE1", "dc1-spine1"),
            _device("CLAB-NTC01-DC1SPINE1", "dc1-spine1"),
        ]
        found, problems = self._match(devices, {"CLAB-NTC01-DC1SPINE1"})
        self.assertEqual((found, problems), ({"dc1-spine1": "CLAB-NTC01-DC1SPINE1"}, []))

    def test_an_untagged_switch_says_to_promote_again(self):
        found, problems = self._match([_device("CLAB-NTC01-DC1SPINE1", "dc1-spine1")], set())
        self.assertEqual(found, {})
        self.assertIn("promote again", problems[0])

    def test_a_tagged_switch_that_is_not_streaming_is_named(self):
        found, problems = self._match(
            [_device("CLAB-NTC01-DC1SPINE1", "dc1-spine1", status="STREAMING_STATUS_INACTIVE")],
            {"CLAB-NTC01-DC1SPINE1"},
        )
        self.assertEqual(found, {})
        self.assertIn("not streaming (CLAB-NTC01-DC1SPINE1)", problems[0])

    def test_two_tagged_streaming_devices_are_ambiguous(self):
        devices = [_device("A", "dc1-spine1"), _device("B", "dc1-spine1")]
        found, problems = self._match(devices, {"A", "B"})
        self.assertEqual(found, {})
        self.assertIn("more than one", problems[0])


class WriteSerialTest(unittest.TestCase):
    def test_appends_or_replaces_the_top_level_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dc1-spine1.yml"
            path.write_text("hostname: dc1-spine1\nrouter_bgp:\n  as: '65000'\n", encoding="utf-8")
            serials_from_tags.write_serial(path, "S1")
            self.assertTrue(path.read_text(encoding="utf-8").endswith('serial_number: "S1"\n'))
            serials_from_tags.write_serial(path, "S2")
            text = path.read_text(encoding="utf-8")
            self.assertEqual(text.count("serial_number:"), 1)
            self.assertIn('serial_number: "S2"', text)
            self.assertIn("router_bgp:\n  as: '65000'\n", text)


class MainTest(unittest.TestCase):
    def test_refuses_without_a_lab_id(self):
        self.assertEqual(serials_from_tags.main(["--deployment", "DC1", "--lab", "", "--structured-configs", "."]), 2)


if __name__ == "__main__":
    unittest.main()
