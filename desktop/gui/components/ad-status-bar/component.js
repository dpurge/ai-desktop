import { element } from "../dom-helpers.js";
import { ensureStyle } from "../ensure-style.js";

const STYLE_ID = "ad-status-bar-style";
const STYLE_URL = new URL("./component.css", import.meta.url).href;
const CONNECTION_LABELS = {
  connecting: "Connecting to engine…",
  online: "Engine connected",
  offline: "Engine not reachable",
};

class AdStatusBar extends HTMLElement {
  constructor() {
    super();
    this._connection = "connecting";
    this._provider = "";
    this._model = "";
  }

  connectedCallback() {
    ensureStyle(STYLE_ID, STYLE_URL);
    this._render();
  }

  // "connecting" | "online" | "offline"
  set connection(connection) {
    this._connection = connection;
    this._render();
  }

  set provider(provider) {
    this._provider = provider;
    this._render();
  }

  set model(model) {
    this._model = model;
    this._render();
  }

  _render() {
    if (!this.isConnected) return;
    const bar = element("button", "ad-status-button");
    bar.type = "button";
    bar.title = "Open settings";
    bar.addEventListener("click", () =>
      this.dispatchEvent(new CustomEvent("ad-status-open-settings", { bubbles: true })),
    );
    bar.append(
      element("span", `ad-status-dot is-${this._connection}`),
      element("span", "ad-status-connection", CONNECTION_LABELS[this._connection]),
      element("span", "ad-status-model", this._modelText()),
    );
    this.replaceChildren(bar);
  }

  _modelText() {
    return this._provider && this._model ? `${this._provider} · ${this._model}` : "";
  }
}

customElements.define("ad-status-bar", AdStatusBar);
