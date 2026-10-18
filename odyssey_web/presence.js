/** Fire-and-forget authenticated browser presence for an optional local ONNX warmup.
 *
 * No loading spinner: warming overlaps with conversation hydration.
 * A foreground heartbeat prevents the worker from reaping while the user is
 * actually using Odyssey. Pagehide is best effort; server expires lost tabs.
 */
export function startEmbeddingPresence({
  endpoint = "/api/conversation",
  fetchImpl = globalThis.fetch,
  documentImpl = globalThis.document,
  windowImpl = globalThis.window,
  cryptoImpl = globalThis.crypto,
  setIntervalImpl = globalThis.setInterval,
  clearIntervalImpl = globalThis.clearInterval,
} = {}) {
  if (!cryptoImpl || typeof cryptoImpl.randomUUID !== "function" ||
      typeof fetchImpl !== "function" || !documentImpl || !windowImpl) {
    return {stop() {}};
  }
  const sessionId = "presence-" + cryptoImpl.randomUUID();
  let active = false;
  let stopped = false;
  const signal = (state) => {
    try {
      // The session identifier is an opaque per-tab signal, never user knowledge.
      const response = fetchImpl(endpoint, {
        method: "POST",
        credentials: "same-origin",
        keepalive: state === "inactive",
        headers: {"Content-Type": "application/json", Accept: "application/json"},
        body: JSON.stringify({operation: "presence", session_id: sessionId, state}),
      });
      void Promise.resolve(response).catch(() => {});
    } catch {
      // A failed background optimization never prevents typing, loading or saving.
    }
  };
  const enter = () => {
    if (stopped || documentImpl.hidden) return;
    if (!active) {
      active = true;
      signal("active");
    }
  };
  const leave = () => {
    if (!active) return;
    active = false;
    signal("inactive");
  };
  const visibility = () => documentImpl.hidden ? leave() : enter();
  const tick = () => {
    if (stopped) return;
    if (documentImpl.hidden) {
      leave();
    } else if (active) {
      signal("heartbeat");
    } else {
      enter();
    }
  };
  documentImpl.addEventListener("visibilitychange", visibility);
  windowImpl.addEventListener("pagehide", leave);
  windowImpl.addEventListener("pageshow", enter);
  const interval = setIntervalImpl(tick, 60_000);
  enter();
  return {
    stop() {
      if (stopped) return;
      stopped = true;
      leave();
      clearIntervalImpl(interval);
      documentImpl.removeEventListener?.("visibilitychange", visibility);
      windowImpl.removeEventListener?.("pagehide", leave);
      windowImpl.removeEventListener?.("pageshow", enter);
    },
  };
}
