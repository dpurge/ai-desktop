import assert from "node:assert/strict";
import { test } from "node:test";
import { createApi, parseSse } from "./api.js";

const encoder = new TextEncoder();

function streamOf(chunks) {
  return new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(typeof chunk === "string" ? encoder.encode(chunk) : chunk);
      controller.close();
    },
  });
}

async function collect(iterable) {
  const items = [];
  for await (const item of iterable) items.push(item);
  return items;
}

const WIRE = 'event: turn_started\ndata: {"turn_id":"t1"}\n\nevent: text_delta\ndata: {"text":"hi"}\n\n';
const EXPECTED = [
  { event: "turn_started", data: { turn_id: "t1" } },
  { event: "text_delta", data: { text: "hi" } },
];

test("parses events delivered in one chunk", async () => {
  assert.deepEqual(await collect(parseSse(streamOf([WIRE]))), EXPECTED);
});

test("parses when chunks split mid-event at every position", async () => {
  for (let cut = 1; cut < WIRE.length; cut++) {
    const events = await collect(parseSse(streamOf([WIRE.slice(0, cut), WIRE.slice(cut)])));
    assert.deepEqual(events, EXPECTED, `cut at ${cut}`);
  }
});

test("parses when a multi-byte character is split across chunks", async () => {
  const bytes = encoder.encode('event: text_delta\ndata: {"text":"zażółć"}\n\n');
  const cut = bytes.indexOf(0xc5) + 1; // between the two bytes of a 2-byte character
  const events = await collect(parseSse(streamOf([bytes.slice(0, cut), bytes.slice(cut)])));
  assert.deepEqual(events, [{ event: "text_delta", data: { text: "zażółć" } }]);
});

test("accepts CRLF line endings and ignores comment blocks", async () => {
  const wire = ': keep-alive\r\n\r\nevent: text_delta\r\ndata: {"text":"x"}\r\n\r\n';
  assert.deepEqual(await collect(parseSse(streamOf([wire]))), [
    { event: "text_delta", data: { text: "x" } },
  ]);
});

test("drops an event cut off before its blank-line terminator", async () => {
  const events = await collect(parseSse(streamOf(['event: text_delta\ndata: {"text":"a"}'])));
  assert.deepEqual(events, []);
});

test("rejects malformed JSON with context", async () => {
  await assert.rejects(collect(parseSse(streamOf(["event: x\ndata: {nope\n\n"]))), /Malformed SSE data/);
});

test("sendMessage sends the token header and streams events", async () => {
  let captured;
  const fetchImpl = async (url, init) => {
    captured = { url, init };
    return new Response(streamOf([WIRE]), { status: 200 });
  };
  const api = createApi({ baseUrl: "http://e", token: "tok", fetchImpl });

  const events = await collect(api.sendMessage("abc", "hello"));

  assert.deepEqual(events, EXPECTED);
  assert.equal(captured.url, "http://e/sessions/abc/messages");
  assert.equal(captured.init.headers["X-AD-Token"], "tok");
  assert.deepEqual(JSON.parse(captured.init.body), { text: "hello" });
});

test("sendMessage surfaces HTTP errors with the server detail", async () => {
  const fetchImpl = async () => new Response(JSON.stringify({ detail: "Unknown session" }), { status: 404 });
  const api = createApi({ baseUrl: "http://e", token: "tok", fetchImpl });
  await assert.rejects(collect(api.sendMessage("x", "hi")), /HTTP 404 Unknown session/);
});

function recordingApi(response) {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init });
    return response();
  };
  return { api: createApi({ baseUrl: "http://e", token: "tok", fetchImpl }), calls };
}

const json = (body, status = 200) => () => new Response(JSON.stringify(body), { status });

test("listSessions GETs /sessions", async () => {
  const { api, calls } = recordingApi(json([{ id: "a" }]));
  assert.deepEqual(await api.listSessions(), [{ id: "a" }]);
  assert.equal(calls[0].url, "http://e/sessions");
  assert.equal(calls[0].init.headers["X-AD-Token"], "tok");
});

test("getSession GETs the encoded session path", async () => {
  const { api, calls } = recordingApi(json({ session: {}, messages: [] }));
  await api.getSession("a/b");
  assert.equal(calls[0].url, "http://e/sessions/a%2Fb");
});

