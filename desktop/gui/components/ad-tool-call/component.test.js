import assert from "node:assert/strict";
import { before, test } from "node:test";
import { installDom } from "../../test-support/dom.js";

before(async () => {
  installDom();
  await import("./component.js");
});

function mount() {
  const card = document.createElement("ad-tool-call");
  document.body.appendChild(card);
  return card;
}

test("starts pending, with no output shown", () => {
  const card = mount();
  assert.equal(card.status, "pending");
  assert.equal(card.querySelector(".ad-tool-call-badge").textContent, "pending");
  assert.equal(card.querySelector("details").hidden, true);
});

test("shows the tool name and pretty-printed arguments", () => {
  const card = mount();
  card.toolName = "shell";
  card.toolArguments = { command: "ls -la" };
  assert.equal(card.querySelector(".ad-tool-call-name").textContent, "shell");
  assert.equal(card.querySelector(".ad-tool-call-args").textContent, '{\n  "command": "ls -la"\n}');
});

test("raw string arguments are shown as they are", () => {
  const card = mount();
  card.toolArguments = "{not json";
  assert.equal(card.querySelector(".ad-tool-call-args").textContent, "{not json");
});

test("status updates the badge and the data attribute", () => {
  const card = mount();
  for (const status of ["running", "done", "denied", "error"]) {
    card.status = status;
    assert.equal(card.dataset.status, status);
    assert.equal(card.querySelector(".ad-tool-call-badge").textContent, status);
  }
});

test("an unknown status is rejected", () => {
  assert.throws(() => (mount().status = "flying"), /Unknown tool call status/);
});

test("output goes into a collapsible pre and reveals it", () => {
  const card = mount();
  card.output = "line one\nline two";
  const pre = card.querySelector("details pre");
  assert.equal(pre.textContent, "line one\nline two");
  assert.equal(card.querySelector("details").hidden, false);
});

test("long output is capped for display", () => {
  const card = mount();
  card.output = "x".repeat(10_000);
  const shown = card.querySelector("details pre").textContent;
  assert.ok(shown.length < 4100);
  assert.ok(shown.endsWith("[display truncated]"));
});

test("markup in arguments and output is not parsed", () => {
  const card = mount();
  card.toolName = "<b>shell</b>";
  card.toolArguments = { command: "<img src=x onerror=alert(1)>" };
  card.output = "<script>alert(1)</script>";
  assert.equal(card.querySelector("img"), null);
  assert.equal(card.querySelector("script"), null);
  assert.equal(card.querySelector("b"), null);
});

test("injects its stylesheet link once", () => {
  mount();
  mount();
  assert.equal(document.querySelectorAll("link#ad-tool-call-style").length, 1);
});
