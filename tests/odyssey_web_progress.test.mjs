import assert from "node:assert/strict";
import test from "node:test";

import {
  createProcessingIndicator,
  formatStage,
  startProgressPolling,
} from "../odyssey_web/progress.js";

class Element {
  constructor(tagName) {
    this.tagName = tagName;
    this.children = [];
    this.className = "";
    this.attributes = new Map();
    this._textContent = "";
  }
  append(...nodes) { this.children.push(...nodes); }
  set textContent(value) { this._textContent = String(value); this.children = []; }
  get textContent() { return this._textContent + this.children.map((c) => c.textContent).join(""); }
  setAttribute(name, value) { this.attributes.set(name, String(value)); }
  getAttribute(name) { return this.attributes.get(name); }
  querySelector(selector) {
    for (const child of this.children) {
      if (selector.startsWith(".") && child.className.split(" ").includes(selector.slice(1))) return child;
      const nested = child.querySelector?.(selector);
      if (nested) return nested;
    }
    return null;
  }
}

const fakeDocument = {createElement: (tag) => new Element(tag)};

test("progress copy keeps only the latest user-facing stage", () => {
  assert.equal(formatStage({stage: "routing.started", details: []}), "Entendiendo tu mensaje…");
  assert.equal(
    formatStage({stage: "routing.ready", details: ["2"]}),
    "He separado tu mensaje en 2 partes.",
  );
  assert.equal(
    formatStage({stage: "temporal.ready", details: ["mañana: 2026-10-08", "20h: 2026-10-08T20:00:00+02:00"]}),
    "Fecha y hora: mañana: 2026-10-08 · 20h: 2026-10-08T20:00:00+02:00",
  );
  assert.equal(
    formatStage({stage: "planner.ready", details: ["Cloe", "Bruno", "Beatriz"]}),
    "He identificado: Cloe, Bruno, Beatriz",
  );
});

test("donut updates monotonically and completes at 100", () => {
  const indicator = createProcessingIndicator(fakeDocument);
  const donut = indicator.element.querySelector(".processing-donut");
  const copy = indicator.element.querySelector(".processing-copy");

  indicator.update({stage: "planner.started", progress: 50, details: []});
  assert.equal(donut.getAttribute("aria-valuenow"), "50");
  assert.equal(copy.textContent, "Organizando la información…");

  indicator.update({stage: "routing.ready", progress: 18, details: []});
  assert.equal(donut.getAttribute("aria-valuenow"), "50");

  indicator.complete();
  assert.equal(donut.getAttribute("aria-valuenow"), "100");
  assert.equal(copy.textContent, "Listo");
  indicator.destroy();
});

test("poller tolerates progress failures without affecting delivery", async () => {
  const queued = [];
  let calls = 0;
  const stop = startProgressPolling({
    requestId: "web-test",
    requestProgress: async () => {
      calls += 1;
      if (calls === 1) throw new Error("transient");
      return {stage: "planner.started", progress: 50, details: []};
    },
    onProgress: (value) => queued.push(value.stage),
    setTimeoutImpl(callback) {
      queueMicrotask(callback);
      return 1;
    },
    clearTimeoutImpl() {},
  });
  await Promise.resolve();
  await Promise.resolve();
  await Promise.resolve();
  stop();

  assert.ok(calls >= 1);
  assert.ok(queued.length <= 1);
});
