import assert from "node:assert/strict";
import { before, test } from "node:test";
import { installDom } from "./test-support/dom.js";

let createTurnView;
let renderHistory;

before(async () => {
  installDom();
  await import("./components/ad-message/component.js");
  await import("./components/ad-tool-call/component.js");
  await import("./components/ad-interaction-card/component.js");
  ({ createTurnView, renderHistory } = await import("./turn-view.js"));
});

function addMessage(list, role, text) {
  const message = document.createElement("ad-message");
  message.dataset.role = role;
  message.text = text;
  list.appendChild(message);
  return message;
}

function setup() {
  const list = document.createElement("div");
  document.body.appendChild(list);
  const answers = [];
  const errors = [];
  const api = {
    async answerInteraction(id, answer) {
      answers.push({ id, answer });
    },
  };
  const view = createTurnView({ list, api, addMessage, onError: (e) => errors.push(e.message) });
  const send = (event, data) => view.handle({ event, data });
  return { list, view, send, answers, errors };
}

const TOOL_CALL = { call_id: "c1", name: "shell", arguments: { command: "ls" } };
const REQUIRED = {
  interaction_id: "i1",
  call_id: "c1",
  kind: "approval",
  tool: "shell",
  payload: { command: "ls", cwd: "/home" },
  timeout_s: 600,
};

test("text deltas stream into one assistant message", () => {
  const { list, send } = setup();
  send("text_delta", { text: "Hel" });
  send("text_delta", { text: "lo" });
  assert.equal(list.children.length, 1);
  assert.equal(list.querySelector("ad-message").text, "Hello");
});

test("a tool call renders a pending card and its result completes it", () => {
  const { list, send } = setup();
  send("tool_call", TOOL_CALL);
  const card = list.querySelector("ad-tool-call");
  assert.equal(card.status, "pending");
  assert.equal(card.toolName, "shell");

  send("tool_result", { call_id: "c1", name: "shell", ok: true, output: "a\nb" });
  assert.equal(card.status, "done");
  assert.equal(card.output, "a\nb");
});

test("a failed result marks the card as error", () => {
  const { list, send } = setup();
  send("tool_call", TOOL_CALL);
  send("tool_result", { call_id: "c1", ok: false, output: "[exit code 2]" });
  assert.equal(list.querySelector("ad-tool-call").status, "error");
});

test("the approval card answers through the api", async () => {
  const { list, send, answers } = setup();
  send("tool_call", TOOL_CALL);
  send("interaction_required", REQUIRED);
  list.querySelector(".ad-interaction-approve").click();
  await Promise.resolve();
  assert.deepEqual(answers, [{ id: "i1", answer: { decision: "approve" } }]);
});

test("a failed answer is reported", async () => {
  const { list, errors } = setup();
  const api = { answerInteraction: async () => Promise.reject(new Error("HTTP 404")) };
  const view = createTurnView({ list, api, addMessage, onError: (e) => errors.push(e.message) });
  view.handle({ event: "interaction_required", data: REQUIRED });
  list.querySelector(".ad-interaction-deny").click();
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.deepEqual(errors, ["HTTP 404"]);
});

test("approval resolved: card disabled, tool call running", () => {
  const { list, send } = setup();
  send("tool_call", TOOL_CALL);
  send("interaction_required", REQUIRED);
  send("interaction_resolved", { interaction_id: "i1", outcome: "approved" });
  assert.equal(list.querySelector(".ad-interaction-approve").disabled, true);
  assert.equal(list.querySelector("ad-tool-call").status, "running");
});

test("denied: tool call shows denied and keeps that badge after its result", () => {
  const { list, send } = setup();
  send("tool_call", TOOL_CALL);
  send("interaction_required", REQUIRED);
  send("interaction_resolved", { interaction_id: "i1", outcome: "denied" });
  send("tool_result", { call_id: "c1", ok: false, output: "The user denied this command." });
  const card = list.querySelector("ad-tool-call");
  assert.equal(card.status, "denied");
  assert.equal(card.output, "The user denied this command.");
});

test("text after a tool card starts a new message below it", () => {
  const { list, send } = setup();
  send("text_delta", { text: "Let me look." });
  send("tool_call", TOOL_CALL);
  send("text_delta", { text: "Done." });
  assert.deepEqual(
    [...list.children].map((node) => node.localName),
    ["ad-message", "ad-tool-call", "ad-message"],
  );
});

test("errors are shown in the transcript", () => {
  const { list, send } = setup();
  send("error", { message: "Cannot reach Ollama" });
  assert.match(list.textContent, /\[error\] Cannot reach Ollama/);
});

