import assert from "node:assert/strict";
import { before, test } from "node:test";
import { installDom } from "../../test-support/dom.js";

before(async () => {
  installDom();
  await import("./component.js");
});

function mount() {
  const composer = document.createElement("ad-composer");
  document.body.appendChild(composer);
  const sent = [];
  composer.addEventListener("ad-send", (event) => sent.push(event.detail.text));
  return { composer, sent, input: composer.querySelector("textarea"), button: composer.querySelector("button") };
}

function pressKey(input, key, options = {}) {
  const event = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...options });
  input.dispatchEvent(event);
  return event;
}

test("Enter sends the trimmed text and clears the input", () => {
  const { sent, input } = mount();
  input.value = "  hello  ";
  const event = pressKey(input, "Enter");
  assert.deepEqual(sent, ["hello"]);
  assert.equal(input.value, "");
  assert.equal(event.defaultPrevented, true);
});

test("Shift+Enter does not send (newline)", () => {
  const { sent, input } = mount();
  input.value = "line";
  const event = pressKey(input, "Enter", { shiftKey: true });
  assert.deepEqual(sent, []);
  assert.equal(event.defaultPrevented, false);
  assert.equal(input.value, "line");
});

test("empty or whitespace-only input is not sent", () => {
  const { sent, input } = mount();
  input.value = "   ";
  pressKey(input, "Enter");
  assert.deepEqual(sent, []);
});

test("the Send button sends", () => {
  const { sent, input, button } = mount();
  input.value = "via button";
  button.click();
  assert.deepEqual(sent, ["via button"]);
});

test("disabled composer disables controls and sends nothing", () => {
  const { composer, sent, input, button } = mount();
  composer.disabled = true;
  assert.equal(input.disabled, true);
  assert.equal(button.disabled, true);
  input.value = "blocked";
  pressKey(input, "Enter");
  assert.deepEqual(sent, []);

  composer.disabled = false;
  assert.equal(input.disabled, false);
  assert.equal(button.disabled, false);
});

test("ad-send bubbles to ancestors", () => {
  const { composer, input } = mount();
  const received = [];
  document.body.addEventListener("ad-send", (event) => received.push(event.detail.text));
  input.value = "up";
  pressKey(input, "Enter");
  assert.deepEqual(received, ["up"]);
  composer.remove();
});

test("Stop is hidden until a turn is running, and emits ad-stop", () => {
  const { composer } = mount();
  const stop = composer.querySelector(".ad-composer-stop");
  assert.equal(stop.hidden, true);

  composer.running = true;
  composer.disabled = true;
  assert.equal(stop.hidden, false);
  assert.equal(stop.disabled, false);

  let stopped = 0;
  composer.addEventListener("ad-stop", () => stopped++);
  stop.click();
  assert.equal(stopped, 1);

  composer.running = false;
  assert.equal(stop.hidden, true);
});
