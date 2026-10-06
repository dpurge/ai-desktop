import { ensureStyle } from "../ensure-style.js";

const STYLE_ID = "ad-composer-style";
const STYLE_URL = new URL("./component.css", import.meta.url).href;

class AdComposer extends HTMLElement {
  static observedAttributes = ["disabled", "running"];

  connectedCallback() {
    ensureStyle(STYLE_ID, STYLE_URL);
    if (this._input) return;

    this._input = document.createElement("textarea");
    this._input.className = "ad-composer-input";
    this._input.rows = 2;
    this._input.placeholder = "Message";
    this._input.addEventListener("keydown", (event) => this._onKeydown(event));

    this._button = document.createElement("button");
    this._button.type = "button";
    this._button.className = "ad-composer-send";
    this._button.textContent = "Send";
    this._button.addEventListener("click", () => this._send());

    // Stays enabled while the composer is disabled: that is exactly when a turn can be stopped.
    this._stopButton = document.createElement("button");
    this._stopButton.type = "button";
    this._stopButton.className = "ad-composer-stop";
    this._stopButton.textContent = "Stop";
    this._stopButton.addEventListener("click", () => {
      this.dispatchEvent(new CustomEvent("ad-stop", { bubbles: true }));
    });

    this.appendChild(this._input);
    this.appendChild(this._button);
    this.appendChild(this._stopButton);
    this._syncDisabled();
  }

  attributeChangedCallback() {
    this._syncDisabled();
  }

  get disabled() {
    return this.hasAttribute("disabled");
  }

  set disabled(value) {
    this.toggleAttribute("disabled", Boolean(value));
  }

  get running() {
    return this.hasAttribute("running");
  }

  set running(value) {
    this.toggleAttribute("running", Boolean(value));
  }

  _syncDisabled() {
    if (!this._input) return;
    this._stopButton.hidden = !this.running;
    this._input.disabled = this.disabled;
    this._button.disabled = this.disabled;
  }

  _onKeydown(event) {
    // isComposing: Enter confirms an IME candidate and must not send the message.
    if (event.key !== "Enter" || event.shiftKey || event.isComposing) return;
    event.preventDefault();
    this._send();
  }

  _send() {
    const text = this._input.value.trim();
    if (this.disabled || text === "") return;
    this._input.value = "";
    this.dispatchEvent(new CustomEvent("ad-send", { detail: { text }, bubbles: true }));
  }
}

customElements.define("ad-composer", AdComposer);
