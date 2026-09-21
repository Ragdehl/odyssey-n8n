"""Static contract checks for the framework-free Odyssey Online browser surface."""

import json
import re
from html.parser import HTMLParser
from pathlib import Path

WEB_ROOT = Path("odyssey_web")


class _IndexParser(HTMLParser):
    """Collect the small set of HTML attributes required by the MVP contract."""

    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.elements: dict[str, dict[str, str | None]] = {}
        self.links: list[str] = []
        self.scripts: list[tuple[str | None, str | None]] = []
        self.api_endpoint: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        element_id = values.get("id")
        if element_id:
            self.ids.add(element_id)
            self.elements[element_id] = values
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
    assert "appendNoteSetAffordance(message, result.note_result_snapshot)" in app
    assert 'selectSurface("notes")' in app
    assert 'new CustomEvent("odyssey:open-note-snapshot"' in app
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
    assert ".app-view { display: grid; height: 100%; min-height: 0;" in styles
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


def test_chat_and_notes_are_exclusive_application_views_with_safe_no_js_fallback() -> None:
    """Keep the inactive application fully absent even when module bootstrap fails."""

    parser = _IndexParser()
    index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    parser.feed(index)

    assert "hidden" in parser.elements["notes-surface"]
    assert "chat-surface" in parser.ids
    assert "notes-surface" in parser.ids
    assert "surface-nav" not in index
    assert index.index('id="chat-surface"') < index.index('id="notes-surface"')
    assert index.index('id="odyssey-form"') < index.index('id="notes-surface"')
    assert index.index('id="notes-search-form"') > index.index('id="notes-surface"')

    app = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    assert "function selectSurface(surface)" in app
    assert "chatSurface.hidden = !chat" in app
    assert "notesSurface.hidden = chat" in app
    assert 'dataset.activeView = chat ? "chat" : "notes"' in app
    assert 'selectSurface("chat")' in app
    assert 'selectSurface("notes");\n    document.dispatchEvent' in app

    styles = (WEB_ROOT / "styles.css").read_text(encoding="utf-8")
    assert "[hidden] { display: none !important; }" in styles
    assert ".chat-view, .notes-workspace { grid-template-rows:" in styles
    assert ".surface-nav" not in styles


def test_notes_mobile_controls_keep_filtering_sorting_and_search_in_separate_roles() -> None:
    """Keep mobile Notes controls usable without making local typing a provider action."""

    parser = _IndexParser()
    parser.feed((WEB_ROOT / "index.html").read_text(encoding="utf-8"))
    assert {
        "notes-filters",
        "notes-sort",
        "notes-filter-chips",
        "notes-filter-sheet",
        "notes-filter-form",
        "notes-search-form",
        "notes-search",
        "notes-intelligent",
    } <= parser.ids

    notes = (WEB_ROOT / "notes.js").read_text(encoding="utf-8")
    assert "loadCapabilities" in notes
    assert "renderFilterFields" in notes
    assert "renderTypeSpecificFields" in notes
    assert "applyFilters" in notes
    assert "renderFilterChips" in notes
    assert '"datetime-local"' in notes
    assert "timezoneAwareDateTime" in notes
    assert 'search.addEventListener("input", searchLocal)' in notes
    assert 'mode: state.query.trim() ? "local" : "feed"' in notes
    assert 'operation: "intelligent"' in notes
    assert "runIntelligentSearch" in notes
    assert "filtersAreRepresentable" in notes
    assert "uniqueFilters(page.applied_filters)" in notes
    assert 'filterButton?.addEventListener("click", openFilterSheet)' in notes
    assert "state.filters.splice(index, 1)" in notes
    assert "innerHTML" not in notes

    index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    assert "Ordenar" in index
    assert "Filtros" in index
    assert index.index('id="notes-search-form"') > index.index('id="notes-list-view"')


def test_notes_detail_uses_safe_structured_presentation_and_complete_type_icons() -> None:
    """Keep Markdown storage syntax out of the browser renderer and type cues schema-complete."""

    notes = (WEB_ROOT / "notes.js").read_text(encoding="utf-8")
    client = (WEB_ROOT / "notes-client.js").read_text(encoding="utf-8")
    schema = json.loads(Path("config/note-schema.json").read_text(encoding="utf-8"))

    assert "renderBody(body, value.body_blocks, open)" in notes
    assert "appendBodySegments" in notes
    assert 'document.createElement("a")' in notes
    assert "encodeURIComponent(segment.target_id)" in notes
    assert "note-links" not in notes
    assert "Todavía no hay información adicional." in notes
    assert "No se ha podido abrir la nota." in notes
    assert "La nota ya no está disponible." not in notes
    assert "innerHTML" not in notes
    assert "body_blocks" in client
    assert "isString(value.body)" in client
    for note_type in schema["types"]:
        assert f"{note_type['id']}: {{" in notes


