#!/usr/bin/env python3
"""Validate and narrowly reconcile Odyssey's public DEV Cloudflare route contract."""

from __future__ import annotations

import argparse
import copy
import json
import re
import stat
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ACCOUNT_ID = "224a4945cdca213494403f1e84673e2e"
TUNNEL_ID = "0b99a438-fdb8-4978-9035-ef48df039bc4"
DEV_HOSTNAME = "odyssey-dev.ragdehl.com"
DEV_ORIGIN = "http://172.18.0.1:28780"  # NOSONAR - same-host Docker bridge behind edge TLS.
PRODUCTION_HOSTNAME = "odyssey.ragdehl.com"
TOKEN_FILE = Path("/home/ragdehl/.config/odyssey/secrets/cloudflare-api-token")
API_ROOT = "https://api.cloudflare.com/client/v4"
INVENTORY_FILE = Path(__file__).resolve().parents[1] / "deploy" / "odyssey-dev-product-routes.tsv"


class ContractError(RuntimeError):
    """Report a fail-closed mismatch in the bounded DEV public-route contract."""


class ControlPlaneUnavailable(ContractError):
    """Report that live Cloudflare state could not be read authoritatively."""


@dataclass(frozen=True)
class ProductRoute:
    """Describe one explicitly allowed Odyssey DEV browser or API route."""

    method: str
    path: str
    kind: str


def load_inventory(path: Path) -> tuple[ProductRoute, ...]:
    """Load the canonical explicit DEV route inventory and reject unsafe entries."""
    routes: list[ProductRoute] = []
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) != 3:
            raise ContractError(f"invalid route inventory line {line_number}")
        method, route_path, kind = parts
        if method not in {"GET", "POST"} or kind not in {"static", "api"}:
            raise ContractError(f"invalid route inventory contract on line {line_number}")
        if not re.fullmatch(r"/api/[A-Za-z0-9.-]+", route_path):
            raise ContractError(f"unsafe route inventory path on line {line_number}")
        routes.append(ProductRoute(method=method, path=route_path, kind=kind))
    if not routes or len({route.path for route in routes}) != len(routes):
        raise ContractError("route inventory must contain unique paths")
    return tuple(routes)


def tunnel_path_expression(routes: tuple[ProductRoute, ...]) -> str:
    """Build the exact anchored Cloudflare tunnel expression for the route inventory."""
    alternatives = [route.path.removeprefix("/api/").replace(".", r"\.") for route in routes]
    return rf"^/api/({'|'.join(alternatives)})$"


def routes_from_expression(expression: str) -> tuple[str, ...]:
    """Decode only Odyssey's bounded exact-path expression, rejecting wildcards."""
    prefix = "^/api/("
    suffix = ")$"
    if not expression.startswith(prefix) or not expression.endswith(suffix):
        raise ContractError("DEV tunnel path is not an exact Odyssey API expression")
    encoded = expression[len(prefix) : -len(suffix)]
    if not encoded:
        raise ContractError("DEV tunnel path expression is empty")
    paths: list[str] = []
    for alternative in encoded.split("|"):
        decoded = alternative.replace(r"\.", ".")
        if "\\" in decoded or not re.fullmatch(r"[A-Za-z0-9.-]+", decoded):
            raise ContractError("DEV tunnel path contains unsupported regex semantics")
        paths.append(f"/api/{decoded}")
    if len(set(paths)) != len(paths):
        raise ContractError("DEV tunnel path expression contains duplicates")
    return tuple(paths)


def _find_dev_ingress(config: dict[str, Any]) -> dict[str, Any]:
    """Return the unique DEV ingress rule from a Cloudflare tunnel configuration."""
    ingress = config.get("ingress")
    if not isinstance(ingress, list):
        raise ContractError("tunnel configuration has no ingress list")
    matches = [item for item in ingress if item.get("hostname") == DEV_HOSTNAME]
    if len(matches) != 1:
        raise ContractError("tunnel must contain exactly one Odyssey DEV ingress rule")
    rule = matches[0]
    if rule.get("service") != DEV_ORIGIN:
        raise ContractError("Odyssey DEV ingress targets an unexpected origin")
    if set(rule) - {"hostname", "path", "service"}:
        raise ContractError("Odyssey DEV ingress contains unexpected settings")
    return rule


