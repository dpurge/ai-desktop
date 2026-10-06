import { createApi } from "./api.js";
import { waitForEngine } from "./engine-ready.js";
import { HOME, SETTINGS, createRouter, takeTokenFromHash } from "./router.js";
import { createAppStore } from "./store.js";
import { createTurnView, renderHistory } from "./turn-view.js";
import "./components/ad-message/component.js";
import "./components/ad-composer/component.js";
import "./components/ad-interaction-card/component.js";
import "./components/ad-session-list/component.js";
import "./components/ad-settings-form/component.js";
import "./components/ad-status-bar/component.js";
import "./components/ad-tool-call/component.js";
import { createSettingsScreen } from "./settings-screen.js";
import { applyTheme } from "./theme.js";

const HEALTH_POLL_MS = 10_000;

// The desktop shell injects window.__AI_DESKTOP__; a browser dev session passes #token=... instead.
// The token is taken before the router starts so the hash is free for routes.
function readConnection() {
  const injected = window.__AI_DESKTOP__ ?? {};
  const token = injected.token ?? takeTokenFromHash(window.location, window.history);
  if (!token) throw new Error("No engine token: open the URL printed by the engine (#token=...)");
  return { baseUrl: injected.baseUrl ?? window.location.origin, token };
}

function addMessage(list, role, text) {
  const message = document.createElement("ad-message");
  message.dataset.role = role;
  message.text = text;
  list.appendChild(message);
  list.scrollTop = list.scrollHeight;
  return message;
}

async function streamReply(api, sessionId, text, turnView) {
  for await (const event of api.sendMessage(sessionId, text)) turnView.handle(event);
}

async function main() {
  const api = createApi(readConnection());
  await waitForEngine(() => api.getHealth());
  const store = createAppStore();
  const sessionList = document.getElementById("sessions");
  const messageList = document.getElementById("messages");
  const composer = document.getElementById("composer");
  const chatView = document.getElementById("chat-view");
  const settingsView = document.getElementById("settings-view");
  const statusBar = document.getElementById("status");

  const reportError = (error) => addMessage(messageList, "error", error.message);

  async function refreshSessions() {
    store.setState({ sessions: await api.listSessions() });
  }

  async function showSession(sessionId) {
    const { messages } = await api.getSession(sessionId);
    messageList.replaceChildren();
    renderHistory({ list: messageList, messages, addMessage });
    store.setState({ activeId: sessionId });
  }

  async function openMostRecentOrNew() {
    const [mostRecent] = store.getState().sessions;
    const target = mostRecent ?? (await api.createSession());
    if (!mostRecent) await refreshSessions();
    router.navigate({ name: "chat", id: target.id });
  }

  function applySettings(settings) {
    store.setState({ settings });
    applyTheme(document.documentElement, settings.theme);
  }

  const settingsScreen = createSettingsScreen({
    api,
    form: document.getElementById("settings-form"),
    onSaved: applySettings,
  });

  function showView(routeName) {
    const isSettings = routeName === "settings";
    chatView.hidden = isSettings;
    settingsView.hidden = !isSettings;
  }

  // The form renders nothing without settings, so a load failure is shown above it instead.
  async function showSettings() {
    const loadError = document.getElementById("settings-error");
    try {
      await settingsScreen.show();
      loadError.hidden = true;
    } catch (error) {
      loadError.textContent = error.message;
      loadError.hidden = false;
    }
  }

  async function handleRoute(route) {
    showView(route.name);
    if (route.name === "settings") await showSettings();
    else if (route.name === "chat") await showSession(route.id);
    else await openMostRecentOrNew();
  }

  // Only a change is published, so the 10 s poll does not re-render (and reset) the sidebar.
  async function pollConnection() {
    const connection = await api.getHealth().then(
      () => "online",
      () => "offline",
    );
    if (store.getState().connection !== connection) store.setState({ connection });
  }

  // A chat route whose session no longer exists would leave the pane blank, so fall back to home.
  // Only when the session is really gone, otherwise home would route straight back here.
  async function recoverFromFailedRoute(route, error) {
    reportError(error);
    if (route.name !== "chat") return;
    await refreshSessions();
    const isStillListed = store.getState().sessions.some((session) => session.id === route.id);
    if (!isStillListed) router.navigate(HOME);
  }

  const router = createRouter({
    window,
    onRoute: (route) =>
      handleRoute(route).catch((error) => recoverFromFailedRoute(route, error).catch(reportError)),
  });

  store.subscribe(({ sessions, activeId, settings, connection }) => {
    sessionList.sessions = sessions;
    sessionList.activeId = activeId;
    statusBar.connection = connection;
    statusBar.provider = settings?.provider ?? "";
    statusBar.model = settings?.model ?? "";
  });

  statusBar.addEventListener("ad-status-open-settings", () => router.navigate(SETTINGS));

  sessionList.addEventListener("ad-session-select", (event) =>
    router.navigate({ name: "chat", id: event.detail.id }),
  );

  sessionList.addEventListener("ad-session-new", async () => {
    try {
      const session = await api.createSession();
      await refreshSessions();
      router.navigate({ name: "chat", id: session.id });
    } catch (error) {
      reportError(error);
    }
  });

  sessionList.addEventListener("ad-session-rename", async (event) => {
    try {
      await api.renameSession(event.detail.id, event.detail.title);
      await refreshSessions();
    } catch (error) {
      reportError(error);
    }
  });

  sessionList.addEventListener("ad-session-delete", async (event) => {
    const { id } = event.detail;
    try {
      await api.deleteSession(id);
      await refreshSessions();
      if (store.getState().activeId === id) {
        store.setState({ activeId: null });
        await openMostRecentOrNew();
      }
    } catch (error) {
      reportError(error);
    }
  });

  composer.addEventListener("ad-send", async (event) => {
    const { text } = event.detail;
    const { activeId } = store.getState();
    if (!activeId) return;
    composer.disabled = true;
    composer.running = true;
    addMessage(messageList, "user", text);
    const turnView = createTurnView({
      list: messageList,
      api,
      addMessage,
      onError: reportError,
    });
    try {
      await streamReply(api, activeId, text, turnView);
    } catch (error) {
      turnView.showError(error.message);
    } finally {
      composer.disabled = false;
      composer.running = false;
      // The first message gives the session its title.
      await refreshSessions().catch(reportError);
    }
  });

  composer.addEventListener("ad-stop", () => {
    const { activeId } = store.getState();
    if (activeId) api.cancelTurn(activeId).catch(reportError);
  });

  await refreshSessions();
  await api.getSettings().then(applySettings, reportError);
  pollConnection();
  setInterval(pollConnection, HEALTH_POLL_MS);
  router.start();
}

main().catch((error) => {
  addMessage(document.getElementById("messages"), "error", error.message);
});
