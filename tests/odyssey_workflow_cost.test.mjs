import test from "node:test";
import assert from "node:assert/strict";
import {readFileSync} from "node:fs";

// Run the actual n8n helper source in an isolated VM-like function. This keeps
// accounting tests attached to the workflow implementation rather than a copy.
const source = readFileSync(new URL("../workflows/odyssey-online.ts", import.meta.url), "utf8");
const marker = "const costHelpers = String.raw`";
const start = source.indexOf(marker);
const end = source.indexOf("`;\n\nconst routeCode", start + marker.length);
assert.ok(start >= 0 && end > start);
const helpers = source.slice(start + marker.length, end);
const {providerCost, requestCost} = new Function(`${helpers}\nreturn {providerCost, requestCost};`)();

const pricing = JSON.parse(readFileSync(new URL("../config/runtime-pricing-snapshot.json", import.meta.url), "utf8"));
const pricedUsage = {
  input_tokens: 1_000,
  cached_input_tokens: 200,
  cache_write_tokens: 100,
  output_tokens: 300,
  reasoning_tokens: 120,
};

test("workflow prices input cache writes and output exactly once", () => {
  // gpt-5.6-luna: 700 ordinary*.2 + 200 cached*.02 + 100 write*.25 + 300 output*1.2 per M.
  assert.equal(providerCost(pricedUsage, "gpt-5.6-luna", pricing), 0.000529);
  assert.equal(providerCost({...pricedUsage, reasoning_tokens: 300}, "gpt-5.6-luna", pricing), 0.000529);
});

test("workflow leaves cache-write and partial billing evidence unavailable", () => {
  assert.equal(providerCost(pricedUsage, "gpt-5-nano", pricing), undefined);
  assert.equal(providerCost({input_tokens: 1, output_tokens: 1}, "gpt-6-luna", pricing), undefined);
  assert.equal(providerCost({...pricedUsage, cached_input_tokens: 950, cache_write_tokens: 100}, "gpt-5.6-luna", pricing), undefined);
});

test("request total sums known provider calls once and fails closed for a missing call", () => {
  const operational = {stages: [{model: "gpt-5.6-luna", usage: pricedUsage}, {
    model: "gpt-6-luna", usage: {input_tokens: 100, cached_input_tokens: 0, output_tokens: 10},
  }]};
  const total = requestCost(operational, pricing);
  assert.equal(total.status, "estimated");
  assert.equal(total.amount_usd, 0.000544);
  assert.equal(requestCost({stages: [...operational.stages, {model: "gpt-6-luna", usage: {input_tokens: 1}}]}, pricing).status, "unavailable");
});
