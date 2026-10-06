import assert from "node:assert/strict";
import { before, test } from "node:test";
import { installDom } from "../../test-support/dom.js";

before(async () => {
  installDom();
  await import("./component.js");
});

function mount() {
  const message = document.createElement("ad-message");
  message.dataset.role = "assistant";
  document.body.appendChild(message);
  return message;
}

test("shows the role and the text", () => {
  const message = mount();
  message.text = "hello";
  assert.equal(message.querySelector(".ad-message-role").textContent, "assistant");
  assert.equal(message.querySelector(".ad-message-body").textContent, "hello");
});

test("append streams text onto the end", () => {
  const message = mount();
  message.append("Hel");
  message.append("lo");
  assert.equal(message.text, "Hello");
  assert.equal(message.querySelector(".ad-message-body").textContent, "Hello");
});

test("text set before the element is connected survives connecting", () => {
  const message = document.createElement("ad-message");
  message.text = "early";
  document.body.appendChild(message);
  assert.equal(message.querySelectorAll(".ad-message-body").length, 1);
  assert.equal(message.text, "early");
});

test("markup in model text is not parsed", () => {
  const message = mount();
  message.text = '<img src=x onerror="alert(1)"><b>bold</b>';
  assert.equal(message.querySelector("img"), null);
  assert.equal(message.querySelector("b"), null);
  assert.equal(message.text, '<img src=x onerror="alert(1)"><b>bold</b>');
});

test("changing data-role updates the label", () => {
  const message = mount();
  message.dataset.role = "user";
  assert.equal(message.querySelector(".ad-message-role").textContent, "user");
});

test("injects its stylesheet link once", () => {
  mount();
  mount();
  assert.equal(document.querySelectorAll("link#ad-message-style").length, 1);
});
