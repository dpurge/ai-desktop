import { JSDOM } from "jsdom";

// Installs a jsdom window as the globals the components expect. Call before importing a component.
export function installDom() {
  const dom = new JSDOM("<!doctype html><html><head></head><body></body></html>", {
    url: "http://localhost/",
  });
  const { window } = dom;
  for (const name of ["window", "document", "HTMLElement", "customElements", "CustomEvent", "KeyboardEvent"]) {
    Object.defineProperty(globalThis, name, { value: window[name] ?? window, configurable: true, writable: true });
  }
  globalThis.window = window;
  return window;
}
