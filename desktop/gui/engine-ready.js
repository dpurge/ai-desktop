const DEFAULT_ATTEMPTS = 100;
const DEFAULT_DELAY_MS = 150;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// The desktop shell opens the window as soon as it has spawned the engine, so the first
// requests can arrive before the engine is listening. Retrying here keeps that race out of
// every other call site.
export async function waitForEngine(
  getHealth,
  { attempts = DEFAULT_ATTEMPTS, delayMs = DEFAULT_DELAY_MS, wait = sleep } = {},
) {
  let lastError;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      return await getHealth();
    } catch (error) {
      lastError = error;
      await wait(delayMs);
    }
  }
  throw new Error(`The engine did not start: ${lastError?.message ?? "no response"}`);
}
