#!/usr/bin/env python3
"""Write an Ansible inventory for the running containerlab digital twin.

The CI pipeline launches a digital twin of DC1 through Nautobot. The twin runs
on a containerlab host next to the production lab, under a different lab name,
so the only way to find it from a runner is to ask the containerlab API server
which labs are up and pick the one that is not production.

This script does that, then writes an inventory whose hosts carry the
PRODUCTION device names (dc1-spine1, dc1-leaf1, ...) even though the twin
containers are named after the twin lab. That naming is what lets the AVD
artifacts under sites/DC1 - intended configs and ANTA catalogs, both keyed by
device name - be pushed at and validated against the twin unchanged.

Standard library only, with an optional PyJWT fast path, so it runs on a bare
CI runner without a virtualenv. Usage:

    export CLAB_JWT_SECRET='...'          # the API server's shared JWT secret
    python3 digital_twin/clab/twin_inventory.py \\
        --api http://clab-host:8080 \\
        --jwt-secret-env CLAB_JWT_SECRET \\
        --production dc1 \\
        --out twin_inventory.yml

The secret is read from the environment and the minted token only ever goes
into an Authorization header, so neither appears in argv, in the output, or in
any message this script prints.

Exit codes:
    0   the inventory was written
    1   a configuration, network, or API error (the message says what to fix)
    2   no digital twin lab is running
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# ---------------------------------------------------------------------------
# Inventory shape
# ---------------------------------------------------------------------------

GROUP_NAME = "DC1_TWIN"

# Rendered verbatim into the group vars block. Values are already YAML.
# containerlab boots cEOS with its default credentials (admin/admin) and eAPI
# enabled over HTTPS with a self-signed certificate.
GROUP_VARS = (
    ("ansible_user", '"admin"'),
    ("ansible_password", '"admin"'),
    ("ansible_network_os", '"arista.eos.eos"'),
    ("ansible_connection", '"ansible.netcommon.httpapi"'),
    ("ansible_httpapi_use_ssl", "true"),
    ("ansible_httpapi_validate_certs", "false"),
)

# Containers whose production name matches this glob are the linux endpoint
# hosts in the topology, not switches, so they are left out of the inventory.
DEFAULT_SKIP_GLOB = "dc1-host*"

NO_TWIN_MESSAGE = "no digital twin lab is running; launch Create & Deploy Digital Twin for DC1 first"


class TwinError(Exception):
    """A failure that should stop the run with exit code 1."""


class NoTwinError(Exception):
    """No lab other than production is running; exit code 2."""


# ---------------------------------------------------------------------------
# clab-api-server field mapping
# ---------------------------------------------------------------------------
#
# Everything that depends on the API server's JSON field names lives in this
# section. Adjust the tuples below, and nothing else, if the API changes.

NAME_FIELDS = ("name", "container_name", "containerName", "Names", "shortname", "hostname")
IPV4_FIELDS = (
    "ipv4_address",
    "ipv4Address",
    "IPv4Address",
    "ipv4addr",
    "mgmt_ipv4_address",
    "mgmtIpv4Address",
    "mgmt-ipv4",
    "ipv4",
)
KIND_FIELDS = ("kind", "Kind", "node_kind", "nodeKind")
LAB_NAME_FIELDS = ("lab_name", "labName", "labname", "lab", "name", "Name")
CONTAINER_COLLECTION_FIELDS = ("containers", "Containers", "nodes", "Nodes")


def container_fields(entry):
    """Pull ``(name, ipv4, kind)`` out of one container entry.

    Written against clab-api-server v0.6.0. Its swagger was not reachable when
    this was authored, so fields are picked by presence rather than against a
    fixed schema: the name may be a string or docker's list-of-names, and the
    address may carry a prefix length. Any field that is absent comes back as
    ``None``.

    To adapt this to another API version, add the new field names to
    NAME_FIELDS / IPV4_FIELDS / KIND_FIELDS above. No other function in this
    script reads a raw API field name.
    """
    if not isinstance(entry, dict):
        return None, None, None

    name = _first_present(entry, NAME_FIELDS)
    if isinstance(name, (list, tuple)):
        name = name[0] if name else None
    if name is not None:
        name = str(name).lstrip("/").strip()

    ipv4 = _first_present(entry, IPV4_FIELDS)
    if isinstance(ipv4, dict):  # some encoders nest the address under a struct
        ipv4 = _first_present(ipv4, IPV4_FIELDS + ("address", "Address"))
    if ipv4 is not None:
        ipv4 = str(ipv4).split("/", 1)[0].strip()
        if ipv4 in ("", "N/A", "n/a", "<nil>"):
            ipv4 = None

    kind = _first_present(entry, KIND_FIELDS)
    if kind is not None:
        kind = str(kind).strip().lower()

    return name or None, ipv4, kind


def _first_present(mapping, fields):
    for field in fields:
        if field in mapping and mapping[field] not in (None, ""):
            return mapping[field]
    return None


def _as_container_list(value):
    """Normalise a container collection that may be a list or a name-keyed dict."""
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        containers = []
        for key, item in value.items():
            if isinstance(item, dict):
                merged = dict(item)
                merged.setdefault("name", key)
                containers.append(merged)
        return containers
    return []


def _extract_containers(lab_obj):
    """Return the container entries carried inside a lab object, if any."""
    if not isinstance(lab_obj, dict):
        return []
    for field in CONTAINER_COLLECTION_FIELDS:
        if field in lab_obj:
            return _as_container_list(lab_obj[field])
    return []


def _looks_like_container(entry):
    if not isinstance(entry, dict):
        return False
    if any(field in entry for field in CONTAINER_COLLECTION_FIELDS):
        return False
    if _first_present(entry, IPV4_FIELDS) is not None:
        return True
    return any(field in entry for field in ("lab_name", "labName", "labname", "state", "State", "kind", "Kind"))


def parse_labs(payload):
    """Return ``{lab name: [container entry, ...]}`` from a /api/v1/labs body.

    Tolerates the shapes clab-api-server v0.6.0 and containerlab itself have
    used: a bare list of labs, ``{"labs": [...]}``, a lab-name-keyed mapping of
    container lists, and a flat list of containers that each name their lab.
    """
    if isinstance(payload, dict):
        for wrapper in ("labs", "Labs", "data"):
            if wrapper in payload:
                return parse_labs(payload[wrapper])
        labs = {}
        for key, value in payload.items():
            if isinstance(value, list):
                labs[str(key)] = _as_container_list(value)
            elif isinstance(value, dict):
                name = _first_present(value, LAB_NAME_FIELDS) or key
                labs[str(name)] = _extract_containers(value)
        return labs

    if isinstance(payload, list):
        if payload and all(_looks_like_container(entry) for entry in payload):
            labs = {}
            for entry in payload:
                name = _first_present(entry, ("lab_name", "labName", "labname", "lab")) or ""
                labs.setdefault(str(name), []).append(entry)
            return labs
        labs = {}
        for entry in payload:
            if not isinstance(entry, dict):
                continue
            name = _first_present(entry, LAB_NAME_FIELDS)
            if name is None:
                continue
            labs[str(name)] = _extract_containers(entry)
        return labs

    raise TwinError(
        "the containerlab API returned an unexpected body for /api/v1/labs "
        "(expected a list of labs or an object with a 'labs' key); "
        "check that --api points at clab-api-server and not another service"
    )


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------


def _b64url(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def mint_token(secret, now=None):
    """Mint the HS256 bearer token clab-api-server expects.

    Uses PyJWT when it is importable and falls back to hmac/base64, which is
    all an HS256 token needs: three base64url segments, the third being
    HMAC-SHA256 over the first two.
    """
    issued_at = int(time.time()) if now is None else int(now)
    claims = {"username": "admin", "sub": "admin", "iat": issued_at, "exp": issued_at + 3600}

    try:
        import jwt  # noqa: PLC0415  (optional dependency, probed at call time)
    except ImportError:
        pass
    else:
        token = jwt.encode(claims, secret, algorithm="HS256")
        return token.decode("ascii") if isinstance(token, bytes) else token

    header = {"alg": "HS256", "typ": "JWT"}
    segments = [
        _b64url(json.dumps(header, separators=(",", ":"), sort_keys=True).encode("utf-8")),
        _b64url(json.dumps(claims, separators=(",", ":")).encode("utf-8")),
    ]
    signing_input = ".".join(segments).encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    segments.append(_b64url(signature))
    return ".".join(segments)


def read_secret(env_name):
    # Stripped, not just checked: a secret read from a file (`--body -` from a
    # here-doc, `$(cat ...)`, a GitHub secret pasted with a trailing return)
    # picks up surrounding whitespace, and an HMAC over " secret\n" is a
    # different HMAC from one over "secret". The API server strips its own copy,
    # so not stripping here is a 401 that looks like the wrong secret.
    secret = os.environ.get(env_name, "").strip()
    if not secret:
        raise TwinError(
            "the containerlab API JWT secret is empty: export {name} with the same secret "
            "clab-api-server was started with, or pass a different variable with "
            "--jwt-secret-env".format(name=env_name)
        )
    return secret


# ---------------------------------------------------------------------------
# API access
# ---------------------------------------------------------------------------


def api_get(base_url, path, token, timeout):
    url = base_url.rstrip("/") + path
    request = urllib.request.Request(
        url,
        headers={"Authorization": "Bearer " + token, "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise TwinError(
                "the containerlab API rejected the token (HTTP {code}) for {url}: the JWT secret "
                "does not match the one clab-api-server was started with".format(code=exc.code, url=url)
            ) from exc
        if exc.code == 404:
            raise TwinError(
                "the containerlab API has no {path} endpoint (HTTP 404): check that {base} is a "
                "clab-api-server v0.6.0 instance".format(path=path, base=base_url)
            ) from exc
        raise TwinError(
            "GET {url} failed with HTTP {code} {reason}".format(url=url, code=exc.code, reason=exc.reason)
        ) from exc
    except urllib.error.URLError as exc:
        raise TwinError(
            "cannot reach the containerlab API server at {url} ({reason}): check the host and that "
            "clab-api-server is listening on port 8080".format(url=url, reason=exc.reason)
        ) from exc
    except OSError as exc:
        raise TwinError("cannot reach the containerlab API server at {url} ({exc})".format(url=url, exc=exc)) from exc

    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise TwinError(
            "the containerlab API returned a non-JSON body for {url}: check that --api points at "
            "clab-api-server and not another service".format(url=url)
        ) from exc


# ---------------------------------------------------------------------------
# Inventory building
# ---------------------------------------------------------------------------


def strip_lab_suffix(container_name, lab_name):
    """Turn a twin container name into the production device name.

    ``dc1-spine1.dc1-twin.clab`` with lab ``dc1-twin`` becomes ``dc1-spine1``.
    """
    base = container_name
    for suffix in (".{0}.clab".format(lab_name), ".{0}".format(lab_name), ".clab"):
        if len(suffix) > 1 and base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base.split(".", 1)[0]


def _matches_glob(name, glob):
    import fnmatch  # noqa: PLC0415  (only needed here)

    return fnmatch.fnmatchcase(name, glob)


def select_twin_lab(labs, production):
    """Return ``(lab name, container entries)`` for the first non-production lab."""
    for name in sorted(labs):
        if name and name != production:
            return name, labs[name]
    raise NoTwinError(NO_TWIN_MESSAGE)


def build_hosts(lab_name, containers, skip_glob):
    """Map container entries to sorted ``(production name, ipv4)`` pairs."""
    hosts = {}
    skipped_without_address = []
    for entry in containers:
        raw_name, ipv4, kind = container_fields(entry)
        if not raw_name:
            continue
        name = strip_lab_suffix(raw_name, lab_name)
        if kind == "linux" or _matches_glob(name, skip_glob):
            continue
        if not ipv4:
            skipped_without_address.append(name)
            continue
        hosts[name] = ipv4

    if not hosts:
        if skipped_without_address:
            raise TwinError(
                "the digital twin lab '{lab}' has no container with a management IPv4 address "
                "({names}); the containers are probably still booting, so wait and rerun".format(
                    lab=lab_name, names=", ".join(sorted(skipped_without_address))
                )
            )
        raise TwinError(
            "the digital twin lab '{lab}' has no switch containers; check the twin topology that "
            "Create & Deploy Digital Twin for DC1 rendered".format(lab=lab_name)
        )
    return sorted(hosts.items())


# YAML characters that must not reach the output unescaped, plus the control
# characters a double-quoted scalar spells with an escape.
_YAML_ESCAPES = {"\\": "\\\\", '"': '\\"', "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def yaml_double_quoted(value):
    """Render ``value`` as a YAML double-quoted scalar.

    Host names and addresses come from the containerlab API, so they are not
    this script's to trust: a name carrying a quote, a colon, a ``#``, or a
    newline would otherwise rewrite the inventory's structure rather than
    appear in it. A double-quoted scalar with backslash escapes is safe for
    every byte, and keeps the value on one line.
    """
    rendered = ['"']
    for character in str(value):
        if character in _YAML_ESCAPES:
            rendered.append(_YAML_ESCAPES[character])
        elif ord(character) < 0x20 or ord(character) == 0x7F:
            rendered.append("\\x{0:02x}".format(ord(character)))
        else:
            rendered.append(character)
    rendered.append('"')
    return "".join(rendered)


def render_inventory(hosts, lab_name):
    lines = [
        "---",
        "# Generated by digital_twin/clab/twin_inventory.py from containerlab lab {0}.".format(
            yaml_double_quoted(lab_name)
        ),
        "# Hosts carry the production device names so the sites/DC1 artifacts apply unchanged.",
        "all:",
        "  children:",
        "    {0}:".format(GROUP_NAME),
        "      hosts:",
    ]
    for name, ipv4 in hosts:
        lines.append("        {0}:".format(yaml_double_quoted(name)))
        lines.append("          ansible_host: {0}".format(yaml_double_quoted(ipv4)))
    lines.append("      vars:")
    for key, value in GROUP_VARS:
        lines.append("        {0}: {1}".format(key, value))
    return "\n".join(lines) + "\n"


def write_twin_inventory(api, secret_env, production, out_path, timeout=30, skip_glob=DEFAULT_SKIP_GLOB):
    """Discover the twin and write the inventory. Returns ``(lab name, hosts)``."""
    token = mint_token(read_secret(secret_env))
    labs = parse_labs(api_get(api, "/api/v1/labs", token, timeout))
    lab_name, containers = select_twin_lab(labs, production)

    if not containers:
        # Some API versions only list lab names on the collection endpoint.
        detail = api_get(api, "/api/v1/labs/" + urllib.parse.quote(lab_name, safe=""), token, timeout)
        containers = _extract_containers(detail)
        if not containers:
            if isinstance(detail, list):
                containers = _as_container_list(detail)
            elif isinstance(detail, dict):
                containers = parse_labs(detail).get(lab_name, [])

    hosts = build_hosts(lab_name, containers, skip_glob)
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(render_inventory(hosts, lab_name))
    return lab_name, hosts


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Write an Ansible inventory for the running containerlab digital twin.",
    )
    parser.add_argument("--api", required=True, help="containerlab API server base URL, e.g. http://clab-host:8080")
    parser.add_argument(
        "--jwt-secret-env",
        default="CLAB_JWT_SECRET",
        help="name of the environment variable holding the API server's JWT secret (default: %(default)s)",
    )
    parser.add_argument("--production", default="dc1", help="name of the production lab to ignore (default: %(default)s)")
    parser.add_argument("--out", default="twin_inventory.yml", help="inventory file to write (default: %(default)s)")
    parser.add_argument("--timeout", type=float, default=30.0, help="API request timeout in seconds (default: %(default)s)")
    parser.add_argument(
        "--skip-glob",
        default=DEFAULT_SKIP_GLOB,
        help="skip containers whose production name matches this glob (default: %(default)s)",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        lab_name, hosts = write_twin_inventory(
            api=args.api,
            secret_env=args.jwt_secret_env,
            production=args.production,
            out_path=args.out,
            timeout=args.timeout,
            skip_glob=args.skip_glob,
        )
    except NoTwinError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except TwinError as exc:
        print("error: {0}".format(exc), file=sys.stderr)
        return 1

    print(
        "wrote {out} from containerlab lab '{lab}': {count} host(s) in {group} ({names})".format(
            out=args.out,
            lab=lab_name,
            count=len(hosts),
            group=GROUP_NAME,
            names=", ".join(name for name, _ in hosts),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
