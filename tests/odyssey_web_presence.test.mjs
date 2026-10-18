// Browser presence must remain fire-and-forget, tab-scoped and background-aware.
import test from "node:test";
import assert from "node:assert/strict";
import {startEmbeddingPresence} from "../odyssey_web/presence.js";

function fixture() {
  const docEvents = new Map();
  const winEvents = new Map();
  const documentImpl = {
    hidden: false,
    addEventListener: (name, fn) => docEvents.set(name, fn),
    removeEventListener: (name) => docEvents.delete(name),
  };
  const windowImpl = {
    addEventListener: (name, fn) => winEvents.set(name, fn),
    removeEventListener: (name) => winEvents.delete(name),
  };
  const events = [];
  let tick;
  let cleared = false;
  const controller = startEmbeddingPresence({
    documentImpl, windowImpl,
    fetchImpl: (_url, props) => {
      events.push({...JSON.parse(props.body), keepalive: props.keepalive, credentials: props.credentials});
      return Promise.resolve({ok: true});
    },
    cryptoImpl: {randomUUID: () => "25af0a78-b8ee-4d7e-b352-f6e1e7af7481"},
    setIntervalImpl: fn => {tick = fn; return 11;},
    clearIntervalImpl: id => {assert.equal(id, 11); cleared = true;},
  });
  return {events, controller, docEvents, winEvents, documentImpl, get tick() {return tick;}, get cleared() {return cleared;}};
}

test("opening and 60-second heartbeat keep the same authenticated tab session", () => {
  const fx = fixture();
  assert.equal(fx.events[0].state, "active");
  fx.tick();
  fx.tick();
  assert.deepEqual(fx.events.map(e => e.state), ["active", "heartbeat", "heartbeat"]);
  assert.ok(fx.events.every(e => e.session_id === fx.events[0].session_id));
  assert.ok(fx.events.every(e => e.credentials === "same-origin"));
  fx.controller.stop();
  assert.equal(fx.cleared, true);
});

test("background closes session and foreground resumes without reloading", () => {
  const fx = fixture();
  fx.documentImpl.hidden = true;
  fx.docEvents.get("visibilitychange")();
  fx.tick();
  assert.deepEqual(fx.events.map(e => e.state), ["active", "inactive"]);
  assert.equal(fx.events.at(-1).keepalive, true);
  fx.documentImpl.hidden = false;
  fx.docEvents.get("visibilitychange")();
  fx.tick();
  assert.deepEqual(fx.events.map(e => e.state), ["active", "inactive", "active", "heartbeat"]);
  fx.winEvents.get("pagehide")();
  assert.equal(fx.events.at(-1).state, "inactive");
  fx.winEvents.get("pageshow")();
  assert.equal(fx.events.at(-1).state, "active");
  fx.controller.stop();
});

test("failed background presence is never a user-visible exception", () => {
  const controller = startEmbeddingPresence({
    documentImpl: {hidden: false, addEventListener() {}, removeEventListener() {}},
    windowImpl: {addEventListener() {}, removeEventListener() {}},
    cryptoImpl: {randomUUID: () => "random"},
    fetchImpl: () => {throw new Error("network offline");},
    setIntervalImpl: () => 1,
    clearIntervalImpl() {},
  });
  assert.doesNotThrow(() => controller.stop());
});
