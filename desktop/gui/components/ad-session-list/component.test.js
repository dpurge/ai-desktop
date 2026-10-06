import assert from "node:assert/strict";
import { before, test } from "node:test";
import { installDom } from "../../test-support/dom.js";

before(async () => {
  installDom();
  await import("./component.js");
});

const SESSIONS = [
  { id: "a", title: "First chat", updated_at: "2026-10-06T10:00:00.000+00:00" },
  { id: "b", title: "<b>Second</b>", updated_at: "2026-10-05T09:00:00.000+00:00" },
];

function mount(activeId = null) {
  const list = document.createElement("ad-session-list");
  document.body.appendChild(list);
  list.sessions = SESSIONS;
  list.activeId = activeId;
  return list;
}

function record(list, name) {
  const events = [];
  list.addEventListener(name, (event) => events.push(event.detail));
  return events;
}

function press(input, key) {
  input.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
}

const itemOf = (list, index) => list.querySelectorAll(".ad-session-item")[index];

test("renders title and date for each session, as text only", () => {
  const list = mount();
  assert.equal(list.querySelectorAll(".ad-session-item").length, 2);
  assert.equal(itemOf(list, 0).querySelector(".ad-session-title").textContent, "First chat");
  assert.equal(itemOf(list, 0).querySelector(".ad-session-date").textContent, "2026-10-06");
  assert.equal(itemOf(list, 1).querySelector(".ad-session-title").textContent, "<b>Second</b>");
  assert.equal(list.querySelector("b"), null);
});

test("marks the active session", () => {
  const list = mount("b");
  assert.ok(!itemOf(list, 0).classList.contains("is-active"));
  assert.ok(itemOf(list, 1).classList.contains("is-active"));
});

test("select and new emit their events", () => {
  const list = mount();
  const selected = record(list, "ad-session-select");
  const created = record(list, "ad-session-new");

  itemOf(list, 1).querySelector(".ad-session-select").click();
  list.querySelector(".ad-session-new").click();

  assert.deepEqual(selected, [{ id: "b" }]);
  assert.equal(created.length, 1);
});

test("Enter confirms a rename with the trimmed title", () => {
  const list = mount();
  const renamed = record(list, "ad-session-rename");
  itemOf(list, 0).querySelector(".ad-session-rename").click();

  const input = list.querySelector(".ad-session-edit");
  assert.equal(input.value, "First chat");
  input.value = "  Plans  ";
  press(input, "Enter");

  assert.deepEqual(renamed, [{ id: "a", title: "Plans" }]);
  assert.equal(list.querySelector(".ad-session-edit"), null);
});

test("Escape cancels a rename without emitting", () => {
  const list = mount();
  const renamed = record(list, "ad-session-rename");
  itemOf(list, 0).querySelector(".ad-session-rename").click();
  const input = list.querySelector(".ad-session-edit");
  input.value = "Changed";
  press(input, "Escape");

  assert.deepEqual(renamed, []);
  assert.equal(list.querySelector(".ad-session-edit"), null);
  assert.equal(itemOf(list, 0).querySelector(".ad-session-title").textContent, "First chat");
});

test("an empty or unchanged title is not emitted", () => {
  const list = mount();
  const renamed = record(list, "ad-session-rename");
  for (const value of ["   ", "First chat"]) {
    itemOf(list, 0).querySelector(".ad-session-rename").click();
    const input = list.querySelector(".ad-session-edit");
    input.value = value;
    press(input, "Enter");
  }
  assert.deepEqual(renamed, []);
});

test("delete asks for confirmation first, and No cancels", () => {
  const list = mount();
  const deleted = record(list, "ad-session-delete");

  itemOf(list, 0).querySelector(".ad-session-delete").click();
  assert.equal(itemOf(list, 0).querySelector(".ad-session-confirm-text").textContent, "Delete?");
  assert.deepEqual(deleted, []);

  itemOf(list, 0).querySelector(".ad-session-confirm-no").click();
  assert.equal(itemOf(list, 0).querySelector(".ad-session-confirm"), null);
  assert.deepEqual(deleted, []);
});

test("confirming the delete emits ad-session-delete", () => {
  const list = mount();
  const deleted = record(list, "ad-session-delete");
  itemOf(list, 1).querySelector(".ad-session-delete").click();
  itemOf(list, 1).querySelector(".ad-session-confirm-yes").click();

  assert.deepEqual(deleted, [{ id: "b" }]);
  assert.equal(list.querySelector(".ad-session-confirm"), null);
});

test("injects its stylesheet link once", () => {
  mount();
  assert.equal(document.querySelectorAll("link#ad-session-list-style").length, 1);
});
