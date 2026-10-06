// EventSource is not usable here: it cannot send the X-AD-Token header, and chat is a POST.

const BLANK_LINE = /\r?\n\r?\n/;

function parseEventBlock(block) {
  let event = "message";
  const dataLines = [];
  for (const line of block.split(/\r?\n/)) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^ /, ""));
  }
  if (dataLines.length === 0) return null; // comment or keep-alive block
  const raw = dataLines.join("\n");
  try {
    return { event, data: JSON.parse(raw) };
  } catch (cause) {
    throw new Error(`Malformed SSE data for event "${event}": ${raw}`, { cause });
  }
}

// Yields {event, data} with data already JSON-decoded. A trailing event with no blank-line
// terminator means the connection was cut mid-event, so it is dropped rather than half-parsed.
export async function* parseSse(stream) {
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) return;
      buffer += decoder.decode(value, { stream: true });
      const blocks = buffer.split(BLANK_LINE);
      buffer = blocks.pop();
      for (const block of blocks) {
        const parsed = parseEventBlock(block);
        if (parsed) yield parsed;
      }
    }
  } finally {
    reader.releaseLock();
  }
}

// FastAPI sends a string for most errors and a list of {loc, msg} for validation errors.
function describeDetail(detail) {
  if (Array.isArray(detail)) {
    return detail.map(({ loc = [], msg }) => `${loc.slice(1).join(".")} ${msg}`.trim()).join("; ");
  }
  return typeof detail === "string" ? detail : "";
}

async function failWithStatus(response, action) {
  let detail = "";
  try {
    detail = describeDetail((await response.json()).detail);
  } catch {
    // The body is only extra context for the message; the status already says what failed.
  }
  throw new Error(`${action} failed: HTTP ${response.status} ${detail}`.trim());
}

const sessionPath = (sessionId) => `/sessions/${encodeURIComponent(sessionId)}`;

export function createApi({ baseUrl, token, fetchImpl = (...args) => fetch(...args) }) {
  const request = (path, init = {}) =>
    fetchImpl(`${baseUrl}${path}`, {
      ...init,
      headers: { "X-AD-Token": token, "Content-Type": "application/json", ...init.headers },
    });

  return {
    async listSessions() {
      const response = await request("/sessions");
      if (!response.ok) await failWithStatus(response, "List sessions");
      return response.json();
    },

    async createSession() {
      const response = await request("/sessions", { method: "POST" });
      if (!response.ok) await failWithStatus(response, "Create session");
      return response.json();
    },

    // Resolves to {session, messages}.
    async getSession(sessionId) {
      const response = await request(sessionPath(sessionId));
      if (!response.ok) await failWithStatus(response, "Load session");
      return response.json();
    },

    async renameSession(sessionId, title) {
      const response = await request(sessionPath(sessionId), {
        method: "PATCH",
        body: JSON.stringify({ title }),
      });
      if (!response.ok) await failWithStatus(response, "Rename session");
      return response.json();
    },

    async deleteSession(sessionId) {
      const response = await request(sessionPath(sessionId), { method: "DELETE" });
      if (!response.ok) await failWithStatus(response, "Delete session");
    },

    async getHealth() {
      const response = await request("/health");
      if (!response.ok) await failWithStatus(response, "Check engine");
      return response.json();
    },

    async getSettings() {
      const response = await request("/settings");
      if (!response.ok) await failWithStatus(response, "Load settings");
      return response.json();
    },

    // `patch` holds only the settings to change; resolves to the full saved settings.
    async saveSettings(patch) {
      const response = await request("/settings", { method: "PUT", body: JSON.stringify(patch) });
      if (!response.ok) await failWithStatus(response, "Save settings");
      return response.json();
    },

    // Write-only: the engine never sends a key back.
    async setApiKey(provider, apiKey) {
      const response = await request("/settings/api-key", {
        method: "PUT",
        body: JSON.stringify({ provider, api_key: apiKey }),
      });
      if (!response.ok) await failWithStatus(response, "Save API key");
    },

    async deleteApiKey(provider) {
      const response = await request(`/settings/api-key?provider=${encodeURIComponent(provider)}`, {
        method: "DELETE",
      });
      if (!response.ok) await failWithStatus(response, "Remove API key");
    },

    // Resolves to [{id, name}] sorted by id.
    async listModels(provider) {
      const response = await request(`/models?provider=${encodeURIComponent(provider)}`);
      if (!response.ok) await failWithStatus(response, "List models");
      return response.json();
    },

    // The answer body depends on the interaction kind, e.g. {decision: "approve"}.
    async answerInteraction(interactionId, answer) {
      const response = await request(`/interactions/${encodeURIComponent(interactionId)}`, {
        method: "POST",
        body: JSON.stringify(answer),
      });
      if (!response.ok) await failWithStatus(response, "Answer");
    },

    // Resolves to true when a running turn was found and told to stop.
    async cancelTurn(sessionId) {
      const response = await request(`${sessionPath(sessionId)}/cancel`, { method: "POST" });
      if (!response.ok) await failWithStatus(response, "Stop");
      return (await response.json()).cancelled;
    },

    async *sendMessage(sessionId, text) {
      const response = await request(`${sessionPath(sessionId)}/messages`, {
        method: "POST",
        body: JSON.stringify({ text }),
      });
      if (!response.ok) await failWithStatus(response, "Send message");
      yield* parseSse(response.body);
    },
  };
}