def test_older_chat_pages_restore_note_snapshot_affordances() -> None:
    """Preserve durable historical Notes entry points across bounded chat pagination."""

    app = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    older = app[
        app.index("async function loadOlderConversation") : app.index(
            "conversation.addEventListener"
        )
    ]
    assert "appendDetailButton(message, turn.request_detail);" in older
    assert "appendNoteSetAffordance(message, turn.note_result_snapshot);" in older


def _reachable_local_modules(entry: Path) -> set[Path]:
    """Return the local ES-module closure rooted at the checked-in browser entrypoint."""

    pattern = re.compile(r'^\s*import\s+(?:[^"\']+?\s+from\s+)?["\'](\./[^"\']+)["\']', re.M)
    root = WEB_ROOT.resolve()
    seen: set[Path] = set()

    def visit(path: Path) -> None:
        resolved = path.resolve()
        assert root in resolved.parents
        assert resolved.is_file(), f"missing browser module: {resolved.relative_to(root)}"
        if resolved in seen:
            return
        seen.add(resolved)
        for relative in pattern.findall(resolved.read_text(encoding="utf-8")):
            visit(resolved.parent / relative)

    visit(entry)
    return seen


def test_every_reachable_local_browser_module_has_a_static_workflow_route() -> None:
    """Prevent one unserved ES-module import from disabling the whole browser application."""

    root = WEB_ROOT.resolve()
    modules = _reachable_local_modules(WEB_ROOT / "app.js")
    routes = {path.relative_to(root).as_posix() for path in modules}
    assert routes == {"app.js", "client.js", "notes.js", "notes-client.js"}

    workflow = (Path("workflows") / "odyssey-online-static.ts").read_text(encoding="utf-8")
    for route in routes:
        assert f"path: '{route}'" in workflow
        assert f"/odyssey-web/{route}" in workflow
        assert "text/javascript; charset=utf-8" in workflow

    operator = Path("scripts/odyssey-dev").read_text(encoding="utf-8")
    assert "browser_assets()" in operator
    assert "browser module is unavailable" in operator
    assert "module_routes" in operator
    assert "assert_dev_product_route_inventory" in operator


def test_frontend_has_no_external_asset_or_browser_persistence_dependency() -> None:
    """The offline checkpoint stays self-contained and creates no durable browser history."""

    index = (WEB_ROOT / "index.html").read_text(encoding="utf-8")
    app = (WEB_ROOT / "app.js").read_text(encoding="utf-8")
    client = (WEB_ROOT / "client.js").read_text(encoding="utf-8")
    notes = (WEB_ROOT / "notes.js").read_text(encoding="utf-8")
    notes_client = (WEB_ROOT / "notes-client.js").read_text(encoding="utf-8")
    combined = "\n".join((index, app, client, notes, notes_client))

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


def test_notes_historical_snapshot_contract_uses_safe_dom_and_explicit_rerun() -> None:
    """Keep historical membership presentation bounded, explicit, and framework-free."""
    notes = (WEB_ROOT / "notes.js").read_text(encoding="utf-8")
    notes_client = (WEB_ROOT / "notes-client.js").read_text(encoding="utf-8")
    assert "unavailableRow" in notes
    assert "Nota ya no disponible" in notes
    assert "Resultado histórico" in notes
    assert "rerunHistorical" in notes
    assert "runIntelligentSearch({throwOnError: true})" in notes
    assert "state.snapshot = null" in notes
    assert "snapshot_offset" in notes_client
    assert "unavailable_ids" in notes_client
    assert "innerHTML" not in notes


def test_static_asset_workflow_forces_revalidation_after_dev_deploy() -> None:
    """Prevent normal reloads from retaining an older deployment's app assets."""
    workflow = (Path("workflows") / "odyssey-online-static.ts").read_text(encoding="utf-8")
    assert "Cache-Control" in workflow
    assert "no-cache, no-store, must-revalidate" in workflow
    assert "Pragma" in workflow
    assert "Expires" in workflow
