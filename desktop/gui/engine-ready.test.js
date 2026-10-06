import assert from "node:assert/strict";
import { test } from "node:test";
import { waitForEngine } from "./engine-ready.js";

const noWait = async () => {};

test("returns the health result once the engine answers", async () => {
  let calls = 0;
  const getHealth = async () => {
    calls += 1;
    if (calls < 3) throw new Error("Load failed");
    return { ok: true };
  };
  assert.deepEqual(await waitForEngine(getHealth, { wait: noWait }), { ok: true });
  assert.equal(calls, 3);
});

test("gives up with a readable error after the allowed attempts", async () => {
  let calls = 0;
  const getHealth = async () => {
    calls += 1;
    throw new Error("Load failed");
  };
  await assert.rejects(
    waitForEngine(getHealth, { attempts: 4, wait: noWait }),
    /The engine did not start: Load failed/,
  );
  assert.equal(calls, 4);
});
