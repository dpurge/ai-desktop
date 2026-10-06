const SESSION_ID = /^[A-Za-z0-9_-]{1,64}$/;

export const HOME = Object.freeze({ name: "home" });
export const SETTINGS = Object.freeze({ name: "settings" });
const NOT_FOUND = Object.freeze({ name: "not-found" });

// Pure: maps a location hash to a route object.
export function parseHash(hash) {
  const path = hash.replace(/^#/, "");
  if (path === "" || path === "/") return HOME;
  if (path === "/settings") return SETTINGS;
  const chat = /^\/chat\/([^/]+)$/.exec(path);
  if (chat && SESSION_ID.test(chat[1])) return { name: "chat", id: chat[1] };
  return NOT_FOUND;
}

export function formatRoute(route) {
  if (route.name === "chat") return `#/chat/${route.id}`;
  if (route.name === "settings") return "#/settings";
  return "#/";
}

// The browser dev URL carries the engine token as "#token=...", which collides with hash routing.
// Read it exactly once at startup, keep it in memory only, and strip it from the address bar
// before the router takes over the hash. Call this before createRouter().start().
export function takeTokenFromHash(location, history) {
  const token = new URLSearchParams(location.hash.slice(1)).get("token");
  if (token === null) return null;
  history.replaceState(null, "", location.pathname + location.search);
  return token;
}

export function createRouter({ window, onRoute }) {
  const notify = () => onRoute(parseHash(window.location.hash));
  return {
    start() {
      window.addEventListener("hashchange", notify);
      notify();
    },
    stop() {
      window.removeEventListener("hashchange", notify);
    },
    navigate(route) {
      const hash = formatRoute(route);
      // Assigning the same hash fires no hashchange, so notify directly to keep callers simple.
      if (window.location.hash === hash) notify();
      else window.location.hash = hash;
    },
  };
}
