import { button, element, field } from "../dom-helpers.js";
import { ensureStyle } from "../ensure-style.js";
import "../ad-model-picker/component.js";

const STYLE_ID = "ad-settings-form-style";
const STYLE_URL = new URL("./component.css", import.meta.url).href;
const PROVIDERS = [
  ["ollama", "Ollama"],
  ["openrouter", "OpenRouter"],
];
const THEMES = [
  ["system", "System"],
  ["light", "Light"],
  ["dark", "Dark"],
];

function textInput(value) {
  const input = element("input", "ad-input");
  input.type = "text";
  input.value = value;
  return input;
}

function select(options, value) {
  const node = element("select", "ad-input");
  for (const [optionValue, label] of options) {
    const option = element("option", "", label);
    option.value = optionValue;
    node.appendChild(option);
  }
  node.value = value;
  return node;
}

// The API key is write-only: it is never prefilled, only "saved or not" is shown.
class AdSettingsForm extends HTMLElement {
  constructor() {
    super();
    this._settings = null;
    this._hasApiKey = false;
    this._isReplacingKey = false;
    this._catalog = { models: [], isLoading: false, error: "" };
    this._status = { kind: "", text: "" };
  }

  connectedCallback() {
    ensureStyle(STYLE_ID, STYLE_URL);
    this._render();
  }

  get provider() {
    return this._controls?.provider.value ?? this._settings?.provider;
  }

  set settings(settings) {
    this._settings = settings;
    this._hasApiKey = settings.has_api_key.openrouter;
    this._isReplacingKey = false;
    this._render();
  }

  set hasApiKey(hasApiKey) {
    this._hasApiKey = hasApiKey;
    this._isReplacingKey = false;
    this._syncKeyControls();
  }

  // {models, isLoading, error} for the model picker.
  set modelCatalog(catalog) {
    this._catalog = catalog;
    this._syncPicker();
  }

  // {kind: "success" | "error", text}
  set status(status) {
    this._status = status;
    this._syncStatus();
  }

  _emit(name, detail = {}) {
    this.dispatchEvent(new CustomEvent(name, { detail, bubbles: true }));
  }

  _render() {
    if (!this.isConnected || !this._settings) return;
    const settings = this._settings;
    const controls = {
      provider: select(PROVIDERS, settings.provider),
      ollamaUrl: textInput(settings.ollama.base_url),
      openrouterUrl: textInput(settings.openrouter.base_url),
      apiKey: element("input", "ad-input ad-api-key-input"),
      picker: element("ad-model-picker"),
      theme: select(THEMES, settings.theme),
      sandbox: this._sandboxCheckbox(settings.sandbox),
    };
    controls.apiKey.type = "password";
    controls.apiKey.autocomplete = "off";
    controls.apiKey.placeholder = "Paste a new API key";
    controls.provider.addEventListener("change", () =>
      this._emit("ad-models-request", { provider: controls.provider.value }),
    );
    controls.picker.addEventListener("ad-models-refresh", (event) => {
      event.stopPropagation();
      this._emit("ad-models-request", { provider: controls.provider.value });
    });
    this._controls = controls;

    const form = element("form", "ad-settings");
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      this._save();
    });
    form.append(
      element("h2", "ad-settings-title", "Settings"),
      field("Provider", controls.provider),
      this._section("Ollama", field("Base URL", controls.ollamaUrl)),
      this._section(
        "OpenRouter",
        field("Base URL", controls.openrouterUrl),
        this._renderKeyRow(),
        controls.apiKey,
      ),
      this._section("Model", controls.picker),
      field("Theme", controls.theme),
      this._section(
        "Sandbox",
        this._checkboxRow(controls.sandbox),
        element("p", "ad-sandbox-reason", settings.sandbox.reason),
      ),
      this._renderFooter(),
    );
    this.replaceChildren(form);
    controls.picker.value = settings.model;
    this._syncPicker();
    this._syncKeyControls();
    this._syncStatus();
  }

  // Turning it off must stay possible even when the sandbox cannot be used, e.g. after a hand edit.
  _sandboxCheckbox({ enabled, available }) {
    const checkbox = element("input", "ad-sandbox-toggle");
    checkbox.type = "checkbox";
    checkbox.checked = enabled;
    checkbox.disabled = !enabled && available !== true;
    return checkbox;
  }

  _checkboxRow(checkbox) {
    const label = element("label", "ad-checkbox");
    label.append(checkbox, element("span", "", "Run shell commands in the NVIDIA OpenShell sandbox"));
    return label;
  }

  _section(title, ...children) {
    const section = element("fieldset", "ad-settings-section");
    section.appendChild(element("legend", "", title));
    section.append(...children);
    return section;
  }

  _renderKeyRow() {
    const row = element("div", "ad-key-saved");
    row.append(
      element("span", "ad-key-saved-text", "Key saved"),
      button("ad-key-replace", "Replace", () => {
        this._isReplacingKey = true;
        this._syncKeyControls();
        this._controls.apiKey.focus();
      }),
      button("ad-key-remove", "Remove", () => this._emit("ad-api-key-remove", { provider: "openrouter" })),
    );
    this._keyRow = row;
    return row;
  }

  _renderFooter() {
    const footer = element("div", "ad-settings-footer");
    const save = element("button", "ad-settings-save", "Save");
    save.type = "submit";
    this._statusNode = element("p", "ad-settings-status");
    footer.append(save, this._statusNode);
    return footer;
  }

  _syncKeyControls() {
    if (!this._controls) return;
    this._keyRow.hidden = !this._hasApiKey;
    this._controls.apiKey.hidden = this._hasApiKey && !this._isReplacingKey;
    if (!this._isReplacingKey) this._controls.apiKey.value = "";
  }

  _syncPicker() {
    if (!this._controls) return;
    const { models, isLoading, error } = this._catalog;
    this._controls.picker.models = models;
    this._controls.picker.isLoading = isLoading;
    this._controls.picker.error = error;
  }

  _syncStatus() {
    if (!this._statusNode) return;
    this._statusNode.textContent = this._status.text;
    this._statusNode.className = `ad-settings-status ${this._status.kind}`.trim();
    this._statusNode.setAttribute("role", this._status.kind === "error" ? "alert" : "status");
  }

  _save() {
    const controls = this._controls;
    const model = controls.picker.value.trim();
    if (model === "") {
      this.status = { kind: "error", text: "Choose a model, or type a model id under Other…" };
      return;
    }
    const apiKey = controls.apiKey.value.trim();
    const patch = {
      provider: controls.provider.value,
      model,
      ollama: { base_url: controls.ollamaUrl.value.trim() },
      openrouter: { base_url: controls.openrouterUrl.value.trim() },
      theme: controls.theme.value,
    };
    // Only when changed, so saving other settings never trips the engine's availability check.
    if (controls.sandbox.checked !== this._settings.sandbox.enabled) {
      patch.sandbox = { enabled: controls.sandbox.checked };
    }
    this._emit("ad-settings-save", { patch, apiKey: apiKey === "" ? null : apiKey });
  }
}

customElements.define("ad-settings-form", AdSettingsForm);
