import assert from "node:assert/strict";
import { before, test } from "node:test";
import { installDom } from "../../test-support/dom.js";

before(async () => {
  installDom();
  await import("./component.js");
});

const APPROVAL = {
  id: "i1",
  kind: "approval",
  tool: "shell",
  payload: { command: "rm -rf /tmp/x", cwd: "/home/me" },
};

function mount(interaction = APPROVAL) {
  const card = document.createElement("ad-interaction-card");
  card.interaction = interaction;
  document.body.appendChild(card);
  const answers = [];
  card.addEventListener("ad-interaction-answer", (event) => answers.push(event.detail));
  return { card, answers };
}

test("approval shows the exact command and cwd", () => {
  const { card } = mount();
  assert.equal(card.kind, "approval");
  assert.equal(card.querySelector(".ad-interaction-command").textContent, "rm -rf /tmp/x");
  assert.match(card.querySelector(".ad-interaction-cwd").textContent, /\/home\/me/);
});

test("Approve emits the answer and disables both buttons", () => {
  const { card, answers } = mount();
  card.querySelector(".ad-interaction-approve").click();
  assert.deepEqual(answers, [{ id: "i1", answer: { decision: "approve" } }]);
  assert.equal(card.querySelector(".ad-interaction-approve").disabled, true);
  assert.equal(card.querySelector(".ad-interaction-deny").disabled, true);
});

test("Deny emits a deny decision", () => {
  const { card, answers } = mount();
  card.querySelector(".ad-interaction-deny").click();
  assert.deepEqual(answers, [{ id: "i1", answer: { decision: "deny" } }]);
});

test("a second click after answering sends nothing", () => {
  const { card, answers } = mount();
  card.querySelector(".ad-interaction-approve").click();
  card.querySelector(".ad-interaction-deny").click();
  assert.equal(answers.length, 1);
});

test("markResolved disables the buttons and shows the outcome", () => {
  const { card } = mount();
  card.markResolved("timeout");
  assert.equal(card.querySelector(".ad-interaction-approve").disabled, true);
  assert.match(card.querySelector(".ad-interaction-status").textContent, /No response/);
});

test("an unsupported kind says so instead of rendering controls", () => {
  const { card } = mount({ id: "i2", kind: "poll", payload: {} });
  assert.match(card.textContent, /Unsupported request: poll/);
  assert.equal(card.querySelector("button"), null);
});

test("markup in the command is not parsed", () => {
  const { card } = mount({ ...APPROVAL, payload: { command: "<img src=x onerror=alert(1)>", cwd: "/" } });
  assert.equal(card.querySelector("img"), null);
});

test("the answer event bubbles", () => {
  const { card } = mount();
  const seen = [];
  document.body.addEventListener("ad-interaction-answer", (event) => seen.push(event.detail.id));
  card.querySelector(".ad-interaction-deny").click();
  assert.deepEqual(seen, ["i1"]);
});

const QUESTION = {
  id: "q1",
  kind: "question",
  tool: "ask",
  payload: { question: "Which color?", options: ["red", "blue"] },
};

const PROPOSAL = {
  id: "p1",
  kind: "proposal",
  tool: "propose",
  payload: { title: "Rename project", details: "**Plan**\n\n1. Do it" },
};

test("question shows the text and one button per option", () => {
  const { card } = mount(QUESTION);
  assert.equal(card.kind, "question");
  assert.equal(card.querySelector(".ad-interaction-title").textContent, "Which color?");
  assert.deepEqual(
    [...card.querySelectorAll(".ad-interaction-option")].map((node) => node.textContent),
    ["red", "blue"],
  );
});

test("an option button answers with that option and disables everything", () => {
  const { card, answers } = mount(QUESTION);
  card.querySelectorAll(".ad-interaction-option")[1].click();
  assert.deepEqual(answers, [{ id: "q1", answer: { answer: "blue" } }]);
  assert.equal(card.querySelector(".ad-interaction-input").disabled, true);
  assert.equal(card.querySelector(".ad-interaction-send").disabled, true);
  assert.equal(card.querySelector(".ad-interaction-option").disabled, true);
});

