import assert from "node:assert/strict";
import { before, test } from "node:test";
import { installDom } from "../../test-support/dom.js";

before(async () => {
  installDom();
  await import("./component.js");
});

const MODELS = [
  { id: "b-model", name: "b-model" },
  { id: "a/model", name: "Model A" },
];

function mount(value = "b-model") {
  const picker = document.createElement("ad-model-picker");
  document.body.appendChild(picker);
  picker.models = MODELS;
  picker.value = value;
  const changes = [];
  picker.addEventListener("ad-model-change", (event) => changes.push(event.detail.model));
  return { picker, changes };
}

const select = (picker) => picker.querySelector(".ad-model-select");
const optionValues = (picker) => [...select(picker).options].map((option) => option.value);

test("lists models, labelled by name when it differs from the id, plus Other", () => {
  const { picker } = mount();
  assert.deepEqual([...select(picker).options].map((option) => option.textContent), [
    "b-model",
    "Model A (a/model)",
    "Other…",
  ]);
  assert.equal(select(picker).value, "b-model");
});

test("a current model missing from the list is kept as an option and stays selected", () => {
  const { picker } = mount("custom:1b");
  assert.deepEqual(optionValues(picker).slice(0, 3), ["custom:1b", "b-model", "a/model"]);
  assert.equal(select(picker).value, "custom:1b");
  assert.equal(picker.value, "custom:1b");
});

test("choosing a model emits ad-model-change", () => {
  const { picker, changes } = mount();
  select(picker).value = "a/model";
  select(picker).dispatchEvent(new window.Event("change"));
  assert.deepEqual(changes, ["a/model"]);
  assert.equal(picker.value, "a/model");
});

test("Other shows a text input whose trimmed text becomes the model", () => {
  const { picker, changes } = mount();
  select(picker).value = optionValues(picker).at(-1);
  select(picker).dispatchEvent(new window.Event("change"));
  const input = picker.querySelector(".ad-model-custom");
  assert.ok(input);

  input.value = "  my-model  ";
  input.dispatchEvent(new window.Event("input"));

  assert.equal(picker.value, "my-model");
  assert.deepEqual(changes, ["", "my-model"]);
});

test("Refresh emits ad-models-refresh and is disabled while loading", () => {
  const { picker } = mount();
  let refreshes = 0;
  picker.addEventListener("ad-models-refresh", () => refreshes++);
  picker.querySelector(".ad-model-refresh").click();
  assert.equal(refreshes, 1);

  picker.isLoading = true;
  assert.equal(picker.querySelector(".ad-model-refresh").disabled, true);
  assert.match(picker.textContent, /Loading models/);
});

test("errors render as text and the current model stays available", () => {
  const { picker } = mount();
  picker.error = "<img src=x> Cannot reach Ollama";
  const note = picker.querySelector(".ad-model-error");
  assert.equal(note.textContent, "<img src=x> Cannot reach Ollama");
  assert.equal(note.querySelector("img"), null);
  assert.equal(select(picker).value, "b-model");
});
