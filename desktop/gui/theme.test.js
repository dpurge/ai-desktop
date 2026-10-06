import assert from "node:assert/strict";
import { test } from "node:test";
import { applyTheme } from "./theme.js";

function fakeRoot() {
  const attributes = new Map();
  return {
    attributes,
    setAttribute: (name, value) => attributes.set(name, value),
    removeAttribute: (name) => attributes.delete(name),
  };
}

test("light and dark set data-theme", () => {
  const root = fakeRoot();
  applyTheme(root, "dark");
  assert.equal(root.attributes.get("data-theme"), "dark");
  applyTheme(root, "light");
  assert.equal(root.attributes.get("data-theme"), "light");
});

test("system removes data-theme so the OS preference applies", () => {
  const root = fakeRoot();
  applyTheme(root, "dark");
  applyTheme(root, "system");
  assert.equal(root.attributes.has("data-theme"), false);
});
