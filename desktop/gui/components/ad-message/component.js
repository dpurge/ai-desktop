import { ensureStyle } from "../ensure-style.js";

const STYLE_ID = "ad-message-style";
const STYLE_URL = new URL("./component.css", import.meta.url).href;

// Model output is untrusted: this component only ever writes it through a Text node.
// `data-role` rather than `role`, because role="user" is not a valid ARIA role.
class AdMessage extends HTMLElement {
  static observedAttributes = ["data-role"];

  connectedCallback() {
    ensureStyle(STYLE_ID, STYLE_URL);
    this._ensureStructure();
  }

  attributeChangedCallback() {
    if (this._roleLabel) this._roleLabel.textContent = this.dataset.role || "";
  }

  get text() {
    return this._ensureStructure().data;
  }

  set text(value) {
    this._ensureStructure().data = String(value);
  }

  // Deliberately shadows Element.append(): streaming replies only ever need to add text.
  append(text) {
    this._ensureStructure().data += text;
  }

  // Children cannot be created in the constructor, so build them on first use.
  _ensureStructure() {
    if (!this._textNode) {
      this._roleLabel = document.createElement("div");
      this._roleLabel.className = "ad-message-role";
      this._roleLabel.textContent = this.dataset.role || "";

      const body = document.createElement("div");
      body.className = "ad-message-body";
      this._textNode = document.createTextNode("");
      body.appendChild(this._textNode);

      this.appendChild(this._roleLabel);
      this.appendChild(body);
    }
    return this._textNode;
  }
}

customElements.define("ad-message", AdMessage);
