// Minimal observable state; components stay dumb and app.js decides what to render.
export function createStore(initialState) {
  let state = { ...initialState };
  const subscribers = new Set();

  return {
    getState: () => state,
    setState(patch) {
      state = { ...state, ...patch };
      for (const subscriber of [...subscribers]) subscriber(state);
    },
    subscribe(subscriber) {
      subscribers.add(subscriber);
      return () => subscribers.delete(subscriber);
    },
  };
}

export function createAppStore() {
  return createStore({ sessions: [], activeId: null, settings: null, connection: "connecting" });
}
