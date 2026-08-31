#!/usr/bin/env python3
"""Offline tests for digital_twin/clab/twin_config_filter.py.

Standard library only, so this runs on a bare CI runner:

    python3 digital_twin/clab/tests/test_twin_config_filter.py

The fixture in tests/fixtures/dc1-leaf1-intended.cfg is a copy of a real
twin-mode intended configuration (dc1-leaf1, the richest one: MLAG, tenant
VRFs, and the full management plane). The point of these tests is the two-sided
contract: the management plane must be gone, and everything the pull request is
actually validating must come through byte for byte.
"""

import importlib.util
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent.parent / "twin_config_filter.py"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "dc1-leaf1-intended.cfg"
REPO_ROOT = Path(__file__).resolve().parents[3]

_spec = importlib.util.spec_from_file_location("twin_config_filter", MODULE_PATH)
twin_config_filter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(twin_config_filter)

filter_config = twin_config_filter.filter_config

TWIN_ADDRESS = "192.168.1.13/24"


def blocks(text):
    """Split a configuration into ``{top-level line: block text}``.

    A block is its top-level line plus the indented lines under it, which is
    how a byte-for-byte comparison of one stanza is done below.
    """
    found = {}
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line or line.startswith((" ", "\t")):
            index += 1
            continue
        body = [line]
        index += 1
        while index < len(lines) and lines[index].startswith((" ", "\t")):
            body.append(lines[index])
            index += 1
        found[line] = "\n".join(body)
    return found


class FilterConfigTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.original = FIXTURE.read_text(encoding="utf-8")
        cls.filtered = filter_config(cls.original, TWIN_ADDRESS)
        cls.original_blocks = blocks(cls.original)
        cls.filtered_blocks = blocks(cls.filtered)

    # --- the management plane is replaced ---------------------------------

    def test_production_management_interface_is_gone(self):
        """The production Management1 stanza, address and VRF, does not survive."""
        self.assertIn("interface Management1", self.original)
        self.assertIn("   ip address 192.168.0.12/24", self.original)
        self.assertNotIn("192.168.0.12/24", self.filtered)
        self.assertNotIn("OOB_MANAGEMENT", self.filtered)

    def test_no_management_stanza_still_references_vrf_mgmt(self):
        """Nothing under a management stanza puts the session in VRF MGMT."""
        for header, body in self.filtered_blocks.items():
            if header.startswith(("management ", "interface Management")):
                self.assertNotIn("vrf MGMT", body, "{0} still names VRF MGMT".format(header))

    def test_the_production_management_route_is_gone(self):
        self.assertIn("ip route vrf MGMT 0.0.0.0/0 192.168.0.1", self.original)
        self.assertNotIn("ip route vrf MGMT 0.0.0.0/0 192.168.0.1", self.filtered)

    def test_the_ntp_local_interface_is_gone(self):
        """It names the management interface the filter removed."""
        self.assertIn("ntp local-interface", self.original)
        self.assertNotIn("ntp local-interface", self.filtered)

    def test_the_terminattr_daemon_is_gone(self):
        """It streams to CloudVision with an onboarding token the twin never has."""
        self.assertIn("daemon TerminAttr", self.original)
        self.assertNotIn("TerminAttr", self.filtered)

    def test_sflow_is_gone(self):
        """cEOS-lab rejects every sflow command with "not supported on this hardware platform"."""
        self.assertIn("sflow run", self.original)
        self.assertIn("   sflow enable", self.original)
        self.assertNotIn("sflow", self.filtered)

    def test_the_vrf_mgmt_instance_is_kept(self):
        """MLAG's heartbeat, the name servers and NTP all reference it."""
        self.assertIn("vrf instance MGMT", self.filtered)
        self.assertIn("   peer-address heartbeat 192.168.0.13 vrf MGMT", self.filtered)
        self.assertIn("no ip routing vrf MGMT", self.filtered)
        self.assertIn("ntp server vrf MGMT 0.north-america.pool.ntp.org prefer", self.filtered)

    # --- the reachability tail --------------------------------------------

    def test_the_tail_is_present_exactly_once(self):
        self.assertEqual(self.filtered.count("username admin privilege 15 role network-admin secret 0 admin"), 1)
        self.assertEqual(self.filtered.count("management api http-commands"), 1)
        self.assertEqual(self.filtered.count("interface Management1"), 1)
        self.assertEqual(self.filtered.count("   vrf default"), 1)
        self.assertIn(
            "\n".join(
                [
                    "username admin privilege 15 role network-admin secret 0 admin",
                    "!",
                    "interface Management1",
                    "   description TWIN_MANAGEMENT",
                    "   no shutdown",
                    "   ip address " + TWIN_ADDRESS,
                    "!",
                    "management api http-commands",
                    "   protocol https",
                    "   no shutdown",
                    "   vrf default",
                    "      no shutdown",
                ]
            ),
            self.filtered,
        )

    def test_the_tail_goes_before_end(self):
        self.assertTrue(self.original.rstrip("\n").endswith("end"))
        self.assertTrue(self.filtered.rstrip("\n").endswith("end"))
        self.assertEqual(self.filtered.count("\nend"), 1)

    def test_without_an_address_the_tail_omits_the_interface(self):
        filtered = filter_config(self.original)
        self.assertNotIn("interface Management1", filtered)
        self.assertIn("username admin privilege 15 role network-admin secret 0 admin", filtered)
        self.assertIn("   vrf default", filtered)

    def test_an_existing_admin_user_is_not_duplicated(self):
        text = self.original.replace(
            "no aaa root",
            "no aaa root\n!\nusername admin privilege 15 role network-admin secret 0 somethingelse",
        )
        filtered = filter_config(text, TWIN_ADDRESS)
        self.assertNotIn("somethingelse", filtered)
        self.assertEqual(filtered.count("username admin "), 1)

    # --- everything else is untouched -------------------------------------

    def test_the_validated_stanzas_are_byte_for_byte_identical(self):
        """BGP, the VLANs, and every Ethernet interface come through unchanged."""
        compared = 0
        for header, body in self.original_blocks.items():
            if header.startswith(
                (
                    "router bgp",
                    "vlan ",
                    "interface Ethernet",
                    "interface Vlan",
                    "interface Port-Channel",
                    "mlag configuration",
                )
            ):
                self.assertIn(header, self.filtered_blocks, "{0} was dropped".format(header))
                expected = "\n".join(line for line in body.splitlines() if line.strip() != "sflow enable")
                self.assertEqual(expected, self.filtered_blocks[header], "{0} was modified".format(header))
                compared += 1
        self.assertGreater(compared, 10, "the fixture should carry more than ten validated stanzas")

    def test_only_the_management_stanzas_changed(self):
        """Nothing but the management plane is dropped, rewritten, or added."""
        self.assertEqual(
            set(self.original_blocks) - set(self.filtered_blocks),
            {
                "daemon TerminAttr",
                "ip route vrf MGMT 0.0.0.0/0 192.168.0.1",
                "ntp local-interface vrf MGMT Management1",
                "sflow sample 10",
                "sflow polling-interval 50",
                "sflow destination 127.0.0.1 6343",
                "sflow source-interface Loopback0",
                "sflow run",
            },
        )
        self.assertEqual(
            set(self.filtered_blocks) - set(self.original_blocks),
            {"username admin privilege 15 role network-admin secret 0 admin"},
        )
        rewritten = {
            header
            for header, body in self.filtered_blocks.items()
            if header in self.original_blocks and body != self.original_blocks[header]
        }
        sflow_interfaces = {
            header
            for header, body in self.original_blocks.items()
            if header.startswith("interface ") and "sflow enable" in body
        }
        self.assertGreater(len(sflow_interfaces), 0)
        self.assertEqual(rewritten, {"interface Management1", "management api http-commands"} | sflow_interfaces)

    def test_the_username_cvpadmin_hash_survives(self):
        cvpadmin = [line for line in self.original.splitlines() if line.startswith("username cvpadmin ")]
        self.assertEqual(len(cvpadmin), 1)
        self.assertIn(cvpadmin[0], self.filtered)

    def test_the_banner_survives(self):
        self.assertIn("banner motd\nNTC + Arista lifecycle demo.", self.original)
        self.assertIn("banner motd\nNTC + Arista lifecycle demo.", self.filtered)

    # --- idempotency and the CLI ------------------------------------------

    def test_filtering_twice_is_filtering_once(self):
        self.assertEqual(filter_config(self.filtered, TWIN_ADDRESS), self.filtered)
        no_address = filter_config(self.original)
        self.assertEqual(filter_config(no_address), no_address)

    def test_an_empty_configuration_is_only_the_tail(self):
        self.assertEqual(
            filter_config(""),
            "!\nusername admin privilege 15 role network-admin secret 0 admin\n"
            "!\nmanagement api http-commands\n   protocol https\n   no shutdown\n"
            "   vrf default\n      no shutdown\n!\n",
        )

    def test_the_cli_writes_the_filtered_file(self):
        with tempfile.TemporaryDirectory() as workdir:
            destination = Path(workdir) / "dc1-leaf1.cfg"
            code = twin_config_filter.main(["--management-address", TWIN_ADDRESS, str(FIXTURE), str(destination)])
            self.assertEqual(code, 0)
            self.assertEqual(destination.read_text(encoding="utf-8"), self.filtered)

    def test_the_cli_reports_an_unreadable_source(self):
        with tempfile.TemporaryDirectory() as workdir, io.StringIO() as captured:
            with redirect_stderr(captured):
                code = twin_config_filter.main([str(Path(workdir) / "missing.cfg"), str(Path(workdir) / "out.cfg")])
            self.assertEqual(code, 1)
            self.assertIn("missing.cfg", captured.getvalue())

    def test_the_script_runs_as_a_subprocess(self):
        """The playbook calls this as `python3 twin_config_filter.py in out`."""
        with tempfile.TemporaryDirectory() as workdir:
            destination = Path(workdir) / "dc1-leaf1.cfg"
            result = subprocess.run(
                [sys.executable, str(MODULE_PATH), str(FIXTURE), str(destination)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(destination.read_text(encoding="utf-8"), filter_config(self.original))


class EveryGeneratedTwinConfigTest(unittest.TestCase):
    """Run the filter over the committed twin configs, if they are present.

    This is the regression net for a future AVD version rendering a management
    stanza this filter has not been taught about: no filtered configuration may
    leave the session in VRF MGMT or without an account to log in with.
    """

    def test_no_committed_twin_config_keeps_production_management(self):
        configs = sorted((REPO_ROOT / "sites/DC1/digital_twins/clab/intended/configs").glob("*.cfg"))
        if not configs:
            self.skipTest("the generated twin configs are not present")
        self.assertEqual(len(configs), 6)
        for config in configs:
            filtered = filter_config(config.read_text(encoding="utf-8"), TWIN_ADDRESS)
            for header, body in blocks(filtered).items():
                if header.startswith(("management ", "interface Management")):
                    self.assertNotIn("vrf MGMT", body, "{0}: {1}".format(config.name, header))
            self.assertIn("username admin privilege 15 role network-admin secret 0 admin", filtered)
            self.assertNotIn("ip address 192.168.0.", filtered, config.name)
            self.assertNotIn("ip route vrf MGMT 0.0.0.0/0 192.168.0.1", filtered, config.name)
            self.assertNotIn("TerminAttr", filtered, config.name)
            self.assertNotIn("sflow", filtered, config.name)


if __name__ == "__main__":
    unittest.main(verbosity=2 if os.environ.get("VERBOSE") else 1)