test("unknown events are ignored", () => {
  const { list, send } = setup();
  send("turn_started", { turn_id: "t" });
  send("turn_done", { reason: "completed" });
  assert.equal(list.children.length, 0);
});

test("history renders tool calls as read-only cards with the stored result", () => {
  const list = document.createElement("div");
  renderHistory({
    list,
    addMessage,
    messages: [
      { role: "user", content: "run ls" },
      {
        role: "assistant",
        content: "",
        tool_calls: [
          { id: "c1", type: "function", function: { name: "shell", arguments: '{"command":"ls"}' } },
        ],
      },
      { role: "tool", tool_call_id: "c1", content: "file.txt" },
      { role: "assistant", content: "One file." },
    ],
  });

  assert.deepEqual(
    [...list.children].map((node) => node.localName),
    ["ad-message", "ad-tool-call", "ad-message"],
  );
  const card = list.querySelector("ad-tool-call");
  assert.equal(card.toolName, "shell");
  assert.equal(card.output, "file.txt");
  assert.equal(card.status, "done");
  assert.equal(list.querySelector("button"), null);
  assert.equal(list.querySelector("ad-interaction-card"), null);
});

test("history keeps unparseable stored arguments as text", () => {
  const list = document.createElement("div");
  renderHistory({
    list,
    addMessage,
    messages: [
      {
        role: "assistant",
        content: "",
        tool_calls: [{ id: "c1", type: "function", function: { name: "shell", arguments: "{bad" } }],
      },
    ],
  });
  assert.equal(list.querySelector(".ad-tool-call-args").textContent, "{bad");
});

const ASK_CALL = { call_id: "c2", name: "ask", arguments: { question: "Which color?" } };
const ASK_REQUIRED = {
  interaction_id: "q1",
  call_id: "c2",
  kind: "question",
  tool: "ask",
  payload: { question: "Which color?", options: [] },
  timeout_s: 600,
};

test("a question card answers through the api and the tool call completes", async () => {
  const { list, send, answers } = setup();
  send("tool_call", ASK_CALL);
  send("interaction_required", ASK_REQUIRED);
  list.querySelector(".ad-interaction-input").value = "blue";
  list.querySelector(".ad-interaction-send").click();
  await Promise.resolve();
  assert.deepEqual(answers, [{ id: "q1", answer: { answer: "blue" } }]);

  send("interaction_resolved", { interaction_id: "q1", outcome: "answered" });
  const toolCard = list.querySelector("ad-tool-call");
  assert.equal(toolCard.status, "running");
  send("tool_result", { call_id: "c2", ok: true, output: "blue" });
  assert.equal(toolCard.status, "done");
});

test("an unanswered question ends as an error, not as denied", () => {
  const { list, send } = setup();
  send("tool_call", ASK_CALL);
  send("interaction_required", ASK_REQUIRED);
  send("interaction_resolved", { interaction_id: "q1", outcome: "timeout" });
  send("tool_result", { call_id: "c2", ok: false, output: "No answer from the user." });
  assert.equal(list.querySelector("ad-tool-call").status, "error");
});

test("a rejected proposal still completes its tool call", () => {
  const { list, send } = setup();
  send("tool_call", { call_id: "c3", name: "propose", arguments: { title: "T", details: "d" } });
  send("interaction_required", {
    interaction_id: "p1",
    call_id: "c3",
    kind: "proposal",
    tool: "propose",
    payload: { title: "T", details: "d" },
  });
  send("interaction_resolved", { interaction_id: "p1", outcome: "rejected" });
  send("tool_result", { call_id: "c3", ok: true, output: "rejected: no" });
  assert.equal(list.querySelector("ad-tool-call").status, "done");
});

test("history renders ask and propose calls as read-only tool cards", () => {
  const list = document.createElement("div");
  const call = (id, name, args) => ({
    id,
    type: "function",
    function: { name, arguments: JSON.stringify(args) },
  });
  renderHistory({
    list,
    addMessage,
    messages: [
      {
        role: "assistant",
        content: "",
        tool_calls: [call("c1", "ask", { question: "Which color?" })],
      },
      { role: "tool", tool_call_id: "c1", content: "blue" },
      {
        role: "assistant",
        content: "",
        tool_calls: [call("c2", "propose", { title: "T", details: "d" })],
      },
      { role: "tool", tool_call_id: "c2", content: "accepted: ok" },
    ],
  });

  const cards = [...list.querySelectorAll("ad-tool-call")];
  assert.deepEqual(cards.map((card) => card.toolName), ["ask", "propose"]);
  assert.deepEqual(cards.map((card) => card.output), ["blue", "accepted: ok"]);
  assert.equal(list.querySelector("button"), null);
});
