// Wires the settings form to the engine. The form and picker stay dumb; all fetching happens here.
const NO_STATUS = { kind: "", text: "" };

export function createSettingsScreen({ api, form, onSaved }) {
  let latestModelsRequest = 0;

  async function requestModels(provider) {
    const requestId = ++latestModelsRequest;
    form.modelCatalog = { models: [], isLoading: true, error: "" };
    let catalog;
    try {
      catalog = { models: await api.listModels(provider), isLoading: false, error: "" };
    } catch (error) {
      catalog = { models: [], isLoading: false, error: error.message };
    }
    // A slower answer for a provider the user already switched away from must not win.
    if (requestId === latestModelsRequest) form.modelCatalog = catalog;
  }

  async function save({ patch, apiKey }) {
    form.status = NO_STATUS;
    try {
      if (apiKey !== null) {
        await api.setApiKey("openrouter", apiKey);
        form.hasApiKey = true;
      }
      const settings = await api.saveSettings(patch);
      form.settings = settings;
      form.status = { kind: "success", text: "Saved. Your next message uses these settings." };
      onSaved(settings);
    } catch (error) {
      form.status = { kind: "error", text: error.message };
    }
  }

  async function removeKey(provider) {
    try {
      await api.deleteApiKey(provider);
      form.hasApiKey = false;
      form.status = { kind: "success", text: "API key removed." };
      onSaved(await api.getSettings());
    } catch (error) {
      form.status = { kind: "error", text: error.message };
    }
  }

  form.addEventListener("ad-models-request", (event) => requestModels(event.detail.provider));
  form.addEventListener("ad-settings-save", (event) => save(event.detail));
  form.addEventListener("ad-api-key-remove", (event) => removeKey(event.detail.provider));

  return {
    async show() {
      const settings = await api.getSettings();
      form.settings = settings;
      form.status = NO_STATUS;
      requestModels(settings.provider);
    },
  };
}
