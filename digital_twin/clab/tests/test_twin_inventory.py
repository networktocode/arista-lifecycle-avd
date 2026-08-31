#!/usr/bin/env python3
"""Offline tests for digital_twin/clab/twin_inventory.py.

Standard library only, so this runs on a bare CI runner:

    python3 digital_twin/clab/tests/test_twin_inventory.py

Each test starts a throwaway http.server on a random port that plays the part
of clab-api-server: it verifies the HS256 bearer token the script minted, then
answers /api/v1/labs with a canned body.
"""

import base64
import hashlib
import hmac
import importlib.util
import io
import json
import os
import re
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parent.parent / "twin_inventory.py"
SECRET_ENV = "TEST_CLAB_JWT_SECRET"
SECRET = "unit-test-secret"

_spec = importlib.util.spec_from_file_location("twin_inventory", MODULE_PATH)
twin_inventory = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(twin_inventory)


# The twin lab that Nautobot launched, plus the production lab it must ignore.
TWIN_LABS = {
    "labs": [
        {
            "name": "dc1",
            "containers": [
                {"name": "dc1-spine1.dc1.clab", "kind": "ceos", "ipv4_address": "192.168.0.10/24"},
            ],
        },
        {
            "name": "dc1-twin-42",
            "containers": [
                {"name": "dc1-spine1.dc1-twin-42.clab", "kind": "ceos", "ipv4_address": "172.20.20.11/24"},
                {"name": "dc1-spine2.dc1-twin-42.clab", "kind": "ceos", "ipv4_address": "172.20.20.12/24"},
                {"name": "dc1-leaf1.dc1-twin-42.clab", "kind": "ceos", "ipv4_address": "172.20.20.13/24"},
                {"name": "dc1-leaf2.dc1-twin-42.clab", "kind": "ceos", "ipv4_address": "172.20.20.14/24"},
                {"name": "dc1-host1.dc1-twin-42.clab", "kind": "linux", "ipv4_address": "172.20.20.50/24"},
                {"name": "dc1-host2.dc1-twin-42.clab", "kind": "linux", "ipv4_address": "172.20.20.51/24"},
            ],
        },
    ]
}

PRODUCTION_ONLY_LABS = {"labs": [TWIN_LABS["labs"][0]]}

# A different plausible v0.6.0 encoding: lab name keys mapping to container lists,
# camelCase fields, and addresses without a prefix length.
ALTERNATE_SHAPE = {
    "dc1": [{"containerName": "dc1-spine1", "kind": "ceos", "ipv4Address": "192.168.0.10"}],
    "dc1-twin-42": [
        {"containerName": "dc1-leaf1.dc1-twin-42", "kind": "ceos", "ipv4Address": "172.20.20.13"},
        {"containerName": "dc1-host1.dc1-twin-42", "kind": "linux", "ipv4Address": "172.20.20.50"},
    ],
}


def verify_token(header_value):
    """Verify the Authorization header the way clab-api-server would."""
    if not header_value or not header_value.startswith("Bearer "):
        return False
    token = header_value[len("Bearer ") :]
    parts = token.split(".")
    if len(parts) != 3:
        return False

    def decode(segment):
        return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))

    expected = base64.urlsafe_b64encode(
        hmac.new(SECRET.encode(), ".".join(parts[:2]).encode(), hashlib.sha256).digest()
    ).rstrip(b"=").decode()
    if not hmac.compare_digest(expected, parts[2]):
        return False
    header = json.loads(decode(parts[0]))
    claims = json.loads(decode(parts[1]))
    return (
        header.get("alg") == "HS256"
        and claims.get("username") == "admin"
        and claims.get("sub") == "admin"
        and claims["exp"] == claims["iat"] + 3600
    )


