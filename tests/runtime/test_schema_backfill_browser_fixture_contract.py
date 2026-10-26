"""Offline safety contract for opt-in real Chromium/source-local Core acceptance."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NODE = ROOT / "scripts/odyssey_schema_backfill_chromium_local.cjs"
PYTHON = ROOT / "scripts/odyssey_schema_backfill_chromium_local.py"


def test_fixture_is_credential_free_ephemeral_and_never_targets_prod():
    browser = NODE.read_text()
    driver = PYTHON.read_text()
    assert "127.0.0.1" in browser
    assert 'assert.equal(upstream.hostname,"127.0.0.1")' in browser
    assert "Object.keys(body).some(" in browser
    assert '"schema_scan","schema_backfill"' in browser
    assert "schema_confirm" not in browser
    assert "schema_suggest" not in browser
    assert "schema_review" not in browser
    assert "curl" not in browser
    assert "Authorization" not in browser
    assert "process.env.ODYSSEY_SYNTH_LOCAL_HTTP" in browser
    assert "new URL(process.env.ODYSSEY_SYNTH_LOCAL_HTTP" in browser
    assert "tempfile.TemporaryDirectory(" in driver
    assert '"/tmp"' in driver
    assert "fixture(container)" in driver
    assert "ThreadingHTTPServer" in driver
    assert "_handler_for(app)" in driver
    assert "repo.read_text(path)" in driver
    assert "assert commits == 2" in driver
    assert 'browser.get("reloadPersisted")' in driver
    assert "/data/odyssey" not in browser + driver
    assert "Cloudflare" not in browser + driver


def test_browser_labels_real_and_unverified_boundaries_separately():
    browser = NODE.read_text()
    driver = PYTHON.read_text()
    assert 'n8n:n8nSocket ? "REAL_OFFLINE" : "NOT_TESTED"' in browser
    assert "deployedDev:false" in browser
    assert "ODYSSEY_SYNTH_N8N_SOCKET" in browser
    assert "socketPath:n8nSocket" in browser
    assert '"n8n": "NOT_TESTED"' in driver
    assert '"DEV": "NOT_TESTED"' in driver
    assert "page.click(" in browser
    assert "page.reload(" in browser
    assert "schema_backfill:advance" in browser
    assert "assert.equal(overflow,false" in browser
    assert "assert.equal(errors.length,0" in browser
