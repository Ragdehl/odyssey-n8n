"""Static contract checks for the framework-free Odyssey Online browser surface."""

from html.parser import HTMLParser
from pathlib import Path

WEB_ROOT = Path("odyssey_web")


class _IndexParser(HTMLParser):
    """Collect the small set of HTML attributes required by the MVP contract."""

    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.links: list[str] = []
        self.scripts: list[tuple[str | None, str | None]] = []
        self.api_endpoint: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        element_id = values.get("id")
        if element_id:
            self.ids.add(element_id)
        if tag == "link" and values.get("href"):
            self.links.append(values["href"] or "")
        if tag == "script":
            self.scripts.append((values.get("type"), values.get("src")))
        if tag == "meta" and values.get("name") == "odyssey-api-endpoint":
            self.api_endpoint = values.get("content")


def test_static_frontend_has_transcript_and_composer_contract_elements() -> None:
    """The checked-in page exposes a session transcript and narrow product composer seams."""

    parser = _IndexParser()
    parser.feed((WEB_ROOT / "index.html").read_text(encoding="utf-8"))

    assert parser.api_endpoint == "/api/request"
    assert "./styles.css" in parser.links
    assert (None, "./environment.js") in parser.scripts
    assert ("module", "./app.js") in parser.scripts
    assert {
        "odyssey-form",
        "request-input",
        "send-button",
        "interaction",
    } <= parser.ids

    app = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    assert "conversation.append(article)" in app
    assert "conversation.scrollTop = conversation.scrollHeight" in app
    assert 'globalThis.matchMedia?.("(pointer: coarse)").matches' in app
    assert "if (event.shiftKey) return;" in app
    assert 'event.key !== "Enter" || event.isComposing' in app
    assert "appendRetryControl(retrySubmission)" in app
    assert "void sendSubmission(submission, true)" in app
    assert 'deployment.environment !== "DEV"' in app
    assert "marker.textContent = deployment.commit" in app

    index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    assert 'enterkeyhint="enter"' in index

    styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")
    assert ".workspace { display: grid; grid-template-rows: minmax(0, 1fr) auto;" in styles
    assert ".conversation { display: flex; flex-direction: column;" in styles
    assert "overflow-y: auto" in styles
    assert '.conversation::before { content: ""; flex: 1 0 0; }' in styles
    assert ".deployment-marker" in styles

    environment = (WEB_ROOT / "environment.js").read_text(encoding="utf-8")
    assert 'environment: "PROD"' in environment


def test_frontend_has_no_external_asset_or_browser_persistence_dependency() -> None:
    """The offline checkpoint stays self-contained and creates no durable browser history."""

    index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    app = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    client = (WEB_ROOT / "client.js").read_text(encoding="utf-8")
    combined = "\n".join((index, app, client))

    assert "https://" not in index
    assert "http://" not in index
    assert "localStorage" not in combined
    assert "sessionStorage" not in combined
    assert "innerHTML" not in combined
    assert "request_id" in client
    assert 'credentials: "same-origin"' in client
    assert "PRODUCT_REQUEST_TIMEOUT_MS = 125_000" in client
    assert "signal: controller.signal" in client
