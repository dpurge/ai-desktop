import { button, element } from "../dom-helpers.js";
import { ensureStyle } from "../ensure-style.js";

const STYLE_ID = "ad-model-picker-style";
const STYLE_URL = new URL("./component.css", import.meta.url).href;
const OTHER = "\u0000other";

function labelFor({ id, name }) {
  return name && name !== id ? `${name} (${id})` : id;
}

// Model names come from remote servers, so every string is written via textContent.
class AdModelPicker extends HTMLElement {
  constructor() {
    super();
    this._models = [];
    this._value = "";
    this._isLoading = false;
    this._error = "";
    this._isCustom = false;
  }

  connectedCallback() {
    ensureStyle(STYLE_ID, STYLE_URL);
    this._render();
  }

  get value() {
    return this._value;
  }

  set value(value) {
    this._value = value;
    this._isCustom = false;
    this._render();
  }

  set models(models) {
    this._models = models;
    this._render();
  }

  set isLoading(isLoading) {
    this._isLoading = isLoading;
    this._render();
  }

  set error(message) {
    this._error = message;
    this._render();
  }

  _emitChange() {
    this.dispatchEvent(
      new CustomEvent("ad-model-change", { detail: { model: this._value }, bubbles: true }),
    );
  }

  // The current model stays selectable even when the server does not list it, so opening the
  // screen never changes the model by itself.
  _options() {
    const options = [...this._models];
    if (this._value && !options.some((model) => model.id === this._value)) {
      options.unshift({ id: this._value, name: this._value });
    }
    return options;
  }

  _render() {
    if (!this.isConnected) return;
    const refresh = button("ad-model-refresh", "Refresh", () =>
      this.dispatchEvent(new CustomEvent("ad-models-refresh", { bubbles: true })),
    );
    refresh.disabled = this._isLoading;
    const row = element("div", "ad-model-row");
    row.append(this._renderSelect(), refresh);
    const children = [row];
    if (this._isCustom) children.push(this._renderCustomInput());
    if (this._isLoading) children.push(element("p", "ad-model-note", "Loading models…"));
    if (this._error) {
      const note = element("p", "ad-model-note ad-model-error", this._error);
      note.setAttribute("role", "alert");
      children.push(note);
    }
    this.replaceChildren(...children);
  }

  _renderSelect() {
    const select = element("select", "ad-model-select");
    select.setAttribute("aria-label", "Model");
    for (const model of this._options()) {
      const option = element("option", "", labelFor(model));
      option.value = model.id;
      select.appendChild(option);
    }
    const other = element("option", "", "Other…");
    other.value = OTHER;
    select.appendChild(other);
    select.value = this._isCustom ? OTHER : this._value;
    select.addEventListener("change", () => this._onSelect(select.value));
    return select;
  }

  _onSelect(selected) {
    if (selected === OTHER) {
      this._isCustom = true;
      this._value = "";
    } else {
      this._isCustom = false;
      this._value = selected;
    }
    this._render();
    this.querySelector(".ad-model-custom")?.focus();
    this._emitChange();
  }

  _renderCustomInput() {
    const input = element("input", "ad-model-custom");
    input.type = "text";
    input.placeholder = "Model id";
    input.setAttribute("aria-label", "Custom model id");
    input.value = this._value;
    // No re-render here: it would drop focus on every keystroke.
    input.addEventListener("input", () => {
      this._value = input.value.trim();
      this._emitChange();
    });
    return input;
  }
}

customElements.define("ad-model-picker", AdModelPicker);
