import assert from "node:assert/strict";
import { before, test } from "node:test";
import { installDom } from "../../test-support/dom.js";

before(async () => {
  installDom();
  await import("./component.js");
});

function mount() {
  const bar = document.createElement("ad-status-bar");
  document.body.appendChild(bar);
  return bar;
}

test("starts as connecting with no model text", () => {
  const bar = mount();
  assert.equal(bar.querySelector(".ad-status-connection").textContent, "Connecting to engine…");
  assert.equal(bar.querySelector(".ad-status-model").textContent, "");
});

test("shows the connection state and 'provider · model'", () => {
  const bar = mount();
  bar.connection = "online";
  bar.provider = "ollama";
  bar.model = "gemma4:12b";
  assert.equal(bar.querySelector(".ad-status-connection").textContent, "Engine connected");
  assert.ok(bar.querySelector(".ad-status-dot").classList.contains("is-online"));
  assert.equal(bar.querySelector(".ad-status-model").textContent, "ollama · gemma4:12b");

  bar.connection = "offline";
  assert.equal(bar.querySelector(".ad-status-connection").textContent, "Engine not reachable");
  assert.ok(bar.querySelector(".ad-status-dot").classList.contains("is-offline"));
});

test("model text is written as text only", () => {
  const bar = mount();
  bar.provider = "openrouter";
  bar.model = "<img src=x>";
  assert.equal(bar.querySelector("img"), null);
  assert.equal(bar.querySelector(".ad-status-model").textContent, "openrouter · <img src=x>");
});

test("click asks to open settings", () => {
  const bar = mount();
  let opened = 0;
  bar.addEventListener("ad-status-open-settings", () => opened++);
  bar.querySelector("button").click();
  assert.equal(opened, 1);
});