def validate_tunnel_config(
    config: dict[str, Any], routes: tuple[ProductRoute, ...]
) -> tuple[str, ...]:
    """Validate that the live DEV rule exactly covers the canonical route inventory."""
    rule = _find_dev_ingress(config)
    expression = rule.get("path")
    if not isinstance(expression, str):
        raise ContractError("Odyssey DEV ingress has no path expression")
    actual = routes_from_expression(expression)
    expected = tuple(route.path for route in routes)
    if set(actual) != set(expected) or len(actual) != len(expected):
        raise ContractError("Odyssey DEV public route inventory is stale")
    fallback = config.get("ingress", [])[-1]
    if fallback != {"service": "http_status:404"}:
        raise ContractError("tunnel fallback is not the required explicit 404")
    return actual


def build_updated_config(
    config: dict[str, Any], routes: tuple[ProductRoute, ...]
) -> dict[str, Any]:
    """Return a copy with only the bounded DEV path expression reconciled."""
    current_rule = _find_dev_ingress(config)
    expression = current_rule.get("path")
    if not isinstance(expression, str):
        raise ContractError("Odyssey DEV ingress has no path expression")
    current_routes = set(routes_from_expression(expression))
    expected_routes = {route.path for route in routes}
    if not current_routes <= expected_routes:
        raise ContractError("DEV ingress contains a route outside the canonical inventory")
    if config.get("ingress", [])[-1] != {"service": "http_status:404"}:
        raise ContractError("tunnel fallback is not the required explicit 404")
    updated = copy.deepcopy(config)
    updated_rule = _find_dev_ingress(updated)
    updated_rule["path"] = tunnel_path_expression(routes)
    return updated


def validate_access_app(apps: list[dict[str, Any]]) -> dict[str, Any]:
    """Require one hostname-wide DEV Access application with an allow policy."""
    matches = [app for app in apps if app.get("domain") == DEV_HOSTNAME]
    if len(matches) != 1:
        raise ContractError("Cloudflare Access must contain one Odyssey DEV application")
    app = matches[0]
    if app.get("type") != "self_hosted":
        raise ContractError("Odyssey DEV Access application is not self-hosted")
    domains = app.get("self_hosted_domains")
    if domains != [DEV_HOSTNAME]:
        raise ContractError("Odyssey DEV Access application is not hostname-wide")
    policies = app.get("policies")
    if not isinstance(policies, list) or not policies:
        raise ContractError("Odyssey DEV Access application has no policy")
    if any(policy.get("decision") != "allow" for policy in policies):
        raise ContractError("Odyssey DEV Access application has an unexpected policy decision")
    return app


def _read_token(path: Path) -> str:
    """Read the protected API token without exposing it through output or arguments."""
    file_stat = path.stat()
    if not stat.S_ISREG(file_stat.st_mode) or file_stat.st_mode & 0o077:
        raise ContractError("Cloudflare API token file permissions are unsafe")
    token = path.read_text(encoding="utf-8").strip()
    if not token or "\n" in token:
        raise ContractError("Cloudflare API token file is invalid")
    return token


