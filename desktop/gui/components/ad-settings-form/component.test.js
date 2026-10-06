import assert from "node:assert/strict";
import { before, test } from "node:test";
import { installDom } from "../../test-support/dom.js";

before(async () => {
  installDom();
  await import("./component.js");
});

const SETTINGS = {
  provider: "ollama",
  model: "gemma4:12b",
  ollama: { base_url: "http://localhost:11434" },
  openrouter: { base_url: "https://openrouter.ai/api/v1" },
  has_api_key: { openrouter: false },
  theme: "system",
  sandbox: { enabled: false, available: false, reason: "OpenShell is not installed." },
};

function mount(overrides = {}) {
  const form = document.createElement("ad-settings-form");
  document.body.appendChild(form);
  form.settings = { ...SETTINGS, ...overrides };
  const events = {};
  for (const name of ["ad-settings-save", "ad-models-request", "ad-api-key-remove"]) {
    events[name] = [];
    form.addEventListener(name, (event) => events[name].push(event.detail));
  }
  return { form, events };
}

const submit = (form) => form.querySelector("form").dispatchEvent(new window.Event("submit", { cancelable: true }));
const change = (node) => node.dispatchEvent(new window.Event("change"));

test("shows the saved values and never a key", () => {
  const { form } = mount({ has_api_key: { openrouter: true } });
  const values = [...form.querySelectorAll("input")].map((input) => input.value);
  assert.ok(values.includes("http://localhost:11434"));
  assert.equal(form.querySelector(".ad-api-key-input").value, "");
  assert.equal(form.querySelector(".ad-api-key-input").type, "password");
  assert.equal(form.querySelector("ad-model-picker").value, "gemma4:12b");
});

test("Save emits the whole patch and no key when none was typed", () => {
  const { form, events } = mount();
  submit(form);
  assert.deepEqual(events["ad-settings-save"], [
    {
      patch: {
        provider: "ollama",
        model: "gemma4:12b",
        ollama: { base_url: "http://localhost:11434" },
        openrouter: { base_url: "https://openrouter.ai/api/v1" },
        theme: "system",
      },
      apiKey: null,
    },
  ]);
});

test("a typed key is sent once with Save", () => {
  const { form, events } = mount();
  form.querySelector(".ad-api-key-input").value = "  sk-test-not-real ";
  submit(form);
  assert.equal(events["ad-settings-save"][0].apiKey, "sk-test-not-real");
});

test("with a saved key the input is hidden until Replace; Remove emits an event", () => {
  const { form, events } = mount({ has_api_key: { openrouter: true } });
  const keyInput = form.querySelector(".ad-api-key-input");
  assert.equal(form.querySelector(".ad-key-saved").hidden, false);
  assert.equal(form.querySelector(".ad-key-saved-text").textContent, "Key saved");
  assert.equal(keyInput.hidden, true);

  form.querySelector(".ad-key-replace").click();
  assert.equal(keyInput.hidden, false);

  form.querySelector(".ad-key-remove").click();
  assert.deepEqual(events["ad-api-key-remove"], [{ provider: "openrouter" }]);

  form.hasApiKey = false;
  assert.equal(form.querySelector(".ad-key-saved").hidden, true);
  assert.equal(keyInput.hidden, false);
});

test("changing the provider requests that provider's models", () => {
  const { form, events } = mount();
  const provider = form.querySelector("select");
  provider.value = "openrouter";
  change(provider);
  assert.deepEqual(events["ad-models-request"], [{ provider: "openrouter" }]);
  assert.equal(form.provider, "openrouter");
});

test("the picker's Refresh asks for the chosen provider's models", () => {
  const { form, events } = mount();
  form.querySelector(".ad-model-refresh").click();
  assert.deepEqual(events["ad-models-request"], [{ provider: "ollama" }]);
});

test("an empty model is refused client-side with a readable message", () => {
  const { form, events } = mount();
  const pickerSelect = form.querySelector(".ad-model-select");
  pickerSelect.value = [...pickerSelect.options].at(-1).value; // Other...
  change(pickerSelect);
  submit(form);
  assert.deepEqual(events["ad-settings-save"], []);
  assert.match(form.querySelector(".ad-settings-status").textContent, /Choose a model/);
});

test("status is shown as text and marked as an alert on error", () => {
  const { form } = mount();
  form.status = { kind: "error", text: "<b>boom</b>" };
  const status = form.querySelector(".ad-settings-status");
  assert.equal(status.textContent, "<b>boom</b>");
  assert.equal(status.querySelector("b"), null);
  assert.equal(status.getAttribute("role"), "alert");

  form.status = { kind: "success", text: "Saved" };
  assert.equal(status.getAttribute("role"), "status");
});

test("the model catalog is forwarded to the picker", () => {
  const { form } = mount();
  form.modelCatalog = { models: [{ id: "x", name: "x" }], isLoading: false, error: "" };
  assert.ok([...form.querySelectorAll(".ad-model-select option")].some((o) => o.value === "x"));
  form.modelCatalog = { models: [], isLoading: false, error: "Cannot reach Ollama" };
  assert.match(form.querySelector(".ad-model-error").textContent, /Cannot reach Ollama/);
});

test("an unavailable sandbox is a disabled checkbox with the reason shown as text", () => {
  const { form } = mount();
  const toggle = form.querySelector(".ad-sandbox-toggle");
  assert.equal(toggle.disabled, true);
  assert.equal(toggle.checked, false);
  assert.equal(form.querySelector(".ad-sandbox-reason").textContent, "OpenShell is not installed.");
  assert.match(form.querySelector(".ad-checkbox").textContent, /NVIDIA OpenShell sandbox/);
});

test("an unchanged sandbox is left out of the save payload", () => {
  const { form, events } = mount();
  submit(form);
  assert.equal("sandbox" in events["ad-settings-save"][0].patch, false);
});

test("an available sandbox can be toggled and is saved only when changed", () => {
  const sandbox = { enabled: false, available: true, reason: "ready" };
  const { form, events } = mount({ sandbox });
  const toggle = form.querySelector(".ad-sandbox-toggle");
  assert.equal(toggle.disabled, false);
  toggle.checked = true;
  submit(form);
  assert.deepEqual(events["ad-settings-save"][0].patch.sandbox, { enabled: true });
});

test("a sandbox that is on but unavailable can still be switched off", () => {
  const sandbox = { enabled: true, available: false, reason: "not wired" };
  const { form, events } = mount({ sandbox });
  const toggle = form.querySelector(".ad-sandbox-toggle");
  assert.equal(toggle.disabled, false);
  toggle.checked = false;
  submit(form);
  assert.deepEqual(events["ad-settings-save"][0].patch.sandbox, { enabled: false });
});
