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
        "request-detail-sheet",
        "request-detail-content",
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
    assert "appendDetailButton(message, result.request_detail)" in app
    assert "renderProductResultWithContinuity" in app
    assert "appendContinuityWarning" in app
    assert "La respuesta se ha obtenido" in app
    assert (
        "The existing chat remains usable if the optional history projection is unavailable." in app
    )
    success_flow = app[
        app.index("const result = await requestProductResult") : app.index("} catch (error)")
    ]
    assert success_flow.index("retrySubmission = null") < success_flow.index(
        "renderProductResultWithContinuity"
    )
    assert "appendRetryControl" not in success_flow
    assert 'header.className = "message-header"' in app
    assert 'article.querySelector(".message-header")?.append(button)' in app
    assert "requestDetailSheet.showModal()" in app
    assert 'const MAIN_CONVERSATION_ID = "main"' in app
    assert 'operation: "main"' in app
    assert "payload: {limit: 40}" in app
    assert "payload: {limit: 40, before: cursor}" in app
    assert "if (!hasOlder || !olderCursor || loadingOlder) return;" in app
    assert "loadingOlder = true" in app
    assert (
        "conversation.scrollTop = previousTop + conversation.scrollHeight - previousHeight" in app
    )
    assert 'conversation.addEventListener("scroll"' in app
    assert 'article.querySelector(".detail-button")' in app
    assert "olderCursor = data.before ?? null" in app
    assert "hasOlder = data.has_older === true" in app
    assert "loadConversationList" not in app
    assert "startConversation" not in app

    index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    assert 'enterkeyhint="enter"' in index
    assert "Nuevo chat" not in index
    assert 'id="conversation-list"' not in index

    styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")
    assert ".workspace { display: grid; grid-template-rows: minmax(0, 1fr) auto;" in styles
    assert ".conversation { display: flex; flex-direction: column;" in styles
    assert ".message-header { display: flex; align-items: center;" in styles
    assert (
        ".detail-button { display: inline-grid; flex: 0 0 2.75rem; min-height: 2.75rem;" in styles
    )
    assert "overflow-y: auto" in styles
    assert '.conversation::before { content: ""; flex: 1 0 0; }' in styles
    assert ".deployment-marker" in styles
    assert ".continuity-warning" in styles

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
    assert "validateRequestDetail" in client
    assert "request_detail" in client
    assert "validateEstimatedCost" in client
    assert '"Coste estimado"' in app
    assert '"Base de precios"' in app


def test_static_asset_workflow_forces_revalidation_after_dev_deploy() -> None:
    """Prevent normal reloads from retaining an older deployment's app assets."""
    workflow = (Path("workflows") / "odyssey-online-static.ts").read_text(encoding="utf-8")
    assert "Cache-Control" in workflow
    assert "no-cache, no-store, must-revalidate" in workflow
    assert "Pragma" in workflow
    assert "Expires" in workflow
