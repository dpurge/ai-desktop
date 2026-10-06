import assert from "node:assert/strict";
import { test } from "node:test";
import { HOME, SETTINGS, createRouter, formatRoute, parseHash, takeTokenFromHash } from "./router.js";

test("parses the known routes", () => {
  assert.deepEqual(parseHash(""), HOME);
  assert.deepEqual(parseHash("#/"), HOME);
  assert.deepEqual(parseHash("#/settings"), SETTINGS);
  assert.deepEqual(parseHash("#/chat/abc-123_X"), { name: "chat", id: "abc-123_X" });
});

test("rejects unknown paths and malformed chat ids", () => {
  for (const hash of ["#/nope", "#/chat/", "#/chat/a/b", "#/chat/a.b", "#/chat/" + "a".repeat(65)]) {
    assert.equal(parseHash(hash).name, "not-found", hash);
  }
});

test("formatRoute round-trips through parseHash", () => {
  for (const route of [HOME, SETTINGS, { name: "chat", id: "abc" }]) {
    assert.deepEqual(parseHash(formatRoute(route)), route);
  }
});

test("takeTokenFromHash returns the token and strips the hash", () => {
  const calls = [];
  const location = { hash: "#token=s3cret", pathname: "/", search: "?x=1" };
  const history = { replaceState: (...args) => calls.push(args) };

  assert.equal(takeTokenFromHash(location, history), "s3cret");
  assert.deepEqual(calls, [[null, "", "/?x=1"]]);
});

test("takeTokenFromHash leaves a route hash alone", () => {
  const history = { replaceState: () => assert.fail("must not touch the URL") };
  assert.equal(takeTokenFromHash({ hash: "#/chat/abc", pathname: "/", search: "" }, history), null);
});

function fakeWindow(hash = "") {
  const listeners = new Set();
  const win = {
    location: {
      _hash: hash,
      get hash() {
        return this._hash;
      },
      set hash(value) {
        this._hash = value;
        for (const listener of listeners) listener();
      },
    },
    addEventListener: (_type, listener) => listeners.add(listener),
    removeEventListener: (_type, listener) => listeners.delete(listener),
  };
  return { win, listeners };
}

test("start reports the current route, then follows hash changes", () => {
  const { win } = fakeWindow("#/chat/one");
  const seen = [];
  const router = createRouter({ window: win, onRoute: (route) => seen.push(route) });

  router.start();
  win.location.hash = "#/settings";

  assert.deepEqual(seen, [{ name: "chat", id: "one" }, SETTINGS]);
});

test("navigate sets the hash and also notifies when the hash is unchanged", () => {
  const { win } = fakeWindow("#/");
  const seen = [];
  const router = createRouter({ window: win, onRoute: (route) => seen.push(route.name) });
  router.start();

  router.navigate({ name: "chat", id: "two" });
  router.navigate({ name: "chat", id: "two" });

  assert.equal(win.location.hash, "#/chat/two");
  assert.deepEqual(seen, ["home", "chat", "chat"]);
});

test("stop detaches the listener", () => {
  const { win, listeners } = fakeWindow();
  const router = createRouter({ window: win, onRoute: () => {} });
  router.start();
  router.stop();
  assert.equal(listeners.size, 0);
});
