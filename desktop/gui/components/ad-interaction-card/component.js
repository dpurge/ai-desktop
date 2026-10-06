import { ensureStyle } from "../ensure-style.js";
import { button, element } from "../dom-helpers.js";

const STYLE_ID = "ad-interaction-card-style";
const STYLE_URL = new URL("./component.css", import.meta.url).href;

const MAX_COMMENT_LENGTH = 2000;

const OUTCOME_LABELS = {
  approved: "Approved",
  denied: "Denied",
  answered: "Answered",
  accepted: "Accepted",
  rejected: "Rejected",
  cancelled: "Cancelled",
};

const TIMEOUT_LABELS = {
  approval: "No response; treated as denied",
  question: "No answer",
  proposal: "No response; treated as rejected",
};

// A question the engine is waiting on. `kind` selects what is rendered, so another kind is one
// more case in _renderBody. The answer leaves as an `ad-interaction-answer` event; the card does
// not talk to the engine itself.
class AdInteractionCard extends HTMLElement {
  connectedCallback() {
    ensureStyle(STYLE_ID, STYLE_URL);
    this._render();
  }

  get kind() {
    return this._interaction?.kind;
  }

  // {id, kind, tool, payload}
  set interaction(value) {
    this._interaction = value;
    this._render();
  }

  // Called when the engine reports how the interaction ended, whoever answered it.
  markResolved(outcome) {
    this._disableAnswers();
    if (this._status) this._status.textContent = this._outcomeLabel(outcome);
  }

  _outcomeLabel(outcome) {
    if (outcome === "timeout") return TIMEOUT_LABELS[this.kind] ?? "No response";
    return OUTCOME_LABELS[outcome] ?? outcome;
  }

  _render() {
    if (!this._interaction || this._renderedFor === this._interaction) return;
    this._renderedFor = this._interaction;
    this._controls = [];
    this.replaceChildren(this._renderBody(this._interaction));
  }

  _renderBody(interaction) {
    switch (interaction.kind) {
      case "approval":
        return this._renderApproval(interaction);
      case "question":
        return this._renderQuestion(interaction);
      case "proposal":
        return this._renderProposal(interaction);
      default:
        return element("p", "ad-interaction-unsupported", `Unsupported request: ${interaction.kind}`);
    }
  }

  _renderApproval({ tool, payload }) {
    const body = element("div", "ad-interaction-body");
    body.appendChild(element("div", "ad-interaction-title", `Allow ${tool} to run this command?`));
    body.appendChild(element("pre", "ad-interaction-command", payload.command));
    body.appendChild(element("div", "ad-interaction-cwd", `in ${payload.cwd}`));

    body.appendChild(
      this._actions(
        this._answerButton("ad-interaction-approve", "Approve", () => ({ decision: "approve" })),
        this._answerButton("ad-interaction-deny", "Deny", () => ({ decision: "deny" })),
      ),
    );
    return body;
  }

  _renderQuestion({ payload }) {
    const body = element("div", "ad-interaction-body");
    body.appendChild(element("div", "ad-interaction-title", payload.question));

    const options = element("div", "ad-interaction-options");
    for (const option of payload.options ?? []) {
      options.appendChild(
        this._answerButton("ad-interaction-option", option, () => ({ answer: option })),
      );
    }
    if (options.hasChildNodes()) body.appendChild(options);

    const input = this._control(element("input", "ad-interaction-input"));
    input.type = "text";
    input.placeholder = "Type your own answer";
    const send = this._answerButton("ad-interaction-send", "Send", () => this._typedAnswer(input));
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") send.click();
    });
    body.appendChild(this._actions(input, send));
    return body;
  }

  _typedAnswer(input) {
    const text = input.value.trim();
    return text ? { answer: text } : null;
  }

  _renderProposal({ payload }) {
    const body = element("div", "ad-interaction-body");
    body.appendChild(element("div", "ad-interaction-title", payload.title));
    // Plain text: Markdown rendering is not part of this version.
    body.appendChild(element("pre", "ad-interaction-details", payload.details));

    const comment = this._control(element("textarea", "ad-interaction-comment"));
    comment.placeholder = "Comment (optional)";
    comment.maxLength = MAX_COMMENT_LENGTH;
    comment.rows = 2;
    body.appendChild(comment);

    const decide = (decision) => () => {
      const text = comment.value.trim();
      return text ? { decision, comment: text } : { decision };
    };
    body.appendChild(
      this._actions(
        this._answerButton("ad-interaction-accept", "Accept", decide("accept")),
        this._answerButton("ad-interaction-reject", "Reject", decide("reject")),
      ),
    );
    return body;
  }

  // The row of answer controls, followed by the place the outcome is shown.
  _actions(...controls) {
    const actions = element("div", "ad-interaction-actions");
    this._status = element("span", "ad-interaction-status");
    actions.append(...controls, this._status);
    return actions;
  }

  // `buildAnswer` runs on click; returning null means there is nothing to send yet.
  _answerButton(className, label, buildAnswer) {
    return this._control(
      button(className, label, () => {
        const answer = buildAnswer();
        if (answer) this._answer(answer);
      }),
    );
  }

  _control(node) {
    this._controls.push(node);
    return node;
  }

  _answer(answer) {
    // Disabled first, so a double click cannot send two answers.
    this._disableAnswers();
    this.dispatchEvent(
      new CustomEvent("ad-interaction-answer", {
        detail: { id: this._interaction.id, answer },
        bubbles: true,
      }),
    );
  }

  _disableAnswers() {
    for (const node of this._controls ?? []) node.disabled = true;
  }
}

customElements.define("ad-interaction-card", AdInteractionCard);
