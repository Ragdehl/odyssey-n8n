"""Deterministic guards for the narrow Cloudflare DEV product ingress."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

import scripts.odyssey_dev_public_routes as public_routes
from scripts.odyssey_dev_public_routes import (
    DEV_HOSTNAME,
    DEV_ORIGIN,
    PRODUCTION_HOSTNAME,
    ContractError,
    build_updated_config,
    load_inventory,
    routes_from_expression,
    tunnel_path_expression,
    validate_access_app,
    validate_tunnel_config,
)

INVENTORY = Path("deploy/odyssey-dev-product-routes.tsv")
LEGACY_EXPRESSION = (
    r"^/api/(odyssey|styles\.css|app\.js|client\.js|environment\.js|request|conversation)$"
)


def tunnel_config(expression: str = LEGACY_EXPRESSION) -> dict[str, object]:
    """Return the smallest realistic shared-tunnel configuration fixture."""
    return {
        "ingress": [
            {"hostname": "n8n.ragdehl.com", "service": "http://n8n:5678"},
            {
                "hostname": PRODUCTION_HOSTNAME,
                "service": "http://n8n:5678",
                "originRequest": {
                    "access": {
                        "audTag": ["production-audience"],
                        "required": True,
                        "teamName": "example-team",
                    }
                },
            },
            {"hostname": DEV_HOSTNAME, "path": expression, "service": DEV_ORIGIN},
            {"service": "http_status:404"},
        ],
        "warp-routing": {"enabled": False},
    }


def access_apps() -> list[dict[str, object]]:
    """Return a hostname-wide protected DEV Access application fixture."""
    return [
        {
            "id": "dev-app",
            "name": "Odyssey DEV",
            "type": "self_hosted",
            "domain": DEV_HOSTNAME,
            "self_hosted_domains": [DEV_HOSTNAME],
            "policies": [{"id": "allow", "decision": "allow"}],
        }
    ]


def test_inventory_is_the_complete_explicit_ui2_product_surface() -> None:
    """Keep browser assets and API operations in one narrow canonical inventory."""
    routes = load_inventory(INVENTORY)
    assert [(route.method, route.path, route.kind) for route in routes] == [
        ("GET", "/api/odyssey", "static"),
        ("GET", "/api/styles.css", "static"),
        ("GET", "/api/environment.js", "static"),
        ("GET", "/api/app.js", "static"),
        ("GET", "/api/client.js", "static"),
        ("GET", "/api/notes.js", "static"),
        ("GET", "/api/notes-client.js", "static"),
        ("POST", "/api/request", "api"),
        ("POST", "/api/conversation", "api"),
        ("POST", "/api/notes", "api"),
    ]


def test_reconciliation_adds_only_missing_dev_routes() -> None:
    """Preserve every shared-tunnel field except the stale DEV path expression."""
    routes = load_inventory(INVENTORY)
    before = tunnel_config()
    original = copy.deepcopy(before)
    after = build_updated_config(before, routes)

    assert before == original
    assert after["ingress"][0:2] == original["ingress"][0:2]  # type: ignore[index]
    assert after["ingress"][-1] == {"service": "http_status:404"}  # type: ignore[index]
    assert after["warp-routing"] == original["warp-routing"]
    assert validate_tunnel_config(after, routes) == tuple(route.path for route in routes)
    assert routes_from_expression(after["ingress"][2]["path"]) == tuple(  # type: ignore[index]
        route.path for route in routes
    )


def test_reconciliation_is_idempotent() -> None:
    """Avoid a control-plane write when the live route contract already matches."""
    routes = load_inventory(INVENTORY)
    current = tunnel_config(tunnel_path_expression(routes))
    assert build_updated_config(current, routes) == current


def test_reconciliation_rejects_an_unapproved_live_route() -> None:
    """Never remove or absorb an unexpected path during an authorized narrow update."""
    routes = load_inventory(INVENTORY)
    current = tunnel_config(r"^/api/(odyssey|admin)$")
    with pytest.raises(ContractError, match="outside the canonical inventory"):
        build_updated_config(current, routes)


def test_reconciliation_rejects_wrong_origin_or_open_fallback() -> None:
    """Fail closed rather than broadening origin or n8n editor reachability."""
    routes = load_inventory(INVENTORY)
    wrong_origin = tunnel_config()
    wrong_origin["ingress"][2]["service"] = "http://n8n:5678"  # type: ignore[index]
    with pytest.raises(ContractError, match="unexpected origin"):
        build_updated_config(wrong_origin, routes)

    open_fallback = tunnel_config()
    open_fallback["ingress"][-1] = {"service": "http://n8n:5678"}  # type: ignore[index]
    with pytest.raises(ContractError, match="explicit 404"):
        build_updated_config(open_fallback, routes)


def test_access_validation_requires_hostname_wide_allow_protection() -> None:
    """Keep all explicit DEV routes behind the existing host-wide Access boundary."""
    app = validate_access_app(access_apps())
    assert app["domain"] == DEV_HOSTNAME

    path_limited = access_apps()
    path_limited[0]["self_hosted_domains"] = [f"{DEV_HOSTNAME}/api/odyssey"]
    with pytest.raises(ContractError, match="hostname-wide"):
        validate_access_app(path_limited)

    denied = access_apps()
    denied[0]["policies"] = [{"decision": "deny"}]
    with pytest.raises(ContractError, match="policy decision"):
        validate_access_app(denied)


@pytest.mark.parametrize(
    ("failure", "expected"),
    [
        (FileNotFoundError("token unavailable"), "UNKNOWN"),
        (ContractError("route mismatch"), "DRIFT"),
    ],
)
def test_machine_status_distinguishes_unavailable_control_plane_from_drift(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: Exception,
    expected: str,
) -> None:
    """Keep missing credentials/network distinct from an authoritative live mismatch."""

    def fail_inspection(_inventory: Path) -> dict[str, object]:
        raise failure

    monkeypatch.setattr(public_routes, "inspect_live", fail_inspection)
    monkeypatch.setattr(
        "sys.argv",
        ["odyssey_dev_public_routes.py", "status", "--inventory", str(INVENTORY), "--machine"],
    )
    assert public_routes.main() == 1
    assert capsys.readouterr().out.strip() == expected


def test_live_update_requires_explicit_human_authorization_flag(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Prevent the checked-in repair command from becoming routine implicit authority."""
    monkeypatch.setattr(
        "sys.argv",
        ["odyssey_dev_public_routes.py", "update", "--inventory", str(INVENTORY)],
    )
    assert public_routes.main() == 2
    assert "requires --authorized-dev-change" in capsys.readouterr().err