def _api_request(
    path: str,
    token: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> Any:
    """Call one fixed Cloudflare API resource and return its successful result."""
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    request = urllib.request.Request(
        f"{API_ROOT}{path}",
        data=body,
        method=method,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            document = json.load(response)
    except urllib.error.HTTPError as error:
        try:
            error_document = json.loads(error.read())
            errors = error_document.get("errors", [])
        except (json.JSONDecodeError, AttributeError):
            errors = []
        raise ControlPlaneUnavailable(
            f"Cloudflare API returned HTTP {error.code}: {errors}"
        ) from error
    except OSError as error:
        raise ControlPlaneUnavailable(f"Cloudflare API is unavailable: {error}") from error
    if document.get("success") is not True:
        raise ControlPlaneUnavailable(
            f"Cloudflare API rejected the request: {document.get('errors', [])}"
        )
    return document.get("result")


def _fetch_tunnel(token: str) -> dict[str, Any]:
    """Fetch the fixed shared tunnel configuration used by Odyssey DEV."""
    result = _api_request(f"/accounts/{ACCOUNT_ID}/cfd_tunnel/{TUNNEL_ID}/configurations", token)
    if not isinstance(result, dict) or not isinstance(result.get("config"), dict):
        raise ContractError("Cloudflare tunnel response is invalid")
    return result


def _fetch_access_apps(token: str) -> list[dict[str, Any]]:
    """Fetch Access applications in the fixed account for DEV protection validation."""
    result = _api_request(f"/accounts/{ACCOUNT_ID}/access/apps?per_page=100", token)
    if not isinstance(result, list):
        raise ContractError("Cloudflare Access response is invalid")
    return result


def _production_ingress(config: dict[str, Any]) -> dict[str, Any]:
    """Return the unique production Odyssey ingress for before/after comparison."""
    matches = [
        item for item in config.get("ingress", []) if item.get("hostname") == PRODUCTION_HOSTNAME
    ]
    if len(matches) != 1:
        raise ContractError("shared tunnel has no unique production Odyssey ingress")
    return matches[0]


def inspect_live() -> dict[str, Any]:
    """Inspect and validate the live DEV tunnel plus hostname-wide Access boundary."""
    routes = load_inventory(INVENTORY_FILE)
    token = _read_token(TOKEN_FILE)
    tunnel = _fetch_tunnel(token)
    config = tunnel["config"]
    access = validate_access_app(_fetch_access_apps(token))
    actual_routes = validate_tunnel_config(config, routes)
    _production_ingress(config)
    return {
        "version": tunnel.get("version"),
        "routes": actual_routes,
        "access_name": access.get("name"),
        "access_policy_count": len(access.get("policies", [])),
    }


def update_live() -> dict[str, Any]:
    """Add only missing canonical DEV paths and verify all other live state is unchanged."""
    routes = load_inventory(INVENTORY_FILE)
    token = _read_token(TOKEN_FILE)
    before_tunnel = _fetch_tunnel(token)
    before_config = before_tunnel["config"]
    before_production = copy.deepcopy(_production_ingress(before_config))
    before_access = copy.deepcopy(validate_access_app(_fetch_access_apps(token)))
    updated_config = build_updated_config(before_config, routes)
    changed = updated_config != before_config
    if changed:
        _api_request(
            f"/accounts/{ACCOUNT_ID}/cfd_tunnel/{TUNNEL_ID}/configurations",
            token,
            method="PUT",
            payload={"config": updated_config},
        )
    after_tunnel = _fetch_tunnel(token)
    after_config = after_tunnel["config"]
    actual_routes = validate_tunnel_config(after_config, routes)
    if after_config != updated_config:
        raise ContractError(
            "post-update tunnel configuration differs from the approved narrow diff"
        )
    if _production_ingress(after_config) != before_production:
        raise ContractError("production Odyssey ingress changed unexpectedly")
    after_access = validate_access_app(_fetch_access_apps(token))
    if after_access != before_access:
        raise ContractError("Odyssey DEV Access application changed unexpectedly")
    return {
        "changed": changed,
        "before_version": before_tunnel.get("version"),
        "after_version": after_tunnel.get("version"),
        "routes": actual_routes,
        "production_unchanged": True,
        "access_unchanged": True,
    }


def _parser() -> argparse.ArgumentParser:
    """Build the bounded command-line interface for status and authorized reconciliation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "update"))
    parser.add_argument("--machine", action="store_true")
    parser.add_argument(
        "--authorized-dev-change",
        action="store_true",
        help="confirm separate human authorization for the DEV-only Cloudflare mutation",
    )
    return parser


def main() -> int:
    """Run a read-only live check or the explicitly authorized narrow DEV update."""
    arguments = _parser().parse_args()
    if arguments.action == "update" and not arguments.authorized_dev_change:
        print(
            "odyssey-dev-public-routes: update requires --authorized-dev-change",
            file=sys.stderr,
        )
        return 2
    try:
        result = inspect_live() if arguments.action == "status" else update_live()
    except (ContractError, OSError) as error:
        if arguments.machine:
            print("UNKNOWN" if isinstance(error, (ControlPlaneUnavailable, OSError)) else "DRIFT")
        else:
            print(f"odyssey-dev-public-routes: {error}", file=sys.stderr)
        return 1
    if arguments.machine:
        print("MATCH")
    else:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