test("a question without options shows only the free-text input", () => {
  const { card } = mount({ ...QUESTION, payload: { question: "Name?", options: [] } });
  assert.equal(card.querySelector(".ad-interaction-option"), null);
  assert.ok(card.querySelector(".ad-interaction-input"));
});

test("Send answers with the trimmed typed text", () => {
  const { card, answers } = mount(QUESTION);
  card.querySelector(".ad-interaction-input").value = "  green ";
  card.querySelector(".ad-interaction-send").click();
  assert.deepEqual(answers, [{ id: "q1", answer: { answer: "green" } }]);
});

test("Enter in the input sends the answer", () => {
  const { card, answers } = mount(QUESTION);
  const input = card.querySelector(".ad-interaction-input");
  input.value = "teal";
  input.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter" }));
  assert.deepEqual(answers, [{ id: "q1", answer: { answer: "teal" } }]);
});

test("Send with an empty input sends nothing and stays enabled", () => {
  const { card, answers } = mount(QUESTION);
  card.querySelector(".ad-interaction-input").value = "   ";
  card.querySelector(".ad-interaction-send").click();
  assert.deepEqual(answers, []);
  assert.equal(card.querySelector(".ad-interaction-send").disabled, false);
});

test("markup in a question or option is not parsed", () => {
  const { card } = mount({
    ...QUESTION,
    payload: { question: "<img src=x onerror=alert(1)>", options: ["<b>x</b>"] },
  });
  assert.equal(card.querySelector("img"), null);
  assert.equal(card.querySelector("b"), null);
});

test("question outcomes read as answered or no answer", () => {
  const first = mount(QUESTION).card;
  first.markResolved("answered");
  assert.equal(first.querySelector(".ad-interaction-status").textContent, "Answered");
  const second = mount(QUESTION).card;
  second.markResolved("timeout");
  assert.equal(second.querySelector(".ad-interaction-status").textContent, "No answer");
});

test("proposal shows title and details as plain text", () => {
  const { card } = mount(PROPOSAL);
  assert.equal(card.kind, "proposal");
  assert.equal(card.querySelector(".ad-interaction-title").textContent, "Rename project");
  assert.equal(card.querySelector("pre.ad-interaction-details").textContent, "**Plan**\n\n1. Do it");
});

test("Accept without a comment answers with the decision only", () => {
  const { card, answers } = mount(PROPOSAL);
  card.querySelector(".ad-interaction-accept").click();
  assert.deepEqual(answers, [{ id: "p1", answer: { decision: "accept" } }]);
  assert.equal(card.querySelector(".ad-interaction-reject").disabled, true);
  assert.equal(card.querySelector(".ad-interaction-comment").disabled, true);
});

test("Reject carries the trimmed comment", () => {
  const { card, answers } = mount(PROPOSAL);
  card.querySelector(".ad-interaction-comment").value = " too risky ";
  card.querySelector(".ad-interaction-reject").click();
  assert.deepEqual(answers, [{ id: "p1", answer: { decision: "reject", comment: "too risky" } }]);
});

test("the comment box is limited to what the engine accepts", () => {
  const { card } = mount(PROPOSAL);
  assert.equal(card.querySelector(".ad-interaction-comment").maxLength, 2000);
});

test("proposal outcomes are labelled", () => {
  const accepted = mount(PROPOSAL).card;
  accepted.markResolved("accepted");
  assert.equal(accepted.querySelector(".ad-interaction-status").textContent, "Accepted");
  const silent = mount(PROPOSAL).card;
  silent.markResolved("timeout");
  assert.match(silent.querySelector(".ad-interaction-status").textContent, /treated as rejected/);
});
