import assert from "node:assert/strict";
import { test } from "node:test";
import { createAppStore, createStore } from "./store.js";

test("setState merges the patch and notifies subscribers with the new state", () => {
  const store = createStore({ a: 1, b: 2 });
  const seen = [];
  store.subscribe((state) => seen.push(state));

  store.setState({ b: 3 });

  assert.deepEqual(store.getState(), { a: 1, b: 3 });
  assert.deepEqual(seen, [{ a: 1, b: 3 }]);
});

test("unsubscribe stops notifications", () => {
  const store = createStore({ a: 1 });
  let calls = 0;
  const unsubscribe = store.subscribe(() => calls++);
  store.setState({ a: 2 });
  unsubscribe();
  store.setState({ a: 3 });
  assert.equal(calls, 1);
});

test("the initial state object is not mutated", () => {
  const initial = { a: 1 };
  createStore(initial).setState({ a: 2 });
  assert.equal(initial.a, 1);
});

test("app store starts empty and connecting", () => {
  assert.deepEqual(createAppStore().getState(), {
    sessions: [],
    activeId: null,
    settings: null,
    connection: "connecting",
  });
});
