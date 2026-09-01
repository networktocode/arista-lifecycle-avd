#!/usr/bin/env python3
"""Offline tests for digital_twin/clab/build_twin_lab.py.

Standard library only: the topology builder is a pure function over parsed dicts, so no
YAML parser or network is needed.

    python3 digital_twin/clab/tests/test_build_twin_lab.py
"""

import importlib.util
import os
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures" / "dc1-leaf1-intended.cfg"


def _load(name):
    spec = importlib.util.spec_from_file_location(name, HERE.parent / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


import sys

sys.path.insert(0, str(HERE.parent))
build_twin_lab = _load("build_twin_lab")

PROD_TOPOLOGY = {
    "name": "dc1",
    "prefix": "",
    "mgmt": {"network": "clab_mgmt", "ipv4-subnet": "192.168.0.0/24"},
    "topology": {
        "defaults": {"env": {"INTFTYPE": "et"}},
        "kinds": {
            "ceos": {"image": "arista/ceos:latest", "startup-config": "init-configs/basic.cfg"},
            "linux": {"image": "ghcr.io/aristanetworks/aclabs/host-ubuntu:rev1.2"},
        },
        "nodes": {
            "dc1-spine1": {"kind": "ceos", "mgmt-ipv4": "192.168.0.10"},
            "dc1-leaf1": {"kind": "ceos", "mgmt-ipv4": "192.168.0.12"},
            "dc1-host1": {"kind": "linux", "mgmt-ipv4": "192.168.0.50"},
        },
        "links": [
            {"endpoints": ["dc1-spine1:et1_1", "dc1-leaf1:et49_1"]},
            {"endpoints": ["dc1-leaf1:et1", "dc1-host1:eth1"]},
        ],
    },
}


class BuildTopologyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        intended = FIXTURE.read_text(encoding="utf-8")
        cls.configs = {"dc1-spine1": intended, "dc1-leaf1": intended}
        cls.topology, cls.addresses = build_twin_lab.build_topology(
            PROD_TOPOLOGY, "dc1clab", ".dc1.clab", cls.configs, "clab_twin", "192.168.1.0/24"
        )
        cls.nodes = cls.topology["topology"]["nodes"]

    def test_lab_identity_and_management_network(self):
        self.assertEqual(self.topology["name"], "dc1clab")
        self.assertEqual(self.topology["prefix"], "")
        self.assertEqual(self.topology["mgmt"], {"network": "clab_twin", "ipv4-subnet": "192.168.1.0/24"})

    def test_nodes_carry_the_twin_suffix_and_production_octets(self):
        self.assertEqual(sorted(self.nodes), ["dc1-host1.dc1.clab", "dc1-leaf1.dc1.clab", "dc1-spine1.dc1.clab"])
        self.assertEqual(self.nodes["dc1-spine1.dc1.clab"]["mgmt-ipv4"], "192.168.1.10")
        self.assertEqual(self.nodes["dc1-leaf1.dc1.clab"]["mgmt-ipv4"], "192.168.1.12")
        self.assertEqual(self.nodes["dc1-host1.dc1.clab"]["mgmt-ipv4"], "192.168.1.50")

    def test_ceos_nodes_boot_a_filtered_startup_config(self):
        config = self.nodes["dc1-leaf1.dc1.clab"]["startup-config"]
        self.assertIn("username admin privilege 15 role network-admin secret 0 admin", config)
        self.assertIn("ip address 192.168.1.12/24", config)
        self.assertNotIn("192.168.0.12/24", config)
        self.assertNotIn("TerminAttr", config)
        self.assertNotIn("sflow", config)
        self.assertIn(build_twin_lab.INTF_MAPPING_BIND, self.nodes["dc1-leaf1.dc1.clab"]["binds"])

    def test_linux_nodes_have_no_startup_config(self):
        self.assertNotIn("startup-config", self.nodes["dc1-host1.dc1.clab"])
        self.assertNotIn("binds", self.nodes["dc1-host1.dc1.clab"])

    def test_the_kind_level_startup_config_is_dropped(self):
        self.assertNotIn("startup-config", self.topology["topology"]["kinds"]["ceos"])

    def test_links_are_renamed_per_side(self):
        self.assertEqual(
            self.topology["topology"]["links"][0]["endpoints"],
            ["dc1-spine1.dc1.clab:et1_1", "dc1-leaf1.dc1.clab:et49_1"],
        )
        self.assertEqual(
            self.topology["topology"]["links"][1]["endpoints"],
            ["dc1-leaf1.dc1.clab:et1", "dc1-host1.dc1.clab:eth1"],
        )


class SelectTwinLabTest(unittest.TestCase):
    def test_dict_and_list_shapes(self):
        self.assertEqual(build_twin_lab.select_twin_lab({"dc1": [], "dc1clab": []}, "dc1"), "dc1clab")
        self.assertEqual(build_twin_lab.select_twin_lab([{"name": "dc1"}, {"name": "x"}], "dc1"), "x")
        self.assertIsNone(build_twin_lab.select_twin_lab({"dc1": []}, "dc1"))


if __name__ == "__main__":
    unittest.main(verbosity=2 if os.environ.get("VERBOSE") else 1)
