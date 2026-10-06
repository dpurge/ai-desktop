import assert from "node:assert/strict";
import { before, test } from "node:test";
import { installDom } from "./test-support/dom.js";

let createSettingsScreen;
before(async () => {
  installDom();
  ({ createSettingsScreen } = await import("./settings-screen.js"));
});

const SETTINGS = { provider: "ollama", model: "m", has_api_key: { openrouter: false } };

function setup(apiOverrides = {}) {
  const calls = [];
  const api = {
    getSettings: async () => SETTINGS,
    listModels: async (provider) => {
      calls.push(["listModels", provider]);
      return [{ id: "m", name: "m" }];
    },
    setApiKey: async (...args) => calls.push(["setApiKey", ...args]),
    deleteApiKey: async (...args) => calls.push(["deleteApiKey", ...args]),
    saveSettings: async (patch) => {
      calls.push(["saveSettings", patch]);
      return { ...SETTINGS, ...patch };
    },
    ...apiOverrides,
  };
  const form = document.createElement("div");
  const saved = [];
  const screen = createSettingsScreen({ api, form, onSaved: (settings) => saved.push(settings) });
  const fire = (name, detail) => form.dispatchEvent(new CustomEvent(name, { detail }));
  return { calls, form, saved, screen, fire };
}

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

test("show loads settings into the form and requests the provider's models", async () => {
  const { screen, form, calls } = setup();
  await screen.show();
  await tick();
  assert.deepEqual(form.settings, SETTINGS);
  assert.deepEqual(calls, [["listModels", "ollama"]]);
  assert.deepEqual(form.modelCatalog.models, [{ id: "m", name: "m" }]);
});

test("a failed model list becomes an error message in the catalog", async () => {
  const { screen, form } = setup({
    listModels: async () => {
      throw new Error("List models failed: HTTP 502 Cannot reach Ollama at http://x");
    },
  });
  await screen.show();
  await tick();
  assert.match(form.modelCatalog.error, /Cannot reach Ollama/);
});

test("save stores the key first, then the settings, then reports success", async () => {
  const { form, calls, saved, fire } = setup();
  fire("ad-settings-save", { patch: { model: "x" }, apiKey: "sk-test-not-real" });
  await tick();
  assert.deepEqual(calls.map(([name]) => name), ["setApiKey", "saveSettings"]);
  assert.equal(form.hasApiKey, true);
  assert.equal(form.status.kind, "success");
  assert.equal(saved.length, 1);
});

test("a rejected save shows the engine's message and does not report saved", async () => {
  const { form, saved, fire } = setup({
    saveSettings: async () => {
      throw new Error("Save settings failed: HTTP 422 ollama.base_url must start with http://");
    },
  });
  fire("ad-settings-save", { patch: {}, apiKey: null });
  await tick();
  assert.equal(form.status.kind, "error");
  assert.match(form.status.text, /base_url must start with http/);
  assert.equal(saved.length, 0);
});

test("removing the key clears the saved state", async () => {
  const { form, calls, fire } = setup();
  fire("ad-api-key-remove", { provider: "openrouter" });
  await tick();
  assert.deepEqual(calls, [["deleteApiKey", "openrouter"]]);
  assert.equal(form.hasApiKey, false);
});

test("a slow answer for a previous provider is ignored", async () => {
  const resolvers = {};
  const { form, fire } = setup({
    listModels: (provider) => new Promise((resolve) => (resolvers[provider] = resolve)),
  });
  fire("ad-models-request", { provider: "ollama" });
  fire("ad-models-request", { provider: "openrouter" });
  resolvers.openrouter([{ id: "or", name: "or" }]);
  await tick();
  resolvers.ollama([{ id: "old", name: "old" }]);
  await tick();
  assert.deepEqual(form.modelCatalog.models, [{ id: "or", name: "or" }]);
});

test("a refused sandbox change shows the engine's reason as the inline error", async () => {
  const { form, saved, fire } = setup({
    saveSettings: async () => {
      throw new Error("Save settings failed: HTTP 422 OpenShell is not installed.");
    },
  });
  fire("ad-settings-save", { patch: { sandbox: { enabled: true } }, apiKey: null });
  await tick();
  assert.deepEqual(form.status, {
    kind: "error",
    text: "Save settings failed: HTTP 422 OpenShell is not installed.",
  });
  assert.deepEqual(saved, []);
});
