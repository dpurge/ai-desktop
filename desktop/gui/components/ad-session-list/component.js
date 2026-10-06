import { ensureStyle } from "../ensure-style.js";

const STYLE_ID = "ad-session-list-style";
const STYLE_URL = new URL("./component.css", import.meta.url).href;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function button(className, label, onClick) {
  const node = element("button", className, label);
  node.type = "button";
  node.addEventListener("click", onClick);
  return node;
}

// Session titles are user- and model-derived, so every string is written via textContent.
class AdSessionList extends HTMLElement {
  constructor() {
    super();
    this._sessions = [];
    this._activeId = null;
    this._editingId = null;
    this._confirmingDeleteId = null;
  }

  connectedCallback() {
    ensureStyle(STYLE_ID, STYLE_URL);
    this._render();
  }

  get sessions() {
    return this._sessions;
  }

  set sessions(value) {
    this._sessions = value;
    this._render();
  }

  get activeId() {
    return this._activeId;
  }

  set activeId(value) {
    this._activeId = value;
    this._render();
  }

  _emit(name, detail = {}) {
    this.dispatchEvent(new CustomEvent(name, { detail, bubbles: true }));
  }

  _setMode({ editingId = null, confirmingDeleteId = null }) {
    this._editingId = editingId;
    this._confirmingDeleteId = confirmingDeleteId;
    this._render();
  }

  _render() {
    if (!this.isConnected) return;
    const list = element("ul", "ad-session-items");
    for (const session of this._sessions) list.appendChild(this._renderItem(session));

    const newButton = button("ad-session-new", "New chat", () => this._emit("ad-session-new"));
    this.replaceChildren(newButton, list);
    this.querySelector(".ad-session-edit")?.focus();
  }

  _renderItem(session) {
    const item = element("li", "ad-session-item");
    if (session.id === this._activeId) item.classList.add("is-active");

    if (session.id === this._editingId) item.appendChild(this._renderEditor(session));
    else {
      item.appendChild(this._renderLabel(session));
      item.appendChild(
        session.id === this._confirmingDeleteId
          ? this._renderDeleteConfirm(session)
          : this._renderActions(session),
      );
    }
    return item;
  }

  _renderLabel(session) {
    const label = button("ad-session-select", "", () =>
      this._emit("ad-session-select", { id: session.id }),
    );
    label.appendChild(element("span", "ad-session-title", session.title));
    // The date part of the ISO timestamp is enough here and is timezone-independent.
    label.appendChild(element("span", "ad-session-date", session.updated_at.slice(0, 10)));
    return label;
  }

  _renderActions(session) {
    const actions = element("span", "ad-session-actions");
    actions.appendChild(
      button("ad-session-rename", "Rename", () => this._setMode({ editingId: session.id })),
    );
    actions.appendChild(
      button("ad-session-delete", "Delete", () =>
        this._setMode({ confirmingDeleteId: session.id }),
      ),
    );
    return actions;
  }

  _renderDeleteConfirm(session) {
    const confirm = element("span", "ad-session-confirm");
    confirm.appendChild(element("span", "ad-session-confirm-text", "Delete?"));
    confirm.appendChild(
      button("ad-session-confirm-yes", "Yes", () => {
        this._setMode({});
        this._emit("ad-session-delete", { id: session.id });
      }),
    );
    confirm.appendChild(button("ad-session-confirm-no", "No", () => this._setMode({})));
    return confirm;
  }

  _renderEditor(session) {
    const input = element("input", "ad-session-edit");
    input.type = "text";
    input.value = session.title;
    input.setAttribute("aria-label", "Session title");
    input.addEventListener("keydown", (event) => {
      if (event.isComposing) return; // Enter confirms an IME candidate, not the rename.
      if (event.key === "Enter") this._confirmRename(session, input.value);
      else if (event.key === "Escape") this._setMode({});
    });
    // Guarded: confirming or cancelling removes the input, which also fires blur.
    input.addEventListener("blur", () => {
      if (this._editingId === session.id) this._setMode({});
    });
    return input;
  }

  _confirmRename(session, rawTitle) {
    const title = rawTitle.trim();
    this._setMode({});
    if (title !== "" && title !== session.title) {
      this._emit("ad-session-rename", { id: session.id, title });
    }
  }
}

customElements.define("ad-session-list", AdSessionList);