test("renameSession PATCHes the title", async () => {
  const { api, calls } = recordingApi(json({ id: "a", title: "T" }));
  await api.renameSession("a", "T");
  assert.equal(calls[0].init.method, "PATCH");
  assert.deepEqual(JSON.parse(calls[0].init.body), { title: "T" });
});

test("deleteSession accepts 204 and surfaces other statuses", async () => {
  const ok = recordingApi(() => new Response(null, { status: 204 }));
  await ok.api.deleteSession("a");
  assert.equal(ok.calls[0].init.method, "DELETE");

  const busy = recordingApi(json({ detail: "A turn is running" }, 409));
  await assert.rejects(busy.api.deleteSession("a"), /Delete session failed: HTTP 409 A turn is running/);
});

test("getSettings GETs /settings and getHealth GETs /health", async () => {
  const { api, calls } = recordingApi(json({ provider: "ollama" }));
  assert.deepEqual(await api.getSettings(), { provider: "ollama" });
  await api.getHealth();
  assert.deepEqual(calls.map((call) => call.url), ["http://e/settings", "http://e/health"]);
});

test("saveSettings PUTs only the patch and returns the saved settings", async () => {
  const { api, calls } = recordingApi(json({ model: "m" }));
  assert.deepEqual(await api.saveSettings({ model: "m" }), { model: "m" });
  assert.equal(calls[0].init.method, "PUT");
  assert.deepEqual(JSON.parse(calls[0].init.body), { model: "m" });
});

test("validation errors list each field and message", async () => {
  const detail = [{ loc: ["body", "ollama", "base_url"], msg: "must start with http://" }];
  const { api } = recordingApi(json({ detail }, 422));
  await assert.rejects(api.saveSettings({}), /HTTP 422 ollama\.base_url must start with http:\/\//);
});

test("setApiKey PUTs provider and key, and deleteApiKey sends the provider", async () => {
  const { api, calls } = recordingApi(() => new Response(null, { status: 204 }));
  await api.setApiKey("openrouter", "k");
  await api.deleteApiKey("openrouter");
  assert.equal(calls[0].url, "http://e/settings/api-key");
  assert.deepEqual(JSON.parse(calls[0].init.body), { provider: "openrouter", api_key: "k" });
  assert.equal(calls[1].url, "http://e/settings/api-key?provider=openrouter");
  assert.equal(calls[1].init.method, "DELETE");
});

test("setApiKey errors never repeat the key", async () => {
  const { api } = recordingApi(json({ detail: "bad" }, 422));
  await assert.rejects(api.setApiKey("openrouter", "sk-secret"), (error) => !error.message.includes("sk-secret"));
});

test("listModels GETs /models for the provider", async () => {
  const { api, calls } = recordingApi(json([{ id: "a", name: "A" }]));
  assert.deepEqual(await api.listModels("ollama"), [{ id: "a", name: "A" }]);
  assert.equal(calls[0].url, "http://e/models?provider=ollama");
});

test("answerInteraction POSTs the answer to the encoded interaction path", async () => {
  const { api, calls } = recordingApi(json({ resolved: true }));
  await api.answerInteraction("i/1", { decision: "approve" });
  assert.equal(calls[0].url, "http://e/interactions/i%2F1");
  assert.equal(calls[0].init.method, "POST");
  assert.equal(calls[0].init.headers["X-AD-Token"], "tok");
  assert.deepEqual(JSON.parse(calls[0].init.body), { decision: "approve" });
});

test("answerInteraction surfaces a 404 for an already-answered interaction", async () => {
  const { api } = recordingApi(json({ detail: "Unknown or already answered" }, 404));
  await assert.rejects(api.answerInteraction("i", { decision: "deny" }), /HTTP 404 Unknown or already/);
});

test("cancelTurn POSTs to the session cancel path and returns the flag", async () => {
  const { api, calls } = recordingApi(json({ cancelled: true }));
  assert.equal(await api.cancelTurn("abc"), true);
  assert.equal(calls[0].url, "http://e/sessions/abc/cancel");
  assert.equal(calls[0].init.method, "POST");
});
