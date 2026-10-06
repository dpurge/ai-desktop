// Light-DOM components cannot ship a shadow-root <style>, so each one injects its stylesheet once.
export function ensureStyle(id, cssUrl) {
  if (document.getElementById(id)) return;
  const link = document.createElement("link");
  link.id = id;
  link.rel = "stylesheet";
  link.href = cssUrl;
  document.head.appendChild(link);
}
