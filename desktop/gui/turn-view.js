// Turns engine events and stored history into chat elements. Only elements are created here;
// every piece of text reaches the page through the components' textContent.

function scrollToEnd(list) {
  list.scrollTop = list.scrollHeight;
}

function createToolCard(name, args) {
  const card = document.createElement("ad-tool-call");
  card.toolName = name;
  card.toolArguments = args;
  return card;
}

// What a tool call is doing once its interaction is settled; an unlisted outcome (denial,
// timeout) reads as denied.
const STATUS_AFTER_OUTCOME = {
  approved: "running",
  answered: "running",
  accepted: "running",
  rejected: "running",
  cancelled: "error",
};

function statusAfter(kind, outcome) {
  // Only an approval can end as a denial; an unanswered question ends with a failed result.
  if (kind !== "approval" && outcome === "timeout") return "running";
  return STATUS_AFTER_OUTCOME[outcome] ?? "denied";
}

// Live view of one running turn.
export function createTurnView({ list, api, addMessage, onError }) {
  const toolCards = new Map();
  const interactionCards = new Map();
  const callIdByInteraction = new Map();
  const kindByInteraction = new Map();
  // Text after a tool card must start a new message, or it would render above the card.
  let reply = null;

  function append(node) {
    reply = null;
    list.appendChild(node);
    scrollToEnd(list);
  }

  const handlers = {
    text_delta({ text }) {
      reply ??= addMessage(list, "assistant", "");
      reply.append(text);
    },

    tool_call({ call_id, name, arguments: args }) {
      const card = createToolCard(name, args);
      toolCards.set(call_id, card);
      append(card);
    },

    interaction_required({ interaction_id, call_id, kind, tool, payload }) {
      callIdByInteraction.set(interaction_id, call_id);
      kindByInteraction.set(interaction_id, kind);
      const card = document.createElement("ad-interaction-card");
      card.interaction = { id: interaction_id, kind, tool, payload };
      card.addEventListener("ad-interaction-answer", ({ detail }) => {
        api.answerInteraction(detail.id, detail.answer).catch(onError);
      });
      interactionCards.set(interaction_id, card);
      append(card);
    },

    interaction_resolved({ interaction_id, outcome }) {
      interactionCards.get(interaction_id)?.markResolved(outcome);
      const toolCard = toolCards.get(callIdByInteraction.get(interaction_id));
      if (toolCard) toolCard.status = statusAfter(kindByInteraction.get(interaction_id), outcome);
    },

    tool_result({ call_id, ok, output }) {
      const card = toolCards.get(call_id);
      if (!card) return;
      // A denied card keeps its badge; the output only explains why.
      if (card.status !== "denied") card.status = ok ? "done" : "error";
      card.output = output;
    },

    error({ message }) {
      showError(message);
    },
  };

  function showError(message) {
    const target = reply ?? addMessage(list, "assistant", "");
    reply = target;
    target.append(`[error] ${message}`);
  }

  return {
    handle({ event, data }) {
      handlers[event]?.(data);
    },
    showError,
  };
}

function parseStoredArguments(raw) {
  try {
    return JSON.parse(raw);
  } catch {
    return raw;
  }
}

// Reloaded history is read-only: tool calls show their stored result and no approval controls.
export function renderHistory({ list, messages, addMessage }) {
  const toolCards = new Map();
  for (const message of messages) {
    if (message.role === "tool") {
      showStoredResult(list, toolCards, message);
      continue;
    }
    if (message.content) addMessage(list, message.role, message.content);
    for (const call of message.tool_calls ?? []) {
      const card = createToolCard(call.function.name, parseStoredArguments(call.function.arguments));
      card.status = "pending";
      toolCards.set(call.id, card);
      list.appendChild(card);
    }
  }
}

function showStoredResult(list, toolCards, { tool_call_id, content }) {
  let card = toolCards.get(tool_call_id);
  if (!card) {
    card = createToolCard("tool", "");
    list.appendChild(card);
  }
  card.status = "done";
  card.output = content;
}