class _StubServer:
    """A one-endpoint stand-in for clab-api-server on a random port."""

    def __init__(self, payload):
        self.payload = payload
        self.bad_auth = False
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if not verify_token(self.headers.get("Authorization")):
                    stub.bad_auth = True
                    self.send_response(401)
                    self.end_headers()
                    return
                if self.path != "/api/v1/labs":
                    self.send_response(404)
                    self.end_headers()
                    return
                body = json.dumps(stub.payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:{0}".format(self.httpd.server_address[1])

    def __enter__(self):
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


def run_script(api_url, out_path, production="dc1"):
    """Run the script's main() and return (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = twin_inventory.main(
            [
                "--api",
                api_url,
                "--jwt-secret-env",
                SECRET_ENV,
                "--production",
                production,
                "--out",
                out_path,
                "--timeout",
                "10",
            ]
        )
    return code, out.getvalue(), err.getvalue()


class TwinInventoryTest(unittest.TestCase):
    def setUp(self):
        os.environ[SECRET_ENV] = SECRET
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.out = os.path.join(self.tmpdir.name, "twin_inventory.yml")

    def test_writes_inventory_for_the_non_production_lab(self):
        with _StubServer(TWIN_LABS) as stub:
            code, stdout, stderr = run_script(stub.url, self.out)
        self.assertEqual(code, 0, stderr)
        self.assertFalse(stub.bad_auth, "the stub rejected the minted JWT")
        text = Path(self.out).read_text()

        # Group and hosts, named after the production devices.
        self.assertIn("    DC1_TWIN:", text)
        self.assertIn("      hosts:", text)
        for host in ("dc1-spine1", "dc1-spine2", "dc1-leaf1", "dc1-leaf2"):
            self.assertIn('        "{0}":\n'.format(host), text)

        # The lab suffix is stripped, so no container name survives.
        self.assertNotIn("dc1-twin-42", text.split("containerlab lab", 1)[1].split("\n", 1)[1])

        # Twin addresses, not production ones.
        self.assertIn('          ansible_host: "172.20.20.11"', text)
        self.assertIn('          ansible_host: "172.20.20.14"', text)
        self.assertNotIn("192.168.0.10", text)

        # Linux endpoint hosts are skipped.
        self.assertNotIn("dc1-host1", text)
        self.assertNotIn("dc1-host2", text)

        # Connection vars for containerlab's default cEOS credentials.
        self.assertIn('        ansible_user: "admin"', text)
        self.assertIn('        ansible_password: "admin"', text)
        self.assertIn('        ansible_network_os: "arista.eos.eos"', text)
        self.assertIn('        ansible_connection: "ansible.netcommon.httpapi"', text)
        self.assertIn("        ansible_httpapi_use_ssl: true", text)
        self.assertIn("        ansible_httpapi_validate_certs: false", text)

        # No secret and no token anywhere in the output.
        self.assertNotIn(SECRET, text)
        self.assertNotIn(SECRET, stdout + stderr)
        self.assertNotIn("Bearer", stdout + stderr)

    def test_exits_2_when_only_the_production_lab_is_running(self):
        with _StubServer(PRODUCTION_ONLY_LABS) as stub:
            code, _stdout, stderr = run_script(stub.url, self.out)
        self.assertEqual(code, 2)
        self.assertIn(
            "no digital twin lab is running; launch Create & Deploy Digital Twin for DC1 first",
            stderr,
        )
        self.assertFalse(os.path.exists(self.out), "no inventory should be written without a twin")

    def test_handles_an_alternate_response_shape(self):
        with _StubServer(ALTERNATE_SHAPE) as stub:
            code, _stdout, stderr = run_script(stub.url, self.out)
        self.assertEqual(code, 0, stderr)
        text = Path(self.out).read_text()
        self.assertIn('        "dc1-leaf1":\n', text)
        self.assertIn('          ansible_host: "172.20.20.13"', text)
        self.assertNotIn("dc1-host1", text)

    def test_missing_secret_is_an_actionable_error(self):
        os.environ.pop(SECRET_ENV, None)
        code, _stdout, stderr = run_script("http://127.0.0.1:1", self.out)
        self.assertEqual(code, 1)
        self.assertIn(SECRET_ENV, stderr)

    def test_unreachable_api_is_an_actionable_error(self):
        code, _stdout, stderr = run_script("http://127.0.0.1:1", self.out)
        self.assertEqual(code, 1)
        self.assertIn("cannot reach the containerlab API server", stderr)

    def test_a_secret_with_a_trailing_newline_still_verifies(self):
        """A secret read from a file or pasted into a GitHub secret keeps its newline."""
        os.environ[SECRET_ENV] = SECRET + "\n"
        with _StubServer(TWIN_LABS) as stub:
            code, _stdout, stderr = run_script(stub.url, self.out)
        self.assertEqual(code, 0, stderr)
        self.assertFalse(stub.bad_auth, "the stub rejected a token minted from a padded secret")

    def test_a_whitespace_only_secret_is_still_an_error(self):
        os.environ[SECRET_ENV] = "   \n"
        code, _stdout, stderr = run_script("http://127.0.0.1:1", self.out)
        self.assertEqual(code, 1)
        self.assertIn(SECRET_ENV, stderr)

    def test_read_secret_strips(self):
        os.environ[SECRET_ENV] = "  padded-secret\n"
        self.assertEqual(twin_inventory.read_secret(SECRET_ENV), "padded-secret")

    def test_a_hostile_container_name_cannot_rewrite_the_inventory(self):
        """Names come from the API, so they are quoted, not trusted."""
        hostile = 'dc1-evil": {"ansible_host": "10.0.0.1"}\n#'
        rendered = twin_inventory.render_inventory([(hostile, "172.20.20.99")], "dc1-twin-42")
        hosts_section = rendered.split("      hosts:\n", 1)[1].split("      vars:", 1)[0]
        lines = hosts_section.splitlines()

        # One host key, one address under it, however the name is spelled.
        host_keys = [line for line in lines if re.match(r"^ {8}\S", line)]
        addresses = [line for line in lines if line.startswith("          ansible_host: ")]
        self.assertEqual(len(host_keys), 1, rendered)
        self.assertEqual(addresses, ['          ansible_host: "172.20.20.99"'], rendered)

        # The name is one double-quoted scalar: quotes and the newline escaped.
        self.assertTrue(host_keys[0].startswith('        "'), host_keys[0])
        self.assertTrue(host_keys[0].endswith('":'), host_keys[0])
        self.assertIn('\\"', host_keys[0])
        self.assertIn("\\n", host_keys[0])
        self.assertEqual(twin_inventory.yaml_double_quoted(hostile) + ":", host_keys[0].strip())

    def test_yaml_double_quoted(self):
        cases = [
            ("dc1-spine1", '"dc1-spine1"'),
            ('say "hi"', '"say \\"hi\\""'),
            ("back\\slash", '"back\\\\slash"'),
            ("two\nlines", '"two\\nlines"'),
            ("bell\x07", '"bell\\x07"'),
            ("plain: value #comment", '"plain: value #comment"'),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(twin_inventory.yaml_double_quoted(raw), expected)

    def test_a_hostile_lab_name_stays_inside_the_header_comment(self):
        rendered = twin_inventory.render_inventory([("dc1-spine1", "172.20.20.11")], "lab\nall:\n  hosts:")
        lines = rendered.splitlines()
        self.assertEqual(lines[0], "---")
        self.assertTrue(lines[1].startswith("# Generated by"), lines[1])
        self.assertIn("\\n", lines[1])
        self.assertTrue(lines[2].startswith("# Hosts carry"), lines[2])
        self.assertEqual(lines[3], "all:")
        self.assertEqual([line for line in lines if line == "all:"], ["all:"])

    def test_strip_lab_suffix(self):
        cases = [
            ("dc1-spine1.dc1-twin-42.clab", "dc1-twin-42", "dc1-spine1"),
            ("dc1-leaf1.dc1-twin-42", "dc1-twin-42", "dc1-leaf1"),
            ("dc1-leaf1", "dc1-twin-42", "dc1-leaf1"),
            ("dc1-leaf1.clab", "dc1-twin-42", "dc1-leaf1"),
        ]
        for raw, lab, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(twin_inventory.strip_lab_suffix(raw, lab), expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
