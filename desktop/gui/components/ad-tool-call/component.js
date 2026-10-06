import { ensureStyle } from "../ensure-style.js";
import { element } from "../dom-helpers.js";

const STYLE_ID = "ad-tool-call-style";
const STYLE_URL = new URL("./component.css", import.meta.url).href;
const MAX_DISPLAYED_OUTPUT = 4000;

export const STATUSES = ["pending", "running", "done", "denied", "error"];

function formatArguments(value) {
  return typeof value === "string" ? value : JSON.stringify(value ?? {}, null, 2);
}

function capForDisplay(text) {
  if (text.length <= MAX_DISPLAYED_OUTPUT) return text;
  return `${text.slice(0, MAX_DISPLAYED_OUTPUT)}\n[display truncated]`;
}

// One tool call: what was asked, how far it got, and what came back. All text goes in through
// textContent because arguments and output come from the model and from commands.
class AdToolCall extends HTMLElement {
  connectedCallback() {
    ensureStyle(STYLE_ID, STYLE_URL);
    this._ensureStructure();
  }

  get toolName() {
    return this._ensureStructure().name.textContent;
  }

  set toolName(value) {
    this._ensureStructure().name.textContent = String(value);
  }

  // An object is pretty-printed; a string (stored raw arguments) is shown as it is.
  set toolArguments(value) {
    this._ensureStructure().args.textContent = formatArguments(value);
  }

  get status() {
    return this.dataset.status;
  }

  set status(value) {
    if (!STATUSES.includes(value)) throw new Error(`Unknown tool call status: ${value}`);
    this.dataset.status = value;
    this._ensureStructure().badge.textContent = value;
  }

  get output() {
    return this._ensureStructure().output.textContent;
  }

  set output(value) {
    const { output, details } = this._ensureStructure();
    output.textContent = capForDisplay(String(value));
    details.hidden = false;
  }

  _ensureStructure() {
    if (!this._parts) {
      const name = element("span", "ad-tool-call-name");
      const badge = element("span", "ad-tool-call-badge");
      const args = element("pre", "ad-tool-call-args");
      const output = element("pre", "ad-tool-call-output");
      const details = element("details", "ad-tool-call-result");
      details.hidden = true;
      details.appendChild(element("summary", "", "Output"));
      details.appendChild(output);

      const header = element("div", "ad-tool-call-header");
      header.append(name, badge);
      this.append(header, args, details);
      this._parts = { name, badge, args, output, details };
      this.status = "pending";
    }
    return this._parts;
  }
}

customElements.define("ad-tool-call", AdToolCall);
