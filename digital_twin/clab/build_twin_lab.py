#!/usr/bin/env python3
"""Redeploy the digital twin with the pull request's configurations as startup configs.

The twin's nodes boot the configuration instead of receiving it over a runtime session.
EOS applies startup configuration without the platform-capability gating that runtime
sessions are subject to on cEOS-lab, so a booted twin comes up fully converged: routing,
BGP, VXLAN, everything the pull request is validating.

The flow:

1. Discover the running twin lab through the containerlab API server, exactly like
   ``twin_inventory.py`` (the lab whose name is not the production lab's).
2. Build a fresh containerlab topology for that lab from the production topology the AVD
   build renders (``topology.clab.yml``): same nodes and links, node names carrying the
   twin's suffix, management moved to the twin's own network with STATIC addresses that
   reuse each node's production last octet (so twin dc1-spine1 lives at .10 of the twin
   subnet, and the host's 3xxx SSH port band still reads last-octet).
3. Filter each node's twin-mode intended configuration through ``twin_config_filter``
   (management plane replaced with the twin's own static address and credentials) and
   embed it in the topology as an inline ``startup-config``.
4. ``POST /api/v1/labs?reconfigure=true`` deploys the new topology over the existing
   lab: same lab name and node names, so the Nautobot containerlab app's pages keep
   working against the same objects. (``PUT`` redeploys the lab's stored topology file
   and ignores a body, so it cannot carry new content.)
5. Poll every cEOS node's eAPI until it answers, so the validate job that follows runs
   ANTA against a booted, converged fabric.

Standard library plus PyYAML (present in the AVD universal image) for reading the
production topology; the topology is sent to the API server as JSON.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

from twin_config_filter import filter_config
from twin_inventory import mint_token

TWIN_CREDENTIALS = ("admin", "admin")
INTF_MAPPING_BIND = "/opt/clab/labs/EosIntfMapping.json:/mnt/flash/EosIntfMapping.json:ro"

NO_TWIN_MESSAGE = "no digital twin lab is running; run Nautobot's Deploy Twin & Publish PR job for DC1 first"


def api_request(api, token, path, method="GET", body=None, timeout=600):
    """One authenticated JSON request to the containerlab API server."""
    request = urllib.request.Request(
        api.rstrip("/") + path,
        method=method,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read() or "{}")


def select_twin_lab(labs, production):
    """The first lab that is not production; labs may be a dict or a list of objects."""
    if isinstance(labs, dict):
        names = sorted(labs)
    else:
        names = sorted(lab.get("name", "") for lab in labs)
    for name in names:
        if name and name != production:
            return name
    return None


def twin_mgmt_address(prod_address, twin_prefix):
    """Reuse the production node's last octet on the twin's management network."""
    octet = prod_address.rsplit(".", 1)[1]
    base = twin_prefix.split("/")[0].rsplit(".", 1)[0]
    length = twin_prefix.split("/")[1]
    return f"{base}.{octet}", length


def build_topology(prod_topology, lab_name, node_suffix, configs, mgmt_network, mgmt_subnet):
    """Return the twin lab's topology dict, with filtered configs embedded as startup configs.

    Pure: ``prod_topology`` is the parsed production topology, ``configs`` maps production
    node name to that node's twin-mode intended configuration text.
    """
    prod_nodes = prod_topology["topology"]["nodes"]
    nodes = {}
    addresses = {}
    for name, spec in prod_nodes.items():
        twin_name = name + node_suffix
        address, length = twin_mgmt_address(spec["mgmt-ipv4"], mgmt_subnet)
        addresses[name] = address
        node = {"kind": spec["kind"], "mgmt-ipv4": address}
        if spec["kind"] == "ceos":
            node["binds"] = [INTF_MAPPING_BIND]
            node["startup-config"] = filter_config(configs[name], f"{address}/{length}")
        nodes[twin_name] = node

    links = []
    for link in prod_topology["topology"]["links"]:
        endpoints = []
        for endpoint in link["endpoints"]:
            node, _, interface = endpoint.partition(":")
            endpoints.append(f"{node}{node_suffix}:{interface}")
        links.append({"endpoints": endpoints})

    kinds = {
        "ceos": {"image": prod_topology["topology"]["kinds"]["ceos"]["image"]},
        "linux": {"image": prod_topology["topology"]["kinds"]["linux"]["image"]},
    }

    return (
        {
            "name": lab_name,
            "prefix": "",
            "mgmt": {"network": mgmt_network, "ipv4-subnet": mgmt_subnet},
            "topology": {
                "defaults": {"env": {"INTFTYPE": "et"}},
                "kinds": kinds,
                "nodes": nodes,
                "links": links,
            },
        },
        addresses,
    )


def eapi_ready(address, timeout=10):
    """True when the node's eAPI answers a show version as the twin's admin user."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    auth = base64.b64encode(":".join(TWIN_CREDENTIALS).encode()).decode()
    body = {"jsonrpc": "2.0", "method": "runCmds", "params": {"version": 1, "cmds": ["show version"]}, "id": "1"}
    request = urllib.request.Request(
        f"https://{address}/command-api",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Basic {auth}"},
    )
    try:
        with urllib.request.urlopen(request, context=context, timeout=timeout) as response:
            return "error" not in json.loads(response.read())
    except (urllib.error.URLError, OSError, ValueError):
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--api", required=True, help="containerlab API server, e.g. http://host.docker.internal:8080")
    parser.add_argument("--jwt-secret-env", required=True, help="env var holding the API JWT secret")
    parser.add_argument("--production", required=True, help="the production lab name, never redeployed")
    parser.add_argument("--topology", required=True, help="the production topology.clab.yml the AVD build renders")
    parser.add_argument("--configs", required=True, help="directory of twin-mode intended configurations")
    parser.add_argument("--node-suffix", default=None, help="suffix on twin node names (default: .<production>.clab)")
    parser.add_argument("--mgmt-network", default="clab_twin")
    parser.add_argument("--mgmt-subnet", default="192.168.1.0/24")
    parser.add_argument("--boot-timeout", type=int, default=600, help="seconds to wait for every eAPI")
    args = parser.parse_args(argv)

    secret = os.environ.get(args.jwt_secret_env, "")
    if not secret:
        print(f"error: {args.jwt_secret_env} is empty", file=sys.stderr)
        return 1
    token = mint_token(secret)

    labs = api_request(args.api, token, "/api/v1/labs")
    lab_name = select_twin_lab(labs, args.production)
    if not lab_name:
        print(f"error: {NO_TWIN_MESSAGE}", file=sys.stderr)
        return 2

    import yaml  # noqa: PLC0415  (the universal image ships PyYAML; tests use build_topology directly)

    with open(args.topology, encoding="utf-8") as handle:
        prod_topology = yaml.safe_load(handle)

    suffix = args.node_suffix if args.node_suffix is not None else f".{args.production}.clab"
    configs = {}
    for name, spec in prod_topology["topology"]["nodes"].items():
        if spec["kind"] == "ceos":
            with open(os.path.join(args.configs, f"{name}.cfg"), encoding="utf-8") as handle:
                configs[name] = handle.read()

    topology, addresses = build_topology(prod_topology, lab_name, suffix, configs, args.mgmt_network, args.mgmt_subnet)

    print(f"Redeploying lab {lab_name} with {len(configs)} startup configurations...")
    api_request(args.api, token, "/api/v1/labs?reconfigure=true", method="POST", body={"topologyContent": topology})

    ceos = sorted(
        addresses[name] for name, spec in prod_topology["topology"]["nodes"].items() if spec["kind"] == "ceos"
    )
    deadline = time.monotonic() + args.boot_timeout
    pending = set(ceos)
    while pending and time.monotonic() < deadline:
        for address in sorted(pending):
            if eapi_ready(address):
                print(f"  {address}: eAPI up")
                pending.discard(address)
        if pending:
            time.sleep(10)
    if pending:
        print(f"error: eAPI never answered on {sorted(pending)}", file=sys.stderr)
        return 1
    print(f"Twin lab {lab_name} redeployed and booted with the pull request's configurations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
